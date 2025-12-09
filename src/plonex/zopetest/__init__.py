from dataclasses import dataclass
from pathlib import Path
from plonex.base import BaseService
from textwrap import dedent

import sh  # type: ignore[import-untyped]


@dataclass(kw_only=True)
class ZopeTest(BaseService):

    name: str = "zopetest"
    package: str = ""
    test: str = ""

    @property
    def options_defaults(self):
        return {
            "environment_vars": {
                "ZSERVER_HOST": "127.0.0.2",
                "ZSERVER_PORT": "55001",
            }
        }

    @property
    def package_path(self) -> str:
        """Given a package, find its path within the project.

        package is something like collective.foobar
        we want to find whatever/collective.foobar/src

        Probably using importlib
        """
        if not self.package:
            return ""

        # Use the virtualenv's python to find the package
        python_path = str(self.virtualenv_dir / "bin" / "python")
        python = sh.Command(python_path)
        origin = python(
            "-c",
            f"from importlib.util import find_spec;"
            f"spec = find_spec({self.package!r}); "
            f"print(getattr(spec, 'origin', ''), end='')",
        )

        if not origin:
            return ""
        return str(Path(origin.strip()).parent)

    @property
    def command(self) -> list[str]:
        """Build a zope-testrunner command with the most common arguments."""
        package_path = self.package_path
        if not package_path:
            self.logger.warning(
                dedent(
                    """\
                    No package path found for %r, you may want to try running zope-testrunner manually.
                    $ zope-testrunner -pvc -t %s <path to %s>
                    """  # noqa: E501
                ),
                self.package,
                self.test,
                self.package,
            )
            return []
        command = [
            str(self.virtualenv_dir / "bin" / "zope-testrunner"),
            "--all",
            "--quiet",
            "-pvc",
            "--path",
            package_path,
        ]
        if self.test:
            command += ["-t", self.test]

        return command
