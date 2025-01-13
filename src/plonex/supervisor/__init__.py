from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.template import render

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

    # Location of the supervisord configuration file
    supervisord_conf: Path | None = None

    # You can override the templates used to generate the configuration files
    supervisord_conf_template: str = "plonex.supervisor.templates:supervisord.conf.j2"
    program_conf_template: str = "plonex.supervisor.templates:program.conf.j2"

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
        if self.supervisord_conf is None:
            self.supervisord_conf = self.etc_folder / "supervisord.conf"

    def make_zeoserver_program_conf_example(self):
        options = ProgramConf(
            program="zeoserver",
            command="plonex zeoserver",
            process_name="zeoserver",
            directory=str(self.target),
            priority=1,
        )
        program_conf = self.programs_folder / "zeoserver.conf.example"
        with open(program_conf, "w") as f:
            f.write(render(self.program_conf_template, options))
            f.write("\n")
        self.logger.info("Generated %r", program_conf)

    def make_zeoclient_program_conf_example(self):
        options = ProgramConf(
            program="zeoclient",
            command="plonex zeoclient",
            process_name="zeoclient",
            directory=str(self.target),
            priority=2,
        )
        program_conf = self.programs_folder / "zeoclient.conf.example"
        with open(program_conf, "w") as f:
            f.write(render(self.program_conf_template, options))
            f.write("\n")
        self.logger.info("Generated %r", program_conf)

    def make_supervisord_conf(self):
        options = SupervisordConfOptions(
            target=self.target,
            var_folder=self.var_folder,
            log_folder=self.log_folder,
            pidfile=self.var_folder / "supervisord.pid",
            included_files=self.etc_folder / self.name / "*.conf",
        )
        with open(self.supervisord_conf, "w") as f:
            f.write(render(self.supervisord_conf_template, options))
            f.write("\n")
        self.logger.info(f"Generated {self.supervisord_conf}")

    def check_if_running(self):
        command = [
            str(self.virtualenv_dir / "bin" / "supervisorctl"),
            "-c",
            str(self.supervisord_conf),
            "status",
        ]
        exit_code = subprocess.run(
            command,
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
            return self
        self = super().__enter__()
        self.make_supervisord_conf()
        self.make_zeoserver_program_conf_example()
        self.make_zeoclient_program_conf_example()
        return self

    @property
    def command(self) -> list[str]:
        return [
            str(self.virtualenv_dir / "bin" / "supervisord"),
            "-c",
            str(self.supervisord_conf),
        ]

    def run_status(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.supervisord_conf),
                "status",
            ]
        )

    def run_stop(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.supervisord_conf),
                "shutdown",
            ]
        )

    def run_restart(self):
        subprocess.run(
            [
                str(self.virtualenv_dir / "bin" / "supervisorctl"),
                "-c",
                str(self.supervisord_conf),
                "restart all",
            ]
        )
