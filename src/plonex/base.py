from dataclasses import dataclass
from dataclasses import field
from functools import cached_property
from functools import wraps
from jinja2 import BaseLoader
from jinja2 import Environment
from pathlib import Path
from plonex import logger
from plonex._logger import warning_once
from plonex.config import normalize_options
from rich.console import Console
from tempfile import mkdtemp
from typing import Any
from typing import Callable
from typing import Sequence

import logging
import sh  # type: ignore[import-untyped]
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

    name: str = "base"
    target: Path = field(default_factory=Path.cwd)
    cli_options: dict = field(default_factory=dict)
    config_files: list[str | Path] = field(default_factory=list)

    pre_services: None | list = field(default=None, init=False)
    post_services: None | list = field(default=None, init=False)
    logger: logging.Logger = field(default=logger, init=False)
    _entered: bool = field(default=False, init=False)

    @cached_property
    def options_defaults(self) -> dict:
        return {
            "target": self.target.absolute().as_posix(),
        }

    def _load_yaml_mapping(self, path: Path) -> dict:
        if not path.exists():
            self.logger.warning("Config file %r does not exist", path)
            return {}

        file_options = yaml.safe_load(path.read_text()) or {}
        if not isinstance(file_options, dict):
            self.logger.error("The config file %r should contain a dict", path)
            return {}
        return file_options

    @property
    def legacy_constraints_file(self) -> Path:
        return self.target / "etc" / "constraints.d" / "000-plonex.txt"

    def _legacy_plone_version(self) -> str | None:
        path = self.legacy_constraints_file
        if not path.exists():
            return None

        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("Plone=="):
                return line.split("==", 1)[1].strip()
            if line.startswith("Products.CMFPlone=="):
                return line.split("==", 1)[1].strip()
            marker = "https://dist.plone.org/release/"
            if marker in line and "/constraints.txt" in line:
                return line.split(marker, 1)[1].split("/constraints.txt", 1)[0]
        return None

    def _normalize_profiles(self, profiles: Any, source: Path) -> list[str | Path]:
        if profiles is None:
            return []
        if isinstance(profiles, str):
            profiles = [profiles]
        if not isinstance(profiles, list) or not all(
            isinstance(item, str) for item in profiles
        ):
            self.logger.error(
                "The 'profiles' option in %r should be a string or a list of strings",
                source,
            )
            return []
        return profiles

    def _resolve_profile_source(
        self,
        profile: str | Path,
        relative_to: Path,
    ) -> str | Path:
        if isinstance(profile, Path):
            return profile

        source_path = Path(profile).expanduser()
        if source_path.is_absolute() or profile.startswith(
            ("git@", "http://", "https://", "git://", "ssh://")
        ):
            return profile
        return relative_to / source_path

    def _load_profile_options(
        self,
        profile: str | Path,
        relative_to: Path,
        seen: set[Path] | None = None,
    ) -> dict:
        from plonex.profile import ProfileService

        resolved_profile = self._resolve_profile_source(profile, relative_to)
        profile_service = ProfileService(source=resolved_profile, target=self.target)
        profile_root = profile_service.source_path

        if seen is None:
            seen = set()
        if profile_root in seen:
            return {}
        seen.add(profile_root)

        profile_options: dict = {}
        profile_plonex_yml = profile_root / "etc" / "plonex.yml"
        if not profile_plonex_yml.exists():
            self.logger.warning("No plonex.yml file found in profile %r", profile_root)
            return profile_options

        raw_profile_options = self._load_yaml_mapping(profile_plonex_yml)
        nested_profiles = self._normalize_profiles(
            raw_profile_options.get("profiles"),
            profile_plonex_yml,
        )
        for nested_profile in nested_profiles:
            profile_options.update(
                self._load_profile_options(nested_profile, profile_root, seen)
            )

        profile_options.update(raw_profile_options)
        return profile_options

    @cached_property
    def plonex_options(self) -> dict:
        """Return the options from the plonex.yml file"""
        plonex_yml = self.target / "etc" / "plonex.yml"
        local_options = {}
        if not plonex_yml.exists():
            self.logger.warning("No plonex.yml file found in %r", self.target)
        merged_profile_options = {}
        if plonex_yml.exists():
            local_options = self._load_yaml_mapping(plonex_yml)
            profiles = self._normalize_profiles(
                local_options.get("profiles"), plonex_yml
            )

            for profile in profiles:
                merged_profile_options.update(
                    self._load_profile_options(profile, self.target)
                )

            merged_profile_options.update(local_options)

        if self.legacy_constraints_file.exists():
            warning_key = f"legacy-constraints:{self.legacy_constraints_file}"
            legacy_plone_version = self._legacy_plone_version()
            if (
                "plone_version" in merged_profile_options
                or "plonex_base_constraint" in merged_profile_options
            ):
                warning_once(
                    self.logger,
                    warning_key,
                    "Ignoring legacy constraints file %r because "
                    "plone_version or plonex_base_constraint is "
                    "configured in etc/plonex.yml. Remove the file.",
                    self.legacy_constraints_file,
                )
            elif legacy_plone_version:
                warning_once(
                    self.logger,
                    warning_key,
                    "Ignoring legacy constraints file %r. Using "
                    "plone_version=%s for compatibility; add it to "
                    "etc/plonex.yml and remove the file.",
                    self.legacy_constraints_file,
                    legacy_plone_version,
                )
                merged_profile_options["plone_version"] = legacy_plone_version
            elif (
                "plone_version" not in merged_profile_options
                and "plonex_base_constraint" not in merged_profile_options
            ):
                warning_once(
                    self.logger,
                    warning_key,
                    "Ignoring legacy constraints file %r. Configure "
                    "plone_version or plonex_base_constraint in "
                    "etc/plonex.yml and remove the file.",
                    self.legacy_constraints_file,
                )

        return merged_profile_options

    @cached_property
    def additional_plonex_options(self) -> dict[Path, dict]:
        """Return the options from all the found  plonex.*.yml files (if any).

        Precedence is given in alphabetical order.
        """
        mapping = {}
        paths = list(self.target.glob("etc/plonex.*.yml"))
        paths += list(self.target.glob(f"etc/plonex-{self.name}.yml"))
        paths += list(self.target.glob(f"etc/plonex-{self.name}.*.yml"))

        for path in paths:
            file_options = self._load_yaml_mapping(path)
            mapping[path] = file_options
        return mapping

    @cached_property
    def config_files_options_mapping(self) -> dict:
        """Return the options from the config files"""
        mapping = {}
        for path in self.config_files:
            path = Path(path).absolute()
            file_options = self._load_yaml_mapping(path)
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

            for key in file_options:
                # If the key starts with + or - we want to modify an existing value
                # We will pick the right strategy based
                # on the type of the existing value
                # Supported types are list and dicts
                if key.startswith("+") and key[1:] in options:
                    real_key = key[1:]
                    if isinstance(options[real_key], list):
                        options[real_key].extend(file_options[key])
                    elif isinstance(options[real_key], dict):
                        options[real_key].update(file_options[key])
                    else:
                        self.logger.error(
                            "Cannot add to option %r of type %r option %r of type %r",
                            real_key,
                            type(options[real_key]),
                            key,
                            type(file_options[key]),
                        )
                elif key.startswith("-") and key[1:] in options:
                    real_key = key[1:]
                    if isinstance(options[real_key], list):
                        for item in file_options[key]:
                            try:
                                options[real_key].remove(item)
                            except ValueError:
                                self.logger.warning(
                                    "Cannot remove item %r from option %r",
                                    item,
                                    real_key,
                                )
                    elif isinstance(options[real_key], dict):
                        for item in file_options[key]:
                            try:
                                del options[real_key][item]
                            except KeyError:
                                self.logger.warning(
                                    "Cannot remove item %r from option %r",
                                    item,
                                    real_key,
                                )
                else:
                    options[key] = file_options[key]
        options.update(self.config_files_options)
        options.update(self.cli_options)

        # FIXME: This should probably done in a more sane way
        # The goal is to resolve the variables inside the options
        # Maybe the ansible code has something that can be reused
        options_as_yaml_text = yaml.dump(options)
        env = Environment(loader=BaseLoader())
        counter = 0
        resolved_options = options_as_yaml_text
        while counter < 10:
            resolved_options = env.from_string(options_as_yaml_text).render(
                keep_training_newline=True, **options
            )
            if resolved_options == options_as_yaml_text:
                break
            options_as_yaml_text = resolved_options
            counter += 1
        else:
            self.logger.error("Too many iterations while resolving options")

        resolved = yaml.safe_load(resolved_options) or {}
        if not isinstance(resolved, dict):
            self.logger.error("Resolved options should contain a dict")
            return {}
        return normalize_options(resolved, self.logger)

    @cached_property
    def console(self) -> Console:
        """A console object that can be used to interact with the user"""
        return Console()

    @cached_property
    def print(self) -> Callable[..., None]:
        """A print function that can be used to print to the console"""
        if self.logger.isEnabledFor(logging.INFO):
            return self.console.print
        else:
            return lambda *args, **kwargs: None

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
                self.logger.debug("Setting environment variable %r", key)
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
    def run_command(
        self,
        command: Sequence[str | Path | int],
        cwd: Path | None = None,
    ):
        """Run a command"""
        command_cwd = cwd or self.target
        self.logger.debug("Entering %s", command_cwd)
        command_list: list[str] = list(map(str, command))
        command_str: str = " ".join(command_list)
        stream_output = "fg" in command_list
        start_time = time.time()
        try:
            self.logger.debug("Running %r", command_str)
            try:
                self.execute_command(
                    command_list,
                    cwd=command_cwd,
                    stream_output=stream_output,
                )
            except sh.ErrorReturnCode as e:
                self.logger.error(e)
                sys.exit(e.exit_code)
        except KeyboardInterrupt:
            self.logger.info("Stopping %r", command_str)
        finally:
            stop_time = time.time()
            self.logger.debug("Time taken: %.1f seconds", stop_time - start_time)

    @staticmethod
    def execute_command(
        command: Sequence[str | Path | int],
        cwd: Path | None = None,
        stream_output: bool = False,
    ) -> str:
        """Execute a command with sh and return stdout as text."""
        command_list = list(map(str, command))
        executable, *args = command_list
        kwargs: dict[str, Any] = {"_cwd": str(cwd)} if cwd else {}
        if stream_output:
            # Keep a real TTY for foreground commands (proper width, colors, prompts).
            kwargs.update({"_fg": True})
        return str(sh.Command(executable)(*args, **kwargs))

    @entered_only
    def run(self):
        """Run the command"""
        command = self.command
        if not command:
            return
        self.run_command(command)

    def __exit__(self, exc_type, exc_value, traceback):
        for post_service in self.post_services or []:
            with post_service:
                post_service.run()
        self._entered = False
