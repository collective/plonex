from dataclasses import dataclass
from importlib.metadata import version
from plonex.base import BaseService
from plonex.install import InstallService
from plonex.supervisor import Supervisor
from plonex.template import TemplateService
from typing import ClassVar

import requests
import subprocess


@dataclass(kw_only=True)
class InitService(BaseService):
    """This context manager starts up the project with a minimal configuration"""

    name: str = "init"
    options_defaults: ClassVar[dict] = {
        "plonex_version": version("plonex"),
        "plone_version": "6.1-latest",
    }

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
            if not (self.target / "etc" / "constraints.d" / "000-plonex.txt").exists():
                self.logger.info(
                    "Fetching the constraints.txt file for Plone %s",
                    self.options["plone_version"],
                )

                self.pre_services.append(
                    TemplateService(
                        name="constraints",
                        source_path="resource://plonex.init.templates:default_constraints.txt.j2",  # noqa: E501
                        target_path=etc_folder / "constraints.d" / "000-plonex.txt",
                        options={
                            "constraints": requests.get(
                                f"https://dist.plone.org/release/{self.options['plone_version']}/constraints.txt"  # noqa: E501
                            ).text,
                        },
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
                "\n".join(
                    (
                        "/.venv",
                        "/tmp",
                        "/var",
                    )
                )
                + "\n"
            )
            self.logger.debug("Initializing a .gitignore file")
        git_repo = self.target / ".git"
        if not git_repo.exists():
            self.logger.debug("Initializing a git repository")
            subprocess.run(["git", "init", self.target], cwd=self.target, check=True)
            subprocess.run(["git", "add", self.target], cwd=self.target, check=True)
            subprocess.run(
                ["git", "commit", "-m", "plonex init"], cwd=self.target, check=True
            )
