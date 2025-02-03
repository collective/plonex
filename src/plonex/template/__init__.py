from dataclasses import dataclass
from dataclasses import field
from importlib import resources
from jinja2 import Environment
from jinja2 import StrictUndefined
from pathlib import Path
from plonex.base import BaseService


@dataclass(kw_only=True)
class TemplateService(BaseService):

    name: str = ""
    source_path: Path | str
    target_path: Path | str | None = None
    options: dict = field(default_factory=dict)
    mode: int = 0o600
    target: Path = field(default_factory=Path.cwd)

    @staticmethod
    def default_environment():
        return Environment(
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    environment: Environment = field(default_factory=default_environment)

    def __post_init__(self):
        if isinstance(self.source_path, str) and self.source_path.startswith(
            "resource://"
        ):
            source_path = self.source_path.partition("resource://")[2]
            package, filename_path = source_path.partition(":")[::2]
            package_files = resources.files(package)
            self.source_path = package_files / filename_path

        self.source_path = Path(self.source_path).absolute()
        if not self.source_path.exists():
            raise FileNotFoundError(f"Template {self.source_path} does not exist")

        if not self.name:
            self.name = self.source_path.stem

        if self.target_path is not None:
            self.target_path = Path(self.target_path).absolute()
            self.target = self._ensure_dir(self.target.absolute())

    def run(self):
        """Render the template"""
        if not self.target_path.parent.exists():
            self.target_path.parent.mkdir(parents=True)

        self.target_path.write_text(self.render_template())
        self.target_path.chmod(self.mode)

        relative_source_path = (
            self.source_path.relative_to(self.source)
            if self.source_path in self.source_path.parents
            else self.source_path
        )
        relative_target_path = (
            self.target_path.relative_to(self.target)
            if self.target in self.target_path.parents
            else self.target_path
        )
        self.logger.debug(
            "Rendered template %s -> %s",
            relative_source_path,
            relative_target_path,
        )

    def render_template(self):
        """Just render the template and return the result"""
        template = self.environment.from_string(self.source_path.read_text())
        return template.render(options=self.options, keep_trailing_newline=True)
