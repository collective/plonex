from contextlib import chdir
from functools import cached_property
from functools import wraps
from pathlib import Path
from plonex import logger
from rich.console import Console
from tempfile import mkdtemp
from typing import Callable

import logging
import subprocess
import sys
import time


class BaseService:
    """Base class for a context manager that runs a command.

    The command can be executed only when the context manager is entered.

    Every command needs to have a temporary folder where the configuration will
    be stored.
    """

    name: str = "base"
    logger: logging.Logger = logger
    pre_services: None | list = None
    post_services: None | list = None
    options: None | dict = None

    _entered = False

    def __init__(self):
        # This is a workaround to use this class as a base class for dataclasses
        self.__post_init__()

    def __post_init__(self):
        """ """
        self.tmp_folder = self.mkdtemp()
        self.target = self.mkdtemp()

    @cached_property
    def console(self) -> Console:
        """A console object that can be used to interact with the user"""
        return Console()

    def ask_for_value(self, question: str, default: str = "") -> str:
        """Ask the user for a value"""
        if default:
            question = f"{question} [{default}]"
        if not question.endswith(":"):
            question = f"{question}:"
        return self.console.input(question) or default

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
        return path.absolute()

    def mkdtemp(self, dir=None) -> Path:
        """Wrapper for mkdtemp that creates a temporary folder with a prefix
        that matches the service name.

        Returns a Path object instead than a string
        """
        return self._ensure_dir(mkdtemp(prefix=f"{self.name}-", dir=dir))

    @property
    def executable(self) -> Path:
        """The path to the Python executable"""
        return Path(sys.executable)

    @property
    def executable_dir(self) -> Path:
        """The directory where the Python executable is located

        This is usually the bin folder in a virtualenv.
        """
        return self.executable.parent

    @property
    def virtualenv_dir(self) -> Path:
        """The path to the virtualenv"""
        dir = self.target / ".venv"
        if not (dir / "bin" / "activate").exists():
            logger.error(
                "No virtualenv found in %r. You may want to run `plonex init`", dir
            )
            sys.exit(1)
        return dir.absolute()

    @staticmethod
    def entered_only(method: Callable) -> Callable:
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
        for pre_service in self.pre_services or []:
            with pre_service:
                pre_service.run()
        self._entered = True
        return self

    @property
    def command(self) -> list[str]:
        return ["true"]  # pragma: no cover

    @entered_only
    def run_command(self, command: list[str | Path | int]):
        """Run a command"""
        self.logger.debug("Entering %s", self.target)
        command_list: list[str] = list(map(str, command))
        command_str: str = " ".join(command_list)
        with chdir(self.target):
            try:
                self.logger.debug("Running %r", command_str)
                start_time = time.time()
                subprocess.run(command_list, check=True)
            except KeyboardInterrupt:
                self.logger.info("Stopping %r", command_str)
            finally:
                stop_time = time.time()
                self.logger.debug("Time taken: %.1f seconds", stop_time - start_time)

    @entered_only
    def run(self):
        """Run the command"""
        command = self.command
        self.run_command(command)

    def __exit__(self, exc_type, exc_value, traceback):
        for post_service in self.post_services or []:
            with post_service:
                post_service.run()
        self._entered = False
