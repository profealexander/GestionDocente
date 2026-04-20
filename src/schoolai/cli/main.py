"""
SchoolAI CLI — chat con el Agent Runtime vía HTTP al Gateway.

Uso:
    uv run schoolai-cli
    uv run schoolai-cli --user 5494482378
"""
from __future__ import annotations

import asyncio
import sys

import httpx
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from schoolai.config import settings
from schoolai.gateway.session import get_session_id

console = Console()

DOMAIN_COLOR = {
    "attendance": "green",
    "homework": "blue",
    "cuotas": "yellow",
    "reports": "magenta",
    "web_search": "cyan",
    "general": "white",
}


async def chat_loop(user_id: str) -> None:
    session_id = get_session_id(user_id, "cli")
    base_url = settings.gateway_url

    console.print(Panel(
        f"[bold]SchoolAI CLI[/bold] — Agent Runtime v2\n"
        f"Gateway: [dim]{base_url}[/dim]  |  Escribe [bold]salir[/bold] para terminar.",
        border_style="blue",
    ))

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Health check
        try:
            r = await client.get(f"{base_url}/gateway/health")
            if r.status_code != 200:
                console.print("[red]Gateway no responde. ¿Está corriendo schoolai-gateway?[/red]")
                return
        except httpx.ConnectError:
            console.print("[red]No se puede conectar al gateway en[/red] "
                          f"[bold]{base_url}[/bold]\n"
                          "Ejecuta: [bold cyan]uv run schoolai-gateway[/bold cyan]")
            return

        console.print("[dim]Conectado al gateway.[/dim]\n")

        while True:
            try:
                text = Prompt.ask("[bold cyan]>[/bold cyan]")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Hasta luego.[/dim]")
                break

            if text.strip().lower() in ("salir", "exit", "quit"):
                console.print("[dim]Hasta luego.[/dim]")
                break

            if not text.strip():
                continue

            with console.status("[dim]Procesando...[/dim]", spinner="dots"):
                try:
                    resp = await client.post(
                        f"{base_url}/gateway/message",
                        json={
                            "channel": "cli",
                            "user_id": user_id,
                            "session_id": session_id,
                            "text": text,
                        },
                    )
                    data = resp.json()
                except httpx.HTTPError as e:
                    console.print(f"[red]Error HTTP:[/red] {e}")
                    continue

            if "error" in data:
                console.print(f"[red]{data['error']}[/red]")
                continue

            domain = data.get("domain", "general")
            color = DOMAIN_COLOR.get(domain, "white")
            tag = Text(f" {domain} ", style=f"bold {color} on {color}4")

            console.print()
            console.print(Panel(
                Markdown(data["text"]),
                title=tag,
                border_style=color,
                padding=(0, 1),
            ))
            console.print()


def run() -> None:
    user_id = "5494482378"
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--user" and i + 1 < len(sys.argv) - 1:
            user_id = sys.argv[i + 2]

    asyncio.run(chat_loop(user_id))


if __name__ == "__main__":
    run()
