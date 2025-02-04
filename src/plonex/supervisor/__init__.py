from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.template import TemplateService

import subprocess


@dataclass(kw_only=True)
class SupervisordConfOptions:

    target: Path
    var_folder: Path
    log_folder: Path
    pidfile: Path
    included_files: str


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
    def command(self) -> list[str]:
        return [
            str(self.virtualenv_dir / "bin" / "supervisord"),
            "-c",
            str(self.target / "etc" / "supervisord.conf"),
        ]

    @BaseService.entered_only
    def initialize_configuration(self):
        self.logger.info("Creating the supervisor configuration")

    @BaseService.entered_only
    def run_status(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "status",
            ]
        )

    @BaseService.entered_only
    def run_stop(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "shutdown",
            ]
        )

    @BaseService.entered_only
    def run_restart(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "restart all",
            ]
        )

    @BaseService.entered_only
    def run_reread(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "reread",
            ]
        )

    @BaseService.entered_only
    def run_update(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "update",
            ]
        )

    @BaseService.entered_only
    def reread_update(self):
        self.run_reread()
        self.run_update()
