from dataclasses import dataclass
from dataclasses import field
from functools import cached_property
from pathlib import Path
from plonex.base import BaseService
from plonex.template import TemplateService


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

    @cached_property
    def options_defaults(self) -> dict:
        if self.var_folder is None:
            raise ValueError("var_folder is not set")

        options_defaults = super().options_defaults
        options_defaults.update(
            {
                "http_port": 8080,
                "http_address": "0.0.0.0",
                "zeo_address": str(self.var_folder / "zeosocket.sock"),
                "blobstorage": str(self.var_folder / "blobstorage"),
            }
        )
        return options_defaults

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
                        "address": self.options["zeo_address"],
                        "pidfile": self.var_folder / f"{self.name}.pid",
                        "blob_dir": self.options["blobstorage"],
                        "path": self.var_folder / "filestorage" / "Data.fs",
                        "log_path": self.var_folder / "log" / "zeoserver.log",
                        "tmp_folder": self.tmp_folder,
                        "socket_name": self.var_folder / "zeoserver.sock",
                    },
                )
            ]

    @property
    def command(self):
        return [
            str(self.virtualenv_dir / "bin" / "runzeo"),
            "-C",
            str(self.tmp_folder / "etc" / "zeo.conf"),
        ]

    def run_pack(self, days: int = 7):
        """Run the zeo pack command"""
        zeopack = self.virtualenv_dir / "bin" / "zeopack"
        address = self.options["zeo_address"]
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

    def run_restore(self):
        """Use repozo to restore the latest backup into Data.fs"""
        repozo = self.virtualenv_dir / "bin" / "repozo"
        backup_folder = self.var_folder / "backup"
        filestorage = self.var_folder / "filestorage"
        data_fs = filestorage / "Data.fs"

        if not backup_folder.exists() or not any(backup_folder.iterdir()):
            raise FileNotFoundError(f"No backups found in {backup_folder}")

        self._ensure_dir(filestorage)
        self.logger.info("Running restore")
        self.run_command(
            [
                repozo,
                "-Rv",
                "-r",
                backup_folder,
                "-o",
                data_fs,
            ]
        )
        self.logger.info("Completed restore")
