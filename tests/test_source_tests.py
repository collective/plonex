import subprocess
import sys
import venv
import yaml


def test_configured_source_runner_uses_source_cwd_and_forwards_arguments(tmp_path):
    (tmp_path / "etc").mkdir()
    source = tmp_path / "src/demo"
    source.mkdir(parents=True)
    (source / "pyproject.toml").write_text('[project]\nname="demo"\nversion="1"\n')
    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    script = (
        "import os,sys; print(os.getcwd()); print(sys.prefix); "
        'print("/".join(sys.argv[1:]))'
    )
    (tmp_path / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "sources": {
                    "demo": {
                        "repo": "https://example.org/r",
                        "install": True,
                        "test_command": ["python", "-c", script],
                    }
                },
            }
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "plonex.cli",
            "--target",
            str(tmp_path),
            "test",
            "sources",
            "demo",
            "--",
            "-k",
            "login",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert str(source) in result.stdout
    assert str(tmp_path / ".venv") in result.stdout
    assert "-k/login" in result.stdout


def test_source_runner_validates_every_requested_command_before_running_any(tmp_path):
    from plonex.services.sources.testing import run_selected_tests

    import pytest

    (tmp_path / "etc").mkdir()
    for name in ("first", "second"):
        source = tmp_path / "src" / name
        source.mkdir(parents=True)
        (source / "pyproject.toml").write_text(
            f'[project]\nname="{name}"\nversion="1"\n'
        )
    (tmp_path / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "first": {
                        "repo": "https://example.org/a",
                        "install": True,
                        "test_command": ["python", "-c", 'open("ran", "w").close()'],
                    },
                    "second": {
                        "repo": "https://example.org/b",
                        "install": True,
                        "test_command": "not an argv list",
                    },
                },
            }
        )
    )
    with pytest.raises(ValueError, match="test_command"):
        run_selected_tests(tmp_path, ["first", "second"])
    assert not (tmp_path / "src/first/ran").exists()
