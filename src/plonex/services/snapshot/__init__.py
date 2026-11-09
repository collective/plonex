"""Portable evidence of an installed project and its selected source revisions."""

from packaging.utils import canonicalize_name
from pathlib import Path
from plonex.files import read_only
from plonex.inspection import safe_value
from plonex.preparation.engine import file_digest
from plonex.services.install import InstallService
from plonex.services.sources.installation import source_checkout_path
from urllib.parse import unquote
from urllib.parse import urlparse

import json
import os
import re
import subprocess


def command(*args, cwd):
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
            env=dict(os.environ) | {"GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError(f"Cannot inspect {args[0]}: {type(error).__name__}") from error
    return result.stdout.strip()


def portable_source(target, value):
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme == "file" and parsed.netloc in ("", "localhost"):
        path = Path(unquote(parsed.path)).resolve()
        try:
            return "project:" + path.relative_to(target.resolve()).as_posix()
        except ValueError:
            return "external:" + str(path)
    return safe_value(value)


def has_nested_inputs(path):
    return path.is_file() and any(
        re.match(r"^\s*(?:-[rc](?:\s|\S)|--(?:requirement|constraint)(?:[=\s]))", line)
        for line in path.read_text().splitlines()
    )


def capture(target, *, include_environment=True):
    target = Path(target).absolute()
    with read_only():
        install = InstallService(target=target, dont_ask=True)
        options = install.options
        python = target / ".venv/bin/python"
        if include_environment and not python.is_file():
            raise ValueError(
                "Project Python is missing. Run plonex dependencies install first."
            )
        script = """
import importlib.metadata as metadata, json, platform, sys
rows=[]
for dist in metadata.distributions():
    direct=json.loads(dist.read_text("direct_url.json") or "{}")
    rows.append({"name":dist.metadata.get("Name", ""), "version":dist.version,
                 "url":direct.get("url", ""),
                 "editable":direct.get("dir_info", {}).get("editable", False),
                 "commit":direct.get("vcs_info", {}).get("commit_id", ""),
                 "location":str(getattr(dist, "_path", ""))})
print(json.dumps({"prefix":sys.prefix,"python":platform.python_version(),
                  "implementation":platform.python_implementation(),
                  "system":platform.system(),"machine":platform.machine(),"packages":rows}))
"""
        if include_environment:
            try:
                info = json.loads(
                    command(str(python), "-I", "-B", "-c", script, cwd=target)
                )
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(
                    "Cannot read target Python distribution metadata"
                ) from error
            if Path(info["prefix"]).resolve() != (target / ".venv").resolve():
                raise ValueError("Target Python is not the project virtualenv")
        else:
            info = {
                "python": "",
                "implementation": "",
                "system": "",
                "machine": "",
                "packages": [],
            }
        packages = {}
        ranks = {}
        for row in info["packages"]:
            name = canonicalize_name(row["name"])
            if not name:
                continue
            record = {
                "version": row["version"],
                "source": portable_source(target, row["url"]),
                "editable": row["editable"],
                "commit": row["commit"],
            }
            location = Path(row["location"]).resolve()
            rank = int(location.is_relative_to((target / ".venv").resolve()))
            if name in packages and ranks[name] == rank and packages[name] != record:
                raise ValueError(
                    f"Ambiguous installed distributions named {name}; "
                    "resolve before snapshotting"
                )
            if name not in packages or rank > ranks[name]:
                packages[name] = record
                ranks[name] = rank
        sources = {}
        issues = []
        selected = {
            item.source: item for item in install.source_install_plan.installations
        }
        for name, config in sorted(options.get("sources", {}).items()):
            if not isinstance(config, dict):
                raise ValueError(f"Invalid source declaration: {name}")
            path = source_checkout_path(
                target, str(options.get("sources_location", "src")), name, config
            )
            selection = selected.get(name)
            data = {
                "repo": safe_value(str(config.get("repo", ""))),
                "path": portable_source(target, path.absolute().as_uri()),
                "configured_revision": str(config.get("rev", "main")),
                "install": selection is not None,
                "editable": selection.editable if selection else None,
                "extras": list(selection.extras) if selection else [],
                "distribution": selection.package_name if selection else None,
                "commit": None,
                "dirty": None,
            }
            if path.is_dir():
                try:
                    root = command(
                        "git",
                        "-C",
                        str(path),
                        "rev-parse",
                        "--show-toplevel",
                        cwd=target,
                    )
                    if Path(root).resolve() != path.resolve():
                        raise ValueError("Not a checkout root")
                    data["commit"] = command(
                        "git", "-C", str(path), "rev-parse", "HEAD", cwd=target
                    )
                    data["dirty"] = bool(
                        command(
                            "git",
                            "-C",
                            str(path),
                            "status",
                            "--porcelain",
                            "--untracked-files=normal",
                            cwd=target,
                        )
                    )
                except ValueError:
                    pass
            sources[str(name)] = data
            if data["commit"] is None:
                issues.append(f"Source {name} has no readable Git commit.")
            elif data["dirty"]:
                issues.append(f"Source {name} has uncommitted or untracked changes.")
        files = {}
        for index, root in enumerate(install._dependency_roots_by_precedence()):
            label = "" if index == 0 else f"profile[{index}]/"
            for pattern in (
                "etc/plonex*.yml",
                "etc/requirements.d/*",
                "etc/constraints.d/*",
            ):
                for path in sorted(root.glob(pattern)):
                    if path.is_file():
                        files[label + path.relative_to(root).as_posix()] = file_digest(
                            path
                        )
                        if (
                            "/requirements.d/" in path.as_posix()
                            or "/constraints.d/" in path.as_posix()
                        ) and has_nested_inputs(path):
                            relative = label + path.relative_to(root).as_posix()
                            issues.append(
                                f"Nested dependency inputs in {relative} "
                                "are not captured."
                            )
        if any(
            re.match(r"^\s*(?:-[rc]|--(?:requirement|constraint))", item)
            for item in options.get("pip_requirements", [])
        ):
            issues.append(
                "Nested dependency inputs in pip_requirements are not captured."
            )
        base = install.plonex_base_constraint
        constraint = {"source": safe_value(str(base or "")), "digest": None}
        if base:
            if install._is_remote_requirement_source(base):
                from plonex.preparation.dependencies import ConstraintCache

                cached = ConstraintCache(install.var_folder / "cache/constraints").path(
                    str(base)
                )
                constraint["digest"] = file_digest(cached)
                if has_nested_inputs(cached):
                    issues.append(
                        "Nested includes in cached base constraints are not captured."
                    )
            else:
                constraint["source"] = portable_source(target, Path(base).as_uri())
                constraint["digest"] = file_digest(Path(base))
                if has_nested_inputs(Path(base)):
                    issues.append(
                        "Nested includes in base constraints are not captured."
                    )
        if constraint["digest"] == "missing":
            issues.append("Base constraints are not cached or available locally.")
        return {
            "schema": 1,
            "python": {
                key: info[key]
                for key in ("python", "implementation", "system", "machine")
            },
            "packages": dict(sorted(packages.items())),
            "sources": sources,
            "inputs": files,
            "base_constraints": constraint,
            "issues": issues,
        }


def differences(expected, actual, prefix=""):
    if isinstance(expected, dict) and isinstance(actual, dict):
        result = []
        for name in sorted(expected.keys() | actual.keys()):
            path = f"{prefix}.{name}" if prefix else name
            if name not in expected:
                result.append(
                    {
                        "path": path,
                        "change": "added",
                        "before": None,
                        "after": actual[name],
                    }
                )
            elif name not in actual:
                result.append(
                    {
                        "path": path,
                        "change": "removed",
                        "before": expected[name],
                        "after": None,
                    }
                )
            else:
                result.extend(differences(expected[name], actual[name], path))
        return result
    return (
        []
        if expected == actual
        else [
            {"path": prefix, "change": "changed", "before": expected, "after": actual}
        ]
    )


def write_new(path, snapshot):
    from tempfile import NamedTemporaryFile

    path = Path(path).expanduser().absolute()
    data = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".plonex-snapshot-",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except OSError as error:
        raise ValueError(f"Cannot create snapshot {path}: {error.strerror}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def load(path):
    try:
        value = json.loads(Path(path).read_text())
    except (ValueError, OSError) as error:
        raise ValueError("Cannot read project snapshot") from error
    if (
        not isinstance(value, dict)
        or value.get("schema") != 1
        or not all(
            isinstance(value.get(key), dict)
            for key in ("python", "packages", "sources", "inputs", "base_constraints")
        )
    ):
        raise ValueError("Invalid or unsupported project snapshot")
    if not isinstance(value.get("issues"), list) or not all(
        isinstance(item, str) for item in value["issues"]
    ):
        raise ValueError("Invalid snapshot issues")
    if not all(
        isinstance(value["python"].get(key), str)
        for key in ("python", "implementation", "system", "machine")
    ):
        raise ValueError("Invalid snapshot Python information")
    if not all(
        isinstance(name, str) and isinstance(digest, str)
        for name, digest in value["inputs"].items()
    ):
        raise ValueError("Invalid snapshot inputs")
    if not all(
        isinstance(name, str)
        and isinstance(row, dict)
        and isinstance(row.get("version"), str)
        and isinstance(row.get("source"), str)
        and isinstance(row.get("editable"), bool)
        and isinstance(row.get("commit"), str)
        for name, row in value["packages"].items()
    ):
        raise ValueError("Invalid snapshot packages")
    if not all(
        isinstance(name, str)
        and isinstance(row, dict)
        and isinstance(row.get("path"), str)
        and (row.get("commit") is None or isinstance(row["commit"], str))
        and (row.get("dirty") is None or isinstance(row["dirty"], bool))
        for name, row in value["sources"].items()
    ):
        raise ValueError("Invalid snapshot sources")
    if not isinstance(value["base_constraints"].get("source"), str) or not (
        value["base_constraints"].get("digest") is None
        or isinstance(value["base_constraints"]["digest"], str)
    ):
        raise ValueError("Invalid snapshot constraints")
    return value


def prepare(target, snapshot, destination, *, python=None):
    """Recreate recorded versions in a new environment after checking project inputs."""
    from packaging.requirements import InvalidRequirement
    from packaging.requirements import Requirement

    import shutil
    import sys
    import tempfile

    target = Path(target).absolute()
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Environment destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise ValueError(
            f"Environment destination parent is missing: {destination.parent}"
        )
    if snapshot.get("issues"):
        raise ValueError(
            "Snapshot has unresolved source or constraint issues; cannot prepare it"
        )
    current = capture(target, include_environment=False)
    for key in ("sources", "inputs", "base_constraints", "issues"):
        if differences(snapshot.get(key), current.get(key)):
            raise ValueError(
                f"Project {key} differs from the snapshot; inspect changes first"
            )
    expected_python = snapshot["python"]
    configured_version = str(expected_python.get("python", ""))
    version_parts = configured_version.split(".")
    default = target / ".venv/bin/python"
    candidate = str(
        python
        or (
            default
            if default.is_file()
            else shutil.which("python" + ".".join(version_parts[:2])) or ""
        )
    )
    if not candidate:
        raise ValueError(f"Python {configured_version} not found; supply --python")
    probe = json.loads(
        command(
            candidate,
            "-I",
            "-B",
            "-c",
            "import json,platform; print(json.dumps({"
            '"python":platform.python_version(),'
            '"implementation":platform.python_implementation(),'
            '"system":platform.system(),'
            '"machine":platform.machine()}))',
            cwd=target,
        )
    )
    if probe != expected_python:
        raise ValueError(
            "Python version, implementation, system or machine differs "
            "from the snapshot"
        )
    source_roots = []
    for source in snapshot["sources"].values():
        path = source.get("path", "")
        if (
            path.startswith("project:")
            and source.get("commit")
            and source.get("dirty") is False
        ):
            root = (target / path.removeprefix("project:")).resolve()
            if root.is_relative_to(target.resolve()):
                source_roots.append(root)
    requirements = []
    for name, row in sorted(snapshot["packages"].items()):
        if not isinstance(row, dict) or not isinstance(row.get("version"), str):
            raise ValueError(f"Invalid package entry: {name}")
        try:
            requirement = Requirement(f"{name}=={row['version']}")
        except InvalidRequirement as error:
            raise ValueError(f"Invalid package version for {name}") from error
        if canonicalize_name(requirement.name) != name:
            raise ValueError(f"Invalid package name: {name}")
        source = row.get("source", "")
        if not source:
            requirements.append(str(requirement))
            continue
        if not isinstance(source, str) or not source.startswith("project:"):
            raise ValueError(
                f"Package {name} has an unsupported external or remote source"
            )
        path = (target / source.removeprefix("project:")).resolve()
        if not path.is_relative_to(target.resolve()) or not any(
            path.is_relative_to(root) for root in source_roots
        ):
            raise ValueError(
                f"Package {name} is not inside a clean recorded source checkout"
            )
        if not path.is_dir():
            raise ValueError(f"Source for {name} is missing: {path}")
        if row.get("editable"):
            requirements.append(f"-e {path.as_uri()}")
        else:
            requirements.append(f"{name} @ {path.as_uri()}")
    uv = shutil.which("uv") or str(Path(sys.executable).parent / "uv")
    if not Path(uv).is_file():
        raise ValueError("uv executable is unavailable")
    destination.mkdir(mode=0o700)
    # A failed build stays in its new directory for inspection, never deleting
    # an existing user environment. Unset destructive uv environment options.
    environment = dict(os.environ)
    environment.pop("UV_VENV_CLEAR", None)
    environment.pop("UV_VENV_SEED", None)
    try:
        subprocess.run(
            [
                uv,
                "venv",
                "--allow-existing",
                "--no-python-downloads",
                "--python",
                candidate,
                str(destination),
            ],
            check=True,
            env=environment,
            cwd=target,
        )
        with tempfile.TemporaryDirectory(prefix="plonex-snapshot-") as folder:
            path = Path(folder) / "requirements.txt"
            path.write_text("\n".join(requirements) + "\n")
            subprocess.run(
                [
                    uv,
                    "pip",
                    "sync",
                    "--allow-empty-requirements",
                    "--python",
                    str(destination / "bin/python"),
                    str(path),
                ],
                check=True,
                env=environment,
                cwd=target,
            )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            f"Could not prepare environment; partial output remains at {destination}"
        ) from error
    verify_script = """
import importlib.metadata as m, json, pathlib, sys
root=pathlib.Path(sys.prefix).resolve()
rows={}
for dist in m.distributions():
    if pathlib.Path(getattr(dist, "_path", "")).resolve().is_relative_to(root):
        rows[dist.metadata.get("Name", "")]=dist.version
print(json.dumps(rows))
"""
    actual = json.loads(
        command(
            str(destination / "bin/python"), "-I", "-B", "-c", verify_script, cwd=target
        )
    )
    normalized = {
        canonicalize_name(name): version for name, version in actual.items() if name
    }
    expected = {name: row["version"] for name, row in snapshot["packages"].items()}
    if normalized != expected:
        raise ValueError(f"Installed package versions differ; inspect {destination}")
    after = capture(target, include_environment=False)
    for key in ("sources", "inputs", "base_constraints", "issues"):
        if differences(snapshot.get(key), after.get(key)):
            raise ValueError(
                f"Project {key} changed during preparation; inspect {destination}"
            )
    return destination
