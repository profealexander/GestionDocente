"""schoolai — dispatcher de comandos SchoolAI v2."""
from __future__ import annotations

import sys

from rich.console import Console
from rich.table import Table

console = Console()

HELP_TEXT = """[bold cyan]SchoolAI v2[/bold cyan] — comandos disponibles

[bold]Servicios[/bold]
  [green]schoolai[/green]          Arranca el Gateway hub central (puerto 8001)
                    Recibe Telegram webhook, CLI y WebSocket
  [green]schoolaiapi[/green]       Arranca la REST API (puerto 8000)
                    CRUD para la PWA SvelteKit

[bold]Canales[/bold]
  [green]schoolai-cli[/green]      Chat interactivo en terminal (requiere gateway)
  [green]schoolai-bot[/green]      Bot Telegram "Libre" (docentes)
  [green]schoolai-bot-jornada[/green]  Bot Telegram "Jornada" (vista del día)
  [green]schoolai-bot-agente[/green]   Bot Telegram "Agente" (LLM orchestrator)

[bold]Aliases dentro de schoolai[/bold]
  [green]schoolai help[/green]     Muestra este mensaje
  [green]schoolai api[/green]      Arranca la REST API (alias de schoolaiapi)
  [green]schoolai cli[/green]      Abre el chat CLI (alias de schoolai-cli)
  [green]schoolai bot[/green]      Arranca el bot Libre (alias de schoolai-bot)

[bold]Stack mínimo para usar el sistema[/bold]
  1. PostgreSQL (Docker — arranca automático)
  2. [green]schoolai[/green]       Gateway
  3. [green]schoolaiapi[/green]    API  (si usas la PWA)

[bold]Ejemplo rápido[/bold]
  schoolai &
  schoolaiapi &
  schoolai-cli
"""


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        console.print(HELP_TEXT)
        return

    cmd = args[0]

    if cmd == "api":
        from schoolai.api.runner import run
        run()

    elif cmd == "cli":
        from schoolai.cli.main import run
        run()

    elif cmd == "bot":
        from schoolai.bot.main import run
        run()

    elif cmd == "start":
        _start_gateway()

    else:
        console.print(f"[red]Comando desconocido:[/red] {cmd}")
        console.print("Usa [bold]schoolai help[/bold] para ver los comandos disponibles.")
        sys.exit(1)


def _start_gateway() -> None:
    from schoolai.gateway.runner import run
    run()
