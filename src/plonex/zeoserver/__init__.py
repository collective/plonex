from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.template import TemplateService


_undefined = object()

default_options = {
    "http_port": 8080,
    "http_address": "0.0.0.0",
    "zeo_address": _undefined,
    "blobstorage": _undefined,
}


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

        # We also want to create the blobstorage and filestorage folders
        self._ensure_dir(self.var_folder / "blobstorage")
        self._ensure_dir(self.var_folder / "filestorage")
        self._ensure_dir(self.var_folder / "log")

        if not self.pre_services:
            self.pre_services = [
                TemplateService(
                    source_path="resource://plonex.zeoserver.templates:zeo.conf.j2",
                    target_path=self.tmp_folder / "etc" / "zeo.conf",
                    options={
                        "address": self.var_folder / "zeosocket.sock",
                        "pidfile": self.var_folder / f"{self.name}.pid",
                        "blob_dir": self.var_folder / "blobstorage",
                        "path": self.var_folder / "filestorage" / "Data.fs",
                        "log_path": self.var_folder / "log" / "zeoserver.log",
                        "tmp_folder": self.tmp_folder,
                        "socket_name": self.var_folder / "zeoserver.sock",
                        "runzeo": self.tmp_folder / "bin" / "runzeo",
                    },
                ),
                TemplateService(
                    source_path="resource://plonex.zeoserver.templates:runzeo.j2",
                    target_path=self.tmp_folder / "bin" / "runzeo",
                    options={
                        "python": self.virtualenv_dir / "bin" / "python",
                        "instance_home": self.target,
                        "zeo_conf": self.tmp_folder / "etc" / "zeo.conf",
                    },
                    mode=0o700,
                ),
            ]

    @property
    def command(self):
        return [
            str(self.tmp_folder / "bin" / "runzeo"),
        ]

    def run_pack(self, days: int = 7):
        """Run the zeo pack command"""
        zeopack = self.virtualenv_dir / "bin" / "zeopack"
        address = self.var_folder / "zeosocket.sock"  # type: ignore
        days = 7
        self.logger.info("Running zeopack")
        self.run_command([zeopack, "-u", address, "-d", days])
        self.logger.info("Completed zeopack")

    def run_backup(self):
        """Use repozo to backup the database"""
        repozo = self.virtualenv_dir / "bin" / "repozo"
        backup_folder = self._ensure_dir(self.var_folder / "backup")
        self.logger.info("Running backup")
        self.run_command(
            [
                repozo,
                "-Bv",
                "-r",
                backup_folder,
                "-f",
                self.var_folder / "filestorage" / "Data.fs",
            ]
        )
        self.logger.info("Completed backup")
