from plonex.services.sources import SourcesService
from textwrap import dedent
from unittest import mock

import pytest
import yaml


def run_release(project, *args, **kwargs):
    with SourcesService(target=project) as service:
        return service.run_release(*args, **kwargs)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {"sources": {"demo": {"repo": "example", "path": "custom/demo"}}}
        )
    )
    (tmp_path / "custom/demo").mkdir(parents=True)
    return tmp_path


def test_release_runs_in_checkout_and_uses_repository(project, monkeypatch):
    monkeypatch.setenv("TWINE_REPOSITORY", "private")
    with mock.patch("plonex.services.sources.subprocess.run") as run:
        run.return_value.returncode = 7
        assert run_release(project, "demo", "other") == 7
    args, kwargs = run.call_args
    assert args[0] == [
        "uvx",
        "--from",
        "zest-releaser",
        "--with",
        "zest-releaser[recommended]",
        "--with",
        "zestreleaser-towncrier",
        "fullrelease",
    ]
    assert kwargs["cwd"] == project / "custom/demo"
    assert kwargs["env"]["TWINE_REPOSITORY"] == "other"


def test_release_repository_defaults_and_invalid_sources(project, monkeypatch):
    monkeypatch.setenv("TWINE_REPOSITORY", "private")
    with mock.patch("plonex.services.sources.subprocess.run") as run:
        run.return_value.returncode = 0
        run_release(project, "demo")
        assert run.call_args.kwargs["env"]["TWINE_REPOSITORY"] == "private"
        monkeypatch.delenv("TWINE_REPOSITORY")
        run_release(project, "demo")
        assert run.call_args.kwargs["env"]["TWINE_REPOSITORY"] == "pypi"
        with pytest.raises(ValueError, match="Unknown source"):
            run_release(project, "unknown")
        (project / "custom/demo").rmdir()
        with pytest.raises(ValueError, match="missing"):
            run_release(project, "demo")
        assert run.call_count == 2


def test_cli_release_passes_arguments_and_exit_code(project, monkeypatch):
    import subprocess
    import sys

    bin_dir = project / "bin"
    bin_dir.mkdir()
    uvx = bin_dir / "uvx"
    uvx.write_text(dedent("""\
            #!/bin/sh
            printf "%s\\n" "$PWD" "$TWINE_REPOSITORY" "$@" > release-result
            exit 3
            """))
    uvx.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "plonex.cli",
            "--target",
            str(project),
            "sources",
            "release",
            "demo",
            "--repository",
            "private",
            "--stage",
            "prerelease",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3, result.stderr
    lines = (project / "custom/demo/release-result").read_text().splitlines()
    assert lines == [
        str(project / "custom/demo"),
        "private",
        "--from",
        "zest-releaser",
        "--with",
        "zest-releaser[recommended]",
        "--with",
        "zestreleaser-towncrier",
        "prerelease",
    ]


@pytest.mark.parametrize(
    "stage", ["fullrelease", "prerelease", "release", "postrelease"]
)
def test_release_stage_and_configured_repository(project, monkeypatch, stage):
    config = project / "etc/plonex.yml"
    data = yaml.safe_load(config.read_text())
    data["sources"]["demo"]["release_repository"] = "configured"
    config.write_text(yaml.safe_dump(data))
    monkeypatch.setenv("TWINE_REPOSITORY", "environment")
    with mock.patch("plonex.services.sources.subprocess.run") as run:
        run.return_value.returncode = 0
        run_release(project, "demo", stage=stage)
        assert run.call_args.args[0][-1] == stage
        assert run.call_args.kwargs["env"]["TWINE_REPOSITORY"] == "configured"
        run_release(project, "demo", "override", stage)
        assert run.call_args.kwargs["env"]["TWINE_REPOSITORY"] == "override"


def test_invalid_configured_repository_is_rejected(project):
    config = project / "etc/plonex.yml"
    data = yaml.safe_load(config.read_text())
    data["sources"]["demo"]["release_repository"] = ["invalid"]
    config.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="release_repository"):
        run_release(project, "demo")
