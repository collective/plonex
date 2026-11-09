from pathlib import Path
from plonex.files import write_if_changed
from plonex.preparation.engine import file_digest
from plonex.preparation.engine import Graph
from plonex.preparation.engine import Task
from plonex.preparation.supervisor import SupervisorPreparation
from unittest import mock

import json
import os
import pytest
import sys
import yaml


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc/requirements.d").mkdir(parents=True)
    (tmp_path / "etc/constraints.d").mkdir(parents=True)
    (tmp_path / "etc/plonex.yml").write_text("plonex_base_constraint: null\n")
    return tmp_path


def fake_environment(root):
    binary = root / ".venv/bin"
    binary.mkdir(parents=True)
    (binary / "activate").touch()
    (binary / "python").symlink_to(sys.executable)
    script = """#!/usr/bin/env python3
import pathlib,sys,json
root=pathlib.Path(__file__).resolve().parents[2]
if 'freeze' in sys.argv:
    print('demo==1.0')
elif 'install' in sys.argv:
    with (root/'installations.log').open('a') as output:
        output.write('install\\n')
    with (root/'uv-arguments.jsonl').open('a') as output:
        output.write(json.dumps(sys.argv[1:])+'\\n')
    folder=root/'.venv/lib/python3/site-packages/demo-1.0.dist-info'
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'METADATA').write_text('Name: demo\\nVersion: 1.0\\n')
    print(' + demo==1.0', file=sys.stderr)
"""
    (binary / "uv").write_text(script)
    (binary / "uv").chmod(0o755)
    return binary


def installation_count(root):
    path = root / "installations.log"
    return len(path.read_text().splitlines()) if path.exists() else 0


def test_doit_dag_deduplicates_checks_content_and_recovers_outputs(project):
    graph = Graph(project / "var/preparation")
    source = project / "source"
    source.write_text("first")
    output = project / "generated"
    calls = []
    graph.add(
        Task(
            "generate",
            lambda: (
                calls.append("generate"),
                write_if_changed(output, source.read_text()),
            ),
            lambda: {str(source): file_digest(source)},
            lambda: {str(output): file_digest(output)},
        )
    )
    for name in ("first", "second"):
        graph.add(
            Task(
                name,
                lambda item=name: calls.append(item),
                lambda: {},
                requires=("generate",),
            )
        )
    graph.run()
    assert calls.count("generate") == 1
    stamp = output.stat().st_mtime_ns
    assert graph.run() == []
    assert output.stat().st_mtime_ns == stamp
    source.write_text("other")
    graph.run()
    assert output.read_text() == "other"
    output.write_text("external edit")
    assert "output missing or modified" in repr(graph.plan())
    graph.run()
    assert output.read_text() == "other"
    output.unlink()
    graph.run()
    assert output.read_text() == "other"


def test_failed_task_is_not_recorded_and_blocks_dependents(project):
    graph = Graph(project / "var/preparation")
    action = mock.Mock(side_effect=RuntimeError("failed"))
    graph.add(Task("install", action, lambda: {}))
    dependent = mock.Mock()
    graph.add(Task("start", dependent, lambda: {}, requires=("install",)))
    with pytest.raises(RuntimeError, match="failed"):
        graph.run()
    assert graph.receipt(graph.tasks["install"]) is None
    dependent.assert_not_called()
    action.side_effect = None
    action.return_value = None
    graph.run()
    dependent.assert_called_once()


def test_cycle_and_unknown_prerequisites_fail_before_writing_state(project):
    folder = project / "new-state"
    graph = Graph(folder)
    graph.add(Task("a", lambda: None, lambda: {}, requires=("b",)))
    with pytest.raises(ValueError, match="unknown prerequisites"):
        graph.run()
    graph.add(Task("b", lambda: None, lambda: {}, requires=("a",)))
    with pytest.raises(ValueError, match="cycle"):
        graph.run()
    assert not folder.exists()


