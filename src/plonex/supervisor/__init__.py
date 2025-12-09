from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.template import TemplateService

import sh  # type: ignore[import-untyped]


@dataclass(kw_only=True)
class SupervisordConfOptions:

    target: Path
    var_folder: Path
    log_folder: Path
    pidfile: Path
    included_files: str

    def get(self, key: str, default=None):
        """Allow access to the options as if they were attributes."""
        return getattr(self, key, default)


@dataclass(kw_only=True)
class ProgramConf:
    """
    [program:{{ options.program }}]
    command = {{ options.command }}
    process_name = {{ options.process_name }}
    directory = {{ options.directory }}
    priority = {{ options.priority }}
    """

    program: str
    command: str
    process_name: str
    directory: str
    priority: int

    def get(self, key: str, default=None):
        """Allow access to the options as if they were attributes."""
        return getattr(self, key, default)


@dataclass(kw_only=True)
class Supervisor(BaseService):

    name: str = "supervisor"

    supervisord_conf_template: str = (
        "resource://plonex.supervisor.templates:supervisord.conf.j2"
    )
    program_conf_template: str = (
        "resource://plonex.supervisor.templates:program.conf.j2"
    )

    etc_folder: Path = field(init=False)
    log_folder: Path = field(init=False)
    tmp_folder: Path = field(init=False)
    var_folder: Path = field(init=False)

    # You can override the templates used to generate the configuration files

    def __post_init__(self):
        # Be sure that the required folders exist
        self.etc_folder = self.target / "etc"
        self.tmp_folder = self.target / "tmp" / self.name
        self.var_folder = self.target / "var"
        self.log_folder = self.var_folder / "log"

        self.programs_folder = self.etc_folder / self.name

        self.target = self._ensure_dir(self.target)
        self.etc_folder = self._ensure_dir(self.etc_folder)
        self.programs_folder = self._ensure_dir(self.programs_folder)
        self.log_folder = self._ensure_dir(self.log_folder)
        self.tmp_folder = self._ensure_dir(self.tmp_folder)
        self.var_folder = self._ensure_dir(self.var_folder)

        if not self.pre_services:
            self.pre_services = [
                TemplateService(
                    source_path=self.supervisord_conf_template,
                    target_path=self.etc_folder / "supervisord.conf",
                    options=SupervisordConfOptions(
                        target=self.target,
                        var_folder=self.var_folder,
                        log_folder=self.log_folder,
                        pidfile=self.var_folder / "supervisord.pid",
                        included_files=str(self.etc_folder / self.name / "*.conf"),
                    ),
                ),
                TemplateService(
                    source_path=self.program_conf_template,
                    target_path=self.programs_folder / "zeoserver.conf.example",
                    options=ProgramConf(
                        program="zeoserver",
                        command="plonex zeoserver",
                        process_name="zeoserver",
                        directory=str(self.target),
                        priority=1,
                    ),
                ),
                TemplateService(
                    source_path=self.program_conf_template,
                    target_path=self.programs_folder / "zeoclient.conf.example",
                    options=ProgramConf(
                        program="zeoclient",
                        command="plonex zeoclient",
                        process_name="zeoclient",
                        directory=str(self.target),
                        priority=2,
                    ),
                ),
            ]

    @property
    def supervisord(self) -> sh.Command:
        """Return the supervisord command to run."""
        return sh.Command(str(self.virtualenv_dir / "bin" / "supervisord"))

    @property
    def supervisorctl(self) -> sh.Command:
        """Return the supervisord command to run."""
        return sh.Command(str(self.virtualenv_dir / "bin" / "supervisorctl"))

    @property
    def supervisord_conf(self) -> Path:
        """Return the path to the supervisord.conf file."""
        return self.etc_folder / "supervisord.conf"

    @property
    def command(self) -> list[str]:
        return [
            str(self.virtualenv_dir / "bin" / "supervisord"),
            "-c",
            str(self.supervisord_conf),
        ]

    def is_running(self) -> bool:
        """Check if supervisord is running."""
        try:
            self.supervisorctl("-c", str(self.supervisord_conf), "status")
        except sh.ErrorReturnCode:
            return False
        return True

    @BaseService.entered_only
    def initialize_configuration(self):
        self.logger.info("Creating the supervisor configuration")

    @BaseService.entered_only
    def run_status(self):
        if not self.is_running():
            self.logger.info("supervisord is not running")
            return
        output = self.supervisorctl("-c", str(self.supervisord_conf), "status")
        output = output.replace(" RUNNING ", " [green] RUNNING [/green] ")
        output = output.replace(" STOPPED ", " [red] STOPPED [/red] ")
        output = output.replace(" STARTING ", " [yellow] STARTING [/yellow] ")
        output = output.replace(" FATAL ", " [bold red] FATAL [/bold red] ")
        self.print(output)

    @BaseService.entered_only
    def run_stop(self):
        if not self.is_running():
            self.logger.info("supervisord is not running")
            return
        output = self.supervisorctl("-c", str(self.supervisord_conf), "shutdown")
        self.print(output)

    @BaseService.entered_only
    def run_restart(self):
        if not self.is_running():
            self.logger.info("supervisord is not running, starting it instead")
            return self.run()
        output = self.supervisorctl("-c", str(self.supervisord_conf), "restart", "all")
        output = output.replace(" started", "[green] started[/green]")
        output = output.replace(" stopped", "[red] stopped[/red]")
        self.print(output.rstrip())

    @BaseService.entered_only
    def run_reread(self):
        if not self.is_running():
            self.logger.info("supervisord is not running")
            return
        output = self.supervisorctl("-c", str(self.supervisord_conf), "reread")
        self.print(output)

    @BaseService.entered_only
    def run_update(self):
        if not self.is_running():
            self.logger.info("supervisord is not running")
            return
        output = self.supervisorctl("-c", str(self.supervisord_conf), "update")
        self.print(output)

    @BaseService.entered_only
    def reread_update(self):
        if not self.is_running():
            self.logger.info("supervisord is not running")
            return
        output = self.run_reread()
        self.print(output)
        output = self.run_update()
        self.print(output)
