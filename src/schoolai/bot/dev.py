"""Development runner with auto-reload on file changes."""

from watchfiles import run_process


def run() -> None:
    run_process(
        "src/schoolai",
        target="python -m schoolai.bot.main",
        target_type="command",
    )


if __name__ == "__main__":
    run()