def test_startup_installs_only_when_dependency_inputs_or_environment_change(project):
    fake_environment(project)
    prep = SupervisorPreparation(project)
    prep.run()
    assert installation_count(project) == 1
    stamps = {path: path.stat().st_mtime_ns for path in (project / "var").glob("*.txt")}
    assert SupervisorPreparation(project).run() == []
    assert installation_count(project) == 1
    assert all(path.stat().st_mtime_ns == stamp for path, stamp in stamps.items())
    fragment = project / "etc/requirements.d/new.txt"
    fragment.write_text("new-package>=1\n")
    assert "added" in repr(SupervisorPreparation(project).plan())
    SupervisorPreparation(project).run()
    assert installation_count(project) == 2
    fragment.write_text("new-package>=2\n")
    SupervisorPreparation(project).run()
    assert installation_count(project) == 3
    fragment.unlink()
    SupervisorPreparation(project).run()
    assert installation_count(project) == 4
    metadata = next(
        (project / ".venv").glob("lib/python*/site-packages/*.dist-info/METADATA")
    )
    metadata.write_text("Name: demo\nVersion: external-change\n")
    assert "output missing or modified" in repr(SupervisorPreparation(project).plan())
    SupervisorPreparation(project).run()
    assert installation_count(project) == 5


def test_port_and_template_changes_do_not_install_dependencies(project):
    fake_environment(project)
    template = project / "etc/server.conf.j2"
    template.write_text("[program:web]\ncommand=plonex instance start\npriority=1\n")
    options = {
        "plonex_base_constraint": None,
        "http_port": 8080,
        "services": [
            {
                "template": {
                    "run_for": "supervisor",
                    "source": "etc/server.conf.j2",
                    "target": "tmp/supervisor/etc/supervisor/web.conf",
                }
            }
        ],
    }
    config = project / "etc/plonex.yml"
    config.write_text(yaml.safe_dump(options))
    SupervisorPreparation(project).run()
    runtime = project / "tmp/runwsgi/etc/wsgi.ini"
    assert "8080" in runtime.read_text()
    options["http_port"] = 9090
    config.write_text(yaml.safe_dump(options))
    plan = SupervisorPreparation(project).plan()
    assert (
        next(entry for entry in plan if entry["task"] == "dependencies.ensure")["state"]
        == "current"
    )
    SupervisorPreparation(project).run()
    assert "9090" in runtime.read_text()
    assert installation_count(project) == 1
    template.write_text(template.read_text().replace("priority=1", "priority=2"))
    SupervisorPreparation(project).run()
    assert (
        "priority=2" in (project / "tmp/supervisor/etc/supervisor/web.conf").read_text()
    )
    assert installation_count(project) == 1


def test_plan_never_installs_fetches_or_creates_project_outputs(project):
    before = sorted(project.rglob("*"))
    with mock.patch(
        "plonex.services.install.requests.get", side_effect=AssertionError("network")
    ):
        prep = SupervisorPreparation(project)
        assert prep.plan()
        prep.show_plan()
    assert sorted(project.rglob("*")) == before


def test_editable_python_edits_skip_install_but_metadata_changes_reinstall(project):
    fake_environment(project)
    source = project / "src/demo"
    source.mkdir(parents=True)
    metadata = source / "pyproject.toml"
    metadata.write_text('[project]\nname="demo"\nversion="1.0"\n')
    code = source / "module.py"
    code.write_text("value=1\n")
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "sources": {"demo": {"repo": "unused", "install": True}},
            }
        )
    )
    SupervisorPreparation(project).run()
    code.write_text("value=2\n")
    assert SupervisorPreparation(project).run() == []
    metadata.write_text(metadata.read_text() + 'dependencies=["new-dependency"]\n')
    SupervisorPreparation(project).run()
    assert installation_count(project) == 2


def test_receipts_contain_digests_and_no_configuration_secrets(project):
    fake_environment(project)
    (project / "etc/plonex.local.yml").write_text(
        "environment_vars:\n  UV_INDEX_PASSWORD: hidden-value\n"
    )
    SupervisorPreparation(project).run()
    for path in (project / "var/preparation").glob("*.json"):
        assert "hidden-value" not in path.read_text()
        assert path.stat().st_mode & 0o777 == 0o600


