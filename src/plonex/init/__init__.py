from dataclasses import dataclass
from functools import cached_property
from importlib.metadata import version
from pathlib import Path
from plonex.base import BaseService
from plonex.install import InstallService
from plonex.supervisor import Supervisor
from plonex.template import TemplateService
from textwrap import dedent


@dataclass(kw_only=True)
class InitService(BaseService):
    """This context manager starts up the project with a minimal configuration"""

    name: str = "init"

    @cached_property
    def options_defaults(self) -> dict:
        options_defaults = super().options_defaults
        options_defaults.update(
            {
                "plonex_version": version("plonex"),
                "plone_version": "6.1-latest",
            }
        )
        return options_defaults

    def __post_init__(self):
        self.target = self._ensure_dir(self.target)

        if not self.pre_services:
            self.pre_services = []

            etc_folder = self.target / "etc"

            if not (self.target / "etc" / "plonex.yml").exists():
                self.pre_services.append(
                    TemplateService(
                        name="plonex",
                        source_path="resource://plonex.init.templates:plonex.yml.j2",
                        target_path=etc_folder / "plonex.yml",
                        options=self.options,
                    )
                )
            has_local_default_requirements = (
                etc_folder / "requirements.d" / "000-plonex.txt"
            ).exists()
            has_profile_default_requirements = (
                self._profile_default_requirements_path() is not None
            )
            if (
                not has_local_default_requirements
                and not has_profile_default_requirements
            ):
                self.pre_services.append(
                    TemplateService(
                        name="requirements",
                        source_path="resource://plonex.init.templates:default_requirements.txt.j2",  # noqa: E501
                        target_path=etc_folder / "requirements.d" / "000-plonex.txt",
                    )
                )

    def _collect_profile_roots(
        self,
        profile: str | Path,
        relative_to: Path,
        seen: set[Path],
    ) -> list[Path]:
        from plonex.profile import ProfileService

        resolved_profile = self._resolve_profile_source(profile, relative_to)
        profile_service = ProfileService(source=resolved_profile, target=self.target)
        profile_root = profile_service.source_path.resolve()

        if profile_root in seen:
            return []
        seen.add(profile_root)

        roots: list[Path] = []
        profile_plonex_yml = profile_root / "etc" / "plonex.yml"
        if profile_plonex_yml.exists():
            raw_profile_options = self._load_yaml_mapping(profile_plonex_yml)
            nested_profiles = self._normalize_profiles(
                raw_profile_options.get("profiles"),
                profile_plonex_yml,
            )
            for nested_profile in nested_profiles:
                roots.extend(
                    self._collect_profile_roots(nested_profile, profile_root, seen)
                )

        roots.append(profile_root)
        return roots

    @cached_property
    def profile_roots(self) -> list[Path]:
        plonex_yml = self.target / "etc" / "plonex.yml"
        if not plonex_yml.exists():
            return []

        raw_local = self._load_yaml_mapping(plonex_yml)
        raw_profiles = self._normalize_profiles(raw_local.get("profiles"), plonex_yml)
        seen: set[Path] = set()
        roots: list[Path] = []
        for profile in raw_profiles:
            roots.extend(self._collect_profile_roots(profile, self.target, seen))
        return roots

    def _profile_default_requirements_path(self) -> Path | None:
        for root in self.profile_roots:
            candidate = root / "etc" / "requirements.d" / "000-plonex.txt"
            if candidate.exists():
                return candidate
        return None

    def run(self):
        """Run the init command"""
        with InstallService(target=self.target) as install:
            install.run(save_constraints=True)
        with Supervisor(target=self.target) as supervisor:
            supervisor.initialize_configuration()
        self.logger.info("Project initialized in %s", self.target)
        gitignore = self.target / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                dedent(
                    """\
                    /.venv
                    /tmp
                    /var
                    """
                )
            )
            self.logger.debug("Initializing a .gitignore file")
        git_repo = self.target / ".git"
        if not git_repo.exists():
            self.logger.debug("Initializing a git repository")
            self.execute_command(["git", "init", self.target], cwd=self.target)
            self.execute_command(["git", "add", self.target], cwd=self.target)
            self.execute_command(
                ["git", "commit", "-m", "plonex init"], cwd=self.target
            )
