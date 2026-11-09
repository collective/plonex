"""Service configuration reports, shared by previews and startup snapshots."""

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import fields
from pathlib import Path
from plonex.presentation import MarkdownTable
from rich.console import Console
from tempfile import NamedTemporaryFile
from typing import Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plonex.base import BaseService

import json
import os
import re
import shlex

_SENSITIVE = re.compile(
    r"password|passwd|secret|token|api[_-]?key|authorization|cookie", re.I
)


def _redact_url(value: str) -> str:
    value = re.sub(r"(://[^/:\s]+:)[^@\s]+@", r"\1[redacted]@", value)
    value = re.sub(r"(https?://)[^/@\s]+@", r"\1[redacted]@", value)
    return re.sub(
        r"([?&#](?:_authenticator|access_token|api[_-]?key|token|password)=)[^&#\s]*",
        r"\1[redacted]",
        value,
        flags=re.IGNORECASE,
    )


def redact_tokens(tokens: list[str]) -> list[str]:
    result = list(tokens)
    hide_next = False
    for index, token in enumerate(tokens):
        if hide_next:
            result[index] = "[redacted]"
            hide_next = False
        elif token.startswith("--") and _SENSITIVE.search(token.partition("=")[0]):
            if "=" in token:
                result[index] = token.partition("=")[0] + "=[redacted]"
            else:
                hide_next = True
        elif token == "--user" or (
            token == "-u" and tokens and Path(tokens[0]).name in {"curl", "wget"}
        ):
            hide_next = True
        elif token.startswith("--user="):
            result[index] = "--user=[redacted]"
        elif token in {"-H", "--header"} and index + 1 < len(tokens):
            if _SENSITIVE.search(tokens[index + 1].partition(":")[0]):
                hide_next = True
        elif token in {"adduser", "add-user"} and index + 2 < len(tokens):
            result[index + 2] = "[redacted]"
    return [_redact_url(token) for token in result]


def safe_value(value: Any, key: str = "") -> Any:
    if _SENSITIVE.search(key):
        return "[redacted]"
    if isinstance(value, dict):
        if key == "aliases":
            return {
                str(name): shlex.join(
                    redact_tokens(
                        shlex.split(command) if isinstance(command, str) else command
                    )
                )
                for name, command in value.items()
            }
        return {str(name): safe_value(item, str(name)) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        items = (
            redact_tokens(list(value))
            if all(isinstance(item, str) for item in value)
            else value
        )
        return [safe_value(item) for item in items]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return _redact_url(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


@dataclass(frozen=True)
class ServiceSnapshot:
    service: str
    name: str
    target: str
    arguments: dict[str, Any]
    options: dict[str, Any]
    configuration_files: list[str]

    @classmethod
    def capture(
        cls, service: "BaseService", *, parameters: dict | None = None
    ) -> "ServiceSnapshot":
        service.options
        excluded = {"target", "name", "cli_options", "config_files", "options"}
        arguments = {
            item.name: getattr(service, item.name)
            for item in fields(service)
            if item.init and item.name not in excluded
        }
        if parameters:
            arguments["command"] = parameters
        sources = list(
            dict.fromkeys(
                [
                    *service._yaml_resources,
                    *(str(Path(path).absolute()) for path in service.config_files),
                ]
            )
        )
        return cls(
            type(service).__name__,
            service.name,
            str(service.target),
            safe_value(arguments),
            service.configuration_trace.safe_options(),
            sources,
        )

    def write(self, path: Path) -> None:
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(asdict(self), handle, indent=2)
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def read(cls, path: Path) -> "ServiceSnapshot":
        try:
            snapshot = cls(**json.loads(path.read_text()))
        except TypeError as exc:
            raise ValueError(f"Invalid service snapshot: {path}") from exc
        if not (
            all(
                isinstance(value, str)
                for value in (snapshot.service, snapshot.name, snapshot.target)
            )
            and isinstance(snapshot.arguments, dict)
            and isinstance(snapshot.options, dict)
            and isinstance(snapshot.configuration_files, list)
            and all(isinstance(value, str) for value in snapshot.configuration_files)
        ):
            raise ValueError(f"Invalid service snapshot: {path}")
        return snapshot

    @staticmethod
    def rows(values: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
        rows = []
        for name, value in sorted(values.items()):
            key = f"{prefix}.{name}" if prefix else name
            if isinstance(value, dict) and value:
                rows.extend(ServiceSnapshot.rows(value, key))
            else:
                rows.append(
                    (key, value if isinstance(value, str) else json.dumps(value))
                )
        return rows

    def show(self, console: Console | None = None, *, markdown: bool = False) -> None:
        console = console or Console()
        console.print(
            f"{self.name} ({self.service}) — {self.target}",
            markup=False,
            highlight=False,
            soft_wrap=markdown,
        )
        if self.configuration_files:
            console.print(
                "Configuration: " + ", ".join(self.configuration_files),
                markup=False,
                highlight=False,
                soft_wrap=markdown,
            )
        for title, values in (
            ("Service arguments", self.arguments),
            ("Resolved options", self.options),
        ):
            MarkdownTable(("Option", "Value"), self.rows(values), title).show(
                console, markdown=markdown
            )


def record_service_snapshot(service: "BaseService") -> None:
    """Called at the normal lifecycle boundary, before environment/pre-services."""
    path = os.environ.get("PLONEX_JOB_SNAPSHOT")
    if not path:
        return
    identity = f"{type(service).__module__}.{type(service).__qualname__}"
    if identity != os.environ.get("PLONEX_JOB_SERVICE"):
        return
    if service.name != os.environ.get("PLONEX_JOB_NAME"):
        return
    ServiceSnapshot.capture(service, parameters=service._invocation_parameters).write(
        Path(path)
    )
