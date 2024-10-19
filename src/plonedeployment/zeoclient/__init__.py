from contextlib import chdir
from dataclasses import dataclass
from dataclasses import field
from functools import wraps
from pathlib import Path
from plonedeployment import logger
from plonedeployment.template import render
from shutil import rmtree
from tempfile import mkdtemp
from typing import Callable
from typing import Literal

import subprocess
import sys


@dataclass
class ZopeConfOptions:

    instance_home: Path
    client_home: Path
    blobstorage: Path
    zeo_address: Path
    environment_vars: dict[str, str] = field(default_factory=dict)
    debug_mode: Literal["on", "off"] = "off"
    security_policy_implementation: Literal["PYTHON", "C"] = "C"
    verbose_security: Literal["on", "off"] = "off"


@dataclass
class WSGIOptions:

    zope_conf: Path
    var_folder: Path
    name: str = "instance"
    fast_listen: bool = False
    http_port: int = 8080
    threads: int = 3


@dataclass
class InterpreterOptions:

    python: Path


@dataclass
class InstanceOptions:

    python: Path
    zope_conf_path: Path
    interpreter_path: Path
    wsgi_ini_path: Path


@dataclass
class ZeoClient:
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

    target: Path = field(default_factory=Path.cwd)

    zope_conf_template: str = "plonedeployment.zeoclient.templates:zope.conf.j2"
    wsgi_ini_template: str = "plonedeployment.zeoclient.templates:wsgi.ini.j2"
    interpreter_template: str = "plonedeployment.zeoclient.templates:interpreter.j2"
    instance_template: str = "plonedeployment.zeoclient.templates:instance.j2"

    tmp_folder: Path | None = None
    var_folder: Path | None = None

    conf_folder: Path | None = field(init=False, default=None)
    zope_conf: Path | None = field(init=False, default=None)
    wsgi_ini: Path | None = field(init=False, default=None)
    interpreter: Path | None = field(init=False, default=None)
    instance: Path | None = field(init=False, default=None)

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

    def __post_init__(self):
        self.target = self._ensure_dir(self.target)
        self.tmp_folder = self._ensure_dir(self.tmp_folder or self.target / "tmp")
        self.var_folder = self._ensure_dir(self.var_folder or self.target / "var")

    @staticmethod
    def active_only(method: Callable) -> Callable:
        """Decorator that ensures the context manager is entered before running
        the method

        When we are in the context manager we have the temporary folder
        created and we can run the method
        """

        @wraps(method)
        def wrapper(self, *args, **kwargs):
            if not self.conf_folder:
                raise RuntimeError(
                    f"You need to enter the {self.__class__!r} context manager first"
                )
            return method(self, *args, **kwargs)

        return wrapper

    @active_only
    def make_zope_conf(self):
        options = ZopeConfOptions(
            instance_home=self.tmp_folder,
            client_home=self.tmp_folder,
            blobstorage=self.var_folder / "blobstorage",
            zeo_address=self.var_folder / "zeosocket.sock",
        )
        self.zope_conf.write_text(render(self.zope_conf_template, options))
        logger.info("Generated {self.zope_conf}")
        logger.info(self.zope_conf.read_text())

    @active_only
    def make_wsgi_ini(self):
        options = WSGIOptions(zope_conf=self.zope_conf, var_folder=self.var_folder)
        self.wsgi_ini.write_text(render(self.wsgi_ini_template, options))
        logger.info("Generated {self.wsgi_ini}")
        logger.info(self.wsgi_ini.read_text())

    @active_only
    def make_interpreter(self):
        options = InterpreterOptions(python=Path(sys.executable))
        self.interpreter.write_text(render(self.interpreter_template, options))
        logger.info("Generated {self.interpreter}")
        logger.info(self.interpreter.read_text())

    @active_only
    def make_instance(self):
        options = InstanceOptions(
            python=Path(sys.executable),
            zope_conf_path=self.zope_conf,
            interpreter_path=self.interpreter,
            wsgi_ini_path=self.wsgi_ini,
        )
        self.instance.write_text(render(self.instance_template, options))
        logger.info("Generated {self.instance}")
        logger.info(self.instance.read_text())

    def __enter__(self):
        self.conf_folder = Path(mkdtemp(dir=self.tmp_folder))
        logger.info(f"Temporary folder: {self.conf_folder}")
        etc_folder = self.tmp_folder / "etc"
        bin_folder = self.tmp_folder / "bin"
        self._ensure_dir(etc_folder)
        self._ensure_dir(bin_folder)
        self.zope_conf = etc_folder / "zope.conf"
        self.wsgi_ini = etc_folder / "wsgi.ini"
        self.interpreter = bin_folder / "interpreter"
        self.instance = self.conf_folder / "instance"
        self.instance.touch()
        self.instance.chmod(0o755)
        self.make_zope_conf()
        self.make_wsgi_ini()
        self.make_interpreter()
        self.make_instance()
        return self

    @active_only
    def run(self):  # pragma: no cover
        with chdir(self.conf_folder):
            logger.debug(f"Running {self.instance}")
            try:
                subprocess.run([self.instance, "fg"], check=True)
            except KeyboardInterrupt:
                logger.info("Stopping {self.instance}")

    def __exit__(self, exc_type, exc_value, traceback):
        logger.info(f"Cleaning up {self.conf_folder}")
        rmtree(self.conf_folder)
