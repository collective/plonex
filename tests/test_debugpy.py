from plonex.cli.parser import build_parser
from plonex.services.invocation import ServiceInvocation

import pytest
import venv


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("{}\n")
    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    return tmp_path


def test_debugger_is_opt_in_and_bound_only_to_loopback(project):
    parser = build_parser(target=project)
    args = parser.parse_args(
        ["instance", "debug", "--debugpy", "5678", "--wait-for-debugger"]
    )
    service = ServiceInvocation.from_args(args, project).create()
    command = service.command
    assert command[:5] == [
        str(project / ".venv/bin/python"),
        "-m",
        "debugpy",
        "--listen",
        "127.0.0.1:5678",
    ]
    assert "--wait-for-client" in command
    assert str(project / ".venv/bin/runwsgi") in command
    normal = ServiceInvocation.from_args(
        parser.parse_args(["instance", "debug"]), project
    ).create()
    assert "debugpy" not in normal.command


def test_debugger_options_validate_and_missing_dependency_is_actionable(project):
    parser = build_parser(target=project)
    for argv in (
        ["instance", "debug", "--debugpy", "0"],
        ["instance", "debug", "--wait-for-debugger"],
    ):
        with pytest.raises(ValueError):
            ServiceInvocation.from_args(parser.parse_args(argv), project)
    service = ServiceInvocation.from_args(
        parser.parse_args(["instance", "debug", "--debugpy", "5678"]), project
    ).create()
    with service:
        with pytest.raises(ValueError, match="dependencies add debugpy"):
            service.run()
