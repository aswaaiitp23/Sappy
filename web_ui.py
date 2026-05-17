"""
Sappy Web UI
============
A minimal browser interface for the agent.
Streams responses using Server-Sent Events (SSE) so text appears word-by-word,
exactly like the terminal version.

Usage:
    pip install flask
    python web_ui.py
    Open http://localhost:5000 in your browser

Design decision: Flask over FastAPI because it's simpler and has no async
complexity. SSE over WebSockets because it's one-way (server → client) and
works with plain fetch() — no socket library needed in the browser.
"""

import json
import os
import uuid
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from flask import Flask, Response, request, stream_with_context

from db import init_db, load_session, save_session
from skills import load_skill_summaries
from tools import TOOLS, dispatch_tool

load_dotenv()

app = Flask(__name__)
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")


def build_system_prompt() -> str:
    skills_block = load_skill_summaries()
    return f"""You are Sappy, a helpful data-analysis assistant.
You can read PDF, Excel, and CSV files, then answer questions about them.
Always read the relevant files before answering. Be precise — cite specific
numbers when you flag discrepancies.
{skills_block}
When finished with an analysis, summarise your findings as a bullet list."""


def run_agent_streaming(session_id: str, user_input: str):
    """
    Generator that yields SSE lines.
    The browser's EventSource reads these and appends text to the chat bubble.

    SSE format:  data: <json>\n\n
    We send three event types:
      - {"type": "text",   "content": "..."}   partial text chunk
      - {"type": "tool",   "name": "...", "input": "..."}  tool being called
      - {"type": "done"}   turn complete
      - {"type": "error",  "content": "..."}   something went wrong
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    messages = load_session(session_id)
    messages.append({"role": "user", "content": user_input})
    save_session(session_id, messages)

    system_prompt = build_system_prompt()

    def sse(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    for round_num in range(1, 16):
        try:
            assistant_blocks = []
            stop_reason = None
            full_text = ""

            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            ) as stream:
                for event in stream:
                    if (
                        hasattr(event, "type")
                        and event.type == "content_block_delta"
                        and hasattr(event.delta, "text")
                    ):
                        chunk = event.delta.text
                        full_text += chunk
                        yield sse({"type": "text", "content": chunk})

                final = stream.get_final_message()
                assistant_blocks = [b.model_dump() for b in final.content]
                stop_reason = final.stop_reason

        except Exception as e:
            yield sse({"type": "error", "content": str(e)})
            return

        messages.append({"role": "assistant", "content": assistant_blocks})

        if stop_reason == "end_turn":
            break

        if stop_reason == "tool_use":
            tool_results = []
            for block in assistant_blocks:
                if block["type"] != "tool_use":
                    continue

                tool_name = block["name"]
                tool_input = block["input"]
                tool_use_id = block["id"]

                yield sse({
                    "type": "tool",
                    "name": tool_name,
                    "input": json.dumps(tool_input)[:200],
                })

                try:
                    result = dispatch_tool(tool_name, tool_input)
                except Exception as exc:
                    result = f"Tool error: {exc}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})
            continue

        break

    save_session(session_id, messages)
    yield sse({"type": "done"})


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the single-page chat UI."""
    return Response(HTML, mimetype="text/html")


@app.route("/chat", methods=["POST"])
def chat():
    """Accept a message and stream back SSE."""
    body = request.get_json()
    session_id = body.get("session_id") or str(uuid.uuid4())
    user_input = body.get("message", "").strip()

    if not user_input:
        return {"error": "empty message"}, 400

    return Response(
        stream_with_context(run_agent_streaming(session_id, user_input)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Session-ID": session_id,
        },
    )


@app.route("/session/new")
def new_session():
    return {"session_id": str(uuid.uuid4())}


