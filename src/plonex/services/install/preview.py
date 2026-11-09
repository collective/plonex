"""Resolve proposed dependencies against a disposable environment."""

from pathlib import Path
from plonex.files import read_only
from plonex.inspection import safe_value
from plonex.preparation.dependencies import ConstraintCache
from plonex.services.install import InstallService
from rich.console import Console

import difflib
import json
import shutil
import subprocess
import tempfile


def inspection_environment(python, folder):
    """Give uv a disposable venv with a copy of installed metadata."""
    script = (
        "import json,sys,sysconfig,venv; "
        "print(json.dumps({'prefix':sys.prefix,"
        "'site':sysconfig.get_path('purelib')})); "
        "venv.EnvBuilder(with_pip=False).create(sys.argv[1])"
    )
    process = None
    try:
        process = subprocess.Popen(
            [str(python), "-I", "-B", "-c", script, str(folder)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output, _ = process.communicate(timeout=30)
        if process.returncode:
            raise ValueError("Could not create a temporary inspection virtualenv")
        info = json.loads(output)
        site = Path(info["site"])
        relative = site.relative_to(Path(info["prefix"]))
        destination = folder / relative
        destination.mkdir(parents=True, exist_ok=True)
        for path in site.glob("*.dist-info"):
            if path.is_dir() and not path.is_symlink():
                shutil.copytree(path, destination / path.name, symlinks=False)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise ValueError("Cannot inspect the project virtualenv for preview") from error
    return folder / "bin/python"


def preview_dependencies(target, *, online=False, output_format="terminal"):
    target = Path(target).absolute()
    with tempfile.TemporaryDirectory(prefix="plonex-preview-") as temporary:
        root = Path(temporary)
        var = root / "var"
        var.mkdir()
        (root / "tmp").mkdir()

        class PreviewInstall(InstallService):
            @property
            def var_folder(self):
                return var

            def _parse_requirement_source(self, source):
                if self._is_remote_requirement_source(source):
                    cached = ConstraintCache(var / "cache/constraints").path(
                        str(source)
                    )
                    if not cached.is_file():
                        raise ValueError(
                            "A remote constraint is not cached. "
                            "Run plonex dependencies install first."
                        )
                return super()._parse_requirement_source(source)

        with read_only():
            original = InstallService(target=target, dont_ask=True)
            original.options
            original_var = original.var_folder
            cache = original_var / "cache/constraints"
            if cache.is_dir():
                destination = var / "cache/constraints"
                destination.mkdir(parents=True)
                for item in cache.iterdir():
                    if item.is_file() and not item.is_symlink():
                        shutil.copyfile(item, destination / item.name)
            service = PreviewInstall(target=target, dont_ask=True)
            service.tmp_folder = root / "tmp"
            service._use_cached_constraints = True
            service.source_install_plan.validate()
        service.make_requirements_txt()
        service.make_constraints_txt()
        requirements = (var / "requirements.txt").read_text()
        constraints = (var / "constraints.txt").read_text()
        previous = original_var / "constraints.txt"
        old = previous.read_text().splitlines() if previous.is_file() else []
        diff = "\n".join(
            difflib.unified_diff(
                old,
                constraints.splitlines(),
                fromfile="existing constraints",
                tofile="proposed constraints",
                lineterm="",
            )
        )
        uv = target / ".venv/bin/uv"
        python = target / ".venv/bin/python"
        if not uv.is_file() or not python.is_file():
            raise ValueError(
                "Project uv or Python is missing. "
                "Run plonex dependencies install first."
            )
        inspection_python = inspection_environment(python, root / "environment")
        command = [
            str(uv),
            "pip",
            "install",
            "--dry-run",
            "--python",
            str(inspection_python),
            "-r",
            str(var / "requirements.txt"),
            "-c",
            str(var / "constraints.txt"),
        ]
        if not online:
            command.append("--offline")
        try:
            process = subprocess.run(
                command, cwd=target, capture_output=True, text=True, timeout=120
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError("Cannot run the uv dependency preview") from error
        payload = safe_value(
            {
                "resolved": process.returncode == 0,
                "offline": not online,
                "requirements": requirements,
                "constraints_diff": diff,
                "resolver_output": (process.stdout + process.stderr).strip(),
            }
        )
    console = Console()
    if output_format == "json":
        console.print(
            json.dumps(payload, indent=2), markup=False, highlight=False, soft_wrap=True
        )
    else:
        console.print("Proposed requirements:", style="bold")
        console.print(payload["requirements"], markup=False, highlight=False)
        if payload["constraints_diff"]:
            console.print("Constraint changes:", style="bold")
            console.print(payload["constraints_diff"], markup=False, highlight=False)
        console.print(
            payload["resolver_output"] or "No resolver changes reported.",
            markup=False,
            highlight=False,
        )
    return payload
