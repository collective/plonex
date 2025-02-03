from contextlib import chdir
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.template import TemplateService
from typing import Literal

import subprocess
import yaml


_undefined = object()

default_options = {
    "http_port": 8080,
    "http_address": "0.0.0.0",
    "zeo_address": _undefined,
    "blobstorage": _undefined,
    "zcml_additional": _undefined,
    "zope_conf_additional": _undefined,
}


@dataclass(kw_only=True)
class ZeoClient(BaseService):
    """This is a context manager that allows to run a ZEO client

    The ZEO client configuration is generated in a temporary folder
    Once the context manager is entered, the configuration files are created
    and the ZEO client is started with the `run` method

    Once the context manager is exited, the temporary folder is removed

    Example:
    with ZeoClient() as zeoclient:
        zeoclient.run()

    To stop the process you can use Ctrl+C
    or kill the process with the signal 15
    """

    # Those are the most important parameters passed to the constructor
    name: str = "zeoclient"
    target: Path = field(default_factory=Path.cwd)
    config_files: list[str | Path] = field(default_factory=list)

    # This control how the program runs
    run_mode: Literal[
        "console",
        "fg",
        "start",
        "stop",
        "status",
        "debug",
    ] = "console"  # This is the default for the supervisor program

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

        # Ensure self.config_files is a list of Paths
        self.config_files = [
            Path(file) if isinstance(file, str) else file for file in self.config_files
        ]

        # We will read the config files and update the default options
        for path in self.config_files:
            if not path.is_file():
                self.logger.error("Config file %r is not valid", path)
            else:
                with path.open() as stream:
                    self.logger.info("Reading %r", path)
                    new_options = yaml.safe_load(stream)
                    if not isinstance(new_options, dict):
                        self.logger.error(
                            "The config file %r should contain a dict", path
                        )
                    else:
                        self.options.update(new_options)

        # Command line options will win over the config file options
        self.options.update(self.cli_options)

        # Ensure that the required undefined options are set
        if self.options["zeo_address"] is _undefined:
            self.options["zeo_address"] = self.var_folder / "zeosocket.sock"

        if self.options["blobstorage"] is _undefined:
            self.options["blobstorage"] = self.var_folder / "blobstorage"

        if not self.pre_services:
            # We need to have the following structure in the tmp folder:
            # - etc/zope.conf
            # - etc/site.zcml
            # - etc/wsgi.ini
            # - bin/interpreter
            # - bin/instance
            self.pre_services = [
                TemplateService(
                    source_path="resource://plonex.zeoclient.templates:zope.conf.j2",
                    target_path=self.tmp_folder / "etc" / "zope.conf",
                    options={
                        "context": self,
                        "instance_home": self._ensure_dir(self.tmp_folder),
                        "client_home": self._ensure_dir(self.var_folder / self.name),
                        "debug_mode": self.options.get("debug_mode")
                        or ("on" if self.run_mode in ("debug", "fg") else "off"),
                        "security_policy_implementation": self.options.get(
                            "security_policy_implementation"
                        )
                        or ("python" if self.run_mode in ("debug", "fg") else "C"),
                        "environment_vars": self.options.get("environment_vars", {}),
                        "verbose_security": self.options.get("verbose_security")
                        or ("on" if self.run_mode in ("debug", "fg") else "off"),
                        "blobstorage": self.options["blobstorage"],
                        "zeo_address": self.options["zeo_address"],
                    },
                ),
                TemplateService(
                    source_path="resource://plonex.zeoclient.templates:site.zcml.j2",
                    target_path=self.tmp_folder / "etc" / "site.zcml",
                ),
                TemplateService(
                    source_path="resource://plonex.zeoclient.templates:wsgi.ini.j2",
                    target_path=self.tmp_folder / "etc" / "wsgi.ini",
                    options={
                        "context": self,
                        "name": f"instance-{self.options['http_port']}",
                        "zope_conf": self.tmp_folder / "etc" / "zope.conf",
                        "var_folder": self.var_folder,
                        "http_port": self.options["http_port"],
                        "http_address": self.options["http_address"],
                        "fast_listen": self.options.get("fast_listen", "on"),
                        "threads": self.options.get("threads", 4),
                    },
                ),
                TemplateService(
                    source_path="resource://plonex.zeoclient.templates:interpreter.j2",
                    target_path=self.tmp_folder / "bin" / "interpreter",
                    options={
                        "context": self,
                        "python": Path(self.virtualenv_dir / "bin" / "python"),
                    },
                ),
                TemplateService(
                    source_path="resource://plonex.zeoclient.templates:instance.j2",
                    target_path=self.tmp_folder / "bin" / "instance",
                    options={
                        "context": self,
                        "python": self.virtualenv_dir / "bin" / "python",
                        "zope_conf_path": self.tmp_folder / "etc" / "zope.conf",
                        "interpreter_path": self.tmp_folder / "bin" / "interpreter",
                        "wsgi_ini_path": self.tmp_folder / "etc" / "wsgi.ini",
                    },
                    mode=0o700,
                ),
            ]

            # Check zcml_additional
            zcml_additional = self.options["zcml_additional"]
            if zcml_additional is not _undefined:
                if not isinstance(zcml_additional, list):
                    raise ValueError("zcml_additional should be a list of templates")
                for template in zcml_additional:
                    # Find the proper target path
                    if template.suffix == ".j2":
                        suffix = ""
                    target_path = Path(
                        self.tmp_folder / "etc" / "package-includes" / template.name
                    ).with_suffix(suffix)
                    if not target_path.suffix == ".zcml":
                        target_path = target_path.with_suffix(".zcml")

                    self.pre_services.append(
                        TemplateService(
                            source_path=template,
                            target_path=target_path,
                            options={"context": self},
                        )
                    )

    @property
    def zope_conf_additional(self) -> list[TemplateService]:
        """List the templates in the zope_conf_additional option"""
        zope_conf_additional = self.options["zope_conf_additional"]
        if zope_conf_additional is _undefined:
            return []

        if not isinstance(zope_conf_additional, list):
            raise ValueError("zope_conf_additional should be a list of templates")

        return [
            TemplateService(
                source_path=template,
                options={"context": self},
            )
            for template in zope_conf_additional
        ]

    @property
    def command(self):
        # return [self.instance, self.run_mode]
        return [str(self.tmp_folder / "bin" / "instance"), self.run_mode]

    @BaseService.entered_only
    def adduser(self, username: str, password: str):
        with chdir(self.target):  # type: ignore
            command = [
                str(self.tmp_folder / "bin" / "instance"),  # type: ignore
                "adduser",
                username,
                password,
            ]
            self.logger.info("Running %r", command)
            try:
                subprocess.run(command, check=True)
            except KeyboardInterrupt:
                self.logger.info("Stopping %r", command)
