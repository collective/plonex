"""Real isolated project interpreters, assembled from installed test dependencies."""

from importlib.metadata import distribution
from packaging.requirements import Requirement
from pathlib import Path
from plonex.services.cron.installation import WORKER_REQUIREMENTS

import pytest
import shutil
import subprocess
import tomllib
import venv


@pytest.fixture(scope="session")
def runtime_environment_template(tmp_path_factory):
    """No network or inherited site-packages: copy installed distributions only."""
    root = tmp_path_factory.mktemp("worker-environment") / "venv"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(root)
    site = Path(
        subprocess.check_output(
            [
                str(root / "bin/python"),
                "-I",
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            text=True,
        ).strip()
    )
    metadata = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    pending = (
        metadata["project"]["dependencies"] + list(WORKER_REQUIREMENTS) + ["supervisor"]
    )
    copied = set()
    while pending:
        requirement = Requirement(pending.pop())
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        name = requirement.name.lower().replace("_", "-")
        if name in copied:
            continue
        copied.add(name)
        installed = distribution(requirement.name)
        extras = {"", *requirement.extras}
        for spec in installed.requires or []:
            child = Requirement(spec)
            if child.marker is None or any(
                child.marker.evaluate({"extra": extra}) for extra in extras
            ):
                pending.append(str(child).split(";", 1)[0])
        for filename in installed.files or []:
            if ".." in filename.parts or filename.suffix == ".pyc":
                continue
            source = installed.locate_file(filename)
            if source.is_file():
                destination = site / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    source = Path(__file__).parents[1] / "src/plonex"
    shutil.copytree(
        source, site / "plonex", ignore=shutil.ignore_patterns("__pycache__")
    )
    info = site / f"plonex-{metadata['project']['version']}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: plonex\n"
        f"Version: {metadata['project']['version']}\n"
    )
    return root


@pytest.fixture
def install_job_runtime(runtime_environment_template):
    def install(project):
        destination = project / ".venv"
        shutil.copytree(runtime_environment_template, destination, symlinks=True)
        return destination / "bin/python"

    return install
