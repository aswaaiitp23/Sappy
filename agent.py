"""
Sappy — Minimal Agent Runtime
==============================
The main event loop with four layers:

1. CORE LOOP      — user input → Anthropic API → tool dispatch → repeat until done
2. STREAMING      — text streams word-by-word instead of appearing all at once
3. OBSERVABILITY  — every LLM call + tool call logged to logs/agent.jsonl
4. MEMORY         — when history exceeds MEMORY_THRESHOLD messages, older turns
                    are summarised by the model and compressed into one message

Turn cycle
----------
1. Read user input
2. Append to history, persist to SQLite
3. POST full history + tool schemas + system prompt to Anthropic (streaming)
4. If stop_reason == "tool_use"  → dispatch tools, append results, go to 3
5. If stop_reason == "end_turn"  → print reply, wait for next input

MAX_TOOL_ROUNDS is a hard cap so a runaway model never loops forever.
"""

import argparse
import json
import os
import uuid
import time
import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.live import Live

from db import init_db, load_session, save_session
from skills import load_skill_summaries
from tools import TOOLS, dispatch_tool

load_dotenv()

console = Console()

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_TOOL_ROUNDS = 15
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")
MEMORY_THRESHOLD = 40      # summarise when history exceeds this many messages
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "agent.jsonl"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_block(block) -> dict:
    """
    Convert an Anthropic SDK content block to a plain dict with only the
    fields the API accepts when the block is re-sent in message history.

    model_dump() includes internal SDK fields like `caller` on ToolUseBlock
    and `parsed_output` on some text blocks — the API rejects these with 400.
    We keep only the documented fields per block type.
    """
    raw = block.model_dump() if hasattr(block, "model_dump") else dict(block)
    t = raw.get("type")
    if t == "text":
        return {"type": "text", "text": raw["text"]}
    if t == "tool_use":
        return {"type": "tool_use", "id": raw["id"], "name": raw["name"], "input": raw["input"]}
    # For any other block type, keep only the safe scalar fields.
    return {k: v for k, v in raw.items() if k in ("type", "id", "text", "name", "input")}


# ── Observability ─────────────────────────────────────────────────────────────

def log_event(event_type: str, data: dict) -> None:
    """
    Append one JSON line to logs/agent.jsonl.
    Every LLM call, tool call, error, and session event is recorded here.
    In production you'd ship these to a log aggregator — for now a local file
    is enough to debug and replay what the agent did.
    """
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "type": event_type,
        **data,
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Memory ────────────────────────────────────────────────────────────────────

def maybe_compress_history(messages: list, client: anthropic.Anthropic) -> list:
    """
    When history grows beyond MEMORY_THRESHOLD messages, ask the model to
    summarise the oldest half into a single 'memory' message.

    Why? The Anthropic API has a context window limit. Long conversations will
    eventually hit it and start failing. Compression keeps the context small
    while preserving what mattered.

    Design tradeoff: compression loses detail. We keep the most recent
    MEMORY_THRESHOLD // 2 messages verbatim so recent context is always sharp.
    """
    if len(messages) <= MEMORY_THRESHOLD:
        return messages

    split = len(messages) // 2
    old_messages = messages[:split]
    recent_messages = messages[split:]

    console.print("[dim]  ⟳ Compressing old history into memory…[/dim]")
    log_event("memory_compression", {"messages_compressed": len(old_messages)})

    # Ask the model to summarise the old messages
    summary_prompt = (
        "Summarise the following conversation history concisely. "
        "Preserve all specific numbers, file names, findings, and decisions. "
        "Write in third person. Be brief but complete.\n\n"
        + json.dumps(old_messages, indent=2)
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": summary_prompt}],
        )
        summary_text = resp.content[0].text
        log_event("memory_summary", {"summary": summary_text[:500]})
    except Exception as e:
        log_event("memory_error", {"error": str(e)})
        # If compression fails, just trim crudely rather than crash
        return messages[-MEMORY_THRESHOLD:]

    # Replace old messages with a single summary message
    memory_message = {
        "role": "user",
        "content": f"[Conversation memory — earlier context compressed]\n{summary_text}",
    }
    compressed = [memory_message] + recent_messages
    console.print(f"[dim]  ✓ Compressed {len(old_messages)} messages → 1 memory block[/dim]")
    return compressed


