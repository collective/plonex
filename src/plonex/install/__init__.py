from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from functools import cached_property
from importlib import resources
from pathlib import Path
from pip_requirements_parser import RequirementsFile  # type: ignore
from plonex.base import BaseService
from plonex.sources import SourcesService
from rich.console import Console
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin
from urllib.parse import urlparse

import re
import requests
import sh  # type: ignore[import-untyped]
import tomllib


def name_as_pep503(name: str) -> str:
    """Return a package name that is compatible with PEP 503"""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(kw_only=True)
class InstallService(BaseService):

    name: str = "install"
    dont_ask: bool = False

    etc_folder: Path = field(init=False)
    tmp_folder: Path = field(init=False)
    var_folder: Path = field(init=False)

    requirements_d_folder: Path = field(init=False)
    constraints_d_folder: Path = field(init=False)
    requirements_txt: Path = field(init=False)
    constrainst_txt: Path = field(init=False)

    @cached_property
    def options_defaults(self) -> dict:
        options_defaults = super().options_defaults
        options_defaults["plone_version"] = "6.1-latest"
        options_defaults["plonex_base_constraint"] = (
            "https://dist.plone.org/release/{{ plone_version }}/constraints.txt"
        )
        return options_defaults

    def __post_init__(self):
        self.target = self._ensure_dir(self.target.absolute())
        self.etc_folder = self._ensure_dir(self.target / "etc")
        self.tmp_folder = self._ensure_dir(self.target / "tmp")
        self.var_folder = self._ensure_dir(self.target / "var")
        self.requirements_d_folder = self._ensure_dir(
            self.etc_folder / "requirements.d"
        )
        self.constraints_d_folder = self._ensure_dir(self.etc_folder / "constraints.d")

    @property
    def default_python(self):
        """Check with python executable is available"""
        if "python" in self.options:
            return self.options["python"]

        for python in ["python3", "python"]:
            try:
                return self.execute_command(["which", python]).strip()
            except sh.ErrorReturnCode:
                continue

    def ensure_virtualenv(self):
        """Ensure that we have a virtualenv"""
        if not (self.target / ".venv" / "bin" / "activate").exists():
            if self.options.get("python") or self.dont_ask:
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
            self.execute_command(
                [str(python_path), "-m", "venv", str(self.target / ".venv")]
            )

        if not (self.virtualenv_dir / "bin" / "uv").exists():
            self.logger.info("Installing uv")
            self.execute_command(
                [
                    str(self.virtualenv_dir / "bin" / "pip"),
                    "install",
                    "uv",
                ]
            )

    @BaseService.entered_only
    def add_packages(self, packages: list):
        """Add a list of packages to the requirements"""
        now = datetime.now()
        time_marker = now.strftime("%Y%m%d-%H%M%S")
        lines = [
            "# Packages added by plonex install",
        ]
        lines.extend(sorted(packages))
        (self.requirements_d_folder / f"999-add-package-{time_marker}.txt").write_text(
            "\n".join(lines) + "\n"
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
        self.execute_command(command)

    def make_requirements_txt(self):
        """This will merge the requirements files in one big requirements.txt file"""
        lines = []
        for requirements_folder in self._requirements_d_folders():
            for file in sorted(requirements_folder.iterdir()):
                if file.is_file():
                    lines.append(f"-r {file.absolute()}")

        # Allow users to append direct pip requirement specs from YAML options.
        raw_pip_requirements = self.options.get("pip_requirements") or []
        if isinstance(raw_pip_requirements, str):
            raw_pip_requirements = [raw_pip_requirements]
        if isinstance(raw_pip_requirements, list):
            for requirement in raw_pip_requirements:
                if isinstance(requirement, str) and requirement not in lines:
                    lines.append(requirement)

        self.requirements_txt = self.var_folder / "requirements.txt"
        with open(self.requirements_txt, "w") as file:
            file.write("# This file is generated by plonex\n")
            file.write("\n".join(lines))

    def resolve_package_name_from_path(self, requirement) -> str:
        """Resolve the package name from a path"""
        path = Path(requirement.link.path)

        pyproject_toml = path / "pyproject.toml"
        if pyproject_toml.exists():
            pyproject = tomllib.loads(pyproject_toml.read_text())

            try:
                return pyproject["project"]["name"]
            except KeyError:
                try:
                    return pyproject["tool"]["poetry"]["name"]
                except KeyError:
                    pass

        setup_cfg_path = path / "setup.cfg"
        if setup_cfg_path.exists():
            # This is deprecated
            from setuptools.config import read_configuration

            config = read_configuration(str(setup_cfg_path))
            try:
                return config["metadata"]["name"]
            except KeyError:
                pass

        return path.absolute().name

    def developed_packages(self) -> set[str]:
        """Try to understand which packages are under development"""
        packages = set()
        for requirements_folder in self._requirements_d_folders():
            for file in requirements_folder.iterdir():
                if not file.is_file():
                    continue
                requirements = RequirementsFile.from_file(
                    str(file), include_nested=True
                )
                editable_requirements = (
                    requirement
                    for requirement in requirements.requirements
                    if requirement.is_editable
                )
                for requirement in editable_requirements:
                    try:
                        name = self.resolve_package_name_from_path(requirement)
                    except Exception as e:
                        name = requirement.link.filename
                        self.logger.debug(
                            "Could not resolve package name for requirement %r: %s",
                            requirement,
                            e,
                        )

                    packages.add(name_as_pep503(name))
        return packages

    def developed_packages_and_paths(self) -> set[str]:
        """Try to understand which packages are under development"""
        packages = set()
        for requirements_folder in self._requirements_d_folders():
            for file in requirements_folder.iterdir():
                if not file.is_file():
                    continue
                requirements = RequirementsFile.from_file(
                    str(file), include_nested=True
                )
                editable_requirements = (
                    requirement
                    for requirement in requirements.requirements
                    if requirement.is_editable
                )
                for requirement in editable_requirements:
                    try:
                        name = self.resolve_package_name_from_path(requirement)
                    except Exception as e:
                        name = requirement.link.filename
                        self.logger.debug(
                            "Could not resolve package name for requirement %r: %s",
                            requirement,
                            e,
                        )
                    packages.add(
                        f"{name_as_pep503(name)} → {Path(requirement.link.path).absolute()}"  # noqa: E501
                    )
        return packages

    def make_constraints_txt(self):
        """Merge the constraints files in one big constraints.txt file"""
        developed_packages = self.developed_packages()
        included_files = []
        resolved_constraints = {}
        explicit_constraints = {}
        plonex_base_constraint = self.plonex_base_constraint
        if plonex_base_constraint:
            if self._is_remote_requirement_source(plonex_base_constraint):
                _, base_resolved, base_explicit = (
                    self._collect_compiled_constraint_entries(
                        plonex_base_constraint,
                        developed_packages=developed_packages,
                    )
                )
                for key, requirement in base_resolved.items():
                    if key not in resolved_constraints:
                        resolved_constraints[key] = requirement
                for key, requirement in base_explicit.items():
                    if key not in explicit_constraints:
                        explicit_constraints[key] = requirement
            else:
                included_files.append(f"-c {plonex_base_constraint}")

        for constraints_folder in self._constraints_d_folders():
            for file in sorted(constraints_folder.iterdir()):
                if not file.is_file() or file == self.legacy_constraints_file:
                    continue
                file_includes, file_resolved, file_explicit = (
                    self._collect_compiled_constraint_entries(
                        file,
                        developed_packages=developed_packages,
                    )
                )
                for include_line in file_includes:
                    if include_line not in included_files:
                        included_files.append(include_line)

                for key, requirement in file_resolved.items():
                    if key not in resolved_constraints:
                        resolved_constraints[key] = requirement
                for key, requirement in file_explicit.items():
                    if key not in explicit_constraints:
                        explicit_constraints[key] = requirement

        constraints = dict(resolved_constraints)
        constraints.update(explicit_constraints)

        merged_constraints = included_files + [
            requirement.dumps() for _, requirement in sorted(constraints.items())
        ]

        self.constrainst_txt = self.var_folder / "constraints.txt"

        with open(self.constrainst_txt, "w") as file:
            file.write("# This file is generated by plonex\n")
            file.write("\n".join(merged_constraints))

    @cached_property
    def plonex_base_constraint(self) -> str | Path | None:
        raw_source = self.options.get("plonex_base_constraint")
        if not raw_source:
            return None

        if not isinstance(raw_source, str):
            return raw_source

        if raw_source.startswith("resource://"):
            source_path = raw_source.partition("resource://")[2]
            package, filename_path = source_path.partition(":")[::2]
            return Path(str(resources.files(package) / filename_path)).resolve()

        if self._is_remote_requirement_source(raw_source):
            return raw_source

        path = Path(raw_source).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (self.target / path).resolve()

    @staticmethod
    def _is_remote_requirement_source(source: str | Path) -> bool:
        if isinstance(source, Path):
            return False
        return urlparse(source).scheme in {"http", "https"}

    def _resolve_requirement_source(
        self,
        reference: str,
        base_source: str | Path,
    ) -> str | Path:
        reference_path = Path(reference).expanduser()
        if reference_path.is_absolute() or self._is_remote_requirement_source(
            reference
        ):
            return reference

        if isinstance(base_source, Path):
            return (base_source.parent / reference_path).resolve()
        return urljoin(base_source, reference)

    def _parse_requirement_source(self, source: str | Path):
        if not self._is_remote_requirement_source(source):
            return RequirementsFile.from_file(str(source), include_nested=False)

        remote_source = str(source)
        response = requests.get(remote_source, timeout=30)
        response.raise_for_status()
        with NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            dir=self.tmp_folder,
            delete=False,
        ) as handle:
            handle.write(response.text)
            tmp_name = handle.name
        try:
            return RequirementsFile.from_file(tmp_name, include_nested=False)
        finally:
            Path(tmp_name).unlink(missing_ok=True)

    def _collect_compiled_constraint_entries(
        self,
        source: str | Path,
        developed_packages: set[str] | None = None,
        seen: set[str] | None = None,
    ):
        if seen is None:
            seen = set()

        source_key = str(source.resolve()) if isinstance(source, Path) else source
        if source_key in seen:
            return [], {}, {}
        seen.add(source_key)

        parsed = self._parse_requirement_source(source)
        source_is_remote = self._is_remote_requirement_source(source)
        included_files: list[str] = []
        resolved_constraints = {}
        explicit_constraints = {}

        for option in getattr(parsed, "options", []):
            for option_name, _flag in (("constraints", "-c"), ("requirements", "-r")):
                for reference in option.options.get(option_name, []):
                    resolved = self._resolve_requirement_source(reference, source)
                    if self._is_remote_requirement_source(resolved):
                        nested_includes, nested_resolved, nested_explicit = (
                            self._collect_compiled_constraint_entries(
                                resolved,
                                developed_packages=developed_packages,
                                seen=seen,
                            )
                        )
                        for include_line in nested_includes:
                            if include_line not in included_files:
                                included_files.append(include_line)
                        for key, requirement in nested_resolved.items():
                            if key not in resolved_constraints:
                                resolved_constraints[key] = requirement
                        for key, requirement in nested_explicit.items():
                            if key not in explicit_constraints:
                                explicit_constraints[key] = requirement
                        continue

                    nested_includes, nested_resolved, nested_explicit = (
                        self._collect_compiled_constraint_entries(
                            resolved,
                            developed_packages=developed_packages,
                            seen=seen,
                        )
                    )
                    for include_line in nested_includes:
                        if include_line not in included_files:
                            included_files.append(include_line)
                    for key, requirement in nested_resolved.items():
                        if key not in resolved_constraints:
                            resolved_constraints[key] = requirement
                    for key, requirement in nested_explicit.items():
                        if key not in explicit_constraints:
                            explicit_constraints[key] = requirement

        for requirement in parsed.requirements:
            name = getattr(requirement, "name", None)
            if not name:
                continue
            normalized_name = name_as_pep503(str(name))
            key = (normalized_name, str(requirement.marker))
            if developed_packages is not None and normalized_name in developed_packages:
                continue
            if source_is_remote:
                if key not in resolved_constraints:
                    resolved_constraints[key] = requirement
                continue
            explicit_constraints[key] = requirement

        return included_files, resolved_constraints, explicit_constraints

    def _collect_constraint_entries(
        self,
        source: str | Path,
        developed_packages: set[str] | None = None,
        seen: set[str] | None = None,
        expand_remote_includes: bool = True,
    ):
        if seen is None:
            seen = set()

        source_key = str(source.resolve()) if isinstance(source, Path) else source
        if source_key in seen:
            return [], {}
        seen.add(source_key)

        parsed = self._parse_requirement_source(source)
        included_files: list[str] = []
        constraints = {}

        for option in getattr(parsed, "options", []):
            for option_name, flag in (("constraints", "-c"), ("requirements", "-r")):
                for reference in option.options.get(option_name, []):
                    resolved = self._resolve_requirement_source(reference, source)
                    if self._is_remote_requirement_source(resolved):
                        include_line = f"{flag} {resolved}"
                        if include_line not in included_files:
                            included_files.append(include_line)
                        if not expand_remote_includes:
                            continue

                    nested_includes, nested_constraints = (
                        self._collect_constraint_entries(
                            resolved,
                            developed_packages=developed_packages,
                            seen=seen,
                            expand_remote_includes=expand_remote_includes,
                        )
                    )
                    for include_line in nested_includes:
                        if include_line not in included_files:
                            included_files.append(include_line)
                    for key, requirement in nested_constraints.items():
                        constraints[key] = requirement

        for requirement in parsed.requirements:
            name = getattr(requirement, "name", None)
            if not name:
                continue
            normalized_name = name_as_pep503(str(name))
            key = (normalized_name, str(requirement.marker))
            if developed_packages is not None and normalized_name in developed_packages:
                continue
            constraints[key] = requirement

        return included_files, constraints

    @staticmethod
    def _normalize_requirement_dump(requirement) -> str:
        return requirement.dumps().lower().replace("_", "-")

    @staticmethod
    def _requirement_key(requirement) -> str | None:
        name = getattr(requirement, "name", None)
        if not name:
            return None
        return name_as_pep503(str(name))

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

    @property
    def sources_update_before_dependencies(self) -> bool:
        return bool(self.options.get("sources_update_before_dependencies", False))

    @BaseService.entered_only
    def update_gitman_sources(self) -> None:
        with SourcesService(target=self.target) as gitman_service:
            gitman_service.run_update(assume_yes=True)

    def __enter__(self):
        super().__enter__()
        self.ensure_virtualenv()
        self.make_requirements_txt()
        self.make_constraints_txt()
        return self

    def _resolve_first_profile_root(self) -> Path | None:
        plonex_yml = self.target / "etc" / "plonex.yml"
        if not plonex_yml.exists():
            self.logger.error(
                "No etc/plonex.yml found; cannot determine a profile to write to"
            )
            return None
        raw_local = self._load_yaml_mapping(plonex_yml)
        raw_profiles = raw_local.get("profiles") or []
        if isinstance(raw_profiles, str):
            raw_profiles = [raw_profiles]
        if not raw_profiles:
            self.logger.error(
                "No profiles configured in etc/plonex.yml; "
                "cannot determine a profile to write to"
            )
            return None
        resolved = self._resolve_profile_source(raw_profiles[0], self.target)
        if isinstance(resolved, str):
            self.logger.error("Cannot write to a remote profile: %s", resolved)
            return None
        return resolved

    def _collect_profile_roots(
        self,
        profile: str | Path,
        relative_to: Path,
        seen: set[Path],
    ) -> list[Path]:
        from plonex.profile import ProfileService

        resolved_profile = self._resolve_profile_source(profile, relative_to)
        profile_service = ProfileService(source=resolved_profile, target=self.target)
        profile_root = profile_service.source_path.resolve()

        if profile_root in seen:
            return []
        seen.add(profile_root)

        roots: list[Path] = []
        profile_plonex_yml = profile_root / "etc" / "plonex.yml"
        if profile_plonex_yml.exists():
            raw_profile_options = self._load_yaml_mapping(profile_plonex_yml)
            nested_profiles = self._normalize_profiles(
                raw_profile_options.get("profiles"),
                profile_plonex_yml,
            )
            for nested_profile in nested_profiles:
                roots.extend(
                    self._collect_profile_roots(nested_profile, profile_root, seen)
                )

        roots.append(profile_root)
        return roots

    @cached_property
    def profile_roots(self) -> list[Path]:
        plonex_yml = self.target / "etc" / "plonex.yml"
        if not plonex_yml.exists():
            return []

        raw_local = self._load_yaml_mapping(plonex_yml)
        raw_profiles = self._normalize_profiles(raw_local.get("profiles"), plonex_yml)
        seen: set[Path] = set()
        roots: list[Path] = []
        for profile in raw_profiles:
            roots.extend(self._collect_profile_roots(profile, self.target, seen))
        return roots

    def _dependency_roots_by_precedence(self) -> list[Path]:
        roots = [self.target]
        roots.extend(reversed(self.profile_roots))
        return roots

    def _requirements_d_folders(self) -> list[Path]:
        folders = []
        for root in self._dependency_roots_by_precedence():
            folder = root / "etc" / "requirements.d"
            if folder.is_dir():
                folders.append(folder)
        return folders

    def _constraints_d_folders(self) -> list[Path]:
        folders = []
        for root in self._dependency_roots_by_precedence():
            folder = root / "etc" / "constraints.d"
            if folder.is_dir():
                folders.append(folder)
        return folders

    @BaseService.entered_only
    def run(
        self,
        persist: bool = False,
        persist_local: bool = False,
        persist_profile: bool = False,
        update_sources: bool | None = None,
    ):
        selected = [persist, persist_local, persist_profile]
        if sum(1 for v in selected if v) > 1:
            self.logger.error(
                "Use only one persist flag: --persist, --persist-local, or --persist-profile"  # noqa: E501
            )
            return

        # Check if we have a virtualenv and if not create one
        self.ensure_virtualenv()
        should_update_sources = (
            update_sources
            if update_sources is not None
            else self.sources_update_before_dependencies
        )
        if should_update_sources:
            self.update_gitman_sources()
        super().run()
        # Run pip freeze and compare the output with the constraints
        # to see if we are missing something
        self.logger.debug("Checking if all constraints are met")

        _, merged_constraints = self._collect_constraint_entries(self.constrainst_txt)
        constraints = list(merged_constraints.values())
        installed = self.execute_command(
            [str(self.virtualenv_dir / "bin" / "pip"), "freeze"]
        )

        # Save the installed packages to a temporary file
        with open(self.tmp_folder / "installed.txt", "w") as file:  # type: ignore
            file.write(installed)

        installed = RequirementsFile.from_file(file.name).requirements

        constrained_names = {
            key for req in constraints if (key := self._requirement_key(req))
        }
        constrained_dumps = {
            self._normalize_requirement_dump(req) for req in constraints
        }

        missing = set()
        for requirement in installed:
            requirement_dump = self._normalize_requirement_dump(requirement)
            if requirement_dump.startswith("--editable"):
                continue

            requirement_key = self._requirement_key(requirement)
            if requirement_key and requirement_key in constrained_names:
                continue
            if requirement_dump in constrained_dumps:
                continue
            missing.add(requirement_dump)

        if missing:
            if persist or persist_local or persist_profile:
                if persist_local:
                    autoinstalled_file = (
                        self.target
                        / "etc"
                        / "constraints.d"
                        / "999-autoinstalled.local.txt"
                    )
                elif persist_profile:
                    profile_root = self._resolve_first_profile_root()
                    if profile_root is None:
                        return
                    now = datetime.now().strftime("%Y%m%d-%H%M%S")
                    autoinstalled_file = (
                        profile_root
                        / "etc"
                        / "constraints.d"
                        / f"999-{now}-autoinstalled.txt"
                    )
                else:
                    now = datetime.now().strftime("%Y%m%d-%H%M%S")
                    autoinstalled_file = (
                        self.target
                        / "etc"
                        / "constraints.d"
                        / f"999-{now}-autoinstalled.txt"
                    )
                autoinstalled_file.parent.mkdir(parents=True, exist_ok=True)
                if autoinstalled_file.exists():
                    missing |= set(autoinstalled_file.read_text().splitlines())
                    self.logger.info(f"Adding new constraints to {autoinstalled_file}")
                autoinstalled_file.write_text("\n".join(sorted(missing)) + "\n")
            else:
                self.logger.warning(f"Missing constraints: {sorted(missing)}")
                console = Console()
                console.print(
                    f"You may want to add the following constraints to a file "
                    f"in the {self.constraints_d_folder}:"
                )
                console.print(*sorted(missing), sep="\n")
                console.print(
                    "Running  `plonex dependencies [--persist|--persist-local|--persist-profile]` will do that for you."  # noqa: E501
                )
