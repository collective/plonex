from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.template import render

import subprocess


@dataclass
class SupervisordConfOptions:

    target: Path
    var_folder: Path
    log_folder: Path
    pidfile: Path
    included_files: str


@dataclass
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


@dataclass
class Supervisor(BaseService):

    name = "supervisor"

    target: Path = field(default_factory=Path.cwd)
    supervisord_conf_template: str = "plonex.supervisor.templates:supervisord.conf.j2"
    program_conf_template: str = "plonex.supervisor.templates:program.conf.j2"
    etc_folder: Path | None = None
    tmp_folder: Path | None = None
    var_folder: Path | None = None
    log_folder: Path | None = None

    conf_folder: Path | None = field(init=False, default=None)
    supervisord_conf: Path | None = field(init=False, default=None)

    def __post_init__(self):
        self.target = self._ensure_dir(self.target)
        self.etc_folder = self._ensure_dir(self.etc_folder or self.target / "etc")
        self.tmp_folder = self._ensure_dir(self.tmp_folder or self.target / "tmp")
        self.var_folder = self._ensure_dir(self.var_folder or self.target / "var")
        self.log_folder = self._ensure_dir(self.log_folder or self.var_folder / "log")
        self.supervisord_conf = self.etc_folder / "supervisord.conf"

    def make_zeoserver_program_conf(self):
        options = ProgramConf(
            program="zeoserver",
            command=f"{self.executable_dir / "plonex"} zeoserver",
            process_name="zeoserver",
            directory=str(self.target),
            priority=1,
        )
        program_conf = self.conf_folder / "zeoserver.conf"
        program_conf.write_text(render(self.program_conf_template, options))
        self.logger.info("Generated %r", program_conf)

    def make_zeoclient_program_conf(self):
        options = ProgramConf(
            program="zeoclient",
            command=f"{self.executable_dir / "plonex"} zeoclient",
            process_name="zeoclient",
            directory=str(self.target),
            priority=2,
        )
        program_conf = self.conf_folder / "zeoclient.conf"
        program_conf.write_text(render(self.program_conf_template, options))
        self.logger.info("Generated %r", program_conf)

    def make_supervisord_conf(self):
        options = SupervisordConfOptions(
            target=self.target,
            var_folder=self.var_folder,
            log_folder=self.log_folder,
            pidfile=self.tmp_folder / "supervisord.pid",
            included_files=self.conf_folder / "*.conf",
        )
        self.supervisord_conf.write_text(
            render(self.supervisord_conf_template, options)
        )
        self.logger.info(f"Generated {self.supervisord_conf}")

    def check_if_running(self):
        exit_code = subprocess.run(
            [
                str(self.executable_dir / "supervisorctl"),
                "-c",
                str(self.supervisord_conf),
                "status",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).returncode
        self.logger.info("Supervisorctl returns %r", exit_code)
        if exit_code:
            return False
        return True

    def __enter__(self):
        if self.check_if_running():
            self._entered = True
            self.conf_folder = None
            return self
        self = super().__enter__()
        self.make_zeoserver_program_conf()
        self.make_zeoclient_program_conf()
        self.make_supervisord_conf()
        return self

    @property
    def command(self) -> list[str]:
        return [
            str(self.executable_dir / "supervisord"),
            "-c",
            str(self.supervisord_conf),
        ]

    @BaseService.active_only
    def run(self):
        if not self.conf_folder:
            return
        return super().run()

    def run_status(self):
        subprocess.run(
            [
                str(self.executable_dir / "supervisorctl"),
                "-c",
                str(self.supervisord_conf),
                "status",
            ]
        )

    def run_stop(self):
        subprocess.run(
            [
                str(self.executable_dir / "supervisorctl"),
                "-c",
                str(self.supervisord_conf),
                "shutdown",
            ]
        )

    def run_restart(self):
        subprocess.run(
            [
                str(self.executable_dir / "supervisorctl"),
                "-c",
                str(self.supervisord_conf),
                "restart all",
            ]
        )
