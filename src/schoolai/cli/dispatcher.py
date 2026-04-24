"""schoolai — dispatcher de comandos SchoolAI v2."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()

_PROCS = [
    ("gateway",      "schoolai",            8001),
    ("api",          "schoolaiapi",         8000),
    ("bot-libre",    "schoolai-bot",        None),
    ("bot-jornada",  "schoolai-bot-jornada", None),
    ("bot-agente",   "schoolai-bot-agente", None),
]

_VENV_BIN = Path(__file__).parents[5] / ".venv" / "bin"

_MENU = [
    ("start",  "Arrancar todos los procesos en background"),
    ("stop",   "Parar todos los procesos"),
    ("status", "Ver qué procesos están corriendo"),
    ("api",    "Arrancar solo la REST API (foreground)"),
    ("bot",    "Arrancar solo el bot Libre (foreground)"),
    ("cli",    "Abrir el chat CLI (requiere gateway)"),
    ("salir",  "Salir"),
]


def _log_path(name: str) -> Path:
    return Path(f"/tmp/schoolai-{name}.log")


def _running_lines() -> list[str]:
    result = subprocess.run(["pgrep", "-af", "schoolai"], capture_output=True, text=True)
    my_pid = str(os.getpid())
    return [
        line for line in result.stdout.splitlines()
        if not line.startswith(my_pid) and "dispatcher" not in line
    ]


def _start_all() -> None:
    console.print("[bold cyan]Arrancando SchoolAI...[/bold cyan]")
    for name, cmd, port in _PROCS:
        log = _log_path(name)
        exe = _VENV_BIN / cmd
        with log.open("a") as fh:
            subprocess.Popen([str(exe)], stdout=fh, stderr=fh, start_new_session=True)
        port_str = f" :{port}" if port else ""
        console.print(f"  [green]✓[/green] {cmd}{port_str}  → {log}")
    console.print("\n[dim]Logs: tail -f /tmp/schoolai-<nombre>.log[/dim]")


def _stop_all() -> None:
    console.print("[bold yellow]Deteniendo SchoolAI...[/bold yellow]")
    cmds = {cmd for _, cmd, _ in _PROCS}
    killed = 0
    for line in _running_lines():
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        pid, cmdline = parts
        if any(c in cmdline for c in cmds):
            subprocess.run(["kill", pid], capture_output=True)
            killed += 1
    icon = "[green]✓[/green]" if killed else "[dim]-[/dim]"
    console.print(f"  {icon} {killed} proceso(s) detenido(s)")


def _status() -> None:
    console.print("[bold]SchoolAI Status[/bold]")
    running = _running_lines()
    for name, cmd, port in _PROCS:
        active = any(cmd in line for line in running)
        port_str = f":{port}" if port else "    "
        icon = "[green]●[/green]" if active else "[red]○[/red]"
        console.print(f"  {icon} {cmd:<28} {port_str}")


def _interactive_menu() -> None:
    import questionary
    from questionary import Choice

    running = _running_lines()

    def status_prefix(cmd: str) -> str:
        return "● " if any(cmd in l for l in running) else "○ "

    choices = []
    for key, label in _MENU:
        if key in ("start", "stop", "status", "salir"):
            choices.append(Choice(title=f"  {label}", value=key))
        else:
            cmd_map = {"api": "schoolaiapi", "bot": "schoolai-bot", "cli": "schoolai-cli"}
            cmd = cmd_map.get(key, key)
            prefix = status_prefix(cmd)
            choices.append(Choice(title=f"{prefix} {label}", value=key))

    console.print("[bold cyan]SchoolAI v2[/bold cyan]")
    selection = questionary.select(
        "¿Qué quieres hacer?",
        choices=choices,
        use_shortcuts=False,
    ).ask()

    if selection is None or selection == "salir":
        return

    _dispatch(selection)


def _dispatch(cmd: str) -> None:
    if cmd in ("all", "start"):
        _start_all()
    elif cmd == "stop":
        _stop_all()
    elif cmd == "status":
        _status()
    elif cmd == "api":
        from schoolai.api.runner import run
        run()
    elif cmd == "cli":
        from schoolai.cli.main import run
        run()
    elif cmd == "bot":
        from schoolai.bot.main import run
        run()
    else:
        console.print(f"[red]Comando desconocido:[/red] {cmd}")
        console.print("Escribe [bold]schoolai[/bold] para ver el menú interactivo.")
        sys.exit(1)


def main() -> None:
    args = sys.argv[1:]

    if not args:
        _interactive_menu()
        return

    if args[0] in ("help", "--help", "-h"):
        for key, label in _MENU:
            console.print(f"  [green]schoolai {key:<10}[/green] {label}")
        return

    _dispatch(args[0])


def _start_gateway() -> None:
    from schoolai.gateway.runner import run
    run()
