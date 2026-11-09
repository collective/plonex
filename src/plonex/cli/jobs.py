"""Terminal-backed jobs owned by one interactive plonex shell."""

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.cli.job_view import JobPresenter
from plonex.inspection import ServiceSnapshot
from rich.console import Console
from threading import Event
from threading import RLock
from threading import Thread
from typing import BinaryIO

import fcntl
import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time
import tty

JOB_COMMANDS = ("jobs", "fg", "attach", "bg", "logs", "kill", "options")

# Using a fresh interpreter avoids preexec_fn in a parent with reader threads.
_LAUNCHER = (
    "import os, sys; "
    "os.login_tty(int(sys.argv[1])); "
    "os.execv(sys.argv[2], sys.argv[2:])"
)


def _display(data: bytes) -> None:
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        buffer.flush()
    else:
        sys.stdout.write(data.decode(errors="replace"))
        sys.stdout.flush()


@dataclass
class ShellJob:
    number: int
    label: str
    process: subprocess.Popen
    master: int
    log_path: Path
    log: BinaryIO
    terminal: int
    service_name: str = "—"
    snapshot_path: Path | None = None
    attached: bool = False
    displayed: int = 0
    lock: RLock = field(default_factory=RLock)
    finished: Event = field(default_factory=Event)
    closing: Event = field(default_factory=Event)
    reader: Thread = field(init=False)

    def snapshot(self) -> ServiceSnapshot:
        if self.snapshot_path is None:
            raise ValueError(
                f"Job %{self.number} has no service options "
                "(it may be a help/version command)."
            )
        if not self.snapshot_path.exists():
            if self.process.poll() is not None:
                raise ValueError(
                    f"Job %{self.number} exited before its options were captured. "
                    "Use options COMMAND to preview current settings."
                )
            raise ValueError(
                f"Options for job %{self.number} are not available yet. "
                "Retry once its service starts."
            )
        return ServiceSnapshot.read(self.snapshot_path)

    def start_reader(self) -> None:
        self.reader = Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        try:
            while not self.closing.is_set():
                ready, _, _ = select.select([self.master], [], [], 0.1)
                if not ready:
                    if self.process.poll() is not None:
                        break
                    continue
                data = os.read(self.master, 65536)
                if not data:
                    break
                with self.lock:
                    self.log.write(data)
                    self.log.flush()
                    if self.attached:
                        _display(data)
                        self.displayed = self.log.tell()
        except OSError:
            # A terminal closes with EIO on Linux and EOF on other Unix systems.
            pass
        finally:
            with self.lock:
                os.close(self.master)
                self.master = -1
                self.log.close()
            self.finished.set()

    def resize(self) -> None:
        with self.lock:
            if self.master >= 0:
                try:
                    size = fcntl.ioctl(self.terminal, termios.TIOCGWINSZ, b"\0" * 8)
                    fcntl.ioctl(self.master, termios.TIOCSWINSZ, size)
                except OSError:
                    pass

    def send_signal(self, signum: int) -> None:
        if self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signum)
        except ProcessLookupError:
            # The launcher may not have established its session yet.
            self.process.send_signal(signum)

    def show_output(self, *, resume: bool = False) -> None:
        with self.lock, self.log_path.open("rb") as output:
            end = output.seek(0, os.SEEK_END)
            start = max(self.displayed if resume else 0, end - 65536)
            output.seek(start)
            _display(output.read())
            if resume:
                self.displayed = end
                self.attached = True

    def stop(self) -> None:
        # SIGINT lets the CLI clean up commands it launched in separate sessions.
        for signum, timeout in (
            (signal.SIGINT, 3),
            (signal.SIGTERM, 2),
            (signal.SIGKILL, 2),
        ):
            if self.process.poll() is not None:
                break
            self.send_signal(signum)
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                continue
        self.finished.wait(timeout=1)

    def close(self) -> None:
        self.stop()
        self.closing.set()
        self.reader.join(timeout=2)
        with self.lock:
            self.log.close()


