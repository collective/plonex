"""Read-only project evidence, shared by terminal, JSON, Markdown, and HTML."""

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from functools import cached_property
from packaging.utils import canonicalize_name
from pathlib import Path
from pip_requirements_parser import RequirementsFile  # type: ignore[import-untyped]
from plonex.base import BaseService
from plonex.inspection import redact_tokens
from plonex.inspection import safe_value
from plonex.presentation import MarkdownTable
from plonex.services.cron.model import JobSet
from plonex.services.cron.runner import JobRunner
from plonex.services.sources import SourcesService
from plonex.services.sources.installation import SourceInstallPlan

import configparser
import json
import shlex

SECTIONS = {
    "overview": "Overview",
    "configuration": "Configuration provenance",
    "profiles": "Profiles",
    "analytics": "Configuration analytics",
    "environment": "Environment",
    "sources": "Source checkouts",
    "dependencies": "Dependencies",
    "services": "Services and templates",
    "runtime": "Runtime health",
    "files": "Project files",
    "jobs": "Scheduled jobs",
    "queue": "Queue monitoring",
    "preparation": "Preparation tasks",
}


@dataclass
class Section:
    key: str
    title: str
    description: str = ""
    columns: tuple[str, ...] = ()
    rows: list[tuple[str, ...]] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def markdown(self, include_details=False):
        parts = [f"## {self.title}", self.description]
        if self.columns:
            parts.append(MarkdownTable(self.columns, self.rows).markdown())
        for detail in self.details if include_details else []:
            parts.extend(
                [
                    f"### {detail['key']}",
                    "```json",
                    json.dumps(detail, indent=2, ensure_ascii=False),
                    "```",
                ]
            )
        parts.extend(f"- [{item['label']}]({item['href']})" for item in self.links)
        parts.extend(f"- {note}" for note in self.notes)
        return "\n\n".join(parts)


