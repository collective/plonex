"""Dependency inputs, remote snapshots, and the observed virtualenv manifest."""

from pathlib import Path
from plonex.files import read_only
from plonex.files import write_if_changed
from plonex.preparation.engine import digest
from plonex.preparation.engine import file_digest
from plonex.preparation.engine import Graph
from plonex.preparation.engine import Task
from urllib.parse import unquote

import json
import os
import requests
import shutil


class ConstraintCache:
    def __init__(self, folder: Path):
        self.folder = folder

    def path(self, url: str):
        return self.folder / f"{digest(url)}.txt"

    def store(self, url: str, text: str):
        self.folder.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.folder.chmod(0o700)
        write_if_changed(self.path(url), text)


def environment_manifest(target: Path):
    """Observe distribution metadata, not source edits or volatile pyc files."""
    venv = target / ".venv"
    python = venv / "bin/python"
    if (
        not python.exists()
        or not (venv / "bin/activate").exists()
        or not (venv / "bin/uv").exists()
    ):
        return {"virtualenv": "missing"}
    files = sorted(venv.glob("lib/python*/site-packages/*.dist-info/METADATA"))
    values = {}
    for metadata in files:
        for name in ("METADATA", "direct_url.json", "INSTALLER", "WHEEL"):
            path = metadata.with_name(name)
            values[str(path.relative_to(venv))] = file_digest(path)
    for path in venv.glob("lib/python*/site-packages/*.egg-link"):
        values[str(path.relative_to(venv))] = file_digest(path)
    stat = python.resolve().stat()
    values["interpreter"] = digest(
        (
            str(python.resolve()),
            stat.st_size,
            stat.st_mtime_ns,
            file_digest(venv / "pyvenv.cfg"),
        )
    )
    return {"virtualenv": digest(values)}


