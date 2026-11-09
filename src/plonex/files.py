"""Atomic generated files and construction without filesystem mutations."""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from tempfile import NamedTemporaryFile

import os

_READ_ONLY = ContextVar("plonex_read_only", default=False)


def is_read_only():
    return _READ_ONLY.get()


@contextmanager
def read_only():
    token = _READ_ONLY.set(True)
    try:
        yield
    finally:
        _READ_ONLY.reset(token)


def write_if_changed(path: Path, content: str | bytes, mode: int = 0o600) -> bool:
    """Publish complete content; preserve the timestamp of unchanged outputs."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    if path.is_file() and path.read_bytes() == data:
        if path.stat().st_mode & 0o777 != mode:
            path.chmod(mode)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


_HELD_LOCKS: ContextVar[frozenset[Path]] = ContextVar(
    "plonex_project_locks", default=frozenset()
)


@contextmanager
def project_lock(folder: Path):
    """Serialize preparation and explicit installs; allow nested use in one call."""
    import fcntl

    folder = folder.absolute()
    held = _HELD_LOCKS.get()
    if folder in held:
        yield
        return
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    folder.chmod(0o700)
    with (folder / "project.lock").open("a+") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        token = _HELD_LOCKS.set(held | {folder})
        try:
            yield
        finally:
            _HELD_LOCKS.reset(token)
