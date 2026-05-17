# Sappy — Minimal Agent Runtime

A from-scratch agent runtime that can read files (PDF, Excel, CSV), answer questions spanning multiple documents, and flag inconsistencies — built without any agent framework.

---

## Quickstart

```bash
git clone <repo>
cd sappy
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add your Anthropic API key to .env

# Terminal interface
python agent.py

# Browser interface
python web_ui.py
# Open http://localhost:5000
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
agent.py          — the main loop (streaming + observability + memory)
tools.py          — file reading tools (PDF, Excel, CSV) + dispatch
skills.py         — loads ./skills/*.md and injects summaries into system prompt
db.py             — SQLite session persistence
web_ui.py         — browser interface with SSE streaming
logs/agent.jsonl  — structured log of every LLM call and tool call
skills/           — drop .md files here to add new domain knowledge
```

---

## Design decisions

### The loop

The agent runs in a `while` loop capped at `MAX_TOOL_ROUNDS = 15`. Each iteration:
1. Calls the Anthropic API (streaming)
2. Checks `stop_reason` on the response
3. If `"end_turn"` → prints the answer, breaks out of the loop
4. If `"tool_use"` → dispatches every requested tool, appends results, loops again

The hard cap exists because a confused model can get stuck calling tools in circles. Without it, a buggy prompt could run indefinitely and bill forever. On malformed output, the error is caught, returned to the model as a tool result, and the model gets one chance to recover before the turn ends.

**Tradeoff:** 15 rounds is generous for most tasks. A complex multi-file analysis typically takes 3–5 rounds. I chose 15 over a lower number to avoid cutting off legitimate long-running tasks.

### Tools

Each tool is defined as a dict with a `name`, `description`, and `input_schema` (JSON Schema). This is what the Anthropic API expects — it tells Claude what tools exist and what arguments they take.

When the model emits a `tool_use` block, my loop extracts the tool name and inputs, calls `dispatch_tool()`, and appends the result as a `tool_result` message. The model never executes code directly — it requests, my loop acts, the result flows back into context.

On tool failure, the error string is returned as the tool result rather than crashing the loop. This lets the model say "that file doesn't exist, can you check the path?" instead of dying silently.

**Tradeoff:** Returning errors to the model means it sometimes tries to self-correct, which adds a round-trip. The alternative — crashing immediately — is worse for usability.

### Skills

A skill is a `.md` file in `./skills/`. At startup, `skills.py` scans the folder and builds a one-line summary of each skill (name + first line of the file). This summary is injected into the system prompt.

When the model decides a skill is relevant, it calls the `load_skill` tool to fetch the full content. The full content is only loaded on demand.

**Why not dump all skill content into the system prompt upfront?** Token cost and noise. A system prompt with 20 full-length skill documents would be expensive on every call and would dilute the model's attention. The summary-first, fetch-on-demand pattern keeps the prompt lean while making all skills discoverable.

**Adding a new skill requires zero code changes** — drop a `.md` file into `./skills/` and the agent picks it up on next startup. This is the primary user-facing customisation mechanism.

### Session state

Conversation history lives in SQLite (`agent_sessions.db`). Each session is a row: `(id TEXT, messages TEXT, updated_at TIMESTAMP)` where `messages` is a JSON-serialised list of the full conversation history.

**Why SQLite over a flat JSON file?**
- Atomic writes: SQLite uses `INSERT ... ON CONFLICT DO UPDATE`, so a crash mid-write doesn't corrupt the file
- Concurrent safety: multiple sessions can be read/written without locking issues
- O(1) lookup: `SELECT messages WHERE id = ?` is instant regardless of how many sessions exist

**Why not Postgres or Redis?** This is a local CLI tool. SQLite requires no server, no configuration, and ships with Python. The upgrade path to Postgres is one connection string change.

**Pruning:** When history exceeds `MEMORY_THRESHOLD = 40` messages, the oldest half is summarised by the model into a single memory block. The summary preserves specific numbers, file names, and decisions. This keeps the context window from overflowing on long sessions while retaining what mattered.

### Documents

Parsing is a tool's job, not the runtime's. The `read_file` tool detects the file extension and routes to the appropriate parser:
- **PDF** → `pdfplumber` extracts text page by page with page numbers
- **Excel** → `openpyxl` reads all sheets, returns tab-separated rows with sheet headers
- **CSV** → standard library `csv` reader, returns tab-separated rows

The model receives structured text — not bytes, not base64, not a summary. This lets it do its own analysis rather than being pre-filtered by my parsing assumptions.

**Tradeoff:** Returning full file text can be verbose for large files. A future improvement would be returning row counts and column names first, letting the model request specific ranges if needed.

### The interface

Two interfaces:
- **CLI** (`agent.py`) — uses `rich` for formatted terminal output. Streaming text appears word-by-word via `client.messages.stream()`.
- **Web** (`web_ui.py`) — Flask server with Server-Sent Events. The browser connects to `/chat` with a `fetch()` call and reads the SSE stream, appending text chunks to the chat bubble as they arrive.

I chose SSE over WebSockets for the web UI because SSE is unidirectional (server → client), works with plain `fetch()`, and has no client-side library dependency. WebSockets would add complexity for no benefit here.

### User customisation

A user can adjust agent behaviour without touching code through three mechanisms:
1. **Skills** — drop `.md` files into `./skills/` to add domain expertise
2. **Model** — set `ANTHROPIC_MODEL` env var to swap the underlying model
3. **System prompt** — modify `build_system_prompt()` in `agent.py` (one function, clearly labelled)

---

## Observability

Every LLM call, tool call, and error is logged to `logs/agent.jsonl` as structured JSON lines:

```json
{"ts": "2024-01-15T10:23:41Z", "type": "llm_call_end", "session": "abc-123", "round": 1, "stop_reason": "tool_use", "input_tokens": 842, "output_tokens": 67, "duration_s": 1.24}
{"ts": "2024-01-15T10:23:41Z", "type": "tool_call", "session": "abc-123", "tool": "read_file", "input": {"path": "report.pdf"}}
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

The test suite checks 10 scenarios across basic file reading, cross-file analysis, skill loading, error handling, and session persistence.

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

## What I'd do next

- **Retrieval over large files** — for files too large to fit in context, chunk and embed, retrieve relevant sections by query
- **Sub-agents** — spin up a child agent with isolated context for parallel sub-tasks
- **Eval harness** — automated regression tests against known-good outputs, not just keyword matching
- **Token budget tracking** — warn the user before a session gets close to the context limit