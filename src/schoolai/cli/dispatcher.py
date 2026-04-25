"""schoolai / gestion — CLI profesional SchoolAI v2."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(
    name="gestion",
    help="SchoolAI — gestión de procesos, diagnóstico y utilidades.",
    add_completion=False,
    no_args_is_help=False,
)

_PROCS = [
    ("gateway",       "schoolai-gateway",     8001),
    ("api",           "schoolaiapi",           8000),
    ("bot-libre",     "schoolai-bot",          None),
    ("bot-jornada",   "schoolai-bot-jornada",  None),
    ("bot-agente",    "schoolai-bot-agente",   None),
]

_VENV_BIN = Path(__file__).parents[5] / ".venv" / "bin"

_LOG_DIR = Path("/tmp")

_MENU_ITEMS = [
    ("start",   "Arrancar todos los procesos"),
    ("stop",    "Parar todos los procesos"),
    ("status",  "Ver estado"),
    ("doctor",  "Diagnóstico del sistema"),
    ("logs",    "Ver logs"),
    ("update",  "Actualizar código (git pull + uv sync)"),
    ("cli",     "Abrir chat CLI (requiere gateway)"),
    ("salir",   "Salir"),
]


# ── helpers ────────────────────────────────────────────────────────────────────

def _log_path(name: str) -> Path:
    return _LOG_DIR / f"schoolai-{name}.log"


def _running_lines() -> list[str]:
    result = subprocess.run(["pgrep", "-af", "schoolai"], capture_output=True, text=True)
    my_pid = str(os.getpid())
    return [
        line for line in result.stdout.splitlines()
        if not line.startswith(my_pid) and "dispatcher" not in line
    ]


def _is_running(cmd: str) -> bool:
    return any(cmd in line for line in _running_lines())


# ── commands ───────────────────────────────────────────────────────────────────

@app.command()
def start() -> None:
    """Arrancar todos los procesos en background."""
    console.print("[bold cyan]Arrancando SchoolAI...[/bold cyan]")
    for name, cmd, port in _PROCS:
        log = _log_path(name)
        exe = _VENV_BIN / cmd
        if not exe.exists():
            console.print(f"  [yellow]?[/yellow] {cmd} — ejecutable no encontrado")
            continue
        with log.open("a") as fh:
            subprocess.Popen([str(exe)], stdout=fh, stderr=fh, start_new_session=True)
        port_str = f" :{port}" if port else ""
        console.print(f"  [green]✓[/green] {cmd}{port_str}  → {log}")
    console.print(f"\n[dim]Logs: gestion logs [api|gateway|bot|jornada|agente][/dim]")


@app.command()
def stop() -> None:
    """Parar todos los procesos."""
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


@app.command()
def status() -> None:
    """Ver qué procesos están corriendo."""
    running = _running_lines()
    table = Table(show_header=False, box=None, padding=(0, 2))
    for name, cmd, port in _PROCS:
        active = any(cmd in line for line in running)
        icon = "[green]●[/green]" if active else "[red]○[/red]"
        port_str = f":{port}" if port else "    "
        table.add_row(icon, cmd, f"[dim]{port_str}[/dim]")
    console.print("\n[bold]SchoolAI Status[/bold]")
    console.print(table)
    console.print()


@app.command()
def api() -> None:
    """Arrancar solo la REST API (foreground, puerto 8000)."""
    from schoolai.api.runner import run
    run()


@app.command()
def gateway() -> None:
    """Arrancar solo el Gateway v2 (foreground, puerto 8001)."""
    from schoolai.gateway.runner import run
    run()


@app.command()
def bot() -> None:
    """Arrancar solo el bot Libre (foreground)."""
    from schoolai.bot.main import run
    run()


@app.command()
def cli() -> None:
    """Abrir el chat CLI interactivo (requiere gateway en marcha)."""
    from schoolai.cli.main import run
    run()


@app.command()
def logs(
    service: Annotated[str, typer.Argument(help="api | gateway | bot | jornada | agente")] = "",
) -> None:
    """Seguir el log de un servicio (tail -f)."""
    _service_map = {
        "api":      "api",
        "gateway":  "gateway",
        "bot":      "bot-libre",
        "jornada":  "bot-jornada",
        "agente":   "bot-agente",
    }
    if service not in _service_map:
        console.print("Servicios disponibles: [bold]api  gateway  bot  jornada  agente[/bold]")
        service = _prompt_choice("Servicio", list(_service_map))
    log = _log_path(_service_map[service])
    if not log.exists():
        console.print(f"[yellow]Log no encontrado:[/yellow] {log}")
        raise typer.Exit(1)
    try:
        subprocess.run(["tail", "-f", str(log)])
    except KeyboardInterrupt:
        pass


@app.command()
def debug(
    service: Annotated[str, typer.Argument(help="api | gateway | bot | jornada")] = "",
) -> None:
    """Depuración paso a paso con pudb."""
    _entry_map = {
        "api":      "src/schoolai/api/runner.py",
        "gateway":  "src/schoolai/gateway/runner.py",
        "bot":      "src/schoolai/bot/main.py",
        "jornada":  "src/schoolai/bot/main_dev.py",
    }
    if service not in _entry_map:
        console.print("Servicios: [bold]api  gateway  bot  jornada[/bold]")
        service = _prompt_choice("Servicio", list(_entry_map))
    proj = Path(__file__).parents[5]
    subprocess.run(
        [str(_VENV_BIN / "python"), "-m", "pudb", _entry_map[service]],
        cwd=proj,
    )


@app.command()
def doctor() -> None:
    """Diagnóstico completo del sistema."""
    import asyncio
    asyncio.run(_run_doctor())


@app.command()
def update() -> None:
    """Actualizar código (git pull + uv sync) y ofrecer reinicio."""
    proj = Path(__file__).parents[5]
    was_running = any(_is_running(cmd) for _, cmd, _ in _PROCS)

    console.print("[bold cyan]Actualizando SchoolAI...[/bold cyan]")

    r = subprocess.run(["git", "pull"], cwd=proj, capture_output=True, text=True)
    if r.returncode == 0:
        lines = r.stdout.strip().splitlines()
        summary = lines[-1] if lines else "ok"
        console.print(f"  [green]✓[/green] git pull — {summary}")
    else:
        console.print(f"  [red]✗[/red] git pull falló:\n{r.stderr.strip()}")
        raise typer.Exit(1)

    r = subprocess.run(
        [str(_VENV_BIN / "uv"), "sync"],
        cwd=proj, capture_output=True, text=True,
    )
    if r.returncode == 0:
        console.print("  [green]✓[/green] uv sync")
    else:
        console.print(f"  [red]✗[/red] uv sync falló:\n{r.stderr.strip()}")
        raise typer.Exit(1)

    if was_running:
        import questionary
        if questionary.confirm("¿Reiniciar los procesos?", default=True).ask():
            stop.callback()  # type: ignore[attr-defined]
            import time; time.sleep(1)
            start.callback()  # type: ignore[attr-defined]
    else:
        console.print("\n[dim]Actualización completada. Usa [bold]gestion start[/bold] para arrancar.[/dim]")


# ── doctor internals ───────────────────────────────────────────────────────────

async def _run_doctor() -> None:
    import httpx
    from schoolai.config import settings

    ok_icon = "[green]✓[/green]"
    fail_icon = "[red]✗[/red]"
    warn_icon = "[yellow]?[/yellow]"

    console.print("\n[bold]SchoolAI Doctor[/bold]\n")

    # .env / vars críticas
    _check_env(settings, ok_icon, fail_icon, warn_icon)

    # Procesos
    console.print("\n[bold]Procesos[/bold]")
    for name, cmd, port in _PROCS:
        icon = ok_icon if _is_running(cmd) else f"[dim]○[/dim]"
        port_str = f":{port}" if port else ""
        console.print(f"  {icon} {cmd}{port_str}")

    # HTTP endpoints
    console.print("\n[bold]Endpoints HTTP[/bold]")
    async with httpx.AsyncClient(timeout=3.0) as client:
        await _check_http(client, "API",     f"http://localhost:{settings.effective_api_port}/health", ok_icon, fail_icon)
        await _check_http(client, "Gateway", "http://localhost:8001/gateway/health", ok_icon, fail_icon)

    # Database
    console.print("\n[bold]Base de datos[/bold]")
    await _check_db(settings, ok_icon, fail_icon)

    # Redis
    console.print("\n[bold]Redis[/bold]")
    if settings.redis_url:
        await _check_redis(settings.redis_url, ok_icon, fail_icon)
    else:
        console.print(f"  {warn_icon} Redis no configurado — estado solo en RAM")

    console.print()


def _check_env(settings, ok, fail, warn) -> None:
    console.print("[bold]Variables de entorno[/bold]")
    checks = [
        ("DATABASE_URL",      bool(settings.database_url),          True),
        ("TELEGRAM_BOT_TOKEN", bool(settings.telegram_bot_token),   True),
        ("JWT_SECRET_KEY",    bool(settings.jwt_secret_key),         False),
        ("GROQ_API_KEY",      bool(settings.groq_api_key),           False),
        ("MISTRAL_API_KEY",   bool(settings.mistral_api_key),        False),
    ]
    for name, present, required in checks:
        if present:
            console.print(f"  {ok} {name}")
        elif required:
            console.print(f"  {fail} {name} — [red]REQUERIDA[/red]")
        else:
            console.print(f"  [dim]○[/dim] {name} — no configurada")


async def _check_http(client, label: str, url: str, ok: str, fail: str) -> None:
    import httpx
    try:
        r = await client.get(url)
        if r.status_code < 300:
            console.print(f"  {ok} {label} — {r.status_code}")
        else:
            console.print(f"  {fail} {label} — HTTP {r.status_code}")
    except (httpx.ConnectError, httpx.TimeoutException):
        console.print(f"  [dim]○[/dim] {label} — no responde")


async def _check_db(settings, ok: str, fail: str) -> None:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        engine = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        console.print(f"  {ok} PostgreSQL — conecta")
    except Exception as e:
        console.print(f"  {fail} PostgreSQL — {e}")


async def _check_redis(redis_url: str, ok: str, fail: str) -> None:
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        console.print(f"  {ok} Redis — conecta")
    except Exception as e:
        console.print(f"  {fail} Redis — {e}")


# ── interactive menu ────────────────────────────────────────────────────────────

def _prompt_choice(label: str, options: list[str]) -> str:
    import questionary
    return questionary.select(label, choices=options).ask() or options[0]


def _interactive_menu() -> None:
    import questionary
    from questionary import Choice

    running = _running_lines()

    def prefix(cmd: str) -> str:
        return "● " if any(cmd in line for line in running) else "○ "

    cmd_map = {
        "api":     "schoolaiapi",
        "gateway": "schoolai-gateway",
        "bot":     "schoolai-bot",
        "cli":     "schoolai-cli",
    }

    choices = []
    for key, label in _MENU_ITEMS:
        if key in ("start", "stop", "status", "doctor", "update", "salir"):
            choices.append(Choice(title=f"  {label}", value=key))
        else:
            cmd = cmd_map.get(key, key)
            p = prefix(cmd)
            choices.append(Choice(title=f"{p} {label}", value=key))

    console.print("[bold cyan]SchoolAI v2[/bold cyan]")
    selection = questionary.select(
        "¿Qué quieres hacer?",
        choices=choices,
        use_shortcuts=False,
    ).ask()

    if selection is None or selection == "salir":
        return

    _dispatch_key(selection)


def _dispatch_key(key: str) -> None:
    dispatch = {
        "start":   lambda: app.registered_commands,  # llamado abajo
        "stop":    stop,
        "status":  status,
        "doctor":  doctor,
        "update":  update,
        "api":     api,
        "gateway": gateway,
        "bot":     bot,
        "cli":     cli,
        "logs":    lambda: logs(""),
        "debug":   lambda: debug(""),
    }
    fn = dispatch.get(key)
    if fn is None:
        console.print(f"[red]Comando desconocido:[/red] {key}")
        return
    if key == "start":
        start()
    else:
        fn()


# ── entry point ────────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def _callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _interactive_menu()


def main() -> None:
    app()