# ── System prompt ─────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    """
    Construct the system prompt, injecting the skills index at runtime.

    Skills are injected as a summary (name + one line) rather than full content.
    This keeps the prompt short and lets the model fetch full skill content
    on demand via load_skill — so adding 50 skills won't bloat every request.
    """
    skills_block = load_skill_summaries()
    return f"""You are Sappy, a helpful data-analysis assistant built as a minimal agent runtime.

You can read PDF, Excel, and CSV files, then answer questions about them.
Always read the relevant files before answering. Be precise — cite specific
numbers when you flag discrepancies. Flag anything that looks off.

{skills_block}
When finished with an analysis, summarise your findings as a bullet list."""


# ── Core loop ─────────────────────────────────────────────────────────────────

def run_turn(session_id: str, user_input: str) -> None:
    """
    Run one complete user turn:
      load history → compress if needed → append user message →
      streaming agent loop → save history.

    The agent loop streams from Anthropic, dispatches any tool requests,
    then loops until stop_reason is "end_turn" or we hit MAX_TOOL_ROUNDS.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    messages = load_session(session_id)
    messages = maybe_compress_history(messages, client)
    messages.append({"role": "user", "content": user_input})
    save_session(session_id, messages)

    system_prompt = build_system_prompt()
    turn_start = time.time()

    # Tracks whether we've already done a BadRequestError recovery this turn.
    # We allow one retry with a clean context; a second failure means giving up.
    bad_request_retried = False

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):

        # ── STREAMING LLM call ────────────────────────────────────────────────
        # We use client.messages.stream() so text appears word-by-word.
        # Under the hood this is a Server-Sent Events connection; the SDK
        # reassembles it into the same response object we'd get from .create().
        call_start = time.time()
        log_event("llm_call_start", {
            "session": session_id,
            "round": round_num,
            "model": MODEL,
            "messages": len(messages),
        })

        full_text = ""
        assistant_blocks = []
        stop_reason = None

        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                # Stream text blocks live to the terminal
                with Live(console=console, refresh_per_second=15) as live:
                    for event in stream:
                        if (
                            hasattr(event, "type")
                            and event.type == "content_block_delta"
                            and hasattr(event.delta, "text")
                        ):
                            full_text += event.delta.text
                            live.update(
                                Panel(
                                    Markdown(full_text),
                                    title="[bold green]Sappy[/bold green]",
                                    border_style="green",
                                    expand=False,
                                )
                            )

                # Get the final complete message after streaming finishes.
                # We strip blocks down to only the fields the API accepts on
                # re-send — model_dump() includes internal SDK fields like
                # `caller` (ToolUseBlock) and `parsed_output` that cause 400s.
                final = stream.get_final_message()
                assistant_blocks = [_clean_block(b) for b in final.content]
                stop_reason = final.stop_reason

                call_duration = time.time() - call_start
                log_event("llm_call_end", {
                    "session": session_id,
                    "round": round_num,
                    "stop_reason": stop_reason,
                    "input_tokens": final.usage.input_tokens,
                    "output_tokens": final.usage.output_tokens,
                    "duration_s": round(call_duration, 2),
                })

        except anthropic.BadRequestError as e:
            # 400 errors almost always mean the message history contains something
            # the API won't accept (malformed tool result, stale content block, etc.).
            # Recovery: drop all history except the current user message and retry once.
            log_event("api_error", {"session": session_id, "status_code": 400, "error": str(e)})
            if not bad_request_retried:
                console.print(
                    "[yellow]Request error — this usually means malformed message history. "
                    "Starting fresh context.[/yellow]"
                )
                messages: list[dict] = [{"role": "user", "content": user_input}]
                bad_request_retried = True
                continue
            console.print("[red]Request error on retry too — giving up on this turn.[/red]")
            break

        except anthropic.APIError as e:
            status = getattr(e, "status_code", None)
            log_event("api_error", {"session": session_id, "status_code": status, "error": str(e)})
            if status == 401:
                console.print("[red]Invalid API key — check your .env file[/red]")
            elif status == 429:
                console.print("[yellow]Rate limit hit — wait a moment and try again[/yellow]")
            elif status == 500:
                console.print("[red]Anthropic server error — try again shortly[/red]")
            else:
                console.print(f"[red]API error ({status}): {e}[/red]")
            break

        messages.append({"role": "assistant", "content": assistant_blocks})

        # ── model is done ─────────────────────────────────────────────────────
        if stop_reason == "end_turn":
            break

        # ── model wants tools ─────────────────────────────────────────────────
        if stop_reason == "tool_use":
            tool_results = []

            for block in assistant_blocks:
                if block["type"] != "tool_use":
                    continue

                tool_name = block["name"]
                tool_input = block["input"]
                tool_use_id = block["id"]

                console.print(
                    f"[dim]  → [bold]{tool_name}[/bold] "
                    f"{json.dumps(tool_input, ensure_ascii=False)[:200]}[/dim]"
                )
                log_event("tool_call", {
                    "session": session_id,
                    "tool": tool_name,
                    "input": tool_input,
                })

                tool_start = time.time()
                try:
                    result = dispatch_tool(tool_name, tool_input)
                except Exception as exc:
                    result = f"Tool '{tool_name}' raised an error: {exc}"
                    log_event("tool_error", {
                        "session": session_id,
                        "tool": tool_name,
                        "error": str(exc),
                    })

                tool_duration = time.time() - tool_start
                log_event("tool_result", {
                    "session": session_id,
                    "tool": tool_name,
                    "result_len": len(result),
                    "duration_s": round(tool_duration, 2),
                })

                preview = result[:120] + "…" if len(result) > 120 else result
                console.print(f"[dim]  ← {preview}[/dim]")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})
            continue

        # ── unexpected stop reason ────────────────────────────────────────────
        console.print(f"[yellow]Unexpected stop_reason: {stop_reason}[/yellow]")
        log_event("unexpected_stop", {"session": session_id, "stop_reason": stop_reason})
        break

    else:
        console.print(
            f"[red]Reached MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}). "
            "The model may be stuck — ending this turn.[/red]"
        )
        log_event("max_rounds_hit", {"session": session_id})

    total_duration = time.time() - turn_start
    log_event("turn_complete", {
        "session": session_id,
        "duration_s": round(total_duration, 2),
        "final_history_len": len(messages),
    })

    save_session(session_id, messages)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sappy — minimal agent runtime")
    parser.add_argument(
        "--session",
        metavar="ID",
        help="Resume an existing session by its UUID (omit to start a new one).",
    )
    args = parser.parse_args()

    init_db()

    if args.session:
        session_id = args.session
        log_event("session_resumed", {"session": session_id})
        console.print(Panel(
            f"[green]Resuming session[/green]  [dim]{session_id}[/dim]",
            expand=False,
        ))
    else:
        session_id = str(uuid.uuid4())
        log_event("session_new", {"session": session_id})
        console.print(Panel(
            f"[blue]New session[/blue]  [dim]{session_id}[/dim]\n"
            f"[dim]Resume later:  python agent.py --session {session_id}[/dim]",
            expand=False,
        ))

    console.print("[dim]Type your message. 'exit' or Ctrl-C to quit.[/dim]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            log_event("session_end", {"session": session_id})
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            log_event("session_end", {"session": session_id})
            break

        run_turn(session_id, user_input)
        console.print()


if __name__ == "__main__":
    main()