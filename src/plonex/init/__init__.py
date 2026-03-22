from dataclasses import dataclass
from functools import cached_property
from importlib.metadata import version
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
            if not (etc_folder / "requirements.d" / "000-plonex.txt").exists():
                self.pre_services.append(
                    TemplateService(
                        name="requirements",
                        source_path="resource://plonex.init.templates:default_requirements.txt.j2",  # noqa: E501
                        target_path=etc_folder / "requirements.d" / "000-plonex.txt",
                    )
                )

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
