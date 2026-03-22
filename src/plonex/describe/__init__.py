from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from pathlib import Path
from plonex.base import BaseService
from plonex.compile import CompileService
from plonex.install import InstallService
from plonex.supervisor import Supervisor
from plonex.template import TemplateService
from rich.console import Console
from rich.markdown import Markdown


@dataclass(kw_only=True)
class DescribeService(BaseService):
    """This context manager describes the current project configuration"""

    name: str = "describe"

    describe_template: str = (
        "resource://plonex.describe.templates:plonex_description.md.j2"
    )
    var_folder: Path = field(init=False)
    describe_folder: Path = field(init=False)

    def __post_init__(self):
        self.var_folder = self._ensure_dir(self.target / "var")
        self.describe_folder = self._ensure_dir(self.var_folder / "plonex_description")

    @property
    def description_path(self) -> Path:
        return self.describe_folder / "index.md"

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
        return self.execute_command([self.python_executable, "--version"]).strip()

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
    def project_files(self) -> list[tuple[str, Path]]:
        files = [
            ("Source configuration", self.target / "etc" / "plonex.yml"),
            ("Source requirements", self.target / "etc" / "requirements.d"),
            ("Source constraints", self.target / "etc" / "constraints.d"),
            ("Compiled configuration", self.var_folder / "plonex.yml"),
            ("Compiled requirements", self.var_folder / "requirements.txt"),
            ("Compiled constraints", self.var_folder / "constraints.txt"),
            (
                "Supervisor configuration",
                self.target / "tmp" / "supervisor" / "etc" / "supervisord.conf",
            ),
            ("Markdown description", self.description_path),
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
        with InstallService(target=self.target) as install_service:
            return sorted(install_service.developed_packages_and_paths())

    @property
    def supervisor_status(self) -> str:
        """Return the status of the supervisor as a string"""
        with Supervisor(target=self.target) as supervisor:
            return supervisor.get_status()

    def _compile_project_files(self) -> None:
        with InstallService(target=self.target):
            pass
        with CompileService(target=self.target) as compile_service:
            compile_service.run()

    def _render_description(self) -> None:
        with TemplateService(
            source_path=self.describe_template,
            target_path=self.description_path,
            options={"context": self},
        ) as template_service:
            template_service.run()

    def run(self):
        self._compile_project_files()
        self._render_description()
        console = Console()
        markdown = Markdown(self.description_path.read_text())
        console.print(markdown)