class ProjectReport:
    def __init__(self, service):
        self.service = service
        self.target = service.target.absolute()
        self.options = service.options
        self.inventory_error = ""

    def display(self, path):
        path = Path(path)
        try:
            return str(path.relative_to(self.target))
        except ValueError:
            return str(path)

    def link(self, path, label=""):
        path = Path(path).absolute()
        return {"label": label or self.display(path), "href": path.as_uri()}

    @cached_property
    def inspected(self):
        if not self.service.inspect_command:
            return BaseService(
                target=self.target, config_files=self.service.config_files
            )
        from plonex.cli.parser import build_parser
        from plonex.services.invocation import ServiceInvocation

        tokens = self.service.inspect_command
        if tokens[:1] == ["--"]:
            tokens = tokens[1:]
        args = build_parser(target=self.target).parse_args(tokens)
        return ServiceInvocation.from_args(args, self.target).create()

    @cached_property
    def trace(self):
        return self.inspected.configuration_trace

    @cached_property
    def config_files(self):
        self.options
        files = [self.target / path for path in self.service._yaml_resources]
        return list(dict.fromkeys(path.absolute() for path in files if path.is_file()))

    @cached_property
    def dependency_files(self):
        # Loaded profile configuration supplies the actual resolved profile roots.
        roots = [
            self.target,
            *(path.parent.parent for path in reversed(self.config_files)),
        ]
        result = []
        for root in dict.fromkeys(roots):
            for kind in ("requirements", "constraints"):
                directory = root / "etc" / f"{kind}.d"
                if directory.is_dir():
                    result.extend(
                        (kind, path)
                        for path in sorted(directory.iterdir())
                        if path.is_file()
                    )
        return result

    @cached_property
    def inventory(self):
        python = self.target / ".venv" / "bin" / "python"
        if not python.exists():
            self.inventory_error = (
                "Project virtualenv is missing; run dependencies install."
            )
            return []
        script = (
            "import importlib.metadata as m,json\n"
            "rows=[]\n"
            "for d in m.distributions():\n"
            " u=json.loads(d.read_text('direct_url.json') or '{}')\n"
            " rows.append(dict(name=d.metadata.get('Name',''),version=d.version,"
            "source=u.get('url',''),"
            "editable=u.get('dir_info',{}).get('editable',False)))\n"
            "print(json.dumps(rows))\n"
        )
        try:
            output = self.service.execute_command(
                [python, "-c", script], capture_output=True
            )
            rows = json.loads(output)
            for row in rows:
                row["name"] = canonicalize_name(row["name"])
            return sorted(rows, key=lambda row: row["name"])
        except Exception as error:
            self.inventory_error = (
                f"Could not inspect installed packages: {type(error).__name__}"
            )
            return []

    def overview(self):
        installed = {row["name"]: row for row in self.inventory}
        source = SourcesService(target=self.target, cli_options=self.options)
        jobs = JobSet.from_options(self.options)
        python = self.target / ".venv" / "bin" / "python"
        version = "not installed"
        if python.exists():
            version = self.service.execute_command(
                [python, "--version"], capture_output=True
            ).strip()
        return Section(
            "overview",
            SECTIONS["overview"],
            (
                "A snapshot of the current project. Inspection does not "
                "compile configuration, install packages, or start services."
            ),
            ("Fact", "Value"),
            [
                ("Project", str(self.target)),
                ("Python", version),
                (
                    "Configured Plone",
                    str(self.options.get("plone_version", "installation default")),
                ),
                (
                    "Installed Plone",
                    installed.get("plone", {}).get("version", "not installed"),
                ),
                ("Installed distributions", str(len(installed))),
                ("Configured sources", str(len(source.sources))),
                (
                    "Unmanaged checkouts",
                    str(len(source.unmanaged_existing_checkouts())),
                ),
                ("Configuration files", str(len(self.config_files))),
                ("Scheduled jobs", str(sum(job.enabled for job in jobs.jobs))),
            ],
            notes=[self.inventory_error] if self.inventory_error else [],
        )

    def configuration(self):
        data = self.trace.rows(self.service.key)
        if self.service.key and not data:
            raise ValueError(f"Unknown configuration key {self.service.key!r}")
        rows = [
            (
                row["key"],
                self.value(row["value"]),
                self.display_source(row["source"]),
                str(max(0, len(row["history"]) - 1)),
                ", ".join(row["references"]) or "—",
            )
            for row in data
        ]
        return Section(
            "configuration",
            SECTIONS["configuration"],
            f"Effective values for {type(self.inspected).__name__} "
            f"({self.inspected.name}). Definitions are recorded during the "
            "actual merge. Sensitive values are redacted.",
            (
                "Option",
                "Resolved value",
                "Winning definition",
                "Earlier definitions",
                "References",
            ),
            rows,
            details=data,
            links=[
                self.link(path)
                for path in dict.fromkeys(
                    event["source"] for row in data for event in row["history"]
                )
                if Path(path).is_file()
            ],
            notes=[
                "Use --key OPTION to inspect its complete definition history.",
                (
                    "A mapping replacement also replaces its children; use "
                    "+option to extend a mapping/list."
                ),
            ],
        )

    def analytics(self):
        data = self.trace.rows()
        rows = []
        for row in data:
            if len(row["history"]) > 1:
                rows.append(
                    (
                        row["key"],
                        "override chain",
                        " → ".join(
                            self.display_source(event["source"])
                            for event in row["history"]
                        ),
                    )
                )
            if row["references"]:
                rows.append(
                    (row["key"], "derived value", " ← ".join(row["references"]))
                )
            if not row["active"]:
                rows.append((row["key"], "removed", self.display_source(row["source"])))
        counts = {}
        for row in data:
            counts[row["source"]] = counts.get(row["source"], 0) + int(row["active"])
        notes = [
            f"{self.display_source(source)} supplies {count} "
            "effective top-level settings."
            for source, count in sorted(counts.items())
        ]
        notes.append(
            (
                "Jinja references describe configuration dependencies, not "
                "Python import dependencies. Definition order is low to high "
                "precedence."
            )
        )
        return Section(
            "analytics",
            SECTIONS["analytics"],
            (
                "What overrides what, which settings derive from others, and "
                "where effective settings are defined."
            ),
            ("Option", "Relationship", "Definition chain / inputs"),
            rows,
            notes=notes,
        )

    def profiles(self):
        rows, links = [], []
        for folder, declaration in self.service._profile_sources.items():
            path = folder / "etc" / "plonex.yml"
            rows.append(
                (
                    declaration,
                    self.display(folder),
                    self.display(path),
                    "present" if path.exists() else "missing",
                )
            )
            if path.is_file():
                links.append(self.link(path))
        return Section(
            "profiles",
            SECTIONS["profiles"],
            (
                "Resolved profile locations from configuration loading. "
                "Nested profiles apply before their parent; later profiles "
                "override earlier profiles. Per-option provenance shows the "
                "exact effective chain."
            ),
            ("Declaration", "Resolved folder", "Configuration", "State"),
            rows,
            links=links,
        )

    def environment(self):
        rows = []
        values = self.trace.safe_options().get("environment_vars", {})
        if not isinstance(values, dict):
            values = {
                name: "[redacted]" for name in self.options.get("environment_vars", {})
            }
        origins = {
            row["key"]: row["source"] for row in self.trace.rows("environment_vars")
        }
        for name, value in sorted(values.items()):
            rows.append(
                (
                    name,
                    str(value),
                    self.display_source(
                        origins.get(f"environment_vars.{name}", "configuration")
                    ),
                )
            )
        return Section(
            "environment",
            SECTIONS["environment"],
            (
                "Declared child-process environment; inspection does not "
                "export these variables into its own process."
            ),
            ("Variable", "Configured value", "Definition"),
            rows,
        )

    def sources(self):
        service = SourcesService(target=self.target, cli_options=self.options)
        configured = service.configured_checkouts()
        rows = []
        installs = {
            item.source: item
            for item in SourceInstallPlan.from_options(
                self.target, self.options
            ).installations
        }
        entries = [(name, path, True) for name, path in configured.items()]
        entries += [
            (path.name, path, False) for path in service.unmanaged_existing_checkouts()
        ]
        for name, path, managed in sorted(entries):
            settings = service.sources.get(name, {}) if managed else {}
            details = [] if managed else ["unmanaged"]
            repo, branch = settings.get("repo", "—"), settings.get("rev", "main")
            if not path.exists():
                details.append("missing")
            elif not (path / ".git").exists():
                details.append("not a Git checkout")
            else:
                repo = service._git_remote_url(path) or repo
                actual = service._git_current_branch(path)
                if managed and actual and actual != branch:
                    details.append(f"expected {branch}")
                branch = actual or "detached"
                if service._has_modifications(path):
                    details.append("modified")
                if managed and repo != settings.get("repo"):
                    details.append("repository mismatch")
            item = installs.get(name) if managed else None
            rows.append(
                (
                    name,
                    self.display(path),
                    (
                        item.description
                        if item
                        else "checkout only" if managed else "unmanaged"
                    ),
                    str(repo),
                    str(branch),
                    ", ".join(details) or "clean",
                )
            )
        return Section(
            "sources",
            SECTIONS["sources"],
            (
                "Declared and unmanaged checkouts. Installation selection "
                "expresses intent; dependencies shows the installed "
                "environment."
            ),
            (
                "Source",
                "Folder",
                "Install selection",
                "Repository",
                "Revision",
                "Health",
            ),
            rows,
        )

    def dependencies(self):
        from plonex.services.install import normalize_requirement

        rows, links = [], []
        for kind, path in self.dependency_files:
            links.append(self.link(path))
            parsed = RequirementsFile.from_file(str(path), include_nested=False)
            for requirement in parsed.requirements:
                name = (
                    canonicalize_name(requirement.name)
                    if requirement.name
                    else "local/editable"
                )
                rows.append(
                    (
                        name,
                        normalize_requirement(requirement.dumps()),
                        kind,
                        self.display(path),
                    )
                )
        for spec in self.options.get("pip_requirements", []):
            rows.append(
                (
                    "YAML requirement",
                    normalize_requirement(str(spec)),
                    "requirements",
                    "pip_requirements",
                )
            )
        for item in SourceInstallPlan.from_options(
            self.target, self.options
        ).installations:
            rows.append(
                (
                    item.package_name,
                    item.requirement,
                    "selected source",
                    self.display(item.path),
                )
            )
        rows += [
            (
                row["name"],
                row["version"],
                "installed editable" if row["editable"] else "installed",
                row["source"] or "package index",
            )
            for row in self.inventory
        ]
        notes = [
            "Base constraints: "
            + str(
                self.options.get(
                    "plonex_base_constraint",
                    "Plone release constraints for the configured version",
                )
            ),
            (
                "Remote constraints are not downloaded during inspection. "
                "Fragment declarations and installed metadata are shown "
                "separately; this is not a dependency resolver."
            ),
        ]
        if self.inventory_error:
            notes.append(self.inventory_error)
        return Section(
            "dependencies",
            SECTIONS["dependencies"],
            (
                "Requirement and constraint declarations, their files, "
                "selected source projects, and the actual installed "
                "distributions."
            ),
            ("Package", "Specification / version", "Kind", "Origin"),
            rows,
            links=links,
            notes=notes,
        )

    def services(self):
        rows = []
        for spec in self.options.get("services", []):
            for name, declaration in spec.items():
                declaration = declaration or {}
                rows.append(
                    (
                        name,
                        self.value(declaration.get("run_for", "all commands")),
                        str(
                            declaration.get(
                                "source_path", declaration.get("source", "—")
                            )
                        ),
                        str(
                            declaration.get(
                                "target_path", declaration.get("target", "—")
                            )
                        ),
                    )
                )
        folder = self.target / "tmp" / "supervisor" / "etc" / "supervisor"
        for path in sorted(folder.glob("*.conf")):
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(path)
            for section in parser.sections():
                if section.startswith("program:"):
                    command = parser.get(section, "command", fallback="")
                    rows.append(
                        (
                            section,
                            "Supervisor",
                            shlex.join(redact_tokens(shlex.split(command))),
                            self.display(path),
                        )
                    )
        return Section(
            "services",
            SECTIONS["services"],
            (
                "Configuration helper triggers and their generated files, "
                "followed by existing Supervisor programs. Service "
                "identities and run_for hooks use their configuration names."
            ),
            (
                "Service / program",
                "Triggered by",
                "Template / command",
                "Produces / config",
            ),
            rows,
            notes=["No Supervisor processes are started or restarted by this report."],
        )

    def files(self):
        candidates = [*self.config_files, *(path for _, path in self.dependency_files)]
        candidates += [
            self.service.var_folder / name
            for name in (
                "plonex.yml",
                "gitman.yml",
                "requirements.txt",
                "constraints.txt",
                "compiled-requirements.txt",
            )
        ]
        candidates += sorted((self.target / "tmp").glob("**/*.conf"))
        candidates += sorted((self.target / "tmp").glob("**/*.ini"))
        latest = max((path.stat().st_mtime_ns for path in self.config_files), default=0)
        rows, links = [], []
        for path in dict.fromkeys(candidates):
            if path.is_file():
                stat = path.stat()
                state = (
                    "newer configuration exists"
                    if path not in self.config_files
                    and path not in [p for _, p in self.dependency_files]
                    and stat.st_mtime_ns < latest
                    else "present"
                )
                modified = datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(timespec="seconds")
                rows.append((self.display(path), state, str(stat.st_size), modified))
                links.append(self.link(path))
            else:
                rows.append((self.display(path), "not generated", "—", "—"))
        return Section(
            "files",
            SECTIONS["files"],
            (
                "Inputs and generated artifacts, with file links and "
                "freshness evidence. Times are UTC."
            ),
            ("File", "State", "Bytes", "Modified"),
            rows,
            links=links,
        )

    def runtime(self):
        status = self.service.supervisor_status
        rows = []
        for line in status.splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[1] in {
                "RUNNING",
                "STOPPED",
                "STARTING",
                "STOPPING",
                "BACKOFF",
                "EXITED",
                "FATAL",
                "UNKNOWN",
            }:
                rows.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
            elif line.strip():
                rows.append(("Supervisor", "unavailable", line))
        return Section(
            "runtime",
            SECTIONS["runtime"],
            (
                "Live status from the existing Supervisor configuration. No "
                "runtime files are rendered and no processes are started."
            ),
            ("Program", "State", "Details"),
            rows,
        )

    def jobs(self):
        runner = JobRunner(self.service)
        rows = []
        for job in JobSet.from_options(self.options).jobs:
            history = runner.history(job.name, 1)
            rows.append(
                (
                    job.name,
                    job.schedule,
                    job.timezone,
                    "enabled" if job.enabled else "manual only",
                    job.callable or shlex.join(redact_tokens(list(job.command))),
                    job.user or "OS account",
                    history[0]["status"] if history else "never run",
                )
            )
        links = [
            self.link(row["log"], f"{row['job']}: {row['started']} ({row['status']})")
            for row in runner.history(limit=20)
        ]
        return Section(
            "jobs",
            SECTIONS["jobs"],
            (
                "Huey schedules, explicit execution identities, and "
                "persisted results. Plone callables run through a dedicated "
                "ZEO client, without HTTP passwords or CSRF exemptions."
            ),
            ("Job", "Schedule", "Timezone", "State", "Action", "User", "Last result"),
            rows,
            links=links,
            notes=[
                (
                    "Run a job manually with plonex cron run NAME. Restart the "
                    "daemon after changing job definitions."
                )
            ],
        )

    def preparation(self):
        from plonex.files import read_only
        from plonex.preparation.supervisor import SupervisorPreparation

        try:
            with read_only():
                preparation = SupervisorPreparation(self.target)
                plan = preparation.plan()
        except (ValueError, OSError) as error:
            return Section(
                "preparation",
                SECTIONS["preparation"],
                "Preparation cannot be planned until this configuration "
                "issue is resolved.",
                ("Task", "State", "Reason"),
                [("supervisor.ready", "blocked", str(error))],
            )
        return Section(
            "preparation",
            SECTIONS["preparation"],
            "Supervisor startup prerequisites, content-based freshness, and "
            "affected services. No preparation tasks are executed.",
            ("Task", "State", "Reason", "Prerequisites", "Affected services"),
            [
                (
                    entry["task"],
                    entry["state"],
                    "; ".join(entry["reasons"]) or "current",
                    ", ".join(entry["requires"]),
                    ", ".join(entry["affected"]),
                )
                for entry in plan
            ],
            notes=[
                "Use plonex supervisor start --plan for a preview. Current files "
                "do not establish that running processes have loaded them."
            ],
        )

    def queue(self):
        from plonex.files import read_only
        from plonex.services.cron import CronService

        with read_only():
            service = CronService(
                target=self.target, config_files=self.service.config_files
            )
            configured = bool(service.options.get("cron_jobs"))
            exists = (service.var_folder / "cron/queue.sqlite3").is_file()
        if not configured and not exists:
            return Section(
                "queue", SECTIONS["queue"], notes=["No project jobs are configured."]
            )
        try:
            payload = service.invoke_runtime("status")
        except ValueError as error:
            return Section("queue", SECTIONS["queue"], notes=[str(error)])
        queue, stats = payload["queue"], payload["statistics"]
        rows = [
            (
                "Worker",
                "Consumer",
                "running" if payload["worker"]["running"] else "stopped",
                str(payload["worker"].get("pid", "")),
            ),
            ("Queue", "Pending", str(queue["pending_count"]), ""),
            ("Queue", "Scheduled", str(queue["scheduled_count"]), ""),
            (
                "Statistics",
                "Recorded in flight",
                str(len(stats["inflight"])),
                "Last observed task execution state",
            ),
        ]
        for job in stats["tasks"]:
            rows.append(
                (
                    "Job",
                    job["job"],
                    f"{job['completed']} completed; {job['errors']} errors",
                    f"{job['retries']} retries",
                )
            )
        for group in ("pending", "scheduled"):
            for task in queue[group]:
                state = "revoked" if task["revoked"] else group
                rows.append(("Task", task["job"], state, task["task_id"]))
        return Section(
            "queue",
            SECTIONS["queue"],
            "Live queue depths and Huey execution statistics "
            "from the target virtualenv.",
            ("Area", "Name", "State / count", "Details"),
            rows,
            notes=[
                "Use plonex cron inspect TASK_ID for attempts and events. "
                "Queued revocation does not stop a running process."
            ],
        )

    @staticmethod
    def value(value):
        return json.dumps(safe_value(value), ensure_ascii=False, default=str)

    def display_source(self, source):
        return self.display(source) if source.startswith("/") else source

    def build(self):
        selected = (
            list(SECTIONS) if self.service.section == "all" else [self.service.section]
        )
        if any(name not in SECTIONS for name in selected):
            raise ValueError(f"Unknown description section: {self.service.section}")
        sections = [getattr(self, name)() for name in selected]
        return {
            "title": f"Plonex · {self.target.name}",
            "target": str(self.target),
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "section": self.service.section,
            "sections": [asdict(section) for section in sections],
            "markdown": "# Project description\n\n"
            + "\n\n".join(
                section.markdown(bool(self.service.key)) for section in sections
            ),
        }
