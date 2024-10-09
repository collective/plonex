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

import subprocess
import sys


@dataclass
class ZeoServerOption:

    address: Path
    pidfile: Path
    blob_dir: Path
    path: Path
    log_path: Path
    tmp_folder: Path
    socket_name: Path
    runzeo_path: Path


@dataclass
class RunZeoOption:
    python: Path
    instance_home: Path
    zeo_conf: Path


@dataclass
class ZeoServer:
    """This is a context manager that allows to run a ZEO server

    The ZEO server configuration is created in a temporary folder
    Once the context manager is entered, the configuration file is created
    and can be run with the `run` method.

    Once the context manager is exited, the temporary folder is removed.

    Example:
    with ZeoServer() as zeoserver:
        zeoserver.run()

    To stop the process you can use Ctrl+C
    or kill the process with the signal 15
    """

    target: Path = field(default_factory=Path.cwd)
    zeo_conf_template: str = "plonedeployment.zeoserver.templates:zeo.conf.j2"
    runzeo_template: str = "plonedeployment.zeoserver.templates:runzeo.j2"
    tmp_folder: Path | None = None
    var_folder: Path | None = None

    conf_folder: Path | None = field(init=False, default=None)
    zeo_conf: Path | None = field(init=False, default=None)
    runzeo: Path | None = field(init=False, default=None)

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
    def make_zeo_conf(self):
        """Generate the ZEO configuration file"""
        options = ZeoServerOption(
            address=self.var_folder / "zeosocket.sock",
            pidfile=self.tmp_folder / "zeoserver.pid",
            blob_dir=self.var_folder / "blobstorage",
            path=self.var_folder / "filestorage" / "Data.fs",
            log_path=self.var_folder / "log" / "zeoserver.log",
            tmp_folder=self.tmp_folder,
            socket_name=self.tmp_folder / "zeoserver.sock",
            runzeo_path=self.runzeo,
        )
        self.zeo_conf.write_text(render(self.zeo_conf_template, options))
        logger.info(f"Generated {self.zeo_conf}")
        logger.info(self.zeo_conf.read_text())

    @active_only
    def make_runzeo(self):
        """Generate the runzeo script"""
        options = RunZeoOption(
            python=Path(sys.executable),
            instance_home=self.target,
            zeo_conf=self.zeo_conf,
        )
        self.runzeo.write_text(
            render(self.runzeo_template, options),
        )
        self.runzeo.chmod(0o755)
        logger.info(f"Generated {self.runzeo}")
        logger.info(self.runzeo.read_text())

    def __enter__(self):
        self.conf_folder = Path(mkdtemp(dir=self.tmp_folder))
        logger.info(f"Temporary folder: {self.conf_folder}")
        self.zeo_conf = self.conf_folder / "zeo.conf"
        self.runzeo = self.conf_folder / "runzeo"
        self.make_zeo_conf()
        self.make_runzeo()
        return self

    @active_only
    def run(self):  # pragma: no cover
        with chdir(self.conf_folder):
            logger.debug(f"Running {self.runzeo}")
            try:
                subprocess.run([self.runzeo], check=True)
            except KeyboardInterrupt:
                logger.info("Stopping {self.runzeo}")

    def __exit__(self, exc_type, exc_value, traceback):
        logger.info(f"Cleaning up {self.conf_folder}")
        rmtree(self.conf_folder)
