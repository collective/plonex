from plonex.services.cron import CronService

import os
import pytest
import subprocess
import sys
import time
import yaml


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    raise AssertionError("Daemon did not reach the expected state")


@pytest.fixture
def daemon_project(tmp_path, monkeypatch, install_job_runtime):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    install_job_runtime(tmp_path)
    return tmp_path


def launch(project):
    return subprocess.Popen(
        [sys.executable, "-m", "plonex.cli", "cron", "daemon", "--workers", "1"],
        cwd=project,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_real_daemon_consumes_persistent_queue_rejects_duplicates_and_restarts(
    daemon_project,
):
    root = daemon_project
    options = {
        "cron_jobs": {
            "manual": {
                "schedule": "* * * * *",
                "enabled": False,
                "command": [sys.executable, "-c", "print('worked')"],
            }
        }
    }
    (root / "etc" / "plonex.yml").write_text(yaml.safe_dump(options))
    service = CronService(target=root)
    service.enqueue("manual")
    process = launch(root)
    try:
        wait_for(
            lambda: bool(service.runner.history())
            and service.runner.history()[0]["status"] == "succeeded"
        )
        duplicate = subprocess.run(
            [sys.executable, "-m", "plonex.cli", "cron", "daemon"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=8,
        )
        assert duplicate.returncode == 1
        assert "already running" in duplicate.stderr
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=12)
    assert process.returncode == 0, output
    service.enqueue("manual")
    restarted = launch(root)
    try:
        wait_for(
            lambda: len(service.runner.history()) == 2
            and service.runner.history()[0]["status"] == "succeeded"
        )
    finally:
        restarted.terminate()
        output, _ = restarted.communicate(timeout=12)
    assert restarted.returncode == 0, output


def test_daemon_shutdown_stops_active_job_processes_and_records_interruption(
    daemon_project,
):
    root = daemon_project
    marker = root / "child.pid"
    script = (
        "import os,time; from pathlib import Path; "
        f"Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    )
    options = {
        "cron_jobs": {
            "slow": {
                "schedule": "* * * * *",
                "enabled": False,
                "command": [sys.executable, "-c", script],
            }
        }
    }
    (root / "etc" / "plonex.yml").write_text(yaml.safe_dump(options))
    service = CronService(target=root)
    service.enqueue("slow")
    process = launch(root)
    try:
        wait_for(marker.exists)
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=12)
    assert process.returncode == 0, output
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert service.runner.history()[0]["status"] == "interrupted"
