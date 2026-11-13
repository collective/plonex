"""Install the project worker from the CLI's matching release."""

from importlib.metadata import distribution
from pathlib import Path
from urllib.parse import unquote
from urllib.parse import urlparse

import json

PROTOCOL_VERSION = 1
WORKER_REQUIREMENTS = ("huey[stats]>=3.5,<4",)


def runtime_source() -> Path | None:
    metadata = json.loads(distribution("plonex").read_text("direct_url.json") or "{}")
    url = urlparse(metadata.get("url", ""))
    if metadata.get("dir_info", {}).get("editable") and url.scheme == "file":
        source = Path(unquote(url.path))
        if source.is_dir():
            return source
    return None


def runtime_requirement() -> str:
    source = runtime_source()
    if source is not None:
        return f"-e {source.as_uri()}"
    return f"plonex=={distribution('plonex').version}"


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
