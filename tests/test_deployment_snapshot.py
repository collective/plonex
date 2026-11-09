from pathlib import Path
from plonex.services.snapshot import capture
from plonex.services.snapshot import differences
from plonex.services.snapshot import load
from plonex.services.snapshot import write_new

import json
import pytest
import subprocess
import sys
import venv
import yaml


@pytest.fixture
def project(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("plonex_base_constraint: null\n")
    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    return tmp_path


def test_snapshot_compares_project_metadata_and_never_replaces_output(project):
    site = next((project / ".venv/lib").glob("python*/site-packages"))
    info = site / "Demo_Pkg-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Name: Demo.Pkg\nVersion: 1.0\n")
    snapshot = capture(project)
    assert snapshot["packages"]["demo-pkg"]["version"] == "1.0"
    file = write_new(project / "snapshot.json", snapshot)
    assert load(file) == snapshot
    with pytest.raises(ValueError, match="Cannot create snapshot"):
        write_new(file, snapshot)
    assert load(file) == snapshot
    assert not list(project.glob(".plonex-snapshot-*"))
    (info / "METADATA").write_text("Name: Demo.Pkg\nVersion: 2.0\n")
    changes = differences(snapshot, capture(project))
    assert any(
        c["path"] == "packages.demo-pkg.version" and c["after"] == "2.0"
        for c in changes
    )


def test_snapshot_tracks_dirty_git_sources_and_redacts_credentials(project):
    checkout = project / "src/demo"
    checkout.mkdir(parents=True)
    for args in (
        ["git", "init", "-q"],
        ["git", "add", "pyproject.toml"],
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "initial",
        ],
    ):
        if args[1] == "add":
            (checkout / "pyproject.toml").write_text(
                '[project]\nname="demo"\nversion="1"\n'
            )
        subprocess.run(args, cwd=checkout, check=True)
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "sources": {
                    "demo": {
                        "repo": "https://user:secret@example.org/repo",
                        "install": True,
                        "extras": ["test"],
                    }
                },
            }
        )
    )
    clean = capture(project)
    assert clean["sources"]["demo"]["dirty"] is False
    assert clean["sources"]["demo"]["commit"]
    assert "secret@" not in json.dumps(clean)
    (checkout / "new.py").write_text("print(1)\n")
    dirty = capture(project)
    assert dirty["sources"]["demo"]["dirty"] is True
    assert any("uncommitted" in issue for issue in dirty["issues"])
    assert any(c["path"] == "sources.demo.dirty" for c in differences(clean, dirty))


