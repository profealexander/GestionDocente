"""Entrypoint para el bot Modo Jornada (TELEGRAM_BOT_TOKEN_JORNADA)."""

from schoolai.bot.main import run


def run_dev() -> None:
    run(dev=True)


if __name__ == "__main__":
    run_dev()
