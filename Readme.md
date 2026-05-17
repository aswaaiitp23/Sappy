# Sappy — Minimal Agent Runtime

A from-scratch agent runtime that can read files (PDF, Excel, CSV), answer questions spanning multiple documents, and flag inconsistencies — built without any agent framework.

---

## Quickstart

```bash
git clone https://github.com/aswaaiitp23/Sappy.git
cd Sappy
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add your Anthropic API key to .env

# Terminal interface
python agent.py

# Browser interface
python web_ui.py
# Open http://127.0.0.1:5000
```

To resume a previous session:
```bash
python agent.py --session <session-id>
```

To swap models without touching code:
```bash
ANTHROPIC_MODEL=claude-opus-4-5 python agent.py
```

---

## What it can do

```
You: Read test_data/annual_report.pdf and test_data/revenue.xlsx.
     Does the revenue trajectory in the spreadsheet match what the PDF claims?
     Flag anything that looks off.
```

The agent will:
1. List and read both files using its tools
2. Extract numbers from the PDF and sum the spreadsheet data
3. Compare them and flag discrepancies with specific figures
4. Summarise findings as a bullet list

---

## Architecture

```
agent.py          — the main loop (streaming + observability + memory + error recovery)
tools.py          — file reading tools (PDF, Excel, CSV) + dispatch
skills.py         — loads ./skills/*.md and injects summaries into system prompt
db.py             — SQLite session persistence
web_ui.py         — browser interface with SSE streaming
logs/agent.jsonl  — structured log of every LLM call and tool call
skills/           — drop .md files here to add new domain knowledge
test_data/        — sample files for testing (PDF + Excel + CSV with baked-in discrepancies)
stress_test.py    — automated test suite across 10 scenarios
```

---

## Design decisions

### The loop

The agent runs in a `for` loop capped at `MAX_TOOL_ROUNDS = 15`. Each iteration:
1. Calls the Anthropic API (streaming)
2. Checks `stop_reason` on the response
3. If `"end_turn"` → prints the answer, breaks out of the loop
4. If `"tool_use"` → dispatches every requested tool, appends results, loops again

The hard cap exists because a confused model can get stuck calling tools in circles. Without it, a buggy prompt could run indefinitely and bill forever.

**Tradeoff:** 15 rounds is generous for most tasks. A complex multi-file analysis typically takes 3–5 rounds. I chose 15 over a lower number to avoid cutting off legitimate long-running tasks.

### Error handling and recovery

The API can fail in two distinct ways, handled separately:

**`BadRequestError` (400) — self-healing recovery**

A 400 almost always means the message history contains something the API won't accept — a malformed tool result, a stale content block, or an SDK internal field that leaked into the history.

The recovery strategy:
1. On first `BadRequestError`, log the event, print a human-readable warning, drop all history except the current user message, set `bad_request_retried = True`, and `continue` the loop to retry
2. If a second `BadRequestError` fires on the same turn, give up and surface the error

This one-retry pattern means a single corrupted turn doesn't kill the whole session. The `bad_request_retried` flag is scoped per turn, not per session, so the agent is always willing to attempt recovery on a new turn.

**Other API errors — actionable messages**

Rather than printing a raw stack trace, each HTTP status code maps to a human-readable suggestion:
- `401` → "Invalid API key — check your .env file"
- `429` → "Rate limit hit — wait a moment and try again"
- `500` → "Anthropic server error — try again shortly"
- anything else → raw error with status code

All errors are logged to `logs/agent.jsonl` with `type: "api_error"` and the status code, so they're queryable after the fact.

**SDK field filtering via `_clean_block()`**

The Anthropic SDK's `model_dump()` includes internal fields (`parsed_output`, `caller`) that the API rejects when the block is re-sent in message history. `_clean_block()` strips each block to only its documented fields:
- `text` blocks → keep only `type` and `text`
- `tool_use` blocks → keep only `type`, `id`, `name`, and `input`
- anything else → keep only known safe scalar fields

