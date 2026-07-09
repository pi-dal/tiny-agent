# tiny-agent

A minimal, single-file AI agent that can run shell commands to get things done.
Two implementations, one design:

- **`agent.py`** — ~265 lines of Python, TUI built with [Rich](https://rich.readthedocs.io/)
- **`agent.mjs`** — a Node.js port using the `openai` SDK

Both ship the same feature set: an interactive REPL, a **bash tool** the model can
call, **append-only JSONL session persistence**, and an **agent loop**
(LLM → tool call → result → repeat until done).

## Features

- **Bash tool** — the model executes shell commands (120s timeout, output truncated)
- **Agent loop** — reasoning → tool call → observation → next step, until the task is done
- **Session management** — every message is appended as one JSONL line, so writes are
  crash-safe and never rewrite the whole file. Resume any session by ID.
- **Interactive TUI** — colored output, markdown rendering, tool-call panels
- **One-shot mode** — `agent -m "prompt"` for scripting / piping
- **OpenAI-compatible** — point `AGENT_BASE_URL` at Ollama, LM Studio, vLLM, OpenRouter, etc.
- **Zero framework** — no LangChain, no Textual, no agents SDK. Just the OpenAI client.

## Quick start

### Python

```bash
uv venv && uv pip install openai rich
export OPENAI_API_KEY=sk-...
uv run python agent.py
```

### Node.js

```bash
npm install
export OPENAI_API_KEY=sk-...
node agent.mjs
```

## Usage

```bash
# Interactive REPL (default)
uv run python agent.py

# One-shot mode — print a result and exit
uv run python agent.py -m "list all Python files"

# Resume a session
uv run python agent.py --session <session-id>

# Use a custom model
uv run python agent.py --model gpt-4o

# Use an OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, OpenRouter)
export AGENT_BASE_URL=http://localhost:11434/v1
uv run python agent.py --model llama3
```

The Node version takes the same flags: `node agent.mjs --session <id> --model gpt-4o --base-url <url>`.

## Environment variables

`.env` files are loaded automatically (no `python-dotenv` needed).

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Your API key (or put it in `.env`) |
| `AGENT_MODEL` | `gpt-4o-mini` | Default model |
| `AGENT_BASE_URL` | — | OpenAI-compatible base URL |
| `AGENT_SESSIONS_DIR` | `~/.agent/sessions` | Session storage path |

Copy `.env.example` to `.env` and fill in your key to get started.

## Slash commands

Available inside the REPL:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/new` | Start a new session |
| `/sessions` | List saved sessions |
| `/load <ID>` | Load a session by ID |
| `/clear` | Clear the screen |
| `/exit` | Quit |

## TUI layout

```
  ╔═══════════════════════════════════════════════╗
  ║         tiny-agent — bash-powered AI           ║
  ╠═══════════════════════════════════════════════╣
  ║  /help /new /sessions /load <id> /clear /exit  ║
  ╚═══════════════════════════════════════════════╝
  Session: abc123 | Model: gpt-4o-mini

❯ list all Python files

  You: list all Python files
  Agent: I'll search for Python files...
    🔧 find . -name "*.py" -type f
  ┌─ output ─────────────────────────────────┐
  │ ./agent.py                                 │
  └───────────────────────────────────────────┘
  Agent: Found 1 Python file.

❯ /exit
  Bye!
```

## Architecture

```
agent.py / agent.mjs
├── Config       — env vars + .env loader, system prompt
├── Bash Tool    — run_bash(): execute shell commands (timeout, truncation)
├── Session      — append-only JSONL persistence
├── Agent        — OpenAI client wrapper
└── TUI          — REPL input loop + run_agent_loop()
```

The agent loop sends the conversation (with the bash tool schema) to the LLM.
If the response contains tool calls, each command is executed, its output is
appended as a `tool` message, and the loop continues. When the model replies
with no tool calls, the turn ends and control returns to the user.

Sessions live at `~/.agent/sessions/<id>.jsonl` — the first line is metadata,
every following line is one message. This makes writes atomic and cheap, and
lets you resume or inspect any session with standard line-oriented tools.

## Requirements

- **Python:** `>=3.12`, `openai>=1.0`, `rich>=13.0`
- **Node.js:** `openai ^4.104.0`

## License

MIT