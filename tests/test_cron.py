from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from pathlib import Path
from plonex.services.cron import CronService
from plonex.services.cron.model import JobSet
from plonex.services.cron.plone_runner import execute
from plonex.services.supervisor import Supervisor
from types import ModuleType
from unittest import mock

import os
import pytest
import sys
import threading
import time
import yaml


def declaration(**values):
    return {
        "cron_jobs": {
            "stats": {
                "schedule": "15 2 * * *",
                "command": [sys.executable, "-c", "print('done')"],
                **values,
            }
        }
    }


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "plonex.yml").write_text("{}\n")
    return tmp_path


@pytest.mark.parametrize(
    "values",
    [
        {"schedule": "* *"},
        {"schedule": "70 * * * *"},
        {"schedule": "*/0 * * * *"},
        {"schedule": "bad * * * *"},
        {"timezone": "NoSuch/Zone"},
        {"command": "echo test"},
        {"command": []},
        {"command": [1]},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": float("nan")},
        {"enabled": "false"},
        {"retries": 1.5},
        {"retry_delay": True},
        {"environment": {"BAD=KEY": "value"}},
        {"environment": {"KEY": 1}},
        {"runtime": "../../outside"},
        {"lock": "../outside"},
        {"kwargs": []},
        {"kwargs": {"value": object()}},
        {"vhm": "/VirtualHostBase/https/example.com:443/Plone/"},
        {"vhm": 42},
        {"unknown": True},
    ],
)
def test_invalid_jobs_are_rejected_before_execution(values):
    with pytest.raises(ValueError):
        JobSet.from_options(declaration(**values))


def test_plone_job_requires_one_callable_and_an_explicit_user():
    for spec in (
        {"schedule": "* * * * *", "callable": "example.jobs:run"},
        {"schedule": "* * * * *", "callable": "invalid", "user": "scheduler"},
        {
            "schedule": "* * * * *",
            "callable": "example:run",
            "command": ["echo"],
            "user": "scheduler",
        },
    ):
        with pytest.raises(ValueError):
            JobSet.from_options({"cron_jobs": {"bad": spec}})


@pytest.mark.parametrize(
    "path", ["/VirtualHostBase/https/", "/bad", "/VirtualHostBase/ftp/example.com/"]
)
def test_plone_job_rejects_invalid_virtual_host_path(path):
    with pytest.raises(ValueError, match="vhm"):
        JobSet.from_options(
            {
                "cron_jobs": {
                    "job": {
                        "schedule": "* * * * *",
                        "callable": "example:run",
                        "user": "scheduler",
                        "vhm": path,
                    }
                }
            }
        )


def test_plone_job_accepts_virtual_host_path():
    path = "/VirtualHostBase/https/example.com:443/Plone/client/"
    job = JobSet.from_options(
        {
            "cron_jobs": {
                "job": {
                    "schedule": "* * * * *",
                    "callable": "example:run",
                    "user": "scheduler",
                    "vhm": path,
                }
            }
        }
    ).get("job")
    assert job.vhm == path


def test_cron_matcher_uses_the_declared_timezone_and_accepts_utc_timestamps():
    job = JobSet.from_options(declaration(timezone="Europe/Rome")).get("stats")
    assert job.matcher()(datetime(2026, 11, 8, 1, 15, tzinfo=timezone.utc))
    assert job.matcher()(datetime(2026, 11, 8, 1, 15))
    assert not job.matcher()(datetime(2026, 11, 8, 2, 15, tzinfo=timezone.utc))


def test_real_command_job_records_history_log_and_environment(project):
    service = CronService(
        target=project,
        cli_options=declaration(
            command=[sys.executable, "-c", "import os; print(os.environ['JOB_VALUE'])"],
            environment={"JOB_VALUE": "[literal]"},
        ),
    )
    result = service.runner.run(service.jobs.get("stats"))
    assert result["status"] == "succeeded"
    assert Path(result["log"]).read_text() == "[literal]\n"
    assert service.runner.history("stats")[0]["exit_code"] == 0
    assert Path(result["log"]).stat().st_mode & 0o777 == 0o600
    assert service.runner.database.stat().st_mode & 0o777 == 0o600
    assert "JOB_VALUE" not in os.environ


