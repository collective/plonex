from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from pathlib import Path
from plonex.base import BaseService
from plonex.install import InstallService
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
        self.pre_services = [
            TemplateService(
                source_path=self.describe_template,
                target_path=self.describe_folder / "index.md",
                options={"context": self},
            ),
        ]

    @property
    def now(self):
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def developed_packages(self) -> list[str]:
        """Return a list of developed packages"""
        with InstallService() as install_service:
            return sorted(install_service.developed_packages_and_paths())

    def run(self):
        # Use rich to describe info about this project
        console = Console()
        markdown = Markdown(
            (self.var_folder / "plonex_description" / "index.md").read_text()
        )
        console.print(markdown)
