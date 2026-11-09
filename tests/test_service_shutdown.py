import os
import pytest
import subprocess
import sys
import time


def test_termination_of_launcher_stops_its_separate_child_process(tmp_path):
    marker = tmp_path / "pid"
    child = (
        f'import os,time; open({str(marker)!r},"w").write(str(os.getpid())); '
        "time.sleep(60)"
    )
    script = (
        "from plonex.base import BaseService; "
        f'BaseService.execute_command([{sys.executable!r}, "-c", {child!r}])'
    )
    launcher = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (
            not marker.exists() or not marker.read_text()
        ):
            if launcher.poll() is not None:
                pytest.fail("Launcher exited before creating the child")
            time.sleep(0.02)
        child_pid = int(marker.read_text())
        launcher.terminate()
        launcher.wait(timeout=10)
        assert launcher.returncode == 143
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=5)


def test_termination_escalates_when_child_ignores_sigterm(tmp_path):
    marker = tmp_path / "pid"
    child = (
        f"import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f'open({str(marker)!r},"w").write(str(os.getpid())); time.sleep(60)'
    )
    script = (
        "from plonex.base import BaseService; "
        f'BaseService.execute_command([{sys.executable!r}, "-c", {child!r}])'
    )
    launcher = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (
            not marker.exists() or not marker.read_text()
        ):
            if launcher.poll() is not None:
                pytest.fail("Launcher exited before creating the child")
            time.sleep(0.02)
        child_pid = int(marker.read_text())
        launcher.terminate()
        _, error = launcher.communicate(timeout=10)
        assert launcher.returncode == 143, error.decode()
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=5)