def test_failures_timeouts_and_missing_executables_are_recorded(project):
    service = CronService(
        target=project,
        cli_options=declaration(command=[sys.executable, "-c", "raise SystemExit(7)"]),
    )
    result = service.runner.run(service.jobs.get("stats"))
    assert result["status"] == "failed" and result["exit_code"] == 7
    timeout = CronService(
        target=project,
        cli_options=declaration(
            command=[sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.05
        ),
    )
    result = timeout.runner.run(timeout.jobs.get("stats"))
    assert result["status"] == "timed-out"
    assert "timeout" in Path(result["log"]).read_text()
    missing = CronService(
        target=project,
        cli_options=declaration(command=["/nonexistent/plonex-test-command"]),
    )
    result = missing.runner.run(missing.jobs.get("stats"))
    assert result["status"] == "failed"
    assert "FileNotFoundError" in Path(result["log"]).read_text()


def test_manual_and_scheduled_jobs_share_real_file_locks(project):
    service = CronService(target=project, cli_options=declaration(lock="zope"))
    with service.runner.lock("zope") as held:
        assert held
        result = service.runner.run(service.jobs.get("stats"))
    assert result["status"] == "skipped"
    assert "busy" in Path(result["log"]).read_text()
    assert service.runner.run(service.jobs.get("stats"))["status"] == "succeeded"


def test_cancel_stops_the_active_process_and_records_the_failure(project):
    service = CronService(
        target=project,
        cli_options=declaration(
            command=[sys.executable, "-c", "import time; time.sleep(20)"]
        ),
    )
    results = []
    thread = threading.Thread(
        target=lambda: results.append(service.runner.run(service.jobs.get("stats")))
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not service.runner.processes and time.monotonic() < deadline:
        time.sleep(0.01)
    assert service.runner.processes
    service.runner.cancel_all()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert results[0]["status"] == "interrupted"
    assert not service.runner.processes


def test_huey_queue_persists_and_executes_both_enabled_and_manual_jobs(project):
    from plonex.services.cron.runtime import QueueRuntime

    options = declaration(schedule="* * * * *")
    options["cron_jobs"]["manual"] = {
        "schedule": "* * * * *",
        "enabled": False,
        "command": [sys.executable, "-c", "print('manual')"],
    }
    service = CronService(target=project, cli_options=options)
    with QueueRuntime(service) as first:
        first.enqueue("manual")
    with QueueRuntime(service) as second:
        huey, tasks = second.huey, second.tasks
        assert huey.pending_count() == 1
        huey.execute(huey.dequeue())
        assert second.runner.history("manual")[0]["status"] == "succeeded"
        periodic = huey.read_periodic(datetime(2026, 11, 8, 2, 15))
        assert len(periodic) == 1
        assert tasks["stats"] is not tasks["manual"]


def test_supervisor_includes_the_daemon_only_with_enabled_jobs(project):
    (project / "etc" / "plonex.yml").write_text(yaml.safe_dump(declaration()))
    with Supervisor(target=project) as supervisor:
        path = supervisor.programs_folder / "plonex-cron.conf"
        text = path.read_text()
    assert "plonex.services.cron.runtime" in text
    assert str(project / ".venv/bin/python") in text
    assert "daemon" in text
    assert "[program:plonex-cron]" in text
    assert "stopasgroup=true" in text
    assert "killasgroup=true" in text
    assert "autorestart=true" in text
    assert path.stat().st_mode & 0o777 == 0o600
    (project / "etc" / "plonex.yml").write_text("cron_jobs: {}\n")
    with Supervisor(target=project):
        pass
    assert not path.exists()


@pytest.fixture
def fake_plone(monkeypatch):
    state = {"site": "old", "user": "old", "commits": 0, "aborts": 0}
    transaction = ModuleType("transaction")
    transaction.begin = lambda: None
    transaction.commit = lambda: state.update(commits=state["commits"] + 1)
    transaction.abort = lambda: state.update(aborts=state["aborts"] + 1)
    hooks = ModuleType("zope.component.hooks")
    hooks.getSite = lambda: state["site"]
    hooks.setSite = lambda site: state.update(site=site)
    env = ModuleType("plone.api.env")

    @contextmanager
    def adopt_user(username):
        previous = state["user"]
        state["user"] = username
        try:
            if username == "missing":
                raise ValueError("User not found")
            yield
        finally:
            state["user"] = previous

    env.adopt_user = adopt_user
    business = ModuleType("example_jobs")

    def callback(context, **kwargs):
        state["called"] = (context, kwargs, state["user"], state["site"])
        return "done"

    business.run = callback
    for name, module in {
        "transaction": transaction,
        "zope.component.hooks": hooks,
        "plone.api.env": env,
        "example_jobs": business,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    site = mock.Mock()
    site.restrictedTraverse.return_value = "sectors"
    app = mock.Mock()
    app.unrestrictedTraverse.return_value = site
    return app, site, state, business


def test_plone_job_uses_named_user_context_and_explicit_transaction(fake_plone):
    app, site, state, business = fake_plone
    spec = {
        "site": "/Plone",
        "context": "sectors",
        "user": "scheduler",
        "callable": "example_jobs:run",
        "kwargs": {"days": 1},
    }
    assert execute(app, spec) == "done"
    assert state["called"] == ("sectors", {"days": 1}, "scheduler", site)
    assert state["commits"] == 1 and state["aborts"] == 0
    assert state["user"] == "old" and state["site"] == "old"


def test_plone_failure_aborts_and_restores_user_and_site(fake_plone):
    app, site, state, business = fake_plone
    business.run = mock.Mock(side_effect=RuntimeError("failed"))
    spec = {"site": "/Plone", "user": "scheduler", "callable": "example_jobs:run"}
    with pytest.raises(RuntimeError, match="failed"):
        execute(app, spec)
    assert state["commits"] == 0 and state["aborts"] == 1
    assert state["user"] == "old" and state["site"] == "old"


def test_plone_job_traverses_virtual_host_path(fake_plone):
    app, site, state, business = fake_plone
    path = "/VirtualHostBase/https/example.com:443/Plone/client/"
    spec = {
        "site": "/Plone",
        "user": "scheduler",
        "callable": "example_jobs:run",
        "vhm": path,
    }
    execute(app, spec)
    app.REQUEST.traverse.assert_called_once_with(path)


def test_missing_plone_user_fails_without_running_callback(fake_plone):
    app, site, state, business = fake_plone
    spec = {"site": "/Plone", "user": "missing", "callable": "example_jobs:run"}
    with pytest.raises(ValueError, match="User not found"):
        execute(app, spec)
    assert "called" not in state
    assert state["site"] == "old"


def test_shutdown_interrupts_lock_waiters_without_starting_more_processes(project):
    service = CronService(
        target=project, cli_options=declaration(lock="held", lock_timeout=300)
    )
    results = []
    with service.runner.lock("held") as acquired:
        assert acquired
        thread = threading.Thread(
            target=lambda: results.append(service.runner.run(service.jobs.get("stats")))
        )
        thread.start()
        deadline = time.monotonic() + 5
        while not service.runner.history() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service.runner.history()[0]["status"] == "running"
        service.runner.cancel_all()
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert results[0]["status"] == "interrupted"
    assert not service.runner.processes
    # A task being dispatched during shutdown must not start a new process.
    assert service.runner.run(service.jobs.get("stats"))["status"] == "interrupted"


def test_plone_job_renders_isolated_runtime_and_private_payload_without_global_env(
    project, monkeypatch
):
    import json

    monkeypatch.delenv("PLONEX_RENDER_TEST", raising=False)
    (project / ".venv/bin").mkdir(parents=True)
    (project / ".venv/bin/activate").touch()
    (project / "etc" / "plonex.yml").write_text(
        yaml.safe_dump(
            {
                "environment_vars": {"PLONEX_RENDER_TEST": "global"},
                "cron_jobs": {
                    "stats": {
                        "schedule": "* * * * *",
                        "callable": "my.addon.jobs:run",
                        "user": "scheduler",
                        "runtime": "nightly",
                    }
                },
            }
        )
    )
    (project / "etc" / "plonex-nightly.yml").write_text(
        "zeo_address: /custom/zeo.sock\n"
        "environment_vars:\n  PLONEX_RENDER_TEST: runtime\n"
    )
    service = CronService(target=project)
    runner = service.runner
    runner.prepare()
    command, environment = runner.command(service.jobs.get("stats"), "first-run")
    assert command[:2] == [str(project / ".venv/bin/zconsole"), "run"]
    configuration = Path(command[2])
    assert configuration == project / "tmp/cron-runs/first-run/etc/zope.conf"
    text = configuration.read_text()
    assert "/custom/zeo.sock" in text
    assert str(project / "var/cron/runtime/first-run") in text
    assert str(project / "var/nightly") not in text
    payload = Path(environment["PLONEX_JOB_SPEC"])
    assert payload.stat().st_mode & 0o777 == 0o600
    assert json.loads(payload.read_text())["user"] == "scheduler"
    assert environment["PLONEX_RENDER_TEST"] == "runtime"
    assert "PLONEX_RENDER_TEST" not in os.environ
    second, _ = runner.command(service.jobs.get("stats"), "second-run")
    assert second[2] != command[2]
    assert configuration.read_text() == text


def test_public_job_commands_show_results_and_preserve_exit_codes(
    project, capsys, install_job_runtime
):
    from plonex.cli import main

    install_job_runtime(project)
    (project / "etc/plonex.yml").write_text(yaml.safe_dump(declaration()))

    def invoke(*tokens):
        with mock.patch.object(sys, "argv", ["plonex", "cron", *tokens]):
            main()
        return capsys.readouterr().out

    assert "stats" in invoke("list")
    assert "never run" in invoke("list")
    assert "no execution log" in invoke("logs", "stats")
    assert "succeeded" in invoke("run", "stats")
    assert "done" in invoke("logs", "stats", "--tail", "1")
    assert "succeeded" in invoke("history", "stats", "--limit", "1")
    assert "Queued stats:" in invoke("enqueue", "stats")
    invoke("configure")
    assert (project / "tmp/supervisor/etc/supervisor/plonex-cron.conf").is_file()
    (project / "etc/plonex.yml").write_text("cron_jobs: {}\n")
    assert "No project jobs" in invoke("configure")
    assert not (project / "tmp/supervisor/etc/supervisor/plonex-cron.conf").exists()
    (project / "etc/plonex.yml").write_text(
        yaml.safe_dump(
            declaration(command=[sys.executable, "-c", "raise SystemExit(9)"])
        )
    )
    with pytest.raises(SystemExit) as error:
        invoke("run", "stats")
    assert error.value.code == 9
