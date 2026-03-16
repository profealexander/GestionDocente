"""Entrypoint para el bot de pruebas (token dev)."""

from schoolai.bot.main import run


def run_dev() -> None:
    run(dev=True)


if __name__ == "__main__":
    run_dev()
