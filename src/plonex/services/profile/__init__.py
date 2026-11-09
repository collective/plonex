from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from plonex.base import BaseService
from plonex.files import is_read_only
from plonex.files import project_lock
from urllib.parse import urlparse

import hashlib
import shutil
import tempfile


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
        # Stable paths make profile fragments reproducible across commands.
        # Plans reuse existing snapshots and never perform network operations.
        key = hashlib.sha256(str(self.source).encode()).hexdigest()
        cache = self.target / "var/cache/profiles"
        checkout = cache / key
        if checkout.is_dir():
            return checkout
        if is_read_only():
            raise ValueError(
                "Remote profile is not cached. Run 'plonex project compile' "
                "first, or configure a local profile checkout."
            )
        with project_lock(cache):
            if checkout.is_dir():
                return checkout
            staging = Path(tempfile.mkdtemp(dir=cache))
            try:
                clone_target = staging / "checkout"
                self.logger.info("Cloning remote profile into the project cache")
                self.execute_command(
                    ["git", "clone", "--depth", "1", str(self.source), clone_target]
                )
                clone_target.replace(checkout)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        return checkout

    @cached_property
    def source_path(self) -> Path:
        if self.is_remote_source:
            return self._clone_remote_source()
        return self._resolve_local_source()
