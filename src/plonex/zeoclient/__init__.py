from contextlib import chdir
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseOptions
from plonex.base import BaseService
from plonex.template import render
from typing import Literal

import subprocess
import yaml


_undefined = object()


@dataclass(kw_only=True)
class ZopeConfOptions(BaseOptions):

    context: "ZeoClient"
    instance_home: Path
    client_home: Path
    environment_vars: dict[str, str] = field(default_factory=dict)
    debug_mode: Literal["on", "off"] = "off"
    security_policy_implementation: Literal["PYTHON", "C"] = "C"
    verbose_security: Literal["on", "off"] = "off"


@dataclass(kw_only=True)
class WSGIOptions:

    context: "ZeoClient"
    zope_conf: Path
    var_folder: Path
    name: str = "instance"
    fast_listen: bool = False
    threads: int = 3


@dataclass(kw_only=True)
class InterpreterOptions:

    context: "ZeoClient"
    python: Path


@dataclass(kw_only=True)
class InstanceOptions:

    context: "ZeoClient"
    python: Path
    zope_conf_path: Path
    interpreter_path: Path
    wsgi_ini_path: Path


default_options = {
    "http_port": 8080,
    "http_address": "0.0.0.0",
    "zeo_address": _undefined,
    "blobstorage": _undefined,
}


@dataclass(kw_only=True)
class ZeoClient(BaseService):
    """This is a context manager that allows to run a ZEO client

    The ZEO client configuration is generated in a temporary folder
    Once the context manager is entered, the configuration files are created
    and the ZEO client is started with the `run` method

    Once the context manager is exited, the temporary folder is removed

    Example:
    with ZeoClient() as zeoclient:
        zeoclient.run()

    To stop the process you can use Ctrl+C
    or kill the process with the signal 15
    """

    # Those are the most important parameters passed to the constructor
    name: str = "zeoclient"
    target: Path = field(default_factory=Path.cwd)
    config_files: list[str | Path] = field(default_factory=list)

    # This control how the program runs
    run_mode: Literal[
        "console",
        "fg",
        "start",
        "stop",
        "status",
        "debug",
    ] = "console"  # This is the default for the supervisor program

    # You can override the templates used to generate the configuration files
    zope_conf_template: str = "plonex.zeoclient.templates:zope.conf.j2"
    wsgi_ini_template: str = "plonex.zeoclient.templates:wsgi.ini.j2"
    interpreter_template: str = "plonex.zeoclient.templates:interpreter.j2"
    instance_template: str = "plonex.zeoclient.templates:instance.j2"

    # This service has some folders
    tmp_folder: Path | None = None
    var_folder: Path | None = None

    zope_conf: Path | None = field(init=False, default=None)
    wsgi_ini: Path | None = field(init=False, default=None)
    interpreter: Path | None = field(init=False, default=None)
    instance: Path | None = field(init=False, default=None)

    # The service has some options
    options: dict = field(init=False, default_factory=default_options.copy)

    # Command line options will win over the config file options
    cli_options: dict = field(default_factory=dict)

    def __post_init__(self):
        # Be sure that the required folders exist
        if self.tmp_folder is None:
            # We want a dedicated subfolder for this service
            self.tmp_folder = self.target / "tmp" / self.name
        if self.var_folder is None:
            # This is not dedicated because it is usually shared with the ZEO server
            self.var_folder = self.target / "var"

        self.target = self._ensure_dir(self.target)
        self.tmp_folder = self._ensure_dir(self.tmp_folder)
        self.var_folder = self._ensure_dir(self.var_folder)

        # Ensure self.config_files is a list of Paths
        self.config_files = [
            Path(file) if isinstance(file, str) else file for file in self.config_files
        ]

        # We will read the config files and update the default options
        for path in self.config_files:
            if not path.is_file():
                self.logger.error("Config file %r is not valid", path)
            else:
                with path.open() as stream:
                    self.logger.info("Reading %r", path)
                    new_options = yaml.safe_load(stream)
                    if not isinstance(new_options, dict):
                        self.logger.error(
                            "The config file %r should contain a dict", path
                        )
                    else:
                        self.options.update(new_options)

        # Command line options will win over the config file options
        self.options.update(self.cli_options)

        # Ensure that the required undefined options are set
        if self.options["zeo_address"] is _undefined:
            self.options["zeo_address"] = self.var_folder / "zeosocket.sock"

        if self.options["blobstorage"] is _undefined:
            self.options["blobstorage"] = self.var_folder / "blobstorage"

    @BaseService.entered_only
    def make_zope_conf(self):
        """Generate the zope.conf file for this ZEO client"""
        options = ZopeConfOptions(
            context=self,
            instance_home=self._ensure_dir(self.tmp_folder),
            client_home=self._ensure_dir(self.var_folder / self.name),
        )
        with open(self.zope_conf, "w") as f:
            f.write(render(self.zope_conf_template, options))
            f.write("\n")
        self.logger.info(f"Generated {self.zope_conf}")
        self.logger.info(self.zope_conf.read_text())

    @BaseService.entered_only
    def make_wsgi_ini(self):
        options = WSGIOptions(
            context=self,
            name=f"instance-{self.options['http_port']}",
            zope_conf=self.zope_conf,
            var_folder=self.var_folder,
        )
        self.wsgi_ini.write_text(render(self.wsgi_ini_template, options))
        self.logger.info("Generated {self.wsgi_ini}")
        self.logger.info(self.wsgi_ini.read_text())

    @BaseService.entered_only
    def make_interpreter(self):
        options = InterpreterOptions(
            context=self, python=Path(self.virtualenv_dir / "bin" / "python")
        )
        self.interpreter.write_text(render(self.interpreter_template, options))
        self.logger.info("Generated {self.interpreter}")
        self.logger.info(self.interpreter.read_text())

    @BaseService.entered_only
    def make_instance(self):
        options = InstanceOptions(
            context=self,
            python=self.virtualenv_dir / "bin" / "python",
            zope_conf_path=self.zope_conf,
            interpreter_path=self.interpreter,
            wsgi_ini_path=self.wsgi_ini,
        )
        self.instance.write_text(render(self.instance_template, options))
        self.logger.info("Generated {self.instance}")
        self.logger.info(self.instance.read_text())

    def __enter__(self):
        self = super().__enter__()
        etc_folder = self.tmp_folder / "etc"
        bin_folder = self.tmp_folder / "bin"
        self._ensure_dir(etc_folder)
        self._ensure_dir(bin_folder)
        self.zope_conf = etc_folder / "zope.conf"
        self.wsgi_ini = etc_folder / "wsgi.ini"
        self.interpreter = bin_folder / "interpreter"
        self.instance = etc_folder / "instance"
        self.instance.touch()
        self.instance.chmod(0o755)
        self.make_zope_conf()
        self.make_wsgi_ini()
        self.make_interpreter()
        self.make_instance()
        return self

    @property
    def command(self):
        return [self.instance, self.run_mode]

    @BaseService.entered_only
    def adduser(self, username: str, password: str):
        with chdir(self.target):  # type: ignore
            command = [str(self.instance), "adduser", username, password]
            self.logger.info("Running %r", command)
            try:
                subprocess.run(command, check=True)
            except KeyboardInterrupt:
                self.logger.info("Stopping %r", command)
