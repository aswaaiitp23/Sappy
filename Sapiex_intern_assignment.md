# Sapiex Intern Take-Home — Build a Minimal Agent Runtime

**Time:** 1 week of focused work
**Language:** Your choice — TypeScript or Python
**AI agent:** OpenCode Go subscription provided for the week. Use it freely — we want to see how you collaborate with it.
**Submission:** A git repo + replayable AI-session evidence. Entire.io is a bonus: if you can figure it out and submit useful checkpoint/session evidence from it, great. If not, submit the raw OpenCode / Claude Code / Codex session.

---

## The mission

Build an agent runtime small enough to fit in your head and serious enough to be useful.

By the end of the week, your agent should be able to do something like this — in a real terminal or a real browser, with no scripted demo, on files we hand you:

> *"Here's a folder. It has a spreadsheet of monthly revenue and a PDF of last year's annual report. Tell me whether the trajectory in the spreadsheet matches what the PDF claims happened, and flag anything that looks off."*

It should also let a user (or you) **define new "skills"** — bits of reusable expertise the agent can reach for — without modifying the runtime code.

That's the whole brief. Everything below is constraints and provocations.

---

## The hard constraint

**You may not use any existing agent framework.** That's the whole point.

**Banned** — anything whose whole job is *"loop the LLM and call its tools for you"*: LangChain, LlamaIndex, OpenAI Agents SDK, PydanticAI, Pydantic AI Harness, DeepAgents, Mastra, CrewAI, AutoGen, Inngest agent kit, Agno, smolagents, and so on. Also banned: Vercel AI SDK's agent-loop abstractions such as `experimental_Agent`, agent middleware, or agent runners. If you're not sure, ask.

**Allowed:**
- The raw provider SDK from OpenAI, Anthropic, Google, etc.
- **Vercel AI SDK** at the call level — `generateText`, `streamText`, the `tool()` helper, the provider packages (`@ai-sdk/openai`, `@ai-sdk/anthropic`, etc.). We use this in production at Sapiex; we'd rather you learn it than avoid it. Just don't reach for its agent helpers.
- If you cannot test against a traditional LLM provider like OpenAI, Anthropic, Google, or DeepSeek, you may use any model currently marked free on OpenRouter. Make the model configurable so we can swap it during review.
- Pure HTTP if you want to.
- Anything else: schema libraries, file parsers, web frameworks, test frameworks, UI frameworks — all fine.

In short: an LLM-call abstraction is fine. **The loop, the tool dispatch, the history management, the skill system — these are yours to design.** That's where we're looking.

---

## Open design questions you'll need to answer

These are the things we want to see you wrestle with. Your README is where you defend your answers. There is no single right answer for any of them.

- **The loop.** When does the agent decide it's done? How do you stop it from looping forever? What happens when the model emits malformed output?
- **Tools.** What's the shape of a tool? How does it surface to the LLM? How do results flow back into context? What happens when a tool fails?
- **Skills.** What is a skill, in your runtime? When does the LLM see them — all at once, on demand, by name, by description? What's the smallest possible authoring format?
- **State.** Where does conversation history live? How does it survive a restart? When does it get pruned, and by what rule?
- **Documents.** What does it mean for the agent to "understand" a spreadsheet versus a PDF versus a CSV? What does it see — bytes, text, structured rows, summaries? Whose job is the parsing — a tool, the runtime, the model?
- **The interface.** What's the smallest thing a user has to install, run, or open to talk to your agent? CLI is enough. A web page is enough. We don't care about polish — we care that you picked something on purpose.
- **The user's grip.** How does a user adjust the agent's behaviour without editing your code? Through skills? Config? Prompts on disk? Something else?

We expect your README to answer most of these — briefly, with the tradeoffs you considered.

Minimum expectation on state: your runtime should persist enough conversation/session state that we can restart it once and continue the same task. Anything beyond this — long-term memory, retrieval, summaries across sessions — is bonus.

---

## What we'll actually test

When we evaluate your submission, we'll do this:

1. Clone your repo. Read the README. Try to run it.
2. Hand it a folder with a real Excel file, a real CSV, and a real PDF you've never seen.
3. Ask it questions that span the files.
4. Drop a new skill into the skills folder and see whether it picks it up.
5. Restart the agent mid-conversation and see whether it remembers.
6. Read your code top to bottom.
7. Replay your raw/native AI session evidence, plus Entire checkpoint/session evidence if you used it.

If all of that goes well, that's a very strong signal for the next round. If it doesn't, we'll still give you written feedback.

---

## Bonus dimensions

If you finish the core early, these are where strong submissions become great. Pick a few that interest you. Depth beats breadth.

