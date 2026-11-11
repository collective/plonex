from plonex.base import BaseService
from plonex.cli import main
from plonex.environment import load_project_environment

import os
import pytest
import sys


def test_project_environment_syntax_and_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "# comment\nexport ENV_TEST_SHELL=file\nENV_TEST_FILE='hello # world'\n"
        'ENV_TEST_EMPTY=\nENV_TEST_LITERAL="${ENV_TEST_SHELL}"\n'
    )
    monkeypatch.setenv("ENV_TEST_SHELL", "shell")
    for name in ("ENV_TEST_FILE", "ENV_TEST_EMPTY", "ENV_TEST_LITERAL"):
        monkeypatch.delenv(name, raising=False)
    load_project_environment(tmp_path)
    assert os.environ["ENV_TEST_SHELL"] == "shell"
    assert os.environ["ENV_TEST_FILE"] == "hello # world"
    assert os.environ["ENV_TEST_EMPTY"] == ""
    assert os.environ["ENV_TEST_LITERAL"] == "${ENV_TEST_SHELL}"
    service = BaseService(
        target=tmp_path,
        cli_options={
            "environment_vars": {"ENV_TEST_SHELL": "yaml", "ENV_TEST_FILE": "yaml"}
        },
    )
    with service:
        assert os.environ["ENV_TEST_SHELL"] == "yaml"
        assert os.environ["ENV_TEST_FILE"] == "yaml"


def test_invalid_file_does_not_partially_load(tmp_path, monkeypatch):
    monkeypatch.delenv("ENV_TEST_PARTIAL", raising=False)
    (tmp_path / ".env").write_text("ENV_TEST_PARTIAL=ok\ninvalid line\n")
    with pytest.raises(ValueError, match=r"\.env:2"):
        load_project_environment(tmp_path)
    assert "ENV_TEST_PARTIAL" not in os.environ


def test_cli_loads_resolved_project_environment(tmp_path, monkeypatch):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("{}\n")
    (tmp_path / ".env").write_text("ENV_TEST_CLI=project\n")
    child = tmp_path / "child"
    child.mkdir()
    monkeypatch.delenv("ENV_TEST_CLI", raising=False)
    monkeypatch.setattr(sys, "argv", ["plonex", "-t", str(child), "project", "compile"])
    seen = []
    monkeypatch.setattr(
        "plonex.cli._dispatch",
        lambda *args: seen.append(os.environ.get("ENV_TEST_CLI")),
    )
    main()
    assert seen == ["project"]


def test_local_environment_overrides_file_but_not_shell(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "ENV_LAYER=base\nENV_SHELL=sourced\nENV_BASE_ONLY=base\n"
    )
    (tmp_path / ".env.local").write_text(
        "ENV_LAYER=local\nENV_SHELL=local\nENV_LOCAL_ONLY=local\n"
    )
    (tmp_path / ".env.production").write_text("ENV_LAYER=production\n")
    monkeypatch.setenv("ENV_SHELL", "")
    for name in ("ENV_LAYER", "ENV_BASE_ONLY", "ENV_LOCAL_ONLY"):
        monkeypatch.delenv(name, raising=False)
    load_project_environment(tmp_path)
    assert os.environ["ENV_LAYER"] == "local"
    assert os.environ["ENV_SHELL"] == ""
    assert os.environ["ENV_BASE_ONLY"] == "base"
    assert os.environ["ENV_LOCAL_ONLY"] == "local"


def test_invalid_local_file_does_not_partially_load_base(tmp_path, monkeypatch):
    monkeypatch.delenv("ENV_TEST_PARTIAL", raising=False)
    (tmp_path / ".env").write_text("ENV_TEST_PARTIAL=base\n")
    (tmp_path / ".env.local").write_text("invalid\n")
    with pytest.raises(ValueError, match=r"\.env\.local:1"):
        load_project_environment(tmp_path)
    assert "ENV_TEST_PARTIAL" not in os.environ


def test_local_file_works_without_base(tmp_path, monkeypatch):
    monkeypatch.delenv("ENV_LOCAL_ONLY", raising=False)
    (tmp_path / ".env.local").write_text("ENV_LOCAL_ONLY=local\n")
    load_project_environment(tmp_path)
    assert os.environ["ENV_LOCAL_ONLY"] == "local"
