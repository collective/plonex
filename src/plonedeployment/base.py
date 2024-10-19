from contextlib import chdir
from dataclasses import dataclass
from dataclasses import field
from functools import wraps
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from typing import Callable

import logging
import subprocess


logger = logging.getLogger(__name__)


@dataclass
class ZeoBase:
    """Base class for ZEO Server and ZEO Client."""

    target: Path = field(default_factory=Path.cwd)
    tmp_folder: Path | None = None
    var_folder: Path | None = None

    conf_folder: Path | None = field(init=False, default=None)

    @staticmethod
    def _ensure_dir(path: str | Path) -> Path:
        """Ensure the path is a directory and exists.
        If path is a string, convert it to a Path object.
        """
        if isinstance(path, str):
            path = Path(path)
        if not path.exists():
            path.mkdir(parents=True)
        elif not path.is_dir():
            raise ValueError(f"{path} is not a directory")
        return path

    def __post_init__(self):
        self.target = self._ensure_dir(self.target)
        self.tmp_folder = self._ensure_dir(self.tmp_folder or self.target / "tmp")
        self.var_folder = self._ensure_dir(self.var_folder or self.target / "var")

    @staticmethod
    def active_only(method: Callable) -> Callable:
        """Decorator that ensures the context manager is entered before
        running the method."""

        @wraps(method)
        def wrapper(self, *args, **kwargs):
            if not self.conf_folder:
                raise RuntimeError(
                    f"You need to enter the {self.__class__!r} context manager first"
                )
            return method(self, *args, **kwargs)

        return wrapper

    def __enter__(self):
        self.conf_folder = Path(mkdtemp(dir=self.tmp_folder))
        logger.info(f"Temporary folder: {self.conf_folder}")
        self._setup()
        return self

    def _setup(self):
        """Method to be implemented by subclasses to set up configuration."""
        raise NotImplementedError("Subclasses must implement the _setup method.")

    @active_only
    def run(self, command: list[str]):  # pragma: no cover
        """Run the given command in the configuration folder."""
        with chdir(self.conf_folder):  # type: ignore[union-attr,type-var]
            logger.debug(f"Running {command}")
            try:
                subprocess.run(command, check=True)
            except KeyboardInterrupt:
                logger.info(f"Stopping {command}")

    def __exit__(self, exc_type, exc_value, traceback):
        logger.info(f"Cleaning up {self.conf_folder}")
        rmtree(self.conf_folder)