def test_nested_constraint_changes_and_remote_snapshots_are_tracked(project):
    fake_environment(project)
    url = "https://example.org/base.txt"
    nested = "https://example.org/nested.txt"
    (project / "etc/plonex.yml").write_text(f'plonex_base_constraint: "{url}"\n')
    local = project / "etc/constraints.d/local.txt"
    local.write_text("-c ../nested.txt\n")
    included = project / "etc/nested.txt"
    included.write_text("demo==1.0\n")
    responses = {url: "-c nested.txt\n", nested: "zope.sendmail==7.2\n"}

    def fetch(source, timeout):
        return mock.Mock(text=responses[source], headers={"Content-Type": "text/plain"})

    with mock.patch("plonex.services.install.requests.get", side_effect=fetch) as get:
        SupervisorPreparation(project).run()
        assert get.call_count == 2
    constraints = project / "var/constraints.txt"
    assert "zope-sendmail==7.2" in constraints.read_text()
    with mock.patch(
        "plonex.services.install.requests.get", side_effect=AssertionError("network")
    ):
        assert SupervisorPreparation(project).run() == []
        included.write_text("demo==2.0\n")
        SupervisorPreparation(project).run()
        assert "demo==2.0" in constraints.read_text()
    assert installation_count(project) == 2


def test_explicit_install_receipt_prevents_reinstallation_on_next_start(project):
    from plonex.services.install import InstallService

    fake_environment(project)
    with InstallService(target=project) as service:
        service.run(update_sources=False)
    assert installation_count(project) == 1
    SupervisorPreparation(project).run()
    assert installation_count(project) == 1


def test_startup_does_not_honor_automatic_git_update_defaults(project):
    fake_environment(project)
    (project / "etc/plonex.local.yml").write_text(
        "sources_update_before_dependencies: true\n"
    )
    with mock.patch(
        "plonex.services.install.InstallService.update_gitman_sources",
        side_effect=AssertionError("Git update"),
    ):
        SupervisorPreparation(project).run()
    assert installation_count(project) == 1


def test_jinja_included_template_changes_are_detected_without_mtime_changes(project):
    fake_environment(project)
    template = project / "etc/helper.j2"
    included = project / "etc/included.j2"
    template.write_text("{% include 'included.j2' %}")
    included.write_text("value=first")
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "services": [
                    {
                        "template": {
                            "run_for": "supervisor",
                            "source": "etc/helper.j2",
                            "target": "tmp/helper.conf",
                        }
                    }
                ],
            }
        )
    )
    SupervisorPreparation(project).run()
    before = included.stat()
    included.write_text("value=other")
    os.utime(included, ns=(before.st_atime_ns, before.st_mtime_ns))
    SupervisorPreparation(project).run()
    assert (project / "tmp/helper.conf").read_text() == "value=other"
    assert installation_count(project) == 1


def test_cli_plan_does_not_enter_services_or_write_outputs(project, capsys):
    from plonex.cli import main

    before = sorted(project.rglob("*"))
    with (
        mock.patch.object(sys, "argv", ["plonex", "supervisor", "start", "--plan"]),
        mock.patch(
            "plonex.services.supervisor.Supervisor.__enter__",
            side_effect=AssertionError("entered"),
        ),
        mock.patch(
            "plonex.services.install.requests.get",
            side_effect=AssertionError("network"),
        ),
    ):
        main()
    output = capsys.readouterr().out
    assert "dependencies.ensure" in output
    assert "supervisor.ready" in output
    assert sorted(project.rglob("*")) == before


def test_cli_start_prepares_before_launch_and_stops_on_failure(project):
    from plonex.cli import main

    fake_environment(project)
    with (
        mock.patch.object(sys, "argv", ["plonex", "supervisor", "start"]),
        mock.patch(
            "plonex.services.supervisor.Supervisor.is_running", return_value=False
        ),
        mock.patch("plonex.services.supervisor.Supervisor.run") as start,
    ):
        start.side_effect = lambda: installation_count(project) == 1 or pytest.fail(
            "not prepared"
        )
        main()
        start.assert_called_once()
    metadata = next(
        (project / ".venv").glob("lib/python*/site-packages/*.dist-info/METADATA")
    )
    metadata.unlink()
    with (
        mock.patch.object(sys, "argv", ["plonex", "supervisor", "start"]),
        mock.patch(
            "plonex.preparation.dependencies.DependencyTasks.install",
            side_effect=ValueError("installer failed"),
        ),
        mock.patch("plonex.services.supervisor.Supervisor.run") as start,
    ):
        with pytest.raises(SystemExit) as failure:
            main()
        assert failure.value.code == 1
        start.assert_not_called()


def test_configuration_edits_while_a_plan_is_waiting_require_replanning(project):
    prep = SupervisorPreparation(project)
    (project / "etc/plonex.local.yml").write_text("http_port: 9999\n")
    with pytest.raises(ValueError, match="Configuration changed"):
        prep.run()
    assert installation_count(project) == 0