def test_cli_snapshot_create_and_compare_exit_status(project, monkeypatch, tmp_path):
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "uv-cache"))
    monkeypatch.setenv("UV_OFFLINE", "1")
    target = project / "state.json"
    base = [
        sys.executable,
        "-m",
        "plonex.cli",
        "--target",
        str(project),
        "project",
        "snapshot",
    ]
    create = subprocess.run(
        [*base, "create", "--output", str(target)], capture_output=True, text=True
    )
    assert create.returncode == 0, create.stderr
    assert target.is_file()
    same = subprocess.run(
        [*base, "compare", str(target), "--format", "json"],
        capture_output=True,
        text=True,
    )
    assert same.returncode == 0, same.stderr
    assert json.loads(same.stdout)["differences"] == []
    destination = project / "prepared"
    prepared = subprocess.run(
        [*base, "prepare", str(target), "--to", str(destination)],
        capture_output=True,
        text=True,
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    assert (destination / "bin/python").is_file()
    (project / "etc/plonex.local.yml").write_text("http_port: 9000\n")
    changed = subprocess.run(
        [*base, "compare", str(target), "--format", "json"],
        capture_output=True,
        text=True,
    )
    assert changed.returncode == 1, changed.stderr
    assert json.loads(changed.stdout)["differences"]
    terminal = subprocess.run(
        [*base, "compare", str(target)], capture_output=True, text=True
    )
    assert terminal.returncode == 1
    assert "etc/plonex.local.yml" in terminal.stdout
    assert "→" in terminal.stdout


def test_prepare_recreates_versions_in_a_new_environment_and_refuses_existing(
    project, monkeypatch
):
    from plonex.services.snapshot import prepare

    monkeypatch.setenv("UV_CACHE_DIR", "/tmp/plonex-test-uv-cache")
    monkeypatch.setenv("UV_OFFLINE", "1")
    snapshot = capture(project)
    destination = project / "new-environment"
    assert prepare(project, snapshot, destination) == destination
    assert (destination / "bin/python").is_file()
    with pytest.raises(ValueError, match="already exists"):
        prepare(project, snapshot, destination)


def test_prepare_refuses_drift_and_external_sources_before_creating_environment(
    project,
):
    from plonex.services.snapshot import prepare

    snapshot = capture(project)
    destination = project / "new-environment"
    (project / "etc/plonex.local.yml").write_text("http_port: 9000\n")
    with pytest.raises(ValueError, match="inputs differs"):
        prepare(project, snapshot, destination)
    assert not destination.exists()
    (project / "etc/plonex.local.yml").unlink()
    snapshot["packages"]["demo"] = {
        "version": "1.0",
        "source": "external:/other/demo",
        "editable": True,
        "commit": "",
    }
    with pytest.raises(ValueError, match="unsupported external"):
        prepare(project, snapshot, destination)
    assert not destination.exists()


def test_snapshot_flags_nested_inputs_and_tracks_profile_changes(project):
    from plonex.services.snapshot import prepare

    profile = project / "profile"
    (profile / "etc/requirements.d").mkdir(parents=True)
    (profile / "etc/plonex.yml").write_text("{}\n")
    fragment = profile / "etc/requirements.d/local.txt"
    fragment.write_text("-r another.txt\n")
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "profiles": [str(profile)],
            }
        )
    )
    first = capture(project)
    assert any("Nested dependency inputs" in issue for issue in first["issues"])
    with pytest.raises(ValueError, match="unresolved"):
        prepare(project, first, project / "new-env")
    fragment.write_text("demo==2.0\n")
    assert differences(first, capture(project))


def test_prepare_reinstalls_a_clean_editable_checkout_offline(
    project, monkeypatch, tmp_path
):
    from plonex.services.snapshot import prepare

    checkout = project / "src/demo"
    checkout.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("""[build-system]
requires = []
build-backend = "backend"
backend-path = ["."]
[project]
name = "demo"
version = "1.0"
""")
    (checkout / "demo.py").write_text("VALUE = 42\n")
    (checkout / ".gitignore").write_text("__pycache__/\n")
    (checkout / "backend.py").write_text("""
from pathlib import Path
from zipfile import ZipFile

def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    filename = "demo-1.0-py3-none-any.whl"
    info = "demo-1.0.dist-info/"
    entries = {"demo.pth": str(Path(__file__).parent) + "\\n",
               info + "METADATA": "Metadata-Version: 2.1\\n"
                                  "Name: demo\\nVersion: 1.0\\n",
               info + "WHEEL": "Wheel-Version: 1.0\\nGenerator: test\\n"
                               "Root-Is-Purelib: true\\nTag: py3-none-any\\n"}
    entries[info + "RECORD"] = (
        "".join(f"{name},,\\n" for name in entries) + info + "RECORD,,\\n"
    )
    with ZipFile(Path(wheel_directory) / filename, "w") as wheel:
        for name, data in entries.items():
            wheel.writestr(name, data)
    return filename
""")
    subprocess.run(["git", "init", "-q"], cwd=checkout, check=True)
    subprocess.run(["git", "add", "."], cwd=checkout, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.org",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=checkout,
        check=True,
    )
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "sources": {
                    "demo": {"repo": "https://example.org/demo.git", "install": True}
                },
            }
        )
    )
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "uv-cache"))
    monkeypatch.setenv("UV_OFFLINE", "1")
    uv = str(Path(sys.executable).parent / "uv")
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(project / ".venv/bin/python"),
            "-e",
            str(checkout),
        ],
        cwd=project,
        check=True,
        capture_output=True,
    )
    snapshot = capture(project)
    assert snapshot["issues"] == []
    assert snapshot["packages"]["demo"]["source"] == "project:src/demo"
    destination = prepare(project, snapshot, project / "reconstructed")
    result = subprocess.check_output(
        [
            str(destination / "bin/python"),
            "-I",
            "-B",
            "-c",
            "import demo; print(demo.VALUE)",
        ],
        text=True,
    )
    assert result.strip() == "42"
