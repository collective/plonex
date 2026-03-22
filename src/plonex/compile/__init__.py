from dataclasses import dataclass
from plonex.base import BaseService
from plonex.sources import SourcesService
from yaml import dump


@dataclass(kw_only=True)
class CompileService(BaseService):
    """Service for compiling the configuration files in to a var files"""

    name: str = "compile"

    def __post_init__(self) -> None:
        """Ensure that we have everything we need to run the compile service"""
        self.var_folder = self._ensure_dir(self.target / "var")
        self.target_file = self.var_folder / "plonex.yml"

    def run(self) -> None:
        """Compile the configuration files in to a var files"""
        self.logger.info(f"Compiling configuration files in to {self.target_file}")
        self.target_file.write_text(dump(self.options, sort_keys=True))
        with SourcesService(target=self.target) as gitman_service:
            gitman_file = gitman_service.compile_config()
        if gitman_file is not None:
            self.logger.info(f"Compiling gitman configuration in to {gitman_file}")
