from pathlib import Path
from plonex.services.install.preview import preview_dependencies
from unittest import mock

import json
import pytest
import subprocess
import sys
import venv


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc/requirements.d").mkdir(parents=True)
    (tmp_path / "etc/constraints.d").mkdir(parents=True)
    (tmp_path / "etc/plonex.yml").write_text(
        "plonex_base_constraint: null\npip_requirements: [demo]\n"
    )
    (tmp_path / "etc/constraints.d/local.txt").write_text("demo==1.2\n")
    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    (tmp_path / ".venv/bin/uv").symlink_to(Path(sys.prefix) / "bin/uv")
    return tmp_path


def test_preview_generates_inputs_offline_and_never_writes_project(project, capsys):
    before = {p.relative_to(project) for p in project.rglob("*")}
    fake = subprocess.CompletedProcess([], 0, stdout="Would install demo", stderr="")
    with mock.patch(
        "plonex.services.install.preview.subprocess.run", return_value=fake
    ) as run:
        result = preview_dependencies(project, output_format="json")
    assert json.loads(capsys.readouterr().out) == result
    assert result["resolved"] and result["offline"]
    assert "demo" in result["requirements"]
    assert "demo==1.2" in result["constraints_diff"]
    command = run.call_args.args[0]
    assert "--dry-run" in command and "--offline" in command
    assert before == {p.relative_to(project) for p in project.rglob("*")}
    assert not (project / "var").exists()


def test_preview_never_fetches_missing_remote_constraints(project):
    (project / "etc/plonex.yml").write_text(
        "plonex_base_constraint: https://example.invalid/constraints.txt\n"
    )
    with mock.patch(
        "requests.get", side_effect=AssertionError("network request")
    ) as fetch:
        with pytest.raises(ValueError, match="not cached"):
            preview_dependencies(project)
    fetch.assert_not_called()
    assert not (project / "var").exists()


def test_preview_uses_cached_nested_constraints_without_network_or_mutation(
    project, capsys
):
    from plonex.preparation.dependencies import ConstraintCache

    base = "https://example.invalid/base.txt"
    (project / "etc/plonex.yml").write_text(f"plonex_base_constraint: {base}\n")
    cache = ConstraintCache(project / "var/cache/constraints")
    cache.store(base, "-c nested.txt\n")
    cache.store("https://example.invalid/nested.txt", "zope==6.2\n")
    before = {
        p.relative_to(project): p.read_bytes()
        for p in (project / "var").rglob("*")
        if p.is_file()
    }
    fake = subprocess.CompletedProcess([], 0, stdout="No changes", stderr="")
    with mock.patch("requests.get", side_effect=AssertionError("unexpected fetch")):
        with mock.patch(
            "plonex.services.install.preview.subprocess.run", return_value=fake
        ):
            result = preview_dependencies(project, output_format="json")
    capsys.readouterr()
    assert "zope==6.2" in result["constraints_diff"]
    after = {
        p.relative_to(project): p.read_bytes()
        for p in (project / "var").rglob("*")
        if p.is_file()
    }
    assert before == after


def test_preview_cli_is_read_only_and_passes_options(project):
    from plonex.cli import main

    argv = ["plonex", "dependencies", "preview", "--online", "--format", "json"]
    with mock.patch.object(sys, "argv", argv):
        with mock.patch(
            "plonex.services.install.preview.preview_dependencies",
            return_value={"resolved": True},
        ) as preview:
            main()
    preview.assert_called_once_with(
        project.resolve(), online=True, output_format="json"
    )
    assert not (project / "var").exists()


def test_real_uv_preview_does_not_modify_the_project(project):
    import os
    import tempfile

    before = {p.relative_to(project) for p in project.rglob("*")}
    with tempfile.TemporaryDirectory(prefix="plonex-uv-preview-test-") as cache:
        environment = dict(os.environ) | {"UV_CACHE_DIR": cache, "UV_OFFLINE": "1"}
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "plonex.cli",
                "--target",
                str(project),
                "dependencies",
                "preview",
                "--format",
                "json",
            ],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
        )
    assert process.returncode in {0, 1}, process.stderr
    result = json.loads(process.stdout)
    assert result["offline"] is True
    assert "--dry-run" not in result["requirements"]
    assert before == {p.relative_to(project) for p in project.rglob("*")}
