from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from pathlib import Path
from plonex.base import BaseService
from plonex.services.install import InstallService
from plonex.services.sources import SourcesService
from plonex.services.template import TemplateService
from rich.console import Console
from rich.markdown import Markdown

import sh  # type: ignore[import-untyped]
import webbrowser


@dataclass(kw_only=True)
class DescribeService(BaseService):
    """This context manager describes the current project configuration"""

    name: str = "describe"

    describe_template: str = (
        "resource://plonex.services.describe.templates:plonex_description.md.j2"
    )
    generate_html: bool = False
    browse_html: bool = False
    section: str = "all"
    output_format: str = "terminal"
    key: str = ""
    inspect_command: list[str] = field(default_factory=list)

    @property
    def describe_folder(self) -> Path:
        return self._ensure_dir(self.var_folder / "plonex_description")

    @property
    def description_path(self) -> Path:
        return self.describe_folder / f"{self.report_stem}.md"

    @property
    def description_html_path(self) -> Path:
        return self.describe_folder / f"{self.report_stem}.html"

    @property
    def report_stem(self):
        from .report import SECTIONS

        if self.section != "all" and self.section not in SECTIONS:
            raise ValueError(f"Unknown description section: {self.section}")
        return "index" if self.section == "all" else self.section

    def display_path(self, path: str | Path) -> str:
        path = Path(path)
        try:
            return path.relative_to(self.target).as_posix()
        except ValueError:
            return str(path)

    def display_source(self, source: str | Path | None) -> str:
        if source is None:
            return ""
        if isinstance(source, Path):
            return self.display_path(source)
        if source.startswith(("http://", "https://", "resource://")):
            return source
        source_path = Path(source)
        if source_path.is_absolute():
            return self.display_path(source_path)
        return source

    @property
    def plone_version(self) -> str:
        return str(self.options.get("plone_version", ""))

    @property
    def python_executable(self) -> Path:
        return self.virtualenv_dir / "bin" / "python"

    @property
    def python_version(self) -> str:
        return self.execute_command(
            [self.python_executable, "--version"], capture_output=True
        ).strip()

    @property
    def base_constraint(self) -> str:
        install_service = InstallService(target=self.target)
        return self.display_source(install_service.plonex_base_constraint)

    @property
    def profiles(self) -> list[str]:
        profiles = self.options.get("profiles") or []
        if isinstance(profiles, str):
            profiles = [profiles]
        return (
            [str(profile) for profile in profiles] if isinstance(profiles, list) else []
        )

    @property
    def additional_config_files(self) -> list[Path]:
        return sorted(self.additional_plonex_options)

    @property
    def explicit_config_files(self) -> list[Path]:
        return sorted(self.config_files_options_mapping)

    @property
    def requirement_fragments(self) -> list[Path]:
        folder = self.target / "etc" / "requirements.d"
        return sorted(folder.iterdir()) if folder.exists() else []

    @property
    def constraint_fragments(self) -> list[Path]:
        folder = self.target / "etc" / "constraints.d"
        return sorted(folder.iterdir()) if folder.exists() else []

    @property
    def configured_services(self) -> list[str]:
        services = self.options.get("services") or []
        names = []
        if isinstance(services, list):
            for spec in services:
                if isinstance(spec, dict) and len(spec) == 1:
                    names.append(str(next(iter(spec))))
        return names

    @property
    def supervisor_configuration_status(self) -> str:
        supervisor_conf = (
            self.target / "tmp" / "supervisor" / "etc" / "supervisord.conf"
        )
        return "present" if supervisor_conf.exists() else "missing"

    @property
    def supervisor_graceful_interval(self) -> float:
        value = self.options.get("supervisor_graceful_interval", 1.0)
        return float(value)

    @property
    def sources_options(self) -> dict:
        sources = self.options.get("sources")
        return sources if isinstance(sources, dict) else {}

    @property
    def sources_count(self) -> int:
        return len(self.sources_options)

    @property
    def compiled_gitman_file(self) -> Path:
        return self.var_folder / "gitman.yml"

    @property
    def sources_status_rows(self) -> list[tuple[str, str, str, str, str]]:
        """Return sources status rows for the markdown report table.

        Columns are: source, folder, repo_url, health_symbol, details
        """
        service = SourcesService(target=self.target)
        rows: list[tuple[str, str, str, str, str]] = []

        for source_name, path in sorted(service.configured_checkouts().items()):
            source_options = service.sources.get(source_name)
            configured_repo = None
            configured_rev = None
            if isinstance(source_options, dict):
                configured_repo = source_options.get("repo")
                configured_rev = source_options.get("rev")

            detected_repo = None
            details: list[str] = []
            health_symbol = "✓"

            if not path.exists():
                health_symbol = "✗"
                details.append("missing")
            elif not (path / ".git").exists():
                health_symbol = "⚠"
                details.append("not-git")
            else:
                detected_repo = service._git_remote_url(path)
                branch = service._git_current_branch(path)
                if service._has_modifications(path):
                    health_symbol = "⚠"
                    details.append("modified")

                if branch:
                    details.append(f"branch:{branch}")
                    if (
                        isinstance(configured_rev, str)
                        and configured_rev
                        and configured_rev != branch
                    ):
                        details.append(f"expected:{configured_rev}")
                else:
                    details.append("detached")

                if (
                    isinstance(configured_repo, str)
                    and configured_repo
                    and detected_repo
                    and configured_repo != detected_repo
                ):
                    health_symbol = "✗"
                    details.append("repo-mismatch")

            repo_url = (
                detected_repo
                or (configured_repo if isinstance(configured_repo, str) else None)
                or "-"
            )
            rows.append(
                (
                    source_name,
                    self.display_path(path),
                    repo_url,
                    health_symbol,
                    ", ".join(details) if details else "-",
                )
            )
        return rows

    @property
    def project_files(self) -> list[tuple[str, Path]]:
        files = [
            ("Source configuration", self.target / "etc" / "plonex.yml"),
            ("Source requirements", self.target / "etc" / "requirements.d"),
            ("Source constraints", self.target / "etc" / "constraints.d"),
            ("Compiled configuration", self.var_folder / "plonex.yml"),
            ("Compiled sources (gitman.yml)", self.compiled_gitman_file),
            ("Compiled requirements", self.var_folder / "requirements.txt"),
            ("Compiled constraints", self.var_folder / "constraints.txt"),
            (
                "Supervisor configuration",
                self.target / "tmp" / "supervisor" / "etc" / "supervisord.conf",
            ),
            ("Markdown description", self.description_path),
            ("HTML description", self.description_html_path),
        ]
        files.extend(
            (f"Requirement fragment {path.name}", path)
            for path in self.requirement_fragments
        )
        files.extend(
            (f"Constraint fragment {path.name}", path)
            for path in self.constraint_fragments
        )
        return files

    @property
    def project_file_groups(
        self,
    ) -> list[tuple[str, list[tuple[str, Path, list[tuple[str, Path]]]]]]:
        return [
            (
                "Source Files",
                [
                    (
                        "Requirements directory",
                        self.target / "etc" / "requirements.d",
                        [(path.name, path) for path in self.requirement_fragments],
                    ),
                    (
                        "Constraints directory",
                        self.target / "etc" / "constraints.d",
                        [(path.name, path) for path in self.constraint_fragments],
                    ),
                    ("Configuration", self.target / "etc" / "plonex.yml", []),
                ],
            ),
            (
                "Compiled Files",
                [
                    ("Compiled configuration", self.var_folder / "plonex.yml", []),
                    (
                        "Compiled sources (gitman.yml)",
                        self.compiled_gitman_file,
                        [],
                    ),
                    ("Compiled requirements", self.var_folder / "requirements.txt", []),
                    ("Compiled constraints", self.var_folder / "constraints.txt", []),
                ],
            ),
            (
                "Runtime Files",
                [
                    (
                        "Supervisor configuration",
                        self.target / "tmp" / "supervisor" / "etc" / "supervisord.conf",
                        [],
                    ),
                ],
            ),
            (
                "Reports",
                [
                    ("Markdown description", self.description_path, []),
                    ("HTML description", self.description_html_path, []),
                ],
            ),
        ]

    @property
    def now(self):
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def developed_packages(self) -> list[str]:
        """Return a list of developed packages"""
        return sorted(InstallService(target=self.target).developed_packages_and_paths())

    @property
    def supervisor_status(self) -> str:
        """Inspect the existing daemon without rendering or entering services."""
        configuration = self.target / "tmp" / "supervisor" / "etc" / "supervisord.conf"
        control = self.target / ".venv" / "bin" / "supervisorctl"
        if not configuration.is_file():
            return "Supervisor is not configured"
        if not control.exists():
            return "supervisorctl is not installed"
        try:
            return self.execute_command(
                [control, "-c", configuration, "status"], capture_output=True
            ).strip()
        except sh.ErrorReturnCode as error:
            if error.exit_code == 3 and error.stdout:
                return error.stdout.decode(errors="replace").strip()
            diagnostic = (
                (error.stderr or error.stdout or b"").decode(errors="replace").strip()
            )
            return f"Supervisor status unavailable (exit {error.exit_code})" + (
                f": {diagnostic}" if diagnostic else ""
            )

    def _render_description(self) -> None:
        TemplateService(
            source_path=self.describe_template,
            target_path=self.description_path,
            options={"context": self},
        ).run()

    def run(self):
        from .report import ProjectReport
        from importlib import resources
        from jinja2 import Environment
        from plonex.inspection import safe_value

        import json

        report = safe_value(ProjectReport(self).build())
        self.description_path.write_text(report["markdown"])
        if (
            self.describe_template
            != type(self).__dataclass_fields__["describe_template"].default
        ):
            self._render_description()
            report["markdown"] = self.description_path.read_text()
        json_path = self.describe_folder / f"{self.report_stem}.json"
        json_path.write_text(
            json.dumps(
                {key: value for key, value in report.items() if key != "markdown"},
                indent=2,
                ensure_ascii=False,
            )
        )
        template = (
            resources.files("plonex.services.describe.templates")
            .joinpath("report.html.j2")
            .read_text()
        )
        html = (
            Environment(autoescape=True)
            .from_string(template)
            .render(
                report=report,
                markdown_file=self.description_path.name,
                json_file=json_path.name,
            )
        )
        self.description_html_path.write_text(html)
        for path in (self.description_path, json_path, self.description_html_path):
            path.chmod(0o600)
        console = Console()
        if self.output_format == "json":
            console.print(
                json_path.read_text(), markup=False, highlight=False, soft_wrap=True
            )
        elif self.output_format == "html":
            console.print(
                self.description_html_path.absolute().as_uri(),
                markup=False,
                soft_wrap=True,
            )
        elif self.output_format == "markdown":
            console.print(
                report["markdown"], markup=False, highlight=False, soft_wrap=True
            )
        else:
            console.print(Markdown(report["markdown"]))
        if self.browse_html:
            webbrowser.open(self.description_html_path.resolve().as_uri())

    def __enter__(self):
        # Inspection must not export environment variables or run helper services.
        self.options
        self._entered = True
        if self._invocation_parameters is not None:
            from plonex.inspection import record_service_snapshot

            record_service_snapshot(self)
        return self
