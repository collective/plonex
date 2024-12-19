from contextlib import chdir
from functools import wraps
from pathlib import Path
from plonex import logger
from shutil import rmtree
from tempfile import mkdtemp
from typing import Callable

import subprocess
import sys


class BaseService:
    name = "base"
    logger = logger
    _entered = False

    def __init__(self):
        self.tmp_folder = self.mkdtemp()

    def mkdtemp(self, dir=None) -> Path:
        """Wrapper for mkdtemp that creates a temporary folder with a prefix
        that matches the service name.

        Returns a Path object instead than a string
        """
        return self._ensure_dir(mkdtemp(prefix=f"{self.name}-", dir=dir))

    @property
    def executable(self) -> Path:
        return Path(sys.executable)

    @property
    def executable_dir(self) -> Path:
        return self.executable.parent

    @staticmethod
    def _ensure_dir(path: str | Path) -> Path:
        """Ensure the path is a directory and exists,
        if path is a string, convert it to a Path object.
        """
        if isinstance(path, str):
            path = Path(path)
        if not path.exists():
            path.mkdir(parents=True)
        elif not path.is_dir():
            raise ValueError(f"{path} is not a directory")
        return path

    @staticmethod
    def active_only(method: Callable) -> Callable:
        """Decorator that ensures the context manager is entered before running
        the method

        When we are in the context manager we have the temporary folder
        created and we can run the method
        """

        @wraps(method)
        def wrapper(self, *args, **kwargs):
            if not self._entered:
                raise RuntimeError(
                    f"You need to enter the {self.__class__!r} context manager first"
                )
            return method(self, *args, **kwargs)

        return wrapper

    def __enter__(self):
        self._entered = True
        self._ensure_dir(self.tmp_folder)
        self.conf_folder = self._ensure_dir(self.tmp_folder / "etc")
        self.logger.info(f"Temporary configuration folder: {self.conf_folder}")
        return self

    @property
    def command(self) -> list[str]:
        return ["true"]  # pragma: no cover

    @active_only
    def run(self):
        with chdir(self.conf_folder):
            command = self.command
            self.logger.debug("Running %r", command)
            try:
                subprocess.run(command, check=True)
            except KeyboardInterrupt:
                self.logger.info("Stopping %r", command)

    def __exit__(self, exc_type, exc_value, traceback):
        self._entered = False
        rmtree(self.tmp_folder, ignore_errors=True)
