from dataclasses import dataclass
from importlib.metadata import version
from plonex.base import BaseService
from plonex.template import TemplateService

import requests


@dataclass(kw_only=True)
class InitService(BaseService):
    """This context manager starts up the project with a minimal configuration"""

    name: str = "init"
    target: str = "."
    plone_version: str = ""

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
                        options={
                            "plonex_version": version("plonex"),
                        },
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
                if not self.plone_version:
                    self.plone_version = self.ask_for_value(
                        "Please select the Plone version", "6.0-latest"
                    )
                self.logger.info(
                    "Fetching the constraints.txt file for Plone %s", self.plone_version
                )

                self.pre_services.append(
                    TemplateService(
                        name="constraints",
                        source_path="resource://plonex.init.templates:default_constraints.txt.j2",  # noqa: E501
                        target_path=etc_folder / "constraints.d" / "000-plonex.txt",
                        options={
                            "constraints": requests.get(
                                f"https://dist.plone.org/release/{self.plone_version}/constraints.txt"  # noqa: E501
                            ).text,
                        },
                    )
                )
