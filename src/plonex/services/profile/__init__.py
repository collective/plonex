from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from plonex.base import BaseService
from plonex.files import is_read_only
from plonex.files import project_lock
from urllib.parse import urlparse

import hashlib
import json
import shutil
import tempfile


@dataclass(kw_only=True)
class ProfileService(BaseService):
    """Resolve a local or remote profile folder."""

    name: str = "profile"
    source: Path | str | dict

    @property
    def is_remote_source(self) -> bool:
        if isinstance(self.source, dict):
            return True
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
        if isinstance(self.source, dict):
            raise ValueError("A profile mapping must reference a Git repository")
        source_path = Path(self.source).expanduser().absolute()
        if not source_path.exists():
            raise FileNotFoundError(f"Profile {source_path} does not exist")
        if not source_path.is_dir():
            raise ValueError(f"Profile {source_path} is not a directory")
        return source_path

    def _clone_remote_source(self) -> Path:
        # Stable paths make profile fragments reproducible across commands.
        # Plans reuse existing snapshots and never perform network operations.
        source = self.source
        if isinstance(source, dict):
            repo = source["repo"]
            ref = source.get("ref")
            cache_identity = json.dumps([repo, ref], separators=(",", ":"))
        else:
            repo = str(source)
            ref = None
            cache_identity = repo
        key = hashlib.sha256(cache_identity.encode()).hexdigest()
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
                if ref:
                    self.execute_command(
                        ["git", "clone", "--no-checkout", "--", repo, clone_target]
                    )
                    self.execute_command(
                        ["git", "fetch", "origin", ref], cwd=clone_target
                    )
                    self.execute_command(
                        ["git", "checkout", "--detach", "FETCH_HEAD"], cwd=clone_target
                    )
                else:
                    self.execute_command(
                        ["git", "clone", "--depth", "1", "--", repo, clone_target]
                    )
                clone_target.replace(checkout)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        return checkout

    @cached_property
    def source_path(self) -> Path:
        if isinstance(self.source, dict):
            source = self.source
            if set(source) - {"repo", "ref", "path"}:
                raise ValueError("Profile mapping supports only repo, ref, and path.")
            repo = source.get("repo")
            ref = source.get("ref")
            path = source.get("path", ".")
            if not isinstance(repo, str) or not repo.strip():
                raise ValueError("Profile repo must be a non-empty string.")
            if ref is not None and (
                not isinstance(ref, str) or not ref.strip() or ref.startswith("-")
            ):
                raise ValueError("Profile ref must be a non-empty Git revision.")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("Profile path must be a non-empty relative path.")
            relative = Path(path)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Profile path must stay inside the repository.")
            checkout = self._clone_remote_source().resolve()
            root = (checkout / relative).resolve()
            if not root.is_relative_to(checkout):
                raise ValueError("Profile path must stay inside the repository.")
            if not root.is_dir():
                raise ValueError(
                    f"Profile directory {path!r} does not exist in {repo!r}."
                )
            return root
        if self.is_remote_source:
            return self._clone_remote_source()
        return self._resolve_local_source()
