from importlib.metadata import version
from plonex.cli.parser import build_parser
from plonex.services.invocation import ServiceInvocation
from unittest.mock import patch

import os
import pytest
import yaml


@pytest.mark.parametrize(
    ("arguments", "name", "command"),
    [
        (["start", "--name", "instance1"], "instance1", "instance start"),
        (["debug", "--name", "worker"], "worker", "instance debug"),
        (["console", "--name", "console1"], "console1", "instance console"),
        (["run", "script.py"], "zconsole", "instance run"),
    ],
)
def test_instance_environment(tmp_path, monkeypatch, arguments, name, command):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/activate").touch()
    expected = {
        "PLONEX_TARGET": str(tmp_path),
        "PLONEX_INSTANCE_NAME": name,
        "PLONEX_INSTANCE_HOME": str(tmp_path / "tmp" / name),
        "PLONEX_COMMAND": command,
        "PLONEX_VERSION": version("plonex"),
    }
    (tmp_path / "etc/plonex.yml").write_text(
        yaml.safe_dump({"environment_vars": dict.fromkeys(expected, "configured")})
    )
    for key in expected:
        monkeypatch.setenv(key, "inherited")
    parser = build_parser(target=tmp_path)
    invocation = ServiceInvocation.from_args(
        parser.parse_args(["instance", *arguments]), tmp_path
    )
    with invocation.create() as service:
        text = (service.tmp_folder / "etc/zope.conf").read_text()
        for key, value in expected.items():
            assert f"{key} {value}\n" in text
            os.environ[key] = "before-command"
        with patch.object(service, "execute_command") as execute:

            def check_environment(*args, **kwargs):
                assert {key: os.environ[key] for key in expected} == expected

            execute.side_effect = check_environment
            service.run_command(["true"])
        assert all(os.environ[key] == "before-command" for key in expected)
