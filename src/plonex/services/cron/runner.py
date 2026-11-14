"""Bounded subprocess jobs, process-safe locks, and persistent execution history."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from datetime import timezone
from pathlib import Path
from plonex.base import BaseService
from plonex.services.cron.model import Job
from threading import Event
from threading import Lock

import fcntl
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import time
import uuid


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobRunner:
    def __init__(self, service: BaseService) -> None:
        self.service = service
        self.folder = service.var_folder / "cron"
        self.database = self.folder / "history.sqlite3"
        self.processes: dict[str, subprocess.Popen] = {}
        self.cancelled: set[str] = set()
        self.mutex = Lock()
        self.stopping = Event()

    def prepare(self):
        self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in ("logs", "locks", "specs"):
            (self.folder / name).mkdir(mode=0o700, exist_ok=True)
        if not self.database.exists():
            self.database.touch(mode=0o600)
        with sqlite3.connect(self.database, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, job TEXT NOT NULL, started TEXT NOT NULL,
                finished TEXT, status TEXT NOT NULL, exit_code INTEGER,
                log TEXT NOT NULL
            )""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
            for name, definition in (("task_id", "TEXT"), ("attempt", "INTEGER")):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE runs ADD COLUMN {name} {definition}"
                    )

    @contextmanager
    def lock(self, name: str, timeout: float = 0):
        self.prepare()
        path = self.folder / "locks" / f"{name}.lock"
        with path.open("a+") as handle:
            os.chmod(path, 0o600)
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if self.stopping.is_set() or time.monotonic() >= deadline:
                        yield False
                        return
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def history(self, name: str = "", limit: int = 50, task_id: str = ""):
        if not self.database.exists():
            return []
        with sqlite3.connect(
            self.database.as_uri() + "?mode=ro", uri=True
        ) as connection:
            connection.row_factory = sqlite3.Row
            filters, values = [], []
            if name:
                filters.append("job = ?")
                values.append(name)
            if task_id:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(runs)")
                }
                if "task_id" not in columns:
                    return []
                filters.append("task_id = ?")
                values.append(task_id)
            where = "WHERE " + " AND ".join(filters) if filters else ""
            args = (*values, limit)
            return [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM runs {where} "
                    "ORDER BY started DESC, rowid DESC LIMIT ?",
                    args,
                )
            ]

    def command(self, job: Job, run_id: str):
        if job.command:
            return list(job.command), {}
        from plonex.services.zconsole import ZConsole

        # A unique runtime directory prevents concurrent template writes. Named
        # configuration still uses the declared runtime's service-specific files.
        runtime = ZConsole(
            target=self.service.target,
            name=job.runtime,
            action="run",
            tmp_folder=self.service.target / "tmp" / "cron-runs" / run_id,
            config_files=self.service.config_files,
        )
        script = Path(__file__).with_name("plone_runner.py")
        spec = self.folder / "specs" / f"{run_id}.json"
        descriptor = os.open(spec, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(asdict(job), handle)
        # Rendering template services does not require entering them. In
        # particular, never mutate os.environ from Huey's worker threads.
        runtime.__dict__["client_home"] = self.folder / "runtime" / run_id
        runtime.client_home.mkdir(parents=True, mode=0o700, exist_ok=True)
        runtime.pre_services = runtime._build_zope_pre_services()
        runtime._prepare_zope_runtime()
        for template in runtime.pre_services or []:
            template.run()
        environment = {
            str(key): (
                value.format(**runtime.options)
                if isinstance(value, str)
                else str(value)
            )
            for key, value in runtime.options.get("environment_vars", {}).items()
        }
        return [*runtime.command, str(script)], (
            environment | runtime.plonex_environment | {"PLONEX_JOB_SPEC": str(spec)}
        )

    @staticmethod
    def terminate_many(processes):
        active = [process for process in processes if process.poll() is None]
        # Signal all workers before waiting, so shutdown remains bounded even
        # when several jobs ignore SIGTERM.
        for process in active:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 3
        for process in active:
            try:
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        for process in active:
            # Also stop descendants which outlived their direct parent.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()

    @classmethod
    def terminate(cls, process):
        cls.terminate_many([process])

    def cancel_all(self):
        with self.mutex:
            self.stopping.set()
            processes = list(self.processes.values())
            self.cancelled.update(self.processes)
        self.terminate_many(processes)

    def run(self, job: Job, task_id: str = ""):
        self.prepare()
        run_id = uuid.uuid4().hex
        log_path = self.folder / "logs" / f"{job.name}-{run_id}.log"
        started = timestamp()
        status, exit_code = "failed", None
        with sqlite3.connect(self.database, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = (
                connection.execute(
                    "SELECT COALESCE(MAX(attempt), 0) + 1 FROM runs WHERE task_id = ?",
                    (task_id,),
                ).fetchone()[0]
                if task_id
                else 1
            )
            connection.execute(
                "INSERT INTO runs "
                "(id, job, started, finished, status, exit_code, log, "
                "task_id, attempt) "
                "VALUES (?, ?, ?, NULL, 'running', NULL, ?, ?, ?)",
                (run_id, job.name, started, str(log_path), task_id, attempt),
            )
        log_path.touch(mode=0o600)
        try:
            with (
                self.lock(job.lock, job.lock_timeout) as acquired,
                log_path.open("a") as log,
            ):
                if not acquired:
                    status = "interrupted" if self.stopping.is_set() else "skipped"
                    log.write(f"Lock {job.lock!r} is busy; job {status}.\n")
                else:
                    command, extra_env = self.command(job, run_id)
                    environment = dict(os.environ)
                    venv = self.service.target / ".venv"
                    environment["VIRTUAL_ENV"] = str(venv)
                    environment["PATH"] = (
                        str(venv / "bin") + os.pathsep + environment.get("PATH", "")
                    )
                    environment.update(
                        {
                            str(key): (
                                value.format(**self.service.options)
                                if isinstance(value, str)
                                else str(value)
                            )
                            for key, value in self.service.options.get(
                                "environment_vars", {}
                            ).items()
                        }
                    )
                    environment.update(extra_env)
                    environment.update(job.environment)
                    if "PLONEX_JOB_SPEC" in extra_env:
                        for key in (
                            "PLONEX_JOB_SPEC",
                            "PLONEX_TARGET",
                            "PLONEX_INSTANCE_NAME",
                            "PLONEX_INSTANCE_HOME",
                            "PLONEX_COMMAND",
                            "PLONEX_VERSION",
                        ):
                            environment[key] = extra_env[key]
                    environment.setdefault("PYTHONUNBUFFERED", "1")
                    with self.mutex:
                        if self.stopping.is_set():
                            raise InterruptedError("Job runner is stopping")
                        process = subprocess.Popen(
                            command,
                            cwd=self.service.target,
                            env=environment,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL,
                            start_new_session=True,
                        )
                        self.processes[run_id] = process
                    try:
                        exit_code = process.wait(timeout=job.timeout)
                        status = "succeeded" if exit_code == 0 else "failed"
                        with self.mutex:
                            if run_id in self.cancelled:
                                status = "interrupted"
                    except subprocess.TimeoutExpired:
                        self.terminate(process)
                        exit_code, status = process.returncode, "timed-out"
                        log.write(f"\nJob exceeded its {job.timeout:g}s timeout.\n")
                    except BaseException:
                        self.terminate(process)
                        status = "interrupted"
                        raise
                    finally:
                        with self.mutex:
                            self.processes.pop(run_id, None)
                            self.cancelled.discard(run_id)
        except Exception as error:
            if isinstance(error, InterruptedError):
                status = "interrupted"
            with log_path.open("a") as log:
                log.write(f"{type(error).__name__}: {error}\n")
        finally:
            (self.folder / "specs" / f"{run_id}.json").unlink(missing_ok=True)
            shutil.rmtree(
                self.service.target / "tmp" / "cron-runs" / run_id, ignore_errors=True
            )
            shutil.rmtree(self.folder / "runtime" / run_id, ignore_errors=True)
            with sqlite3.connect(self.database, timeout=30) as connection:
                connection.execute(
                    "UPDATE runs SET finished=?, status=?, exit_code=? WHERE id=?",
                    (timestamp(), status, exit_code, run_id),
                )
        return {
            "id": run_id,
            "job": job.name,
            "status": status,
            "exit_code": exit_code,
            "log": str(log_path),
            "task_id": task_id,
            "attempt": attempt,
        }
