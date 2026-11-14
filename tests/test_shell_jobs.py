from .utils import temp_cwd
from contextlib import redirect_stdout
from plonex.cli.jobs import ShellJob
from plonex.cli.jobs import ShellJobs
from unittest import mock

import io
import os
import pty
import select
import signal
import subprocess
import sys
import time
import unittest


class TerminalShell:
    """Drive the actual shell through a controlling terminal, including key presses."""

    def __init__(self, target):
        self.target = target
        self.pending = b""
        self.output = b""

    def __enter__(self):
        self.pid, self.master = pty.fork()
        if self.pid == 0:
            os.chdir(self.target)
            os.execv(sys.executable, [sys.executable, "-m", "plonex.cli", "shell"])
        self.read_until(b"]> ")
        return self

    def send(self, data):
        os.write(self.master, data.encode() if isinstance(data, str) else data)

    def read_until(self, marker, timeout=10):
        deadline = time.monotonic() + timeout
        while marker not in self.pending:
            if time.monotonic() >= deadline:
                raise AssertionError(f"Waiting for {marker!r}: {self.output!r}")
            if not select.select([self.master], [], [], 0.1)[0]:
                continue
            data = os.read(self.master, 65536)
            if not data:
                raise AssertionError(f"Terminal closed: {self.output!r}")
            self.pending += data
            self.output += data
        end = self.pending.index(marker) + len(marker)
        data, self.pending = self.pending[:end], self.pending[end:]
        return data.decode(errors="replace")

    def command(self, line):
        self.send(line + "\n")
        return self.read_until(b"]> ")

    def wait(self, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.pid = None
                return os.waitstatus_to_exitcode(status)
            time.sleep(0.02)
        raise AssertionError(f"Shell did not exit: {self.output!r}")

    def __exit__(self, *_exc):
        try:
            if self.pid is not None:
                self.send(b"\x1a")
                self.send("exit\n")
                try:
                    self.wait(timeout=5)
                except AssertionError:
                    os.kill(self.pid, signal.SIGKILL)
                    os.waitpid(self.pid, 0)
        except OSError:
            pass
        finally:
            os.close(self.master)
            pid_file = self.target / "server.pid"
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


class TestShellJobsTerminal(unittest.TestCase):
    def setUp(self):
        self.target = self.enterContext(temp_cwd())
        (self.target / "etc").mkdir()
        (self.target / "etc" / "plonex.yml").write_text("{}\n")
        folder = self.target / ".venv" / "bin"
        folder.mkdir(parents=True)
        (folder / "activate").touch()
        self.executable(
            folder / "runwsgi",
            """
import os, time
from pathlib import Path
Path('server.pid').write_text(str(os.getpid()))
print('SERVER_READY', flush=True)
try:
    counter = 0
    while True:
        counter += 1
        Path('heartbeat').write_text(str(counter))
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
finally:
    Path('server.stopped').touch()
""",
        )
        self.executable(
            folder / "upgrade",
            """
import os, time
from pathlib import Path
os.kill(int(Path('server.pid').read_text()), 0)
first = Path('heartbeat').read_text()
time.sleep(0.2)
assert Path('heartbeat').read_text() != first, 'The instance was suspended'
print('UPGRADE_OK', flush=True)
""",
        )

    def executable(self, path, source):
        path.write_text(f"#!{sys.executable}\n" + source)
        path.chmod(0o755)

    def wait_for_output(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            logs = list((self.target / "var" / "log" / "shell").glob("*.log"))
            if any("SERVER_READY" in file.read_text() for file in logs):
                return
            time.sleep(0.02)
        self.fail("Server did not start")

    def test_fg_detach_upgrade_and_resume_the_same_running_instance(self):
        (self.target / "etc/plonex.yml").write_text("upgrade_tempfile_auth: true\n")
        with TerminalShell(self.target) as terminal:
            terminal.send("instance debug\n")
            terminal.read_until(b"SERVER_READY")
            pid = (self.target / "server.pid").read_text()
            terminal.send(b"\x1a")
            detached = terminal.read_until(b"]> ")
            self.assertIn("still running", detached)
            self.assertIn("Running", terminal.command("jobs"))
            upgrade = terminal.command("db upgrade --url http://127.0.0.1:8080/")
            self.assertIn("UPGRADE_OK", upgrade)
            self.assertNotIn("Command exited with status", upgrade)
            self.assertEqual((self.target / "server.pid").read_text(), pid)
            terminal.send("fg\n")
            time.sleep(0.15)
            terminal.send(b"\x03")
            terminal.read_until(b"]> ")
            self.assertTrue((self.target / "server.stopped").exists())
            terminal.send("exit\n")
            self.assertEqual(terminal.wait(), 0)

    def test_background_output_logs_attach_and_kill(self):
        with TerminalShell(self.target) as terminal:
            started = terminal.command("instance debug &")
            self.wait_for_output()
            self.assertNotIn("SERVER_READY", started)
            self.assertIn("SERVER_READY", terminal.command("logs %1"))
            self.assertIn("Running", terminal.command("bg %1"))
            terminal.send("attach %1\n")
            terminal.read_until(b"SERVER_READY")
            terminal.send(b"\x1a")
            terminal.read_until(b"]> ")
            self.assertIn("Exited", terminal.command("kill %1"))
            self.assertIn("SERVER_READY", terminal.command("logs %1"))
            self.assertTrue((self.target / "server.stopped").exists())
            self.assertIn("No shell job", terminal.command("fg %999"))
            self.assertIn("Usage: jobs", terminal.command("jobs extra"))
            terminal.send("exit\n")
            self.assertEqual(terminal.wait(), 0)

    def test_exit_cleans_up_a_detached_instance_and_restores_the_terminal(self):
        with TerminalShell(self.target) as terminal:
            terminal.command("instance debug &")
            self.wait_for_output()
            terminal.send("exit\n")
            self.assertEqual(terminal.wait(), 0)
            self.assertTrue((self.target / "server.stopped").exists())

    def test_foreground_debugger_can_read_terminal_input(self):
        zconsole = self.target / ".venv" / "bin" / "zconsole"
        self.executable(
            zconsole,
            """
line = input('DEBUG_INPUT> ')
print('REPLY=' + line, flush=True)
""",
        )
        with TerminalShell(self.target) as terminal:
            terminal.send("instance console\n")
            terminal.read_until(b"DEBUG_INPUT> ")
            terminal.send("hello debugger\n")
            output = terminal.read_until(b"]> ")
            self.assertIn("REPLY=hello debugger", output)
            terminal.send("exit\n")
            self.assertEqual(terminal.wait(), 0)

    def test_job_table_and_startup_options_survive_configuration_changes_and_exit(self):
        config = self.target / "etc" / "plonex.yml"
        config.write_text(
            "http_port: 9000\nenvironment_vars:\n  API_TOKEN: private-value\n"
        )
        with TerminalShell(self.target) as terminal:
            terminal.command("instance debug --port 8089 &")
            self.wait_for_output()
            table = terminal.command("jobs --markdown")
            self.assertIn("| Job | Service | State | PID | Command | Log |", table)
            self.assertIn("| %1 | fg | Running |", table)
            config.write_text("http_port: 9999\n")
            snapshot = terminal.command("options %1 --markdown")
            self.assertIn("| http_port | 8089 |", snapshot)
            self.assertIn("RunWSGI", snapshot)
            self.assertNotIn("private-value", snapshot)
            preview = terminal.command("options --markdown instance debug")
            self.assertIn("| http_port | 9999 |", preview)
            terminal.command("kill %1")
            self.assertIn(
                "| http_port | 8089 |", terminal.command("options %1 --markdown")
            )
            files = list((self.target / "var" / "log" / "shell").glob("*.json"))
            self.assertTrue(files)
            for path in files:
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("private-value", path.read_text())
            terminal.send("exit\n")
            self.assertEqual(terminal.wait(), 0)


class TestShellJobSelection(unittest.TestCase):
    def test_job_selection_and_background_require_a_terminal(self):
        with temp_cwd() as target, mock.patch("sys.stdin.isatty", return_value=False):
            jobs = ShellJobs(target)
            with self.assertRaisesRegex(ValueError, "no running"):
                jobs.get()
            with self.assertRaisesRegex(ValueError, "No shell job"):
                jobs.get("%3")
            with self.assertRaisesRegex(ValueError, "interactive terminal"):
                jobs.launch(["true"], "true", background=True)

    def test_stopping_an_unresponsive_job_escalates_signals(self):
        process = mock.Mock(pid=1234)
        process.poll.return_value = None
        process.wait.side_effect = [
            subprocess.TimeoutExpired("job", 3),
            subprocess.TimeoutExpired("job", 2),
            None,
        ]
        job = ShellJob(1, "fg", process, -1, mock.Mock(), mock.Mock(), 0)
        job.finished.set()
        with mock.patch("plonex.cli.jobs.os.killpg") as killpg:
            job.stop()
        self.assertEqual(
            killpg.call_args_list,
            [
                mock.call(1234, signal.SIGINT),
                mock.call(1234, signal.SIGTERM),
                mock.call(1234, signal.SIGKILL),
            ],
        )

    def test_log_replay_is_bounded_and_works_after_the_writer_is_closed(self):
        with temp_cwd() as target:
            path = target / "job.log"
            data = b"old output\n" + b"x" * 65536
            path.write_bytes(data)
            with path.open("ab") as writer:
                job = ShellJob(1, "fg", mock.Mock(), -1, path, writer, 0)
            with redirect_stdout(io.StringIO()) as output:
                job.show_output(resume=True)
            self.assertEqual(output.getvalue(), "x" * 65536)
            self.assertEqual(job.displayed, len(data))
            self.assertTrue(job.attached)
