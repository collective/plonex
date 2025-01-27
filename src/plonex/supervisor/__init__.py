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

    name = "supervisor"

    target: Path = field(default_factory=Path.cwd)

    etc_folder: Path | None = None
    log_folder: Path | None = None
    tmp_folder: Path | None = None
    var_folder: Path | None = None

    # You can override the templates used to generate the configuration files
    supervisord_conf_template: str = (
        "resource://plonex.supervisor.templates:supervisord.conf.j2"
    )
    program_conf_template: str = (
        "resource://plonex.supervisor.templates:program.conf.j2"
    )

    def __post_init__(self):
        # Be sure that the required folders exist
        if self.etc_folder is None:
            self.etc_folder = self.target / "etc"
        if self.tmp_folder is None:
            self.tmp_folder = self.target / "tmp" / self.name
        if self.var_folder is None:
            self.var_folder = self.target / "var"
        if self.log_folder is None:
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

    def run_status(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "status",
            ]
        )

    def run_stop(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "shutdown",
            ]
        )

    def run_restart(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "restart all",
            ]
        )

    def run_reread(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "reread",
            ]
        )

    def run_update(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.target / "etc" / "supervisord.conf"),
                "update",
            ]
        )

    def reread_update(self):
        self.run_reread()
        self.run_update()
