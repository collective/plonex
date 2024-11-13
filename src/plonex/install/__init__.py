from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService

import subprocess


@dataclass
class InstallService(BaseService):

    target: Path = field(default_factory=Path.cwd)
    etc_folder: Path | None = None
    tmp_folder: Path | None = None

    requirements_d_folder: Path | None = None
    constraints_d_folder: Path | None = None

    requirements_txt: Path | None = field(init=False, default=None)
    constrainst_txt: Path | None = field(init=False, default=None)

    def __post_init__(self):
        self.target = self._ensure_dir(self.target)
        self.etc_folder = self._ensure_dir(self.etc_folder or self.target / "etc")
        self.tmp_folder = self._ensure_dir(self.tmp_folder or self.target / "tmp")
        self.requirements_d_folder = self._ensure_dir(
            self.requirements_d_folder or self.etc_folder / "requirements.d"
        )
        self.constraints_d_folder = self._ensure_dir(
            self.constraints_d_folder or self.etc_folder / "constraints.d"
        )

    def make_requirements_txt(self):
        """This will merge therequiremets files in one big requirements.txt file"""
        lines = []
        for file in self.requirements_d_folder.iterdir():
            lines.append(f"-r {file.absolute()}")
        self.requirements_txt = self.etc_folder / "requirements.txt"
        self.requirements_txt.write_text("\n".join(lines))

    def make_constraints_txt(self):
        """merge the constraints files in one big constraints.txt file

        Assume the constraints are in a form like:

        package==X.Y.Z

        If the line is not a comment, an empty line or matches this pattern
        we will raise an error
        """
        constraints = {}
        for file in self.constraints_d_folder.iterdir():
            for line in file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "==" not in line:
                    raise ValueError(f"Invalid constraint {line}")
                package, version = line.partition("==")[::2]
                constraints[package] = version
        self.constrainst_txt = self.etc_folder / "constraints.txt"
        self.constrainst_txt.write_text(
            "\n".join(
                f"{package}=={version}"
                for package, version in sorted(constraints.items())
            )
        )

    @property
    def command(self):
        return [
            str(self.executable_dir / "uv"),
            "pip",
            "install",
            "-r",
            str(self.requirements_txt),
            "-c",
            str(self.constrainst_txt),
        ]

    def __enter__(self):
        super().__enter__()
        self.make_requirements_txt()
        self.make_constraints_txt()
        return self

    @BaseService.active_only
    def run(self):
        super().run()
        # Run pip freeze and compare the output with the constraints
        # to see if we are missing something
        self.logger.info("Checking if all constraints are met")
        constraints = set(self.constrainst_txt.read_text().splitlines())
        installed = set(
            subprocess.run(
                [str(self.executable_dir / "pip"), "freeze"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            .stdout.decode()
            .splitlines()
        )
        missing = installed - constraints
        if missing:
            self.logger.error(f"Missing constraints: {sorted(missing)}")
            print(*sorted(missing), sep="\n")
