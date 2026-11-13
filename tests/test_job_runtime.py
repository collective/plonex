from .test_cron_daemon import launch
from .test_cron_daemon import wait_for
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from plonex.services.cron import CronService
from plonex.services.cron.installation import runtime_requirement
from plonex.services.cron.runtime import QueueRuntime
from plonex.services.install import InstallService
from unittest import mock

import json
import os
import pytest
import sqlite3
import subprocess
import sys
import yaml


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("plonex_base_constraint: null\n")
    return tmp_path


def configure(root, script="print('worked')", **options):
    values = {
        "plonex_base_constraint": None,
        "cron_jobs": {
            "manual": {
                "schedule": "* * * * *",
                "enabled": False,
                "command": ["python", "-c", script],
                **options,
            }
        },
    }
    (root / "etc/plonex.yml").write_text(yaml.safe_dump(values))
    return values


def test_job_requirements_are_injected_only_for_configured_jobs(project):
    service = InstallService(target=project)
    service.make_requirements_txt()
    assert (
        runtime_requirement() not in service.requirements_txt.read_text().splitlines()
    )
    assert "huey[stats]" not in service.requirements_txt.read_text()
    assert {"supervisor", "rich"} <= set(
        service.requirements_txt.read_text().splitlines()
    )
    configure(project)
    service = InstallService(target=project)
    service.make_requirements_txt()
    assert runtime_requirement() in service.requirements_txt.read_text().splitlines()
    assert "[jobs]" not in service.requirements_txt.read_text()
    assert "huey[stats]>=3.5,<4" in service.requirements_txt.read_text()
    assert runtime_requirement() == "plonex"


def test_control_panel_also_injects_worker_requirements(project):
    (project / "etc/plonex.yml").write_text(
        "plonex_base_constraint: null\ncron_control_panel: true\n"
    )
    service = InstallService(target=project)
    service.make_requirements_txt()
    requirements = service.requirements_txt.read_text()
    assert runtime_requirement() in requirements.splitlines()
    assert "huey[stats]>=3.5,<4" in requirements


