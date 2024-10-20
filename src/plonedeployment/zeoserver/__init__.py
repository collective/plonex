from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonedeployment.base import BaseService
from plonedeployment.template import render


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
class ZeoServer(BaseService):
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

    def __post_init__(self):
        self.target = self._ensure_dir(self.target)
        self.tmp_folder = self._ensure_dir(self.tmp_folder or self.target / "tmp")
        self.var_folder = self._ensure_dir(self.var_folder or self.target / "var")

    @BaseService.active_only
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
        self.logger.info(f"Generated {self.zeo_conf}")
        self.logger.info(self.zeo_conf.read_text())

    @BaseService.active_only
    def make_runzeo(self):
        """Generate the runzeo script"""
        options = RunZeoOption(
            python=self.executable,
            instance_home=self.target,
            zeo_conf=self.zeo_conf,
        )
        self.runzeo.write_text(
            render(self.runzeo_template, options),
        )
        self.runzeo.chmod(0o755)
        self.logger.info(f"Generated {self.runzeo}")
        self.logger.info(self.runzeo.read_text())

    def __enter__(self):
        self = super().__enter__()
        self.zeo_conf = self.conf_folder / "zeo.conf"
        self.runzeo = self.conf_folder / "runzeo"
        self.make_zeo_conf()
        self.make_runzeo()
        return self

    @property
    def command(self):
        return [str(self.runzeo)]
