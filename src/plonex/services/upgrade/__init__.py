from dataclasses import dataclass
from plonex.base import BaseService


@dataclass(kw_only=True)
class UpgradeService(BaseService):
    name: str = "upgrade"

    @BaseService.entered_only
    def run(self):
        upgrade = self.virtualenv_dir / "bin" / "upgrade"
        self.run_command([upgrade, "plone_upgrade", "-A"])
        self.run_command([upgrade, "install", "-Ap"])