def test_removed_templates_remove_only_unchanged_owned_outputs(project):
    fake_environment(project)
    template = project / "etc/program.j2"
    template.write_text("[program:worker]\ncommand=python worker.py\n")
    output = project / "tmp/supervisor/etc/supervisor/worker.conf"
    config = project / "etc/plonex.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "services": [
                    {
                        "template": {
                            "run_for": "supervisor",
                            "source": "etc/program.j2",
                            "target": str(output),
                        }
                    }
                ],
            }
        )
    )
    SupervisorPreparation(project).run()
    unmanaged = output.with_name("unmanaged.conf")
    unmanaged.write_text("[program:unmanaged]\ncommand=python unmanaged.py\n")
    config.write_text("plonex_base_constraint: null\n")
    SupervisorPreparation(project).run()
    assert not output.exists()
    assert unmanaged.exists()
    assert installation_count(project) == 1


def test_nested_plans_and_concurrent_commands_share_one_installation(project):
    import subprocess

    fake_environment(project)
    command = [sys.executable, "-m", "plonex.cli", "supervisor", "start", "--plan"]
    result = subprocess.run(
        command, cwd=project, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr
    assert installation_count(project) == 0
    script = (
        "from pathlib import Path; "
        "from plonex.preparation.supervisor import SupervisorPreparation; "
        "SupervisorPreparation(Path.cwd()).run()"
    )
    first = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=project,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    second = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=project,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    first_output, _ = first.communicate(timeout=15)
    second_output, _ = second.communicate(timeout=15)
    assert first.returncode == 0, first_output
    assert second.returncode == 0, second_output
    assert installation_count(project) == 1


def test_modified_obsolete_outputs_keep_their_ownership_after_failed_preparation(
    project,
):
    fake_environment(project)
    template = project / "etc/owned.j2"
    template.write_text("original")
    output = project / "tmp/owned.conf"
    config = project / "etc/plonex.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "plonex_base_constraint": None,
                "services": [
                    {
                        "template": {
                            "run_for": "supervisor",
                            "source": str(template),
                            "target": str(output),
                        }
                    }
                ],
            }
        )
    )
    SupervisorPreparation(project).run()
    output.write_text("manual edit")
    config.write_text("plonex_base_constraint: null\n")
    for _ in range(2):
        with pytest.raises(ValueError, match="Obsolete generated file was edited"):
            SupervisorPreparation(project).run()
        assert output.read_text() == "manual edit"
    output.unlink()
    SupervisorPreparation(project).run()


def test_uncached_remote_profiles_are_never_fetched_by_a_plan(project):
    from plonex.cli import main

    (project / "etc/plonex.yml").write_text(
        "profiles: ['https://example.org/profile.git']\n"
    )
    before = sorted(project.rglob("*"))
    with (
        mock.patch.object(sys, "argv", ["plonex", "supervisor", "start", "--plan"]),
        mock.patch(
            "plonex.services.profile.ProfileService.execute_command",
            side_effect=AssertionError("network"),
        ),
    ):
        with pytest.raises(SystemExit) as error:
            main()
    assert error.value.code == 2
    assert sorted(project.rglob("*")) == before


def test_remote_profiles_have_stable_cached_paths_and_require_explicit_updates(project):
    from plonex.files import read_only
    from plonex.services.profile import ProfileService

    def clone(command):
        checkout = Path(command[-1])
        (checkout / "etc").mkdir(parents=True)
        (checkout / "etc/plonex.yml").write_text("http_port: 9010\n")

    with mock.patch(
        "plonex.services.profile.ProfileService.execute_command", side_effect=clone
    ) as git:
        first = ProfileService(
            target=project, source="https://example.org/profile.git"
        ).source_path
        with read_only():
            second = ProfileService(
                target=project, source="https://example.org/profile.git"
            ).source_path
        assert first == second
        assert git.call_count == 1


