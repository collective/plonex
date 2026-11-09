from plonex.cli import main
from unittest import mock

import json
import pytest
import sys
import venv
import yaml


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("plonex_base_constraint: null\n")
    return tmp_path


@pytest.fixture
def project_python(project):
    venv.EnvBuilder(with_pip=False).create(project / ".venv")
    return project / ".venv/bin/python"


def distribution(project, name, version, *, url="", editable=False, requires=()):
    site = next((project / ".venv/lib").glob("python*/site-packages"))
    info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir()
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    metadata += "".join(f"Requires-Dist: {spec}\n" for spec in requires)
    (info / "METADATA").write_text(metadata)
    if url:
        (info / "direct_url.json").write_text(
            json.dumps({"url": url, "dir_info": {"editable": editable}})
        )


def invoke(capsys, *args):
    with mock.patch.object(
        sys, "argv", ["plonex", "project", "doctor", "--format", "json", *args]
    ):
        try:
            main()
            code = 0
        except SystemExit as error:
            code = error.code
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_doctor_reports_multiple_issues_without_project_mutations(project, capsys):
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": (
                    "https://github.com/example/repo/blob/main/constraints.txt"
                ),
                "sources": {
                    "missing": {"repo": "https://example.org/repo.git", "install": True}
                },
            }
        )
    )
    before = {
        str(path.relative_to(project)): path.read_bytes() if path.is_file() else None
        for path in project.rglob("*")
    }
    code, report, _ = invoke(capsys)
    after = {
        str(path.relative_to(project)): path.read_bytes() if path.is_file() else None
        for path in project.rglob("*")
    }
    assert before == after
    assert code == 1
    codes = {finding["code"] for finding in report["findings"]}
    assert {
        "environment.missing",
        "sources.missing",
        "constraints.github_html",
    } <= codes
    assert report["summary"]["error"] >= 3


def test_invalid_yaml_and_uncached_profiles_are_diagnosable(project, capsys):
    config = project / "etc/plonex.yml"
    config.write_text("sources: [not valid\n")
    code, report, _ = invoke(capsys)
    assert code == 1
    assert any(f["code"] == "configuration.invalid" for f in report["findings"])
    config.write_text("profiles:\n  - https://example.invalid/private.git\n")
    with mock.patch(
        "subprocess.run", side_effect=AssertionError("unexpected subprocess")
    ):
        code, report, _ = invoke(capsys)
    assert code == 1
    assert any(f["code"] == "configuration.unavailable" for f in report["findings"])
    assert all(f["code"] != "check.failed" for f in report["findings"])
    assert not (project / "var").exists()


def test_source_install_mode_extra_requirements_and_effective_constraints(
    project, project_python, capsys
):
    checkout = project / "src" / "local"
    checkout.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        '[project]\nname="Demo.Pkg"\nversion="1"\n'
    )
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "pip_requirements": ["other-package>=2"],
                "sources": {
                    "local": {
                        "repo": "https://example.org/r.git",
                        "install": True,
                        "extras": ["test"],
                    }
                },
            }
        )
    )
    distribution(
        project,
        "Demo.Pkg",
        "1",
        url=checkout.as_uri(),
        editable=False,
        requires=['missing-addon>=2; extra == "test"'],
    )
    distribution(project, "other-package", "1")
    var = project / "var"
    var.mkdir()
    (var / "constraints.txt").write_text("other-package==3\n")
    code, report, _ = invoke(capsys)
    codes = {finding["code"] for finding in report["findings"]}
    assert code == 0
    assert {
        "sources.installation_mismatch",
        "sources.extras_unverified",
        "sources.extra_dependency",
        "requirements.version",
        "constraints.installed_version",
    } <= codes
    mismatch = next(
        f for f in report["findings"] if f["code"] == "sources.installation_mismatch"
    )
    assert "editable" in mismatch["detail"]
    code, _, _ = invoke(capsys, "--strict")
    assert code == 1


def test_uninstalled_selected_source_and_html_local_constraints(
    project, project_python, capsys
):
    checkout = project / "src/demo"
    checkout.mkdir(parents=True)
    (checkout / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="demo")\n'
    )
    (project / "etc/constraints.txt").write_text("<!doctype html><html>oops</html>")
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": "etc/constraints.txt",
                "sources": {
                    "demo": {"repo": "https://example.org/r.git", "install": True}
                },
            }
        )
    )
    code, report, _ = invoke(capsys)
    assert code == 1
    codes = {f["code"] for f in report["findings"]}
    assert {"sources.not_installed", "constraints.html"} <= codes


