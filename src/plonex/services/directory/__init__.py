from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService


@dataclass(kw_only=True)
class DirectoryService(BaseService):
    """Service for managing directories"""

    name: str = "directory"
    path: Path = field(default_factory=Path)
    mode: int | None = None

    @BaseService.entered_only
    def run(self) -> None:
        """Manage the directories"""
        self.logger.info("Ensuring that %s exists", self.path)
        self._ensure_dir(self.path)
        if self.mode is not None:
            self.path.chmod(self.mode)
