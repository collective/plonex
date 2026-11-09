from configparser import ConfigParser
from dataclasses import dataclass
from packaging.utils import canonicalize_name
from pathlib import Path
from typing import Any
from typing import Mapping

import ast
import tomllib


def source_checkout_path(target: Path, location: str, name: str, options: Any) -> Path:
    """Share checkout paths between source management and installation."""
    if isinstance(options, dict):
        path = options.get("path")
        if isinstance(path, str) and path.strip():
            return target / path
    return target / location / name


def local_package_name(path: Path) -> str:
    """Read static distribution metadata without executing a checkout's code."""
    pyproject = path / "pyproject.toml"
    if pyproject.is_file():
        metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        name = metadata.get("project", {}).get("name") or (
            metadata.get("tool", {}).get("poetry", {}).get("name")
        )
        if name:
            return canonicalize_name(name)

    setup_cfg = path / "setup.cfg"
    if setup_cfg.is_file():
        config = ConfigParser(interpolation=None)
        config.read(setup_cfg, encoding="utf-8")
        name = config.get("metadata", "name", fallback="").strip()
        if name:
            return canonicalize_name(name)

    setup_py = path / "setup.py"
    if setup_py.is_file():
        tree = ast.parse(setup_py.read_bytes(), filename=str(setup_py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not (
                isinstance(function, ast.Name)
                and function.id == "setup"
                or isinstance(function, ast.Attribute)
                and function.attr == "setup"
            ):
                continue
            for keyword in node.keywords:
                value = keyword.value
                if (
                    keyword.arg == "name"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    return canonicalize_name(value.value)

    return canonicalize_name(path.name)


@dataclass(frozen=True)
class SourceInstallation:
    """One explicitly selected local Python project."""

    source: str
    path: Path
    editable: bool = True
    extras: tuple[str, ...] = ()
    distribution: str = ""

    @property
    def package_name(self) -> str:
        return self.distribution or local_package_name(self.path)

    @property
    def requirement(self) -> str:
        extras = f"[{','.join(self.extras)}]" if self.extras else ""
        # File URIs keep spaces and path characters unambiguous to the resolver.
        location = self.path.as_uri()
        if self.editable:
            return f"-e {location}{extras}"
        return f"{self.package_name}{extras} @ {location}"

    @property
    def description(self) -> str:
        mode = "editable" if self.editable else "regular"
        extras = f" [{','.join(self.extras)}]" if self.extras else ""
        return mode + extras


@dataclass(frozen=True)
class SourceInstallPlan:
    """Resolve source selection using the calling service's merged options."""

    installations: tuple[SourceInstallation, ...] = ()

    @classmethod
    def from_options(
        cls, target: Path, options: Mapping[str, Any]
    ) -> "SourceInstallPlan":
        selected = []
        location = str(options.get("sources_location", "src"))
        for name, source in (options.get("sources") or {}).items():
            if not isinstance(source, dict):
                raise ValueError(f"Source {name!r} must be a YAML mapping")
            install = source.get("install", False)
            if not isinstance(install, bool):
                raise ValueError(f"Source {name!r}: 'install' must be true or false")
            if not install:
                continue
            editable = source.get("editable", True)
            if not isinstance(editable, bool):
                raise ValueError(f"Source {name!r}: 'editable' must be true or false")
            extras = source.get("extras", [])
            if not isinstance(extras, list) or not all(
                isinstance(extra, str) for extra in extras
            ):
                raise ValueError(f"Source {name!r}: 'extras' must be a list of names")
            try:
                normalized_extras = tuple(
                    sorted(
                        {canonicalize_name(extra, validate=True) for extra in extras}
                    )
                )
            except ValueError as exc:
                raise ValueError(f"Source {name!r}: invalid extra name: {exc}") from exc
            distribution = source.get("distribution", "")
            if not isinstance(distribution, str):
                raise ValueError(
                    f"Source {name!r}: 'distribution' must be a package name"
                )
            if distribution:
                try:
                    distribution = canonicalize_name(distribution, validate=True)
                except ValueError as exc:
                    raise ValueError(
                        f"Source {name!r}: invalid distribution name"
                    ) from exc
            checkout = source_checkout_path(target, location, str(name), source)
            subdirectory = source.get("subdirectory", ".")
            if (
                not isinstance(subdirectory, str)
                or not subdirectory.strip()
                or Path(subdirectory).is_absolute()
                or ".." in Path(subdirectory).parts
            ):
                raise ValueError(
                    f"Source {name!r}: 'subdirectory' must be a relative path "
                    "inside the checkout"
                )
            selected.append(
                SourceInstallation(
                    source=str(name),
                    path=(checkout / subdirectory).absolute(),
                    editable=editable,
                    extras=normalized_extras,
                    distribution=distribution,
                )
            )
        return cls(tuple(selected))

    @property
    def package_names(self) -> set[str]:
        return {installation.package_name for installation in self.installations}

    def validate(self) -> None:
        """Fail before invoking the resolver, with a useful recovery command."""
        packages: set[str] = set()
        for installation in self.installations:
            path = installation.path
            if not path.is_dir():
                raise ValueError(
                    f"Selected source {installation.source!r} is missing at {path}. "
                    "Run 'plonex sources clone' or "
                    "'plonex dependencies install --update-sources' first. "
                    "Check 'path' and 'subdirectory' if the checkout already exists."
                )
            if not any(
                (path / filename).is_file()
                for filename in ("pyproject.toml", "setup.py")
            ):
                raise ValueError(
                    f"Selected source {installation.source!r} at {path} has no "
                    "pyproject.toml or setup.py. Set 'subdirectory' to its Python "
                    "project, or disable 'install'."
                )
            if installation.editable and any(char in str(path) for char in "#?"):
                raise ValueError(
                    f"Selected source {installation.source!r} at {path}: uv cannot "
                    "resolve editable paths containing '#' or '?'. Move the "
                    "checkout or set 'editable: false'."
                )
            package = installation.package_name
            if package in packages:
                raise ValueError(
                    f"Multiple selected sources provide {package!r}; "
                    "select only one checkout per distribution."
                )
            packages.add(package)
