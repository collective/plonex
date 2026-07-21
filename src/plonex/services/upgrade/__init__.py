from dataclasses import dataclass
from plonex.base import BaseService
from tempfile import TemporaryDirectory


@dataclass(kw_only=True)
class UpgradeService(BaseService):
    name: str = "upgrade"

    @BaseService.entered_only
    def run(self):
        upgrade = self.virtualenv_dir / "bin" / "upgrade"
        with TemporaryDirectory() as auth_dir:
            self.options["environment_vars"]["UPGRADE_TEMPFILE_AUTH_DIR"] = auth_dir
            self.run_command([upgrade, "plone_upgrade", "-A"])
            self.run_command([upgrade, "install", "-Ap"])
