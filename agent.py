#!/usr/bin/env python3
"""mini-agent — simple TUI agent with bash tool and session management.
Requires: pip install openai rich | Env: OPENAI_API_KEY or .env file"""

import os, sys, json, subprocess, uuid, argparse
from pathlib import Path

# ── Enable arrow keys / line editing / history in input() ──
try:
    import readline
    readline.set_history_length(100)
except ImportError:
    pass

# ── Load .env if present (before reading any env vars) ──
def _load_dotenv():
    env = Path(__file__).resolve().parent / ".env"
    if not env.exists(): return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        if k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

_load_dotenv()

from datetime import datetime
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

# ── Config ──

DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")
DEFAULT_BASE_URL = os.environ.get("AGENT_BASE_URL", None)
SESSIONS_DIR = Path(os.environ.get("AGENT_SESSIONS_DIR", str(Path.home() / ".agent" / "sessions")))
SYSTEM_PROMPT = ("You are a helpful AI assistant with access to a bash tool. "
    "You can run shell commands to help the user accomplish tasks. "
    "Always explain briefly what you are doing, then call the tool. Be concise.")

# ── Bash Tool ──

TOOL_SCHEMA = {"type": "function", "function": {
    "name": "bash", "description": "Execute a shell command and return its output.",
    "parameters": {"type": "object",
        "properties": {"command": {"type": "string", "description": "The shell command to execute."}},
        "required": ["command"]}}}


