from dataclasses import dataclass
from dataclasses import field
from plonex.base import ZopeBasedService
from typing import ClassVar
from typing import Literal


@dataclass(kw_only=True)
class ZConsole(ZopeBasedService):
    """Run zconsole commands with generated Zope runtime configuration."""

    name: str = "zconsole"

    action: Literal["debug", "run"] = "debug"
    args: list[str] = field(default_factory=list)
    stream_output: ClassVar[bool] = True

    def __post_init__(self):
        super().__post_init__()
        if not self.pre_services:
            if self.action != "debug":
                self.pre_services = self._build_zope_pre_services()
            else:
                self.pre_services = self._build_zope_pre_services(
                    debug_mode="on",
                    security_policy_implementation="python",
                    verbose_security="on",
                )

    @property
    def command(self):
        assert (
            self.tmp_folder is not None
        ), "tmp_folder should be set before accessing command"
        return [
            str(self.virtualenv_dir / "bin" / "zconsole"),
            self.action,
            str(self.tmp_folder / "etc" / "zope.conf"),
            *self.args,
        ]