This is a real production concern — SDK internals and API contracts can diverge across patch versions, and without this filter the agent would break silently on every SDK upgrade.

### Tools

Each tool is a dict with a `name`, `description`, and `input_schema` (JSON Schema). This tells the model what tools exist and what arguments they take.

When the model emits a `tool_use` block, the loop extracts the tool name and inputs, calls `dispatch_tool()`, and appends the result as a `tool_result` message. The model never executes code directly — it requests, the loop acts, the result flows back into context.

On tool failure, the error string is returned as the tool result rather than crashing the loop. This lets the model say "that file doesn't exist, can you check the path?" instead of dying silently.

### Skills

A skill is a `.md` file in `./skills/`. At startup, `skills.py` scans the folder and builds a one-line summary of each skill (name + first line). This summary is injected into the system prompt.

When the model decides a skill is relevant, it calls the `load_skill` tool to fetch the full content on demand.

**Why not dump all skill content into the system prompt upfront?** Token cost and noise. A system prompt with 20 full-length skill documents would be expensive on every call and would dilute the model's attention. The summary-first, fetch-on-demand pattern keeps the prompt lean while making all skills discoverable.

**Adding a new skill requires zero code changes** — drop a `.md` file into `./skills/` and the agent picks it up on next startup.

### Session state

Conversation history lives in SQLite (`agent_sessions.db`). Each session is a row: `(id TEXT, messages TEXT, updated_at TIMESTAMP)` where `messages` is a JSON-serialised list of the full conversation history.

**Why SQLite over a flat JSON file?**
- Atomic writes: `INSERT ... ON CONFLICT DO UPDATE` means a crash mid-write never corrupts the file
- Concurrent safety: multiple sessions can be read/written without locking issues
- O(1) lookup: `SELECT messages WHERE id = ?` is instant regardless of how many sessions exist

**Why not Postgres or Redis?** This is a local CLI tool. SQLite requires no server, no configuration, and ships with Python. The upgrade path to Postgres is one connection string change.

**Pruning:** When history exceeds `MEMORY_THRESHOLD = 40` messages, the oldest half is summarised by the model into a single memory block. The summary preserves specific numbers, file names, and decisions. This keeps the context window from overflowing on long sessions while retaining what mattered.

### Streaming

The agent uses `client.messages.stream()` instead of `client.messages.create()`. Under the hood this is a Server-Sent Events connection — the Anthropic API pushes `content_block_delta` events as text is generated, and the SDK reassembles them into the same final message object.

In the CLI, each delta is appended to a `rich.Live` panel that re-renders in place, giving the word-by-word effect. In the web UI, each delta is forwarded as an SSE `data:` line to the browser, where JavaScript appends it to the chat bubble.

**Why stream?** Latency perception. A 5-second response that streams feels faster than a 3-second response that appears all at once. For file analysis tasks that take 10+ seconds, streaming is the difference between "is it frozen?" and "I can see it thinking."

### Observability

Every LLM call, tool call, memory compression, and error is written to `logs/agent.jsonl` as a JSON line with a UTC timestamp. The log captures: session ID, round number, model, token counts, duration, tool name and inputs, error status codes.

**Why JSONL over a plain text log?** Machine-readable. You can pipe it to `jq`, load it into pandas, or ship it to a log aggregator without parsing. Each line is a complete event — no multi-line entries to reassemble.

### Documents

Parsing is a tool's job, not the runtime's. The `read_file` tool detects the file extension and routes to the appropriate parser:
- **PDF** → `pdfplumber` extracts text page by page with page numbers
- **Excel** → `openpyxl` reads all sheets, returns tab-separated rows with sheet headers
- **CSV** → standard library `csv` reader, returns tab-separated rows

The model receives structured text — not bytes, not base64, not a pre-filtered summary. This lets it do its own analysis rather than being constrained by my parsing assumptions.

### The web interface

`web_ui.py` is a Flask server that serves a single-page chat UI and streams responses via Server-Sent Events.