def run_bash(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        out = r.stdout + r.stderr
        return out[:8000] if out else f"[exit code {r.returncode}]"
    except subprocess.TimeoutExpired: return "[Command timed out after 120s]"
    except Exception as e: return f"[Error: {e}]"

def execute_tool(name, args):
    return run_bash(args.get("command", "")) if name == "bash" else f"[Unknown tool: {name}]"

# ── Session (append-only JSONL) ──

class Session:
    """Append-only JSONL persistence. Each message = one line, crash-safe."""
    def __init__(self, sid=None):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.id = sid or uuid.uuid4().hex[:12]
        self.path = SESSIONS_DIR / f"{self.id}.jsonl"
        self.messages, self.created = [], datetime.now().isoformat()
        if self.path.exists(): self.load()
        else:
            self.path.write_text(json.dumps({"type":"meta","id":self.id,"created":self.created}, ensure_ascii=False) + "\n")

    def load(self):
        for line in self.path.read_text().splitlines():
            if not line.strip(): continue
            d = json.loads(line)
            if d.get("type") == "meta": self.created = d.get("created", self.created)
            else: self.messages.append(d)

    def append(self, msg): self.messages.append(msg); self.path.open("a").write(json.dumps(msg, ensure_ascii=False) + "\n")

    @staticmethod
    def list_all():
        out = []
        for f in sorted(SESSIONS_DIR.glob("*.jsonl"), key=os.path.getmtime, reverse=True):
            try:
                lines = f.read_text().splitlines()
                meta = json.loads(lines[0]) if lines else {}
                msgs = [json.loads(l) for l in lines[1:] if l.strip()]
                out.append({"id": meta.get("id", f.stem), "created": meta.get("created", "?"),
                    "msgs": len(msgs), "preview": (msgs[0].get("content", "")[:50] if msgs else "")})
            except Exception: pass
        return out

# ── Agent ──

class Agent:
    def __init__(self, model=DEFAULT_MODEL, base_url=None, api_key=None):
        kw = {}
        if base_url: kw["base_url"] = base_url
        if api_key: kw["api_key"] = api_key
        self.client, self.model = OpenAI(**kw), model

    def call_llm(self, messages):
        return self.client.chat.completions.create(
            model=self.model, messages=messages, tools=[TOOL_SCHEMA], tool_choice="auto")

# ── TUI ──

BANNER = """\
  ╔═══════════════════════════════════════════════╗
  ║         mini-agent — bash-powered AI           ║
  ╠═══════════════════════════════════════════════╣
  ║  /help /new /sessions /load <id> /clear /exit  ║
  ╚═══════════════════════════════════════════════╝"""


def render_history(session):
    for m in session.messages:
        r = m["role"]
        if r == "user":
            console.print(f"[bold cyan]You:[/bold cyan] {m.get('content', '')}")
        elif r == "assistant":
            if m.get("content"):
                console.print("[bold green]Agent:[/bold green]")
                console.print(Markdown(m["content"]))
            for tc in m.get("tool_calls", []):
                try: a = json.loads(tc["function"]["arguments"])
                except Exception: a = {}
                console.print(f"  [yellow]🔧 {a.get('command', '')}[/yellow]")
                tid = tc["id"]
                for m2 in session.messages:
                    if m2.get("role") == "tool" and m2.get("tool_call_id") == tid:
                        console.print(Panel(m2.get("content", "")[:500], title="output", border_style="dim"))
                        break


def run_agent_loop(agent, session):
    msgs = session.messages[:]
    if not msgs or msgs[0]["role"] != "system":
        msgs.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    while True:
        try:
            resp = agent.call_llm(msgs)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return
        msg = resp.choices[0].message
        entry = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = [{"id": tc.id, "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls]
        session.append(entry)
        if msg.content:
            console.print("[bold green]Agent:[/bold green]")
            console.print(Markdown(msg.content))
        if not msg.tool_calls:
            return
        for tc in msg.tool_calls:
            try: args = json.loads(tc.function.arguments)
            except Exception: args = {}
            console.print(f"  [yellow]🔧 {args.get('command', '')}[/yellow]")
            result = execute_tool(tc.function.name, args)
            session.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            console.print(Panel(result[:2000], title="output", border_style="dim"))
        msgs = session.messages[:]
        if msgs[0]["role"] != "system":
            msgs.insert(0, {"role": "system", "content": SYSTEM_PROMPT})


def handle_command(text, agent, session):
    """Returns (session, should_exit)."""
    cmd = text.lower()
    if cmd in ("/exit", "/quit"):
        return session, True
    elif cmd == "/help":
        console.print("[dim]Commands: /new /sessions /load <id> /clear /help /exit[/dim]")
    elif cmd == "/new":
        session = Session()
        console.print(f"[dim]New session: {session.id}[/dim]")
    elif cmd == "/sessions":
        ss = Session.list_all()
        if not ss:
            console.print("[dim]No saved sessions.[/dim]")
        else:
            for s in ss:
                console.print(f"  [bold]{s['id']}[/bold] ({s['msgs']} msgs) {s['preview']}")
    elif cmd.startswith("/load "):
        sid = cmd.split(" ", 1)[1].strip()
        session = Session(sid)
        console.print(f"[dim]Loaded {session.id} ({len(session.messages)} msgs)[/dim]")
        render_history(session)
    elif cmd == "/clear":
        os.system("clear" if os.name != "nt" else "cls")
    else:
        console.print(f"[red]Unknown: {text}[/red]")
    return session, False


def run_repl(agent, session):
    console.print(BANNER)
    console.print(f"  [dim]Session: {session.id} | Model: {agent.model}[/dim]")
    if session.messages:
        render_history(session)
    console.print()
    while True:
        try:
            user_input = input("❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye![/dim]")
            break
        if not user_input:
            continue
        try: readline.add_history(user_input)
        except Exception: pass
        if user_input.startswith("/"):
            session, should_exit = handle_command(user_input, agent, session)
            if should_exit:
                console.print("[dim]Bye![/dim]")
                break
            console.print()
            continue
        console.print(f"\n[bold cyan]You:[/bold cyan] {user_input}")
        session.append({"role": "user", "content": user_input})
        try:
            run_agent_loop(agent, session)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        console.print()

# ── Entry Point ──

def main():
    p = argparse.ArgumentParser(description="mini-agent TUI")
    p.add_argument("-s", "--session", help="Session ID to resume")
    p.add_argument("-m", "--message", help="One-shot: run a single prompt and exit")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"LLM model (default: {DEFAULT_MODEL})")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible base URL (env: AGENT_BASE_URL)")
    p.add_argument("--api-key", help="API key (or set OPENAI_API_KEY)")
    args = p.parse_args()

    if not args.api_key and not os.environ.get("OPENAI_API_KEY"):
        print("Error: Set OPENAI_API_KEY or use --api-key"); sys.exit(1)

    agent = Agent(model=args.model, base_url=args.base_url, api_key=args.api_key)
    session = Session(args.session)

    # One-shot mode
    if args.message:
        console.print(f"[dim]Session: {session.id} | Model: {agent.model}[/dim]\n")
        console.print(f"[bold cyan]You:[/bold cyan] {args.message}")
        session.append({"role": "user", "content": args.message})
        run_agent_loop(agent, session)
        console.print(f"\n[dim]✓ Done. Session: {session.path}[/dim]")
        return

    run_repl(agent, session)

if __name__ == "__main__": main()