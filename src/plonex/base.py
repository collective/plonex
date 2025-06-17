from contextlib import chdir
from dataclasses import dataclass
from dataclasses import field
from functools import cached_property
from functools import wraps
from jinja2 import BaseLoader
from jinja2 import Environment
from pathlib import Path
from plonex import logger
from rich.console import Console
from tempfile import mkdtemp
from typing import Callable
from typing import ClassVar

import logging
import subprocess
import sys
import time
import yaml


@dataclass(kw_only=True)
class BaseService:
    """Base class for a context manager that runs a command.

    The command can be executed only when the context manager is entered.

    Every command needs to have a temporary folder where the configuration will
    be stored.
    """

    options_defaults: ClassVar[dict] = {}

    name: str = "base"
    target: Path = field(default_factory=Path.cwd)
    cli_options: dict = field(default_factory=dict)
    config_files: list[str | Path] = field(default_factory=list)

    pre_services: None | list = field(default=None, init=False)
    post_services: None | list = field(default=None, init=False)
    logger: logging.Logger = field(default=logger, init=False)
    _entered: bool = field(default=False, init=False)

    @cached_property
    def plonex_options(self) -> dict:
        """Return the options from the plonex.yml file"""
        plonex_yml = self.target / "etc" / "plonex.yml"
        if not plonex_yml.exists():
            self.logger.warning("No plonex.yml file found in %r", self.target)
            return {}
        return yaml.safe_load(plonex_yml.read_text()) or {}

    @cached_property
    def additional_plonex_options(self) -> dict:
        """Return the options from all the found  plonex.*.yml files (if any).

        Precedence is given in alphabetical order.
        """
        mapping = {}
        for path in self.target.glob("etc/plonex.*.yml"):
            if not path.exists():
                self.logger.warning("Config file %r does not exist", path)
                file_options = {}
            else:
                file_options = yaml.safe_load(path.read_text())
                if not isinstance(file_options, dict):
                    self.logger.error("The config file %r should contain a dict", path)
                    file_options = {}
            mapping[path] = file_options
        return mapping

    @cached_property
    def config_files_options_mapping(self) -> dict:
        """Return the options from the config files"""
        mapping = {}
        for path in self.config_files:
            path = Path(path).absolute()
            if not path.exists():
                self.logger.warning("Config file %r does not exist", path)
                file_options = {}
            else:
                file_options = yaml.safe_load(path.read_text())
                if not isinstance(file_options, dict):
                    self.logger.error("The config file %r should contain a dict", path)
                    file_options = {}
            mapping[path] = file_options
        return mapping

    @cached_property
    def config_files_options(self) -> dict:
        """Return the options from the config files"""
        options = {}
        for file_options in self.config_files_options_mapping.values():
            options.update(file_options)
        return options

    @cached_property
    def options(self) -> dict:
        """Return the options for this service.

        Options can be specified in multiple ways (and in this order):

        1. In the command line (max priority)
        2. In config files
        3. In the plonex.*.yml files (if any)
        4. In the plonex.yml file
        5. In the class definition options_default (lowest priority)
        """
        options = self.options_defaults.copy()
        options.update(self.plonex_options)
        for path, file_options in self.additional_plonex_options.items():
            if not isinstance(file_options, dict):
                self.logger.error("The config file %r should contain a dict", path)
                continue
            options.update(file_options)
        options.update(self.config_files_options)
        options.update(self.cli_options)

        # FIXME: This should probably done in a more sane way
        # The goal is to resolve the variables inside the options
        # Maybe the ansible code has something that can be reused
        options_as_yaml_text = yaml.dump(options)
        env = Environment(loader=BaseLoader())
        counter = 0
        while counter < 10:
            resolved_options = env.from_string(options_as_yaml_text).render(
                keep_training_newline=True, **options
            )
            if resolved_options == options_as_yaml_text:
                break
            options_as_yaml_text = resolved_options

        return yaml.safe_load(resolved_options)

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
        """Load the environment variables before entering the context manager."""
        if self.options.get("environment_vars"):
            import os

            for key, value in self.options["environment_vars"].items():
                if isinstance(value, str):
                    value = value.format(**self.options)
                else:
                    value = str(value)
                self.logger.debug("Setting environment variable %s=%s", key, value)
                if key in os.environ:
                    old = os.environ[key]
                    if old != value:
                        self.logger.info(
                            "Overriding existing environment variable %r: %r -> %r",
                            key,
                            old,
                            value,
                        )
                os.environ[key] = str(value)
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
                try:
                    subprocess.run(command_list, check=True)
                except subprocess.CalledProcessError as e:
                    self.logger.error(e)
                    sys.exit(e.returncode)
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