- **Memory.** Beyond the required basic session history. What happens after one hundred messages? How does the agent remember what mattered three sessions ago?
- **Context engineering.** The way you teach the model about its environment is itself a craft. Tool catalogs, skill discovery patterns, dynamic system-prompt construction. We pay close attention to this.
- **Streaming.** Render text and tool calls as they happen.
- **Sub-agents.** A child agent for a sub-task with isolated context.
- **Observability.** Log every LLM call, every tool call, every error in a way you'd actually use to debug.
- **Tests.** Real unit and integration tests on real fixtures.
- **A surprising UI choice.** A web interface, a tree view of the conversation, anything that makes us go *"oh, that's clever."*

---

## On using AI agents

We are giving you an **OpenCode Go subscription** for the week and we expect you to use it. Claude Code and Codex are also fine if you prefer them — pick the one you'll actually wrestle with.

We're not testing whether you can hand-write every line. We're testing how you architect, decide, push back on the AI when it's wrong, and review what it produces. A candidate who blindly accepts whatever the agent emits will produce a worse submission than one who treats it like a junior pair-programmer.

### You must share at least one substantive coding session

A "substantive session" means a real chunk of work — a hard design call, a debug that took multiple turns, a refactor where you steered the AI somewhere it wasn't going on its own. We will replay it. We want to see how you ask, when you accept, when you push back.

**Minimum required path — share the raw session file or native share link:**

- **OpenCode** — use its built-in `/share` flow or export the session with `opencode export <session-id>`.
- **Claude Code** — locate your session JSONL file and attach it.
  - macOS / Linux: `~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`
  - Windows: `%USERPROFILE%\.claude\projects\<encoded-cwd>\<session-uuid>.jsonl`
- **Codex** — locate the rollout JSONL and attach it. The first line is a `session_meta` event — that's the right file.
  - macOS / Linux: `~/.codex/sessions/<year>/.../rollout-<timestamp>-<uuid>.jsonl` (or under `~/.codex/archived_sessions/`)
  - Windows: `%USERPROFILE%\.codex\sessions\<year>\...\rollout-<timestamp>-<uuid>.jsonl` (or under `%USERPROFILE%\.codex\archived_sessions\`)

Pick whichever your agent of choice produces.

**Bonus path — try Entire.io and show us what you got working:**

Entire is new, and part of the signal here is whether you can check out a new developer platform, set it up, and give us something useful from it. If you can, submit the relevant Entire checkpoint/session evidence alongside your raw/native session.

```bash
curl -fsSL https://entire.io/install.sh | bash
entire version
cd your-repo
entire enable
```

Then enable the agent you are using and start it:

```bash
# OpenCode
entire agent add opencode
opencode

# Claude Code
# Claude Code is Entire's default integration; this explicit command is fine too.
entire agent add claude-code
claude

# Codex
entire agent add codex
codex
```

Make meaningful commits as you work, then push the repo. If the repo is private, add us as collaborators. If Entire setup fails, that is fine; include a short note about what failed and submit the raw/native session evidence.

Before sharing anything, make sure you have not included API keys, `.env` secrets, private third-party data, or credentials in the transcript or repo. Use `.env.example` for configuration.

We'd rather see you wrestle with the AI for an hour and end up with a thoughtful design than see a clean repo with no visible thinking.

---

## What to submit

1. **A git repo URL** — GitHub, public or private with us added (we'll send GitHub usernames separately).
2. **A coding session** we can replay — required: raw OpenCode share/export, Claude Code JSONL, or Codex rollout JSONL. Bonus: Entire checkpoint/session evidence linked to your commits, plus a short note on what worked or failed during setup.
3. **A short walkthrough** — written or a 3-5 minute Loom — showing your agent doing something real on a real file.
4. **Your README** with the design notes covering the questions above.

---

## Tips, learned the hard way

- **Start with the loop.** Get the LLM to call one fake tool and return one fake result before you build anything else. The shape of that one cycle determines everything else.
- **Resist abstractions.** You probably don't need a plugin system, a class hierarchy, or a registry pattern in week one. A flat list of functions works fine until it doesn't.
- **Real PDFs are messier than you think.** Test on the messiest one you can find before declaring victory.
- **Commit often, with real messages.** Your git history is part of what we look at. Small commits beat one big push.
- **Push back on the AI.** When OpenCode suggests something that feels wrong, follow your instinct and challenge it. We can tell.
- **Ask questions.** We'd much rather you reach out on day two than guess wrong for four days.

---

## A note on what we're really evaluating

You're an undergrad. We don't expect production code. We expect to see how you **think** when given an open problem with a hard constraint and a real deliverable.

If your submission is small, clean, working, and your README explains why every meaningful choice was the choice you made, you've done well. If it's sprawling, half-finished, full of features you don't understand, and the README is a list of TODOs — you haven't.

The best submissions in past rounds are the ones we could read in fifteen minutes and immediately understand the author's mental model. Aim for that.

Good luck. Build something you'd be proud to walk us through.