The browser sends a `POST /chat` with the session ID and message. Flask calls the same `run_agent_streaming()` generator used by the CLI and yields SSE lines of three types:
- `{"type": "text", "content": "..."}` — partial text chunk, appended to the current bubble
- `{"type": "tool", "name": "...", "input": "..."}` — tool being called, rendered as a dim annotation
- `{"type": "done"}` — turn complete, re-enable the send button

**Why SSE over WebSockets?** SSE is unidirectional (server → client), works with plain `fetch()`, and requires no client-side library. WebSockets are bidirectional — useful for multiplayer or real-time collaboration, overkill for a single-user chat tool.

### User customisation

A user can adjust agent behaviour without touching code through three mechanisms:
1. **Skills** — drop `.md` files into `./skills/` to add domain expertise
2. **Model** — set `ANTHROPIC_MODEL` env var to swap the underlying model
3. **System prompt** — modify `build_system_prompt()` in `agent.py` (one clearly-labelled function)

---

## Observability

Every LLM call, tool call, and error is logged to `logs/agent.jsonl` as structured JSON lines:

```json
{"ts": "2024-01-15T10:23:41+00:00", "type": "llm_call_end", "session": "abc-123", "round": 1, "stop_reason": "tool_use", "input_tokens": 842, "output_tokens": 67, "duration_s": 1.24}
{"ts": "2024-01-15T10:23:41+00:00", "type": "tool_call", "session": "abc-123", "tool": "read_file", "input": {"path": "report.pdf"}}
{"ts": "2024-01-15T10:23:41+00:00", "type": "api_error", "session": "abc-123", "status": 429, "suggestion": "Rate limit hit — wait a moment and try again"}
```

To watch logs live:
```bash
tail -f logs/agent.jsonl | python -m json.tool
```

---

## Running the stress test

```bash
# Generate test files (fake company with intentional discrepancies baked in)
pip install reportlab
python generate_test_files.py

# Run all tests
python stress_test.py --agent-dir .

# Run one specific test
python stress_test.py --agent-dir . --test cross_file_discrepancy
```

The test suite checks 10 scenarios: basic file reading, cross-file analysis, skill loading, error handling, and session persistence. Known discrepancies baked into the test data:
- PDF claims revenue of **$5.2B** — Excel monthly sum is **$4.8B**
- PDF says Asia-Pacific is **15%** of revenue — Excel says **18%**

---

## Requirements

```
anthropic
python-dotenv
pdfplumber
openpyxl
rich
flask
reportlab  # only needed to generate test files
```

---

## What I'd build next

**1. Chunked retrieval for large files**
Files too large to fit in context get chunked, embedded, and retrieved by query similarity. The model gets only the relevant sections rather than the full document. This would unlock analysis of real annual reports (often 200+ pages). Implementation: `sentence-transformers` for embeddings, `faiss` for vector search, chunking at paragraph boundaries to preserve context.

**2. `!summary` command**
Type `!summary` at any point to get a concise summary of the entire current session — what files were read, what was found, what decisions were made. Implementation: detect the `!summary` prefix before sending to the agent loop, instead call the API once with the full history and a summarisation prompt, print the result without saving it to history.

**3. Token budget display**
Show a live token counter in the terminal — input + output tokens per turn, running session total, and estimated cost at current model pricing. Implementation: accumulate `usage.input_tokens` and `usage.output_tokens` from each `llm_call_end` log event, display in a `rich` footer panel. Helps the user understand what they're spending and when context is getting tight.

**4. Parallel file reading**
When asked to read multiple files, read them concurrently using `asyncio` rather than sequentially. For 5 large PDFs this could cut wait time by 4x. Implementation: make `read_file` async, gather all tool calls in a turn with `asyncio.gather()` rather than a sequential for loop.

**5. `!export` to report**
A `!export` command that takes the session history and generates a clean markdown or PDF report of the findings — structured as an actual deliverable rather than a chat transcript. Implementation: filter the history for assistant messages only, send to the API with a report-formatting prompt, write the output to `reports/<session-id>.md` using the existing `pdfplumber` pipeline in reverse via `reportlab`.