class ShellJobs:
    """Proxy each interactive command through its own controlling terminal."""

    def __init__(self, target: Path, *, console: Console | None = None):
        self.target = target
        self.console = console or Console()
        self.presenter = JobPresenter(self.console)
        self.enabled = sys.stdin.isatty() and sys.stdout.isatty()
        self.jobs: dict[int, ShellJob] = {}
        self.session = time.time_ns()

    def __enter__(self):
        if self.enabled:
            self.previous_resize = signal.getsignal(signal.SIGWINCH)
            signal.signal(signal.SIGWINCH, self._resize)
        return self

    def __exit__(self, *_exc):
        try:
            if self.active():
                print("Stopping shell jobs...")
            for job in self.jobs.values():
                job.close()
        finally:
            if self.enabled:
                signal.signal(signal.SIGWINCH, self.previous_resize)

    def _resize(self, _signum, _frame) -> None:
        for job in list(self.jobs.values()):
            job.resize()

    def active(self) -> list[ShellJob]:
        return [job for job in self.jobs.values() if job.process.poll() is None]

    def get(self, reference: str | None = None) -> ShellJob:
        if reference is None:
            running = self.active()
            if not running:
                raise ValueError("There are no running shell jobs.")
            return running[-1]
        try:
            return self.jobs[int(reference.removeprefix("%"))]
        except (KeyError, ValueError):
            raise ValueError(
                f"No shell job {reference!r}. Use jobs to list jobs."
            ) from None

    def launch(
        self,
        command: list[str],
        label: str,
        *,
        background: bool = False,
        invocation=None,
    ):
        if not self.enabled:
            raise ValueError("Background jobs require an interactive terminal.")
        log_folder = BaseService(target=self.target).var_folder / "log" / "shell"
        log_folder.mkdir(parents=True, exist_ok=True)
        number = len(self.jobs) + 1
        log_path = log_folder / f"{self.session}-{number}.log"
        snapshot_path = (
            log_path.with_suffix(".json") if invocation is not None else None
        )
        environment = dict(os.environ)
        if invocation is not None:
            environment.update(invocation.snapshot_environment(snapshot_path))
        log = log_path.open("w+b")
        try:
            master, slave = pty.openpty()
        except BaseException:
            log.close()
            raise
        try:
            process = subprocess.Popen(
                [sys.executable, "-c", _LAUNCHER, str(slave), *command],
                cwd=self.target,
                env=environment,
                pass_fds=(slave,),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except BaseException:
            os.close(master)
            log.close()
            raise
        finally:
            os.close(slave)
        job = ShellJob(
            number,
            label,
            process,
            master,
            log_path,
            log,
            sys.stdin.fileno(),
            service_name=invocation.name if invocation is not None else "—",
            snapshot_path=snapshot_path,
        )
        self.jobs[number] = job
        job.resize()
        job.start_reader()
        if background:
            self.describe(job)
            return None
        return self.attach(job)

    def describe(self, job: ShellJob) -> None:
        self.presenter.show([job])

    def attach(self, job: ShellJob):
        terminal = sys.stdin.fileno()
        saved = termios.tcgetattr(terminal)
        try:
            tty.setraw(terminal)
            job.resize()
            job.show_output(resume=True)
            job.send_signal(signal.SIGCONT)
            while not job.finished.is_set():
                try:
                    ready, _, _ = select.select([terminal], [], [], 0.1)
                    if not ready:
                        continue
                    data = os.read(terminal, 1)
                    if data == b"\x1a":
                        break
                    with job.lock:
                        if job.master >= 0 and data:
                            os.write(job.master, data)
                except KeyboardInterrupt:
                    job.send_signal(signal.SIGINT)
        finally:
            with job.lock:
                job.attached = False
            termios.tcsetattr(terminal, termios.TCSADRAIN, saved)
        if job.finished.is_set():
            # PTY EOF can arrive just before the process becomes waitable.
            try:
                job.process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
        if job.process.poll() is None:
            print()
            self.describe(job)
            print(f"Use fg %{job.number} to return to this job; it is still running.")
            return None
        return job.process.returncode

    def builtin(self, tokens: list[str]) -> bool:
        name = tokens[0]
        if name == "options" and len(tokens) > 1:
            reference = next(
                (token for token in tokens[1:] if token != "--markdown"), ""
            )
            if not reference.removeprefix("%").isdigit():
                return False
        resume_fg = name == "fg" and (
            (len(tokens) == 1 and bool(self.active()))
            or (len(tokens) == 2 and tokens[1].removeprefix("%").isdigit())
        )
        if name not in JOB_COMMANDS and not resume_fg:
            return False
        markdown = "--markdown" in tokens[1:]
        if markdown and name not in {"jobs", "options"}:
            raise ValueError(f"--markdown is not supported for {name}")
        tokens = [token for token in tokens if token != "--markdown"]
        if len(tokens) > 2 or (name == "jobs" and len(tokens) != 1):
            raise ValueError(f"Usage: {name}" + ("" if name == "jobs" else " [JOB]"))
        if name == "jobs":
            if not self.jobs:
                print("There are no shell jobs.")
            if self.jobs:
                self.presenter.show(list(self.jobs.values()), markdown=markdown)
            return True
        job = self.get(tokens[1] if len(tokens) == 2 else None)
        if name in {"fg", "attach"}:
            code = self.attach(job)
            if code:
                print(f"Command exited with status {code}.", file=sys.stderr)
        elif name == "bg":
            job.send_signal(signal.SIGCONT)
            self.describe(job)
        elif name == "kill":
            job.stop()
            self.describe(job)
        elif name == "logs":
            job.show_output()
        elif name == "options":
            job.snapshot().show(self.console, markdown=markdown)
        return True
