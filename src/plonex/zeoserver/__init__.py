from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.template import render


@dataclass(kw_only=True)
class ZeoServerOption:

    address: Path
    pidfile: Path
    blob_dir: Path
    path: Path
    log_path: Path
    tmp_folder: Path
    socket_name: Path
    runzeo_path: Path


@dataclass(kw_only=True)
class RunZeoOption:
    python: Path
    instance_home: Path
    zeo_conf: Path


@dataclass(kw_only=True)
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

    name: str = "zeoserver"
    target: Path = field(default_factory=Path.cwd)

    # This service has some folders
    tmp_folder: Path | None = None
    var_folder: Path | None = None

    # You can override the templates used to generate the configuration files
    zeo_conf_template: str = "plonex.zeoserver.templates:zeo.conf.j2"
    runzeo_template: str = "plonex.zeoserver.templates:runzeo.j2"

    zeo_conf: Path | None = field(init=False, default=None)
    runzeo: Path | None = field(init=False, default=None)

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

    @BaseService.entered_only
    def make_zeo_conf(self):
        """Generate the ZEO configuration file"""
        options = ZeoServerOption(
            address=self.var_folder / "zeosocket.sock",
            pidfile=self.var_folder / f"{self.name}.pid",
            blob_dir=self.var_folder / "blobstorage",
            path=self.var_folder / "filestorage" / "Data.fs",
            log_path=self.var_folder / "log" / "zeoserver.log",
            tmp_folder=self.tmp_folder,
            socket_name=self.var_folder / "zeoserver.sock",
            runzeo_path=self.runzeo,
        )
        # Ensure the folder exists
        self._ensure_dir(options.blob_dir)
        self._ensure_dir(options.path.parent)
        with self.zeo_conf.open("w") as f:
            f.write(render(self.zeo_conf_template, options))
            f.write("\n")
        self.logger.info(f"Generated {self.zeo_conf}")
        self.logger.info(self.zeo_conf.read_text())

    @BaseService.entered_only
    def make_runzeo(self):
        """Generate the runzeo script"""
        options = RunZeoOption(
            python=self.virtualenv_dir / "bin" / "python",
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
        etc_folder = self.tmp_folder / "etc"
        bin_folder = self.tmp_folder / "bin"
        self._ensure_dir(bin_folder)
        self._ensure_dir(etc_folder)
        self.zeo_conf = etc_folder / "zeo.conf"
        self.runzeo = bin_folder / "runzeo"
        self.make_zeo_conf()
        self.make_runzeo()
        return self

    @property
    def command(self):
        return [str(self.runzeo)]
