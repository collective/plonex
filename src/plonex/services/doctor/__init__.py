"""Read-only diagnostics for a configured Plone project."""

from collections import Counter
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from jinja2 import TemplateError
from packaging.requirements import InvalidRequirement
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion
from packaging.version import Version
from pathlib import Path
from plonex.base import BaseService
from plonex.files import read_only
from plonex.inspection import safe_value
from rich.console import Console
from rich.table import Table
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlparse

import errno
import json
import os
import shutil
import socket
import subprocess
import yaml


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    summary: str
    detail: str = ""
    remedy: str = ""


@dataclass(kw_only=True)
class Doctor(BaseService):
    """Collect independent evidence without preparing or modifying the project."""

    name: str = "doctor"
    findings: list[Finding] = field(default_factory=list, init=False)
    service: Any = field(default=None, init=False)
    inventory: dict[str, dict] | None = field(default=None, init=False)
    marker_environment: dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self):
        self.target = self.target.absolute()

    def add(self, code, severity, summary, detail="", remedy=""):
        self.findings.append(Finding(code, severity, summary, detail, remedy))

    def configuration(self):
        from plonex import logger
        from plonex.services.install import InstallService

        valid = True
        for path in sorted((self.target / "etc").glob("plonex*.yml")):
            try:
                data = yaml.safe_load(path.read_text())
                if data is not None and not isinstance(data, dict):
                    raise ValueError("The YAML document must be a mapping")
            except (OSError, ValueError, yaml.YAMLError) as error:
                mark = getattr(error, "problem_mark", None)
                location = f" line {mark.line + 1}" if mark else ""
                self.add(
                    "configuration.invalid",
                    "error",
                    "Invalid configuration file",
                    f"{path}{location}",
                    "Correct the YAML mapping and retry.",
                )
                valid = False
        if not valid:
            return

        class DiagnosticLogger:
            def __init__(self):
                self.messages: list[str] = []

            def error(self, message, *args, **kwargs):
                self.messages.append(message % args if args else message)

            def __getattr__(self, name):
                return getattr(logger, name)

        errors = DiagnosticLogger()
        try:
            service = InstallService(target=self.target, dont_ask=True)
            service.logger = errors
            service.options
            for message in errors.messages:
                self.add(
                    "configuration.invalid",
                    "error",
                    "Invalid configuration",
                    message,
                    "Review the reported option in your configuration.",
                )
            if errors.messages:
                return
            self.service = service
            self.add("configuration.loaded", "ok", "Configuration loaded")
        except (ValueError, OSError, yaml.YAMLError, TemplateError) as error:
            if isinstance(error, yaml.YAMLError):
                mark = getattr(error, "problem_mark", None)
                detail = (
                    f"Invalid YAML in {mark.name}, line {mark.line + 1}"
                    if mark
                    else "Invalid YAML in a profile or configuration file"
                )
            else:
                detail = str(error)
            self.add(
                "configuration.unavailable",
                "error",
                "Cannot load configuration",
                detail,
                "Correct the configuration or resolve the profile, then retry.",
            )

    def environment(self):
        python = self.target / ".venv/bin/python"
        if not python.is_file():
            self.add(
                "environment.missing",
                "error",
                "Project Python is missing",
                str(python),
                "Run plonex dependencies install.",
            )
            return
        script = """
import importlib.metadata as m, json, os, platform, sys
from pathlib import Path
rows = []
for d in m.distributions():
    try:
        url = json.loads(d.read_text("direct_url.json") or "{}")
    except (ValueError, OSError):
        url = {}
    rows.append({"name": d.metadata.get("Name", ""), "version": d.version,
                 "url": url.get("url", ""),
                 "editable": url.get("dir_info", {}).get("editable", False),
                 "requires": d.requires or []})
env = {"implementation_name": sys.implementation.name,
       "implementation_version": platform.python_version(),
       "os_name": os.name, "platform_machine": platform.machine(),
       "platform_release": platform.release(), "platform_system": platform.system(),
       "platform_version": platform.version(),
       "platform_python_implementation": platform.python_implementation(),
       "python_full_version": platform.python_version(),
       "python_version": ".".join(map(str, sys.version_info[:2])),
       "sys_platform": sys.platform}
print(json.dumps({"prefix": sys.prefix,
                  "base": getattr(sys, "_base_executable", sys.executable),
                  "version": platform.python_version(), "marker_environment": env,
                  "distributions": rows}))
"""
        try:
            result = subprocess.run(
                [str(python), "-I", "-B", "-c", script],
                cwd=self.target,
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            data = json.loads(result.stdout)
            if Path(data["prefix"]).resolve() != (self.target / ".venv").resolve():
                raise ValueError(
                    "Interpreter prefix does not match the project virtualenv"
                )
            self.marker_environment = data["marker_environment"]
            self.inventory = {
                canonicalize_name(row["name"]): row
                for row in data["distributions"]
                if row["name"]
            }
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            subprocess.SubprocessError,
        ) as error:
            self.add(
                "environment.unusable",
                "error",
                "Cannot inspect project Python",
                str(error),
                "Repair the project virtualenv and run plonex dependencies install.",
            )
            return
        self.add(
            "environment.python",
            "ok",
            "Project Python is usable",
            f"{python} (Python {data['version']})",
        )
        if self.service:
            configured = self.service.options.get("python")
            if configured:
                located = shutil.which(str(configured))
                if located is None:
                    self.add(
                        "environment.configured_python_missing",
                        "warning",
                        "Configured Python cannot be found",
                        str(configured),
                        "Install it or update the python option.",
                    )
                elif Path(located).resolve() != Path(data["base"]).resolve():
                    self.add(
                        "environment.python_mismatch",
                        "warning",
                        "Configured Python differs from the virtualenv interpreter",
                        f"Configured: {located}; virtualenv base: {data['base']}",
                        "Verify the intended interpreter before recreating "
                        "the virtualenv.",
                    )
        for binary in ("uv", "runwsgi", "runzeo", "zconsole", "supervisorctl"):
            executable = self.target / ".venv/bin" / binary
            if not executable.is_file() or not os.access(executable, os.X_OK):
                self.add(
                    "environment.binary_missing",
                    "warning",
                    f"{binary} is missing",
                    "Expected in .venv/bin.",
                    "Run plonex dependencies install if this tool is required.",
                )

    def requirements(self):
        if not self.service or self.inventory is None:
            return
        requirements = [
            "supervisor",
            "zeo",
            "rich",
            "plone",
            *self.service.options.get("pip_requirements", []),
        ]
        missing: set[str] = set()
        for raw in requirements:
            try:
                requirement = Requirement(raw)
            except InvalidRequirement:
                continue  # Files, editable entries and resolver options need uv.
            if requirement.marker and not requirement.marker.evaluate(
                self.marker_environment
            ):
                continue
            name = canonicalize_name(requirement.name)
            installed = self.inventory.get(name)
            if installed is None:
                if name in missing:
                    continue
                missing.add(name)
                self.add(
                    "requirements.missing",
                    "warning",
                    f"{name} is not installed",
                    "A direct project requirement is missing.",
                    "Run plonex dependencies install.",
                )
            elif requirement.specifier:
                try:
                    matches = Version(installed["version"]) in requirement.specifier
                except InvalidVersion:
                    matches = False
                if not matches:
                    self.add(
                        "requirements.version",
                        "warning",
                        f"{name} has an incompatible version",
                        f"Installed {installed['version']}; "
                        f"requested {requirement.specifier}.",
                        "Review the requirement and run plonex dependencies install.",
                    )

    def sources(self):
        if not self.service:
            return
        try:
            plan = self.service.source_install_plan
        except (ValueError, TypeError, AttributeError) as error:
            self.add(
                "sources.invalid",
                "error",
                "Invalid source selection",
                str(error),
                "Review sources in your project configuration.",
            )
            return
        names: set[str] = set()
        for source in plan.installations:
            if not source.path.is_dir():
                self.add(
                    "sources.missing",
                    "error",
                    f"Selected source {source.source} is missing",
                    str(source.path),
                    "Run plonex sources clone and check path and subdirectory.",
                )
                continue
            if not any(
                (source.path / name).is_file()
                for name in ("pyproject.toml", "setup.py")
            ):
                self.add(
                    "sources.not_project",
                    "error",
                    f"{source.source} is not a Python project",
                    str(source.path),
                    "Set the correct subdirectory or disable installation.",
                )
                continue
            try:
                name = source.package_name
            except (ValueError, OSError, SyntaxError) as error:
                self.add(
                    "sources.metadata",
                    "error",
                    f"Cannot read {source.source} metadata",
                    str(error),
                    "Correct the source project metadata.",
                )
                continue
            if name in names:
                self.add(
                    "sources.duplicate",
                    "error",
                    f"Multiple sources provide {name}",
                    "",
                    "Select only one checkout for this distribution.",
                )
                continue
            names.add(name)
            if self.inventory is None:
                continue
            installed = self.inventory.get(name)
            if installed is None:
                self.add(
                    "sources.not_installed",
                    "warning",
                    f"{name} is not installed",
                    f"Selected source: {source.path}",
                    "Run plonex dependencies install.",
                )
                continue
            url = urlparse(installed.get("url", ""))
            actual = Path(unquote(url.path)).resolve() if url.scheme == "file" else None
            if (
                actual != source.path.resolve()
                or bool(installed.get("editable")) != source.editable
            ):
                expected_mode = "editable" if source.editable else "regular"
                actual_mode = "editable" if installed.get("editable") else "regular"
                self.add(
                    "sources.installation_mismatch",
                    "warning",
                    f"{name} is installed from a different source "
                    "or in a different mode",
                    f"Expected {source.path} ({expected_mode}); "
                    f"installed {actual or 'index/unknown'} ({actual_mode}).",
                    "Run plonex dependencies install and inspect its output.",
                )
            # Python distribution metadata does not record which extras were requested.
            if source.extras:
                self.add(
                    "sources.extras_unverified",
                    "info",
                    f"Extras for {name} cannot be verified",
                    f"Requested: {', '.join(source.extras)}; "
                    "installed metadata does not record the selection.",
                )
                for raw in installed.get("requires", []):
                    try:
                        requirement = Requirement(raw)
                    except InvalidRequirement:
                        continue
                    if not requirement.marker or "extra" not in str(requirement.marker):
                        continue
                    if not any(
                        requirement.marker.evaluate(
                            self.marker_environment | {"extra": extra}
                        )
                        for extra in source.extras
                    ):
                        continue
                    dependency = canonicalize_name(requirement.name)
                    present = self.inventory.get(dependency)
                    try:
                        satisfied = present is not None and (
                            not requirement.specifier
                            or requirement.specifier.contains(
                                present["version"], prereleases=True
                            )
                        )
                    except InvalidVersion:
                        satisfied = False
                    if not satisfied:
                        self.add(
                            "sources.extra_dependency",
                            "warning",
                            f"An extra dependency of {name} is missing or incompatible",
                            str(requirement),
                            "Run plonex dependencies install.",
                        )

    def constraints(self):
        if not self.service:
            return
        from plonex.preparation.dependencies import ConstraintCache

        try:
            source = self.service.plonex_base_constraint
            if not source:
                return
            if self.service._is_remote_requirement_source(source):
                parsed = urlparse(str(source))
                if parsed.hostname == "github.com" and "/blob/" in parsed.path:
                    self.add(
                        "constraints.github_html",
                        "error",
                        "Constraint URL points to a GitHub HTML page",
                        str(source),
                        "Use the raw file URL for plonex_base_constraint.",
                    )
                path = ConstraintCache(
                    self.service.var_folder / "cache/constraints"
                ).path(str(source))
                if not path.is_file():
                    self.add(
                        "constraints.uncached",
                        "info",
                        "Remote constraints have not been cached",
                        "Doctor does not download the URL.",
                        "Run plonex dependencies install to fetch and validate them.",
                    )
                    return
            else:
                path = Path(source)
                if not path.is_file():
                    self.add(
                        "constraints.missing",
                        "error",
                        "Base constraints file is missing",
                        str(path),
                        "Correct plonex_base_constraint.",
                    )
                    return
            prefix = path.read_bytes()[:4096].lstrip().lower()
            if prefix.startswith((b"<!doctype html", b"<html")):
                self.add(
                    "constraints.html",
                    "error",
                    "Base constraints contain HTML",
                    str(path),
                    "Use a raw constraints text file and refresh dependencies.",
                )
            else:
                self.add(
                    "constraints.available",
                    "ok",
                    "Base constraints are available",
                    "The existing file was inspected; nested inputs and "
                    "resolution are not verified.",
                )
        except (ValueError, OSError, TypeError) as error:
            self.add(
                "constraints.invalid",
                "error",
                "Cannot inspect base constraints",
                str(error),
                "Review plonex_base_constraint.",
            )

    def preparation(self):
        if not self.service:
            return
        from plonex.preparation.supervisor import SupervisorPreparation

        try:
            plan = SupervisorPreparation(self.target).plan()
        except (ValueError, OSError, TypeError) as error:
            self.add(
                "preparation.blocked",
                "warning",
                "Cannot preview Supervisor preparation",
                str(error),
                "Review the configuration and run plonex supervisor start --plan.",
            )
            return
        stale = [
            entry
            for entry in plan
            if entry["state"] == "stale"
            and entry["reasons"] != ["explicit operation; always evaluated"]
        ]
        if stale:
            names = "\n".join(
                f"{entry['task']}: {entry['reasons'][0]}"
                for entry in stale[:8]
                if entry["reasons"]
            )
            if len(stale) > 8:
                names += f"\n... and {len(stale) - 8} more tasks"
            self.add(
                "preparation.stale",
                "warning",
                "Supervisor preparation needs attention",
                names,
                "Run plonex supervisor start --plan to inspect the reasons.",
            )
        elif any(entry["state"] != "current" for entry in plan):
            self.add(
                "preparation.conditional",
                "info",
                "Preparation includes always-run tasks",
                "Dependent outputs will be checked after those tasks run.",
                "Run plonex supervisor start --plan for details.",
            )
        else:
            self.add("preparation.current", "ok", "Supervisor preparation is current")

    def installed_constraints(self):
        if not self.service or self.inventory is None:
            return
        path = self.service.var_folder / "constraints.txt"
        if not path.is_file():
            return
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")) or "\\" in line:
                continue
            try:
                requirement = Requirement(line.split(" #", 1)[0])
            except InvalidRequirement:
                continue
            if requirement.marker and not requirement.marker.evaluate(
                self.marker_environment
            ):
                continue
            name = canonicalize_name(requirement.name)
            installed = self.inventory.get(name)
            if not installed or not requirement.specifier:
                continue
            try:
                valid = requirement.specifier.contains(
                    installed["version"], prereleases=True
                )
            except InvalidVersion:
                valid = False
            if not valid:
                self.add(
                    "constraints.installed_version",
                    "warning",
                    f"Installed {name} does not satisfy a generated constraint",
                    f"Installed {installed['version']}; "
                    f"constraint {requirement.specifier} in {path}.",
                    "Review the constraint and run plonex dependencies install.",
                )

    def zeo(self):
        if not self.service:
            return
        from plonex.services.zeoserver import ZeoServer

        # The ZEO service may have its own plonex-zeoserver.yml overrides.
        address = ZeoServer(target=self.target).options["zeo_address"]
        address = str(address)
        if "://" in address:
            self.add("zeo.unchecked", "info", "ZEO address was not checked", address)
            return
        if ":" in address and not address.startswith("/"):
            host, _, port = address.rpartition(":")
            host = host.strip("[]")
            if host not in {"localhost", "127.0.0.1", "::1"} or not port.isdigit():
                self.add(
                    "zeo.unchecked",
                    "info",
                    "Non-local ZEO address was not checked",
                    address,
                )
                return
            family = socket.AF_INET6 if ":" in host else socket.AF_INET
            endpoint = ("127.0.0.1" if host == "localhost" else host, int(port))
        else:
            family = socket.AF_UNIX
            path = Path(address)
            endpoint = str(path if path.is_absolute() else self.target / path)
        try:
            with socket.socket(family, socket.SOCK_STREAM) as connection:
                connection.settimeout(0.5)
                connection.connect(endpoint)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EPERM}:
                self.add(
                    "zeo.unchecked",
                    "warning",
                    "ZEO connectivity could not be checked",
                    "The operating system denied the connection attempt.",
                    "Check ZEO from an environment permitted to connect.",
                )
                return
            self.add(
                "zeo.unreachable",
                "warning",
                "ZEO is not reachable",
                address,
                "Start the configured ZEO service if it should be running.",
            )
        except OverflowError:
            self.add(
                "zeo.invalid",
                "error",
                "Invalid ZEO port",
                address,
                "Correct zeo_address in the configuration.",
            )
        else:
            self.add(
                "zeo.reachable",
                "ok",
                "ZEO endpoint accepts connections",
                address,
                "This checks connectivity, not database health.",
            )

    def supervisor(self):
        config = self.target / "tmp/supervisor/etc/supervisord.conf"
        control = self.target / ".venv/bin/supervisorctl"
        if not config.is_file() or not control.is_file():
            self.add(
                "supervisor.unavailable",
                "info",
                "Supervisor status is unavailable",
                "Its generated configuration or supervisorctl is missing.",
            )
            return
        try:
            process = subprocess.run(
                [str(control), "-c", str(config), "status"],
                cwd=self.target,
                capture_output=True,
                text=True,
                timeout=5,
                env=dict(os.environ) | {"PYTHONDONTWRITEBYTECODE": "1"},
            )
        except (OSError, subprocess.TimeoutExpired):
            self.add(
                "supervisor.unavailable",
                "warning",
                "Cannot inspect Supervisor status",
                "The status command failed or timed out.",
                "Run plonex supervisor status.",
            )
            return
        if process.returncode not in (0, 3):
            self.add(
                "supervisor.unavailable",
                "warning",
                "Supervisor status could not be read",
                "Its status command did not succeed; the daemon or connection "
                "may be unavailable.",
                "Run plonex supervisor status.",
            )
            return
        for line in process.stdout.splitlines():
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            name, state = parts[:2]
            if state in {"BACKOFF", "FATAL", "EXITED", "UNKNOWN"}:
                self.add(
                    "supervisor.failed",
                    "warning",
                    f"Supervisor program {name}: {state}",
                    "",
                    "Inspect the program logs and configuration.",
                )
            elif state in {"STOPPED", "STOPPING"}:
                self.add(
                    "supervisor.stopped", "info", f"Supervisor program {name}: {state}"
                )
        self.add("supervisor.checked", "ok", "Supervisor status checked")

    def run(self, *, output_format="terminal"):
        self.findings.clear()
        self.service = None
        self.inventory = None
        self.marker_environment.clear()
        with read_only():
            for check in (
                self.configuration,
                self.environment,
                self.requirements,
                self.sources,
                self.constraints,
                self.installed_constraints,
                self.preparation,
                self.zeo,
                self.supervisor,
            ):
                try:
                    check()
                except Exception as error:
                    self.logger.debug(
                        "Doctor check %s failed", check.__name__, exc_info=True
                    )
                    self.add(
                        "check.failed",
                        "error",
                        f"Could not complete {check.__name__} check",
                        type(error).__name__,
                        "Review the project configuration and retry.",
                    )
        summary = Counter(finding.severity for finding in self.findings)
        payload = {
            "target": str(self.target),
            "summary": {
                key: summary[key] for key in ("error", "warning", "info", "ok")
            },
            "findings": [safe_value(asdict(finding)) for finding in self.findings],
        }
        console = Console()
        if output_format == "json":
            console.print(
                json.dumps(payload, indent=2, ensure_ascii=False),
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        else:
            table = Table(title="Project doctor", show_lines=True)
            for name in ("Status", "Finding", "Details and next step"):
                table.add_column(name)
            for item in payload["findings"]:
                detail = "\n".join(filter(None, (item["detail"], item["remedy"])))
                table.add_row(item["severity"].upper(), item["summary"], detail)
            console.print(table, markup=False, highlight=False)
            console.print(
                f"{summary['error']} errors · {summary['warning']} warnings · "
                f"{summary['ok']} checks passed"
            )
        return payload