def test_real_target_interpreter_and_no_local_state_created(
    project, project_python, capsys
):
    before = {p.relative_to(project) for p in project.rglob("*")}
    code, report, _ = invoke(capsys)
    after = {p.relative_to(project) for p in project.rglob("*")}
    assert before == after
    assert code == 0
    python = next(f for f in report["findings"] if f["code"] == "environment.python")
    assert str(project_python) in python["detail"]
    assert not (project / "var").exists()


def test_generated_json_redacts_constraint_url_credentials(project, capsys):
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": (
                    "https://user:password@github.com/a/b/blob/main/c.txt?token=secret"
                )
            }
        )
    )
    _, report, _ = invoke(capsys)
    text = json.dumps(report)
    assert "password@" not in text
    assert "token=secret" not in text
    assert "[redacted]" in text


def test_healthy_editable_source_and_satisfied_extra_are_recognized(
    project, project_python, capsys
):
    checkout = project / "src/demo"
    checkout.mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        '[project]\nname="Demo.Pkg"\nversion="1"\n'
    )
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "sources": {
                    "demo": {
                        "repo": "https://example.org/r.git",
                        "install": True,
                        "extras": ["test"],
                    }
                },
            }
        )
    )
    distribution(
        project,
        "Demo.Pkg",
        "1",
        url=checkout.as_uri(),
        editable=True,
        requires=['addon>=2; extra == "test"'],
    )
    distribution(project, "addon", "2.1")
    _, report, _ = invoke(capsys)
    codes = {f["code"] for f in report["findings"]}
    assert "sources.installation_mismatch" not in codes
    assert "sources.not_installed" not in codes
    assert "sources.extra_dependency" not in codes
    assert "sources.extras_unverified" in codes


def test_local_zeo_connection_and_supervisor_programs_are_reported(
    project, project_python, capsys
):
    var = project / "var"
    var.mkdir()
    (project / "etc/plonex-zeoserver.yml").write_text(
        "zeo_address: var/custom-zeo.sock\n"
    )
    configuration = project / "tmp/supervisor/etc/supervisord.conf"
    configuration.parent.mkdir(parents=True)
    configuration.write_text("[supervisord]\n")
    control = project / ".venv/bin/supervisorctl"
    control.write_text(
        '#!/bin/sh\nprintf "client FATAL exited\\nzeo RUNNING pid 5\\n"\nexit 3\n'
    )
    control.chmod(0o755)
    with mock.patch("plonex.services.doctor.socket.socket") as socket_factory:
        _, report, _ = invoke(capsys)
    socket_factory.return_value.__enter__.return_value.connect.assert_called_once_with(
        str(var / "custom-zeo.sock")
    )
    codes = {f["code"] for f in report["findings"]}
    assert {"zeo.reachable", "supervisor.failed", "supervisor.checked"} <= codes


def test_invalid_option_does_not_claim_configuration_is_healthy(project, capsys):
    from plonex import logger

    import logging

    (project / "etc/plonex.yml").write_text("sources: invalid\n")
    old_level = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        code, report, _ = invoke(capsys)
        assert logger.level == logging.CRITICAL
    finally:
        logger.setLevel(old_level)
    codes = {f["code"] for f in report["findings"]}
    assert code == 1
    assert "configuration.invalid" in codes
    assert "configuration.loaded" not in codes


def test_permission_denied_does_not_claim_zeo_is_down(project, capsys):
    import errno

    with mock.patch(
        "plonex.services.doctor.socket.socket",
        side_effect=PermissionError(errno.EPERM, "denied"),
    ):
        _, report, _ = invoke(capsys)
    codes = {f["code"] for f in report["findings"]}
    assert "zeo.unchecked" in codes
    assert "zeo.unreachable" not in codes


def test_doctor_is_registered_for_options_inspection(project):
    from plonex.cli.parser import build_parser
    from plonex.services.doctor import Doctor
    from plonex.services.invocation import ServiceInvocation

    args = build_parser(target=project).parse_args(["project", "doctor"])
    assert ServiceInvocation.from_args(args, project).service_type is Doctor


def test_always_run_preparation_tasks_are_not_diagnosed_as_stale(project, capsys):
    entries = [
        {
            "task": "helper",
            "state": "stale",
            "reasons": ["explicit operation; always evaluated"],
            "requires": (),
            "affected": (),
        },
        {
            "task": "template",
            "state": "check after prerequisites",
            "reasons": ["prerequisites may change inputs; recheck before execution"],
            "requires": ("helper",),
            "affected": (),
        },
    ]
    with mock.patch(
        "plonex.preparation.supervisor.SupervisorPreparation.plan", return_value=entries
    ):
        _, report, _ = invoke(capsys)
    codes = {finding["code"] for finding in report["findings"]}
    assert "preparation.conditional" in codes
    assert "preparation.stale" not in codes