class DependencyTasks:
    def __init__(self, target: Path, service=None):
        from plonex.services.install import InstallService

        self.target = target.absolute()
        with read_only():
            self.service = service or InstallService(target=self.target, dont_ask=True)
            self.service.options
            self.var_folder = self.service.var_folder
            self.service.requirements_txt = self.var_folder / "requirements.txt"
            self.service.constrainst_txt = self.var_folder / "constraints.txt"
            self.folder = self.var_folder / "preparation"
            self.cache = ConstraintCache(self.service.var_folder / "cache/constraints")
            self.roots = self.service._dependency_roots_by_precedence()
            self.base = self.service.plonex_base_constraint
        self.local_projects: dict[Path, bool] = {}
        self.graph = Graph(self.folder)
        self.graph.add(
            Task(
                "dependencies.generate",
                self.generate,
                self.inputs,
                outputs=self.generated,
                revision=self.revision(),
            )
        )
        self.graph.add(
            Task(
                "dependencies.ensure",
                self.install,
                self.install_inputs,
                outputs=lambda: environment_manifest(self.target),
                requires=("dependencies.generate",),
                affected=("Plone instances", "cron jobs"),
                revision=self.revision(),
            )
        )

    @staticmethod
    def revision():
        from plonex.services import install

        return digest(
            (file_digest(Path(__file__)), file_digest(Path(install.__file__)))
        )

    def generated(self):
        return {
            str(self.var_folder / name): file_digest(self.var_folder / name)
            for name in ("requirements.txt", "constraints.txt")
        }

    def metadata(self, folder: Path, values, *, editable=True):
        self.local_projects[folder] = editable
        for name in ("pyproject.toml", "setup.cfg", "setup.py"):
            path = folder / name
            values[str(path)] = file_digest(path)
        for pattern in ("requirements*.txt", "requirements/*.txt"):
            for path in sorted(folder.glob(pattern)):
                values[str(path)] = file_digest(path)
        if not editable and folder.is_dir():
            for root, directories, filenames in os.walk(folder):
                directories[:] = sorted(
                    name
                    for name in directories
                    if name
                    not in {
                        ".git",
                        ".venv",
                        "__pycache__",
                        ".pytest_cache",
                        ".mypy_cache",
                        ".ruff_cache",
                        ".tox",
                        "node_modules",
                        "build",
                        "dist",
                    }
                    and not name.endswith(".egg-info")
                    and not (
                        Path(root) == self.target and name in {"var", "tmp", "htmlcov"}
                    )
                )
                for name in sorted(filenames):
                    if not name.endswith((".pyc", ".pyo")):
                        path = Path(root) / name
                        values[str(path)] = file_digest(path)

    def inputs(self, *, fetch=False):
        import pip_requirements_parser  # type: ignore[import-untyped]

        pip_requirements_parser.Path = Path
        from plonex.services.install import normalize_requirement

        service = self.service
        self.local_projects.clear()
        values = {
            "configuration: requirements": digest(
                [
                    normalize_requirement(value)
                    for value in service.options.get("pip_requirements", [])
                ]
            ),
            "configuration: base constraints": digest(str(self.base)),
            "configuration: selected sources": digest(
                [
                    (
                        item.source,
                        str(item.path),
                        item.editable,
                        item.extras,
                        item.distribution,
                    )
                    for item in service.source_install_plan.installations
                ]
            ),
        }
        if service.options.get("cron_jobs") or service.options.get(
            "cron_control_panel"
        ):
            from plonex.services.cron.installation import runtime_requirement
            from plonex.services.cron.installation import WORKER_REQUIREMENTS

            values["configuration: job worker"] = digest(
                [runtime_requirement(), *WORKER_REQUIREMENTS]
            )
        visited = set()

        def visit(source):
            key = str(source)
            if key in visited:
                return
            visited.add(key)
            remote = service._is_remote_requirement_source(source)
            path = self.cache.path(key) if remote else Path(source)
            label = f"remote constraints: {digest(key)[:12]}" if remote else str(path)
            if fetch and remote:
                service._parse_requirement_source(source)
            values[label] = file_digest(path)
            if not path.is_file():
                return
            parsed = pip_requirements_parser.RequirementsFile.from_file(
                str(path), include_nested=False
            )
            for option in parsed.options:
                for name in ("requirements", "constraints"):
                    for reference in option.options.get(name, []):
                        visit(service._resolve_requirement_source(reference, source))
            for requirement in parsed.requirements:
                link = getattr(requirement, "link", None)
                if link is not None and link.scheme in ("", "file"):
                    project = Path(unquote(link.path))
                    if not project.is_absolute():
                        project = self.target / project
                    if project.is_dir():
                        self.metadata(project, values, editable=requirement.is_editable)

        if self.base:
            visit(self.base)
        for root in self.roots:
            for kind in ("requirements", "constraints"):
                folder = root / "etc" / f"{kind}.d"
                files = sorted(
                    path
                    for path in folder.glob("*")
                    if path.is_file() and path != service.legacy_constraints_file
                )
                values[f"fragment membership: {folder}"] = digest(
                    [path.name for path in files]
                )
                for path in files:
                    visit(path)
        for item in service.source_install_plan.installations:
            self.metadata(item.path, values, editable=item.editable)
        # YAML also supports legacy local -e/file requirements.
        raw = "\n".join(service.options.get("pip_requirements", []))
        parsed = pip_requirements_parser.RequirementsFile.from_string(raw)
        for requirement in parsed.requirements:
            link = getattr(requirement, "link", None)
            if link is not None and link.scheme in ("", "file"):
                project = self.target / unquote(link.path)
                if project.is_dir():
                    self.metadata(project, values, editable=requirement.is_editable)
        return values

    def install_inputs(self):
        values = self.generated()
        # Include nested requirement files even when the generated -r lines are
        # unchanged; their membership and contents affect uv's actual input.
        values.update(self.inputs())
        values["configuration: python"] = digest(self.service.options.get("python"))
        values["configuration: build environment"] = digest(
            {
                key: value
                for key, value in self.service.options.get(
                    "environment_vars", {}
                ).items()
                if key.startswith(("UV_", "PIP_"))
                or key in {"CFLAGS", "CXXFLAGS", "LDFLAGS", "RUSTFLAGS", "CC", "CXX"}
            }
        )
        return values

    def generate(self):
        service = self.service
        service._use_cached_constraints = True
        service.tmp_folder.mkdir(parents=True, exist_ok=True)
        try:
            self.inputs(fetch=True)
        except requests.RequestException as error:
            from plonex.inspection import safe_value

            raise ValueError(
                f"Could not download dependency inputs: {safe_value(str(error))}"
            ) from error
        service.source_install_plan.validate()
        service.make_requirements_txt()
        service.make_constraints_txt()

    def install(self):
        from plonex.services.sources.installation import local_package_name

        service = self.service
        self.validate_interpreter()
        previous = self.graph.previous.get("dependencies.ensure", {}).get("inputs", {})
        current = self.install_inputs()
        for project in self.local_projects:
            prefix = str(project) + os.sep
            if any(
                current.get(key) != previous.get(key)
                for key in current.keys() | previous.keys()
                if key.startswith(prefix)
            ):
                service._reinstall_packages.append(local_package_name(project))
        service._inputs_prepared = True
        service._use_cached_constraints = True
        environment = {
            key: os.environ.get(key)
            for key in service.options.get("environment_vars", {})
        }
        try:
            with service:
                # Automatic preparation never fetches Git revisions or removes
                # packages, even if an interactive default requests source updates.
                report = service.run(update_sources=False)
        finally:
            # Installation settings must not leak into the Supervisor process
            # launched later in the same CLI invocation.
            for key, previous in environment.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous
        return {"changed": bool(report.changes or report.installer_activity)}

    def validate_interpreter(self):
        requested = self.service.options.get("python")
        python = self.target / ".venv/bin/python"
        if not requested or not python.exists():
            return
        executable = shutil.which(str(requested))
        if executable is None:
            raise ValueError(f"Configured Python executable was not found: {requested}")
        if Path(executable).resolve() == python.resolve():
            return
        script = (
            "import json,sys; print(json.dumps("
            "[sys.implementation.name,list(sys.version_info[:2])]))"
        )
        expected = json.loads(
            self.service.execute_command(
                [executable, "-c", script], capture_output=True
            )
        )
        actual = json.loads(
            self.service.execute_command([python, "-c", script], capture_output=True)
        )
        if actual != expected:
            raise ValueError(
                "Configured Python differs from the existing virtualenv. "
                "Recreate .venv with the configured interpreter before starting."
            )

    def remember_install(self):
        # Called only after successful explicit installation, using the options
        # and inputs of that very service, rather than a different config load.
        if environment_manifest(self.target)["virtualenv"] != "missing":
            self.graph.remember(self.graph.tasks["dependencies.ensure"])