# ── Inline HTML ───────────────────────────────────────────────────────────────
# Single file — no templates folder needed.

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sappy — Agent Runtime</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f0f; color: #e8e8e8; height: 100vh; display: flex;
         flex-direction: column; }
  header { padding: 16px 24px; border-bottom: 1px solid #222;
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 18px; font-weight: 600; color: #fff; }
  header span { font-size: 12px; color: #555; font-family: monospace; }
  #chat { flex: 1; overflow-y: auto; padding: 24px;
          display: flex; flex-direction: column; gap: 16px; }
  .bubble { max-width: 75%; padding: 12px 16px; border-radius: 12px;
            line-height: 1.6; font-size: 14px; white-space: pre-wrap; }
  .user { background: #1a56db; color: #fff; align-self: flex-end;
          border-bottom-right-radius: 4px; }
  .agent { background: #1e1e1e; color: #e8e8e8; align-self: flex-start;
           border-bottom-left-radius: 4px; border: 1px solid #2a2a2a; }
  .tool-call { background: #111; border: 1px solid #2a2a2a; border-radius: 8px;
               padding: 8px 12px; font-family: monospace; font-size: 12px;
               color: #888; align-self: flex-start; max-width: 75%; }
  .tool-call strong { color: #f59e0b; }
  .thinking { color: #555; font-size: 13px; font-style: italic;
              align-self: flex-start; padding: 4px 0; }
  #input-area { padding: 16px 24px; border-top: 1px solid #222;
                display: flex; gap: 12px; }
  #msg { flex: 1; background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
         padding: 12px 16px; color: #e8e8e8; font-size: 14px; resize: none;
         height: 52px; outline: none; font-family: inherit; }
  #msg:focus { border-color: #1a56db; }
  #send { background: #1a56db; color: #fff; border: none; border-radius: 8px;
          padding: 0 20px; font-size: 14px; cursor: pointer; font-weight: 500; }
  #send:disabled { background: #333; color: #666; cursor: not-allowed; }
  #send:hover:not(:disabled) { background: #1e40af; }
  #session-info { font-size: 11px; color: #444; padding: 4px 24px 0;
                  font-family: monospace; }
</style>
</head>
<body>
<header>
  <h1>🤖 Sappy</h1>
  <span>Minimal Agent Runtime</span>
</header>
<div id="session-info"></div>
<div id="chat"></div>
<div id="input-area">
  <textarea id="msg" placeholder="Ask me to analyse a file…" rows="1"></textarea>
  <button id="send">Send</button>
</div>
<script>
  let sessionId = null;

  async function initSession() {
    const r = await fetch('/session/new');
    const d = await r.json();
    sessionId = d.session_id;
    document.getElementById('session-info').textContent =
      'Session: ' + sessionId + ' — resume with: python agent.py --session ' + sessionId;
  }

  function addBubble(role, text) {
    const div = document.createElement('div');
    div.className = 'bubble ' + role;
    div.textContent = text;
    document.getElementById('chat').appendChild(div);
    div.scrollIntoView({ behavior: 'smooth' });
    return div;
  }

  function addToolCall(name, input) {
    const div = document.createElement('div');
    div.className = 'tool-call';
    div.innerHTML = '<strong>→ ' + name + '</strong> ' + input;
    document.getElementById('chat').appendChild(div);
    div.scrollIntoView({ behavior: 'smooth' });
  }

  async function send() {
    const input = document.getElementById('msg');
    const sendBtn = document.getElementById('send');
    const text = input.value.trim();
    if (!text || !sessionId) return;

    addBubble('user', text);
    input.value = '';
    sendBtn.disabled = true;

    let agentBubble = addBubble('agent', '');
    let agentText = '';

    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n\\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === 'text') {
          agentText += event.content;
          agentBubble.textContent = agentText;
          agentBubble.scrollIntoView({ behavior: 'smooth' });
        } else if (event.type === 'tool') {
          addToolCall(event.name, event.input);
          agentBubble = addBubble('agent', '');
          agentText = '';
        } else if (event.type === 'error') {
          agentBubble.textContent = 'Error: ' + event.content;
          agentBubble.style.color = '#ef4444';
        }
      }
    }

    sendBtn.disabled = false;
    input.focus();
  }

  document.getElementById('send').addEventListener('click', send);
  document.getElementById('msg').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  initSession();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    init_db()
    print("\\n🤖 Sappy Web UI")
    print("   Open http://localhost:5000 in your browser\\n")
    app.run(debug=False, port=5000, threaded=True)