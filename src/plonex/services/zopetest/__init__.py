from dataclasses import dataclass
from plonex.base import BaseService
from typing import ClassVar


@dataclass(kw_only=True)
class ZopeTest(BaseService):

    name: str = "zopetest"
    stream_output: ClassVar[bool] = True
    package: str = ""
    test: str = ""

    @property
    def options_defaults(self):
        options_defaults = super().options_defaults
        options_defaults.update(
            {
                "environment_vars": {
                    "ZSERVER_HOST": "127.0.0.2",
                    "ZSERVER_PORT": "55001",
                }
            }
        )
        return options_defaults

    @property
    def command(self) -> list[str]:
        """Build a zope-testrunner command with the most common arguments."""
        command = [
            str(self.virtualenv_dir / "bin" / "zope-testrunner"),
            "--all",
            "--quiet",
            "-pvc",
            "--package",
            self.package,
            "--auto-path",
        ]
        if self.test:
            command += ["-t", self.test]

        return command
