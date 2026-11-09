"""Run explicitly configured test commands for selected source projects."""

from pathlib import Path
from plonex.files import read_only
from plonex.services.install import InstallService
from plonex.services.sources.installation import SourceInstallPlan

import os
import subprocess


def run_selected_tests(target, tokens):
    target = Path(target).absolute()
    tokens = list(tokens)
    if "--" in tokens:
        index = tokens.index("--")
        names, extra = tokens[:index], tokens[index + 1 :]  # noqa: E203
    else:
        names, extra = tokens, []
    with read_only():
        service = InstallService(target=target, dont_ask=True)
        options = service.options
        selected = {
            item.source: item for item in service.source_install_plan.installations
        }
        declarations = options.get("sources", {})
        if not names:
            names = [
                name for name in selected if declarations[name].get("test_command")
            ]
        if not names:
            raise ValueError("No selected sources have a test_command configured.")
        jobs = []
        for name in names:
            if name not in selected:
                raise ValueError(f"Source {name!r} is not selected for installation.")
            item = selected[name]
            SourceInstallPlan((item,)).validate()
            command = declarations[name].get("test_command")
            if (
                not isinstance(command, list)
                or not command
                or not all(
                    isinstance(part, str) and part and "\0" not in part
                    for part in command
                )
            ):
                raise ValueError(
                    f"Source {name!r}: test_command must be a non-empty argv list."
                )
            jobs.append((name, item.path, [*command, *extra]))
    python = target / ".venv/bin/python"
    if not python.is_file():
        raise ValueError("Project Python is missing. Run plonex dependencies install.")
    environment = dict(os.environ)
    environment["VIRTUAL_ENV"] = str(target / ".venv")
    environment["PATH"] = (
        str(target / ".venv/bin") + os.pathsep + environment.get("PATH", "")
    )
    environment.update(
        {
            str(key): value.format(**options) if isinstance(value, str) else str(value)
            for key, value in options.get("environment_vars", {}).items()
        }
    )
    for name, path, command in jobs:
        print(f"Testing {name}", flush=True)
        result = subprocess.run(command, cwd=path, env=environment).returncode
        if result:
            return result
    return 0
