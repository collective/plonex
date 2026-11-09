from dataclasses import dataclass
from dataclasses import field
from plonex.base import BaseService
from typing import ClassVar


@dataclass(kw_only=True)
class PytestService(BaseService):
    """Run pytest using the target project's interpreter and configuration."""

    name: str = "pytest"
    stream_output: ClassVar[bool] = True
    package: str = ""
    args: list[str] = field(default_factory=list)

    @property
    def command(self) -> list[str]:
        if not self.package:
            raise ValueError("A Python package or test path is required for pytest")
        args = self.args[1:] if self.args[:1] == ["--"] else self.args
        return [
            str(self.virtualenv_dir / "bin" / "python"),
            "-m",
            "pytest",
            "--pyargs",
            self.package,
            *args,
        ]