def test_base_cli_and_reports_do_not_import_huey_or_peewee(project):
    configure(project)
    script = """
import importlib.abc,sys
from pathlib import Path
from datetime import datetime
from datetime import timezone
from datetime import timedelta
class BlockWorker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'huey','peewee'}:
            raise AssertionError('Worker dependency imported by core: '+fullname)
sys.meta_path.insert(0,BlockWorker())
from plonex.cli.parser import build_parser
from plonex.services.cron import CronService
from plonex.services.describe import DescribeService
build_parser(target=Path.cwd()).parse_args(['cron','status'])
assert CronService().jobs.jobs
with DescribeService(section='jobs',output_format='json') as service:
    service.run()
print('core-is-independent')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "core-is-independent" in result.stdout


def test_project_runtime_includes_required_dependencies(project, install_job_runtime):
    python = install_job_runtime(project)
    result = subprocess.run(
        [str(python), "-I", "-B", "-c", "import huey, peewee, rich, supervisor"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_worker_and_relative_python_commands_use_only_the_target_environment(
    project, install_job_runtime
):
    python = install_job_runtime(project)
    configure(project, "import sys; print(sys.prefix)")
    service = CronService(target=project)
    queued = service.enqueue("manual")
    process = launch(project)
    try:
        wait_for(
            lambda: bool(service.runner.history())
            and service.runner.history()[0]["status"] == "succeeded"
        )
        state = service.invoke_runtime("status")
        assert state["prefix"] == str(project / ".venv")
        assert state["worker"]["prefix"] == str(project / ".venv")
        assert state["worker"]["running"]
        run = service.runner.history()[0]
        assert Path(run["log"]).read_text().strip() == str(project / ".venv")
        assert run["task_id"] == queued["task_id"]
        assert run["attempt"] == 1
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=12)
    assert process.returncode == 0, output
    assert not service.invoke_runtime("status")["worker"]["running"]
    origin = subprocess.check_output(
        [str(python), "-I", "-B", "-c", "import huey; print(huey.__file__)"], text=True
    ).strip()
    assert Path(origin).is_relative_to(project / ".venv")


def test_read_only_queue_queries_do_not_bootstrap_or_create_state(
    project, install_job_runtime
):
    install_job_runtime(project)
    configure(project)
    before = sorted(project.rglob("*"))
    service = CronService(target=project)
    state = service.invoke_runtime("status")
    assert state["queue"]["pending_count"] == 0
    assert state["statistics"]["recent_events"] == []
    assert not state["worker"]["running"]
    assert sorted(project.rglob("*")) == before
    assert not (project / "var").exists()


def test_revoke_restore_and_inspect_a_queued_task(project, install_job_runtime):
    install_job_runtime(project)
    configure(project, "from pathlib import Path; Path('should-not-run').touch()")
    service = CronService(target=project)
    queued = service.enqueue("manual")
    task_id = queued["task_id"]
    assert service.invoke_runtime("inspect", task_id)["queued"][0]["task_id"] == task_id
    service.invoke_runtime("revoke", task_id)
    assert service.invoke_runtime("queue")["pending"][0]["revoked"]
    service.invoke_runtime("restore", task_id)
    assert not service.invoke_runtime("queue")["pending"][0]["revoked"]
    service.invoke_runtime("revoke", task_id)
    process = launch(project)
    try:
        wait_for(
            lambda: service.invoke_runtime("status")["statistics"]["counts"].get(
                "revoked", 0
            )
            == 1
        )
    finally:
        process.terminate()
        process.communicate(timeout=12)
    assert not (project / "should-not-run").exists()
    assert service.runner.history() == []


def test_retry_creates_a_new_task_and_preserves_original_failure(
    project, install_job_runtime
):
    install_job_runtime(project)
    configure(project, "raise SystemExit(7)")
    service = CronService(target=project)
    with pytest.raises(SystemExit) as error:
        service.run_job("manual")
    assert error.value.code == 7
    failed = service.runner.history()[0]
    configure(project, "print('recovered')")
    retried = service.invoke_runtime("retry", failed["task_id"])
    assert retried["retry_of"] == failed["task_id"]
    assert retried["task_id"] != failed["task_id"]
    process = launch(project)
    try:
        wait_for(
            lambda: len(service.runner.history()) == 2
            and service.runner.history()[0]["status"] == "succeeded"
        )
    finally:
        process.terminate()
        process.communicate(timeout=12)
    assert (
        service.invoke_runtime("inspect", failed["task_id"])["runs"][0]["status"]
        == "failed"
    )
    with pytest.raises(ValueError, match="Retry requires"):
        service.invoke_runtime("retry", retried["task_id"])


def test_automatic_retries_keep_one_task_id_with_distinct_attempts(
    project, install_job_runtime
):
    install_job_runtime(project)
    configure(project, "raise SystemExit(4)", retries=1, retry_delay=60)
    with QueueRuntime(CronService(target=project)) as queue:
        queued = queue.enqueue("manual")
        queue.huey.execute(queue.huey.dequeue())
        assert queue.queue()["scheduled_count"] == 1
        with pytest.raises(ValueError, match="pending or scheduled"):
            queue.retry(queued["task_id"])
        task = queue.huey.read_schedule(
            datetime.now(timezone.utc) + timedelta(minutes=2)
        )[0]
        task.eta = None  # Simulate the scheduler dispatching the now-due retry.
        queue.huey.execute(task)
        rows = queue.runner.history(task_id=queued["task_id"])
        assert [row["attempt"] for row in rows] == [2, 1]
        assert len({row["id"] for row in rows}) == 2
        assert {row["task_id"] for row in rows} == {queued["task_id"]}
    with QueueRuntime(CronService(target=project), read_only=True) as queue:
        stats = queue.statistics()
    assert stats["counts"]["error"] == 2
    assert stats["counts"]["retrying"] == 1
    assert all(event["args"] is None for event in stats["recent_events"])


def test_old_history_schema_is_upgraded_without_losing_runs(project):
    configure(project)
    folder = project / "var/cron"
    folder.mkdir(parents=True)
    database = folder / "history.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TABLE runs (id TEXT PRIMARY KEY,job TEXT,started TEXT,"
            "finished TEXT,status TEXT,exit_code INTEGER,log TEXT)"
        )
        db.execute(
            "INSERT INTO runs VALUES "
            "('old','manual','before','after','succeeded',0,'old.log')"
        )
    service = CronService(target=project)
    assert service.runner.history(task_id="new") == []
    result = service.runner.run(service.jobs.get("manual"), task_id="new")
    assert result["attempt"] == 1
    rows = service.runner.history()
    assert len(rows) == 2
    assert any(row["id"] == "old" for row in rows)


def test_unknown_tasks_and_removed_definitions_can_be_inspected_safely(project):
    configure(project)
    with QueueRuntime(CronService(target=project)) as queue:
        queued = queue.enqueue("manual")
    (project / "etc/plonex.yml").write_text("cron_jobs: {}\n")
    with QueueRuntime(CronService(target=project), read_only=True) as queue:
        task = queue.inspect(queued["task_id"])["queued"][0]
        assert task["registered"] is False
        with pytest.raises(ValueError, match="Unknown task"):
            queue.inspect("unknown")


def test_job_environment_overrides_runtime_settings_without_global_mutation(
    project, install_job_runtime
):
    install_job_runtime(project)
    configure(
        project,
        "import os; print(os.environ['RUNTIME_VALUE']); "
        "print(os.environ['VIRTUAL_ENV'])",
        environment={"RUNTIME_VALUE": "job"},
    )
    (project / "etc/plonex-cron.yml").write_text(
        "environment_vars:\n  RUNTIME_VALUE: runtime\n"
    )
    with QueueRuntime(CronService(target=project)) as queue:
        result = queue.run_job("manual")
    assert Path(result["log"]).read_text().splitlines() == [
        "job",
        str(project / ".venv"),
    ]
    assert "RUNTIME_VALUE" not in os.environ


def test_cli_monitoring_and_control_outputs_are_valid_json(
    project, install_job_runtime, capsys
):
    from plonex.cli import main

    install_job_runtime(project)
    configure(project)
    service = CronService(target=project)
    task_id = service.enqueue("manual")["task_id"]
    capsys.readouterr()
    for action in ("status", "queue", "inspect", "revoke", "restore"):
        tokens = ["plonex", "cron", action]
        if action in {"inspect", "revoke", "restore"}:
            tokens.append(task_id)
        tokens += ["--format", "json"]
        with mock.patch.object(sys, "argv", tokens):
            main()
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, dict)
    with mock.patch.object(
        sys, "argv", ["plonex", "cron", "history", "--format", "json"]
    ):
        main()
    assert json.loads(capsys.readouterr().out) == []


def test_missing_runtime_uses_the_preparation_graph_then_rechecks(
    project, install_job_runtime
):
    configure(project)
    service = CronService(target=project)
    assert service.runtime_probe() is None
    with mock.patch("plonex.preparation.dependencies.DependencyTasks") as dependencies:
        dependencies.return_value.graph.run.side_effect = lambda: install_job_runtime(
            project
        )
        service.ensure_runtime()
    dependencies.return_value.graph.run.assert_called_once()
    assert service.runtime_probe()["prefix"] == str(project / ".venv")


def test_runtime_probe_accepts_different_version_with_matching_protocol(project):
    service = CronService(target=project)
    payload = {"prefix": str(project / ".venv"), "protocol": 1, "version": "99.0"}
    result = mock.Mock(returncode=0, stdout=json.dumps(payload))
    with mock.patch("plonex.services.cron.subprocess.run", return_value=result):
        assert service.runtime_probe() == payload
        payload["protocol"] = 999
        result.stdout = json.dumps(payload)
        assert service.runtime_probe() is None


def test_read_only_missing_runtime_does_not_install_and_empty_daemon_is_rejected(
    project,
):
    configure(project)
    service = CronService(target=project)
    with mock.patch("plonex.preparation.dependencies.DependencyTasks") as dependencies:
        with pytest.raises(ValueError, match="not installed"):
            service.invoke_runtime("status")
        dependencies.assert_not_called()
    (project / "etc/plonex.yml").write_text("cron_jobs: {}\n")
    with pytest.raises(ValueError, match="No project jobs"):
        CronService(target=project).run_daemon()
    assert not (project / ".venv").exists()


def test_manual_only_jobs_keep_the_supervised_project_consumer(project):
    configure(project)
    service = CronService(target=project)
    programs = project / "tmp/supervisor/etc/supervisor"
    service.configure_supervisor(programs)
    text = (programs / "plonex-cron.conf").read_text()
    assert str(project / ".venv/bin/python") in text
    assert "plonex.services.cron.runtime" in text
    assert sys.executable not in text


def test_producer_overrides_are_sent_privately_to_the_target_runtime(
    project, install_job_runtime
):
    install_job_runtime(project)
    # No persisted jobs: programmatic producers still use their own definitions.
    service = CronService(
        target=project,
        cli_options={
            "cron_jobs": {
                "private": {
                    "schedule": "* * * * *",
                    "enabled": False,
                    "command": ["python", "-c", "print('private')"],
                }
            }
        },
    )
    queued = service.enqueue("private")
    assert queued["job"] == "private"
    assert service.invoke_runtime("inspect", queued["task_id"])["queued"][0][
        "registered"
    ]


def test_dotted_job_names_survive_statistics_and_reports(
    project, install_job_runtime, capsys
):
    from plonex.services.describe import DescribeService
    from plonex.services.describe.report import ProjectReport

    install_job_runtime(project)
    values = configure(project)
    definition = values["cron_jobs"].pop("manual")
    definition["command"][0] = sys.executable
    values["cron_jobs"]["store.session.stats"] = definition
    (project / "etc/plonex.yml").write_text(yaml.safe_dump(values))
    service = CronService(target=project)
    with QueueRuntime(service) as queue:
        run = queue.run_job("store.session.stats")
        queued = queue.enqueue("store.session.stats")
    assert run["status"] == "succeeded"
    with QueueRuntime(service, read_only=True) as queue:
        payload = queue.status()
    assert payload["statistics"]["tasks"][0]["job"] == "store.session.stats"
    assert {event["job"] for event in payload["statistics"]["recent_events"]} == {
        "store.session.stats"
    }
    service.show_queue("status")
    output = capsys.readouterr().out
    assert "store.session.stats" in output
    assert "Worker: stopped" in output
    section = ProjectReport(DescribeService(target=project)).queue()
    assert any(row[:2] == ("Job", "store.session.stats") for row in section.rows)
    assert any(row[-1] == queued["task_id"] for row in section.rows)
