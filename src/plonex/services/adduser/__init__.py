from contextlib import chdir
from dataclasses import dataclass
from plonex.base import ZopeBasedService
from typing import ClassVar


@dataclass(kw_only=True)
class AddUser(ZopeBasedService):
    """Add a user to the Zope instance via addzopeuser."""

    name: str = "adduser"

    username: str = ""
    password: str | None = None
    stream_output: ClassVar[bool] = True

    def __post_init__(self):
        # Reuse the zconsole tmp folder so the Zope config is shared.
        if self.tmp_folder is None:
            self.tmp_folder = self.target / "tmp" / "zconsole"
        super().__post_init__()
        if not self.pre_services:
            self.pre_services = self._build_zope_pre_services()

    @ZopeBasedService.entered_only
    def run(self):
        """Add the user."""
        is_password_generated = self.password is None
        password = self.password or self._generate_password()

        assert self.tmp_folder is not None, "tmp_folder should be set before running"
        zope_conf = self.tmp_folder / "etc" / "zope.conf"

        with chdir(self.target):
            command = [
                str(self.virtualenv_dir / "bin" / "addzopeuser"),
                "-c",
                zope_conf,
                self.username,
                str(password),
            ]
            self.logger.debug("Running %r", command)
            try:
                self.execute_command(command)
            except KeyboardInterrupt:
                self.logger.info("Stopping %r", command)
        if is_password_generated:
            print(f"Please take note of the {self.username} password: {password}")
