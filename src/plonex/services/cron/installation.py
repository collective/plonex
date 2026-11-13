"""Requirements and command for the project job worker."""

from pathlib import Path

PROTOCOL_VERSION = 1
WORKER_REQUIREMENTS = ("huey[stats]>=3.5,<4",)


def runtime_requirement() -> str:
    return "plonex"


def runtime_command(target: Path, configs=()) -> list[str]:
    command = [
        str(target / ".venv/bin/python"),
        "-I",
        "-B",
        "-m",
        "plonex.services.cron.runtime",
        "--target",
        str(target),
    ]
    for config in configs:
        command.extend(["--config", str(Path(config).absolute())])
    return command
