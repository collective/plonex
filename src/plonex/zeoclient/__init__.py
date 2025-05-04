from contextlib import chdir
from dataclasses import dataclass
from pathlib import Path
from plonex.base import BaseService
from plonex.template import TemplateService
from random import choice
from string import ascii_letters
from string import digits
from string import punctuation
from typing import Literal

import os
import subprocess
import sys


_undefined = object()


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

    name: str = "zeoclient"

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

    @property
    def options_defaults(self):
        return {
            "http_port": 8080,
            "http_address": "0.0.0.0",
            "zeo_address": str(self.var_folder / "zeosocket.sock"),
            "blobstorage": str(self.var_folder / "blobstorage"),
            "zcml_additional": [],
            "zope_conf_additional": [],
        }

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
            if not isinstance(zcml_additional, list):
                raise ValueError("zcml_additional should be a list of templates")
            for template in map(Path, zcml_additional):
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
    def pid_file(self) -> Path:
        """Return the pid file for the ZEO client"""
        if not self.var_folder:
            raise ValueError("var_folder is not set")
        return self.var_folder / self.name / "Z4.pid"

    @property
    def zope_conf_additional(self) -> list[TemplateService]:
        """List the templates in the zope_conf_additional option"""
        zope_conf_additional = self.options["zope_conf_additional"]
        if not isinstance(zope_conf_additional, list):
            raise ValueError("zope_conf_additional should be a list of templates")

        return [
            TemplateService(
                source_path=template,
                options={"context": self},
            )
            for template in zope_conf_additional
        ]

    def _generate_password(self):
        """Generate a random password"""
        return "".join(choice(ascii_letters + digits + punctuation) for _ in range(16))

    @property
    def command(self):
        """Before runniong check if the pid file is present and used"""
        if self.pid_file.exists():
            pid = self.pid_file.read_text()
            try:
                if os.kill(int(pid), 0) is None:
                    self.logger.error(
                        "The pid file %s exists and the process is running",
                        self.pid_file,
                    )
                    sys.exit(0)
            except OSError:
                pass

        return [str(self.tmp_folder / "bin" / "instance"), self.run_mode]

    @BaseService.entered_only
    def adduser(self, username: str, password: str | None = None):
        """Add a user to the Zope instance"""
        is_password_generated = password is None
        if password is None:
            password = self._generate_password()

        zope_conf = self.tmp_folder / "etc" / "zope.conf"  # type: ignore

        with chdir(self.target):  # type: ignore
            command = [
                str(self.virtualenv_dir / "bin" / "addzopeuser"),  # type: ignore
                "-c",
                zope_conf,
                username,
                str(password),
            ]
            self.logger.debug("Running %r", command)
            try:
                subprocess.run(command)
            except KeyboardInterrupt:
                self.logger.info("Stopping %r", command)
        if is_password_generated:
            print(f"Please take note of the {username} password: {password}")
