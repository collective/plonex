from dataclasses import dataclass
from dataclasses import field
from plonex.base import BaseService


@dataclass(kw_only=True)
class RobotTest(BaseService):

    name: str = "robottest"
    layer: str = "Products.CMFPlone.testing.PRODUCTS_CMFPLONE_ROBOT_TESTING"
    paths: list[str] = field(default_factory=list)
    browser: str = "firefox"
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
    def command(self) -> list[str]:
        command = [
            str(self.virtualenv_dir / "bin" / "robot"),
            "--variable",
            f"BROWSER:{self.browser}",
        ]
        if self.test:
            command += ["-t", self.test]
        command += self.paths
        return command
