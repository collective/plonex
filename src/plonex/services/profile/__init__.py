from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from plonex.base import BaseService
from urllib.parse import urlparse


@dataclass(kw_only=True)
class ProfileService(BaseService):
    """Resolve a local or remote profile folder."""

    name: str = "profile"
    source: Path | str

    @property
    def is_remote_source(self) -> bool:
        if isinstance(self.source, Path):
            return False

        parsed = urlparse(self.source)
        return parsed.scheme in {
            "git",
            "http",
            "https",
            "ssh",
        } or self.source.startswith("git@")

    def _resolve_local_source(self) -> Path:
        source_path = Path(self.source).expanduser().absolute()
        if not source_path.exists():
            raise FileNotFoundError(f"Profile {source_path} does not exist")
        if not source_path.is_dir():
            raise ValueError(f"Profile {source_path} is not a directory")
        return source_path

    def _clone_remote_source(self) -> Path:
        clone_target = self.mkdtemp()
        self.logger.info("Cloning profile %s", self.source)
        self.execute_command(
            ["git", "clone", "--depth", "1", str(self.source), clone_target]
        )
        return clone_target

    @cached_property
    def source_path(self) -> Path:
        if self.is_remote_source:
            return self._clone_remote_source()
        return self._resolve_local_source()
