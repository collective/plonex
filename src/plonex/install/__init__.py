from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from pip_requirements_parser import RequirementsFile  # type: ignore
from plonex.base import BaseService
from rich.console import Console

import subprocess


@dataclass(kw_only=True)
class InstallService(BaseService):

    name = "install"

    target: Path = field(default_factory=Path.cwd)
    etc_folder: Path | None = None
    tmp_folder: Path | None = None
    var_folder: Path | None = None

    requirements_d_folder: Path | None = None
    constraints_d_folder: Path | None = None

    requirements_txt: Path | None = field(init=False, default=None)
    constrainst_txt: Path | None = field(init=False, default=None)

    dont_ask: bool = False

    def __post_init__(self):
        self.target = self._ensure_dir(self.target.absolute())
        self.etc_folder = self._ensure_dir(self.etc_folder or self.target / "etc")
        self.tmp_folder = self._ensure_dir(self.tmp_folder or self.target / "tmp")
        self.var_folder = self._ensure_dir(self.var_folder or self.target / "var")

        self.requirements_d_folder = self._ensure_dir(
            self.requirements_d_folder or self.etc_folder / "requirements.d"
        )
        self.constraints_d_folder = self._ensure_dir(
            self.constraints_d_folder or self.etc_folder / "constraints.d"
        )

    @property
    def default_python(self):
        """Check with python executable is available"""
        for python in ["python3", "python"]:
            which = subprocess.run(
                ["which", python],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            if which.returncode == 0:
                return which.stdout.decode().strip()

    def ensure_virtualenv(self):
        """Ensure that we have a virtualenv"""
        if not (self.target / ".venv" / "bin" / "activate").exists():
            if self.dont_ask:
                python_path = self.default_python
            else:
                console = Console()
                python_path = (
                    console.input(
                        f"Please select the Python executable "
                        f"(default: {self.default_python}): "
                    )
                    or self.default_python
                )
            self.logger.info("Creating a virtualenv")
            subprocess.run(
                [str(python_path), "-m", "venv", str(self.target / ".venv")],
                check=True,
            )

        if not (self.virtualenv_dir / "bin" / "uv").exists():
            self.logger.info("Installing uv")
            subprocess.run(
                [
                    str(self.virtualenv_dir / "bin" / "pip"),
                    "install",
                    "uv",
                ],
                check=True,
            )

    @BaseService.entered_only
    def install_package(self, package: str):
        """Install a package in the virtualenv respecting the constraints"""
        self.ensure_virtualenv()
        self.logger.info("Installing %r", package)
        command = [
            str(self.virtualenv_dir / "bin" / "uv"),
            "pip",
            "install",
            package,
            "-c",
            str(self.constrainst_txt.absolute()),  # type: ignore
        ]
        subprocess.run(
            command,
            check=True,
        )

    def make_requirements_txt(self):
        """This will merge the requirements files in one big requirements.txt file"""
        lines = []
        for file in sorted(self.requirements_d_folder.iterdir()):
            lines.append(f"-r {file.absolute()}")
        self.requirements_txt = self.var_folder / "requirements.txt"
        with open(self.requirements_txt, "w") as file:
            file.write("# This file is generated by plonex\n")
            file.write("\n".join(lines))

    def make_constraints_txt(self):
        """Merge the constraints files in one big constraints.txt file"""
        included_files = []
        constraints = {}
        for file in self.constraints_d_folder.iterdir():
            requirements = RequirementsFile.from_file(file, include_nested=True)
            for requirement in requirements.requirements:
                constraints[str(requirement.name), str(requirement.marker)] = (
                    requirement
                )

        merged_constraints = included_files + [
            requirement.dumps() for _, requirement in sorted(constraints.items())
        ]

        self.constrainst_txt = self.var_folder / "constraints.txt"

        with open(self.constrainst_txt, "w") as file:
            file.write("# This file is generated by plonex\n")
            file.write("\n".join(merged_constraints))

    @property
    def command(self):
        return [
            str(self.virtualenv_dir / "bin" / "uv"),
            "pip",
            "install",
            "-r",
            str(self.requirements_txt.absolute()),
            "-c",
            str(self.constrainst_txt.absolute()),
        ]

    def __enter__(self):
        super().__enter__()
        self.ensure_virtualenv()
        self.make_requirements_txt()
        self.make_constraints_txt()
        return self

    @BaseService.entered_only
    def run(self):
        # Check if we have a virtualenv and if not create one
        self.ensure_virtualenv()
        super().run()
        # Run pip freeze and compare the output with the constraints
        # to see if we are missing something
        self.logger.info("Checking if all constraints are met")

        constraints = RequirementsFile.from_file(self.constrainst_txt).requirements
        installed = subprocess.run(
            [str(self.virtualenv_dir / "bin" / "pip"), "freeze"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.decode()

        # Save the installed packages to a temporary file
        with open(self.tmp_folder / "installed.txt", "w") as file:
            file.write(installed)

        installed = RequirementsFile.from_file(file.name).requirements

        # XXX: This is an hack because the parser
        # does not return normalized package names
        missing = {req.dumps().lower().replace("_", "-") for req in installed} - {
            req.dumps().lower().replace("_", "-") for req in constraints
        }

        if missing:
            self.logger.warning(f"Missing constraints: {sorted(missing)}")
            console = Console()
            console.print(
                f"You may want to add the following constraints to a file "
                f"in the {self.constraints_d_folder}:"
            )
            console.print(*sorted(missing), sep="\n")
