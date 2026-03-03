from dataclasses import dataclass
from plonex.base import BaseService


@dataclass(kw_only=True)
class RobotServer(BaseService):

    name: str = "robotserver"
    layer: str = "Products.CMFPlone.testing.PRODUCTS_CMFPLONE_ROBOT_TESTING"

    @property
    def options_defaults(self):
        options_defaults = super().options_defaults
        options_defaults.update(
            {
                "environment_vars": {
                    "ZSERVER_HOST": "127.0.0.2",
                    "ZSERVER_PORT": "55001",
                    "DIAZO_ALWAYS_CACHE_RULES": "1",
                }
            }
        )
        return options_defaults

    @property
    def command(self) -> list[str]:
        return [
            str(self.virtualenv_dir / "bin" / "robot-server"),
            "--debug-mode",
            "--verbose",
            self.layer,
        ]
