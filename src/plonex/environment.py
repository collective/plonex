"""Load project environment defaults without executing shell code."""

from pathlib import Path

import os
import re
import shlex

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def load_project_environment(target: Path) -> None:
    """Load project defaults, preserving variables already in the environment."""
    assignments: dict[str, str] = {}
    for filename in (".env", ".env.local"):
        path = target / filename
        if path.exists():
            assignments.update(_read_environment_file(path))
    for name, value in assignments.items():
        os.environ.setdefault(name, value)


def _read_environment_file(path: Path) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not _NAME.fullmatch(name):
            raise ValueError(f"Invalid environment assignment in {path}:{number}")
        try:
            lexer = shlex.shlex(value, posix=True)
            lexer.whitespace_split = True
            lexer.commenters = "#"
            parts = list(lexer)
        except ValueError as exc:
            raise ValueError(
                f"Invalid environment value in {path}:{number}: {exc}"
            ) from exc
        if len(parts) > 1:
            raise ValueError(f"Quote values containing whitespace in {path}:{number}")
        assignments[name] = parts[0] if parts else ""
    return assignments