@pytest.mark.parametrize("legacy", [False, True])
def test_regular_code_and_legacy_editable_metadata_reinstall_local_projects(
    project, legacy
):
    fake_environment(project)
    source = project / "src/demo"
    source.mkdir(parents=True)
    metadata = source / "pyproject.toml"
    metadata.write_text('[project]\nname="demo"\nversion="1.0"\n')
    code = source / "module.py"
    code.write_text("value=1\n")
    if legacy:
        (project / "etc/requirements.d/local.txt").write_text("-e src/demo\n")
    else:
        (project / "etc/plonex.local.yml").write_text(
            yaml.safe_dump(
                {
                    "sources": {
                        "demo": {"repo": "unused", "install": True, "editable": False}
                    },
                }
            )
        )
    SupervisorPreparation(project).run()
    if legacy:
        metadata.write_text(metadata.read_text() + 'dependencies=["changed"]\n')
    else:
        code.write_text("value=2\n")
    SupervisorPreparation(project).run()
    assert installation_count(project) == 2
    command = json.loads((project / "uv-arguments.jsonl").read_text().splitlines()[-1])
    position = command.index("--reinstall-package")
    assert command[position + 1] == "demo"


def test_mismatched_python_requires_explicit_virtualenv_recreation(project):
    fake_environment(project)
    different = project / "old-python"
    different.write_text("#!/bin/sh\necho '[\"cpython\", [2, 7]]'\n")
    different.chmod(0o755)
    (project / "etc/plonex.local.yml").write_text(f'python: "{different}"\n')
    with pytest.raises(ValueError, match="Recreate .venv"):
        SupervisorPreparation(project).run()
    assert installation_count(project) == 0


def test_missing_configured_python_does_not_certify_the_existing_environment(project):
    fake_environment(project)
    (project / "etc/plonex.local.yml").write_text(
        "python: /nonexistent/plonex-python\n"
    )
    with pytest.raises(ValueError, match="Python executable was not found"):
        SupervisorPreparation(project).run()
    assert installation_count(project) == 0


def test_missing_generated_configuration_and_wrong_permissions_are_repaired(project):
    fake_environment(project)
    SupervisorPreparation(project).run()
    configuration = project / "tmp/supervisor/etc/supervisord.conf"
    configuration.chmod(0o644)
    SupervisorPreparation(project).run()
    assert configuration.stat().st_mode & 0o777 == 0o600
    configuration.unlink()
    SupervisorPreparation(project).run()
    assert configuration.exists()
    assert installation_count(project) == 1


def test_conflicting_template_producers_are_rejected_before_installation(project):
    first = project / "etc/first.j2"
    second = project / "etc/second.j2"
    first.write_text("first")
    second.write_text("second")
    (project / "etc/plonex.local.yml").write_text(
        yaml.safe_dump(
            {
                "services": [
                    {
                        "template": {
                            "run_for": "supervisor",
                            "source": str(first),
                            "target": "tmp/shared.conf",
                        }
                    },
                    {
                        "template": {
                            "run_for": "supervisor",
                            "source": str(second),
                            "target": "tmp/shared.conf",
                        }
                    },
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="Conflicting template definitions"):
        SupervisorPreparation(project)
    assert installation_count(project) == 0


def test_report_exposes_a_blocked_preparation_without_running_it(project):
    from plonex.services.describe import DescribeService

    (project / "etc/plonex.local.yml").write_text(
        yaml.safe_dump(
            {
                "services": [
                    {
                        "template": {
                            "run_for": "supervisor",
                            "source": "missing-template.j2",
                            "target": "tmp/generated.conf",
                        }
                    },
                ]
            }
        )
    )
    with DescribeService(
        target=project, section="preparation", output_format="json"
    ) as service:
        service.run()
    report = json.loads((service.describe_folder / "preparation.json").read_text())
    assert report["sections"][0]["rows"][0][1] == "blocked"
    assert not (project / ".venv").exists()


def test_install_specific_environment_does_not_leak_into_supervisor(
    project, monkeypatch
):
    fake_environment(project)
    monkeypatch.setenv("PLONEX_INSTALL_ONLY", "original")
    monkeypatch.delenv("PLONEX_INSTALL_NEW", raising=False)
    (project / "etc/plonex-install.yml").write_text(
        yaml.safe_dump(
            {
                "environment_vars": {
                    "PLONEX_INSTALL_ONLY": "build-value",
                    "PLONEX_INSTALL_NEW": "build-only",
                },
            }
        )
    )
    SupervisorPreparation(project).run()
    assert os.environ["PLONEX_INSTALL_ONLY"] == "original"
    assert "PLONEX_INSTALL_NEW" not in os.environ
