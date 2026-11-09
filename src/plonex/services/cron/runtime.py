"""Project-environment worker and queue API. Huey is optional in the outer CLI."""

from contextlib import nullcontext
from functools import cached_property
from pathlib import Path
from plonex.files import read_only as inspect_only
from plonex.files import write_if_changed
from plonex.inspection import safe_value
from plonex.services.cron.installation import PROTOCOL_VERSION
from plonex.services.cron.runner import JobRunner
from plonex.services.cron.runner import timestamp
from types import SimpleNamespace

import argparse
import fcntl
import json
import logging
import os
import sqlite3
import sys

QUEUE_NAME = "plonex-cron"


class QueueRuntime:
    """One project queue per process; usable by CLI and application producers."""

    def __init__(self, service, *, read_only=False):
        self.service = service
        with inspect_only() if read_only else nullcontext():
            self.runner = JobRunner(service)
            self.jobs = service.jobs
        self.read_only = read_only
        self.queue_path = self.runner.folder / "queue.sqlite3"
        self.stats_path = self.runner.folder / "stats.sqlite3"
        self.recorder = None

    @cached_property
    def huey(self):
        from huey import SqliteHuey  # type: ignore[import-untyped]

        if self.read_only:
            return SqliteHuey(
                QUEUE_NAME,
                filename=self.queue_path.as_uri() + "?mode=ro",
                uri=True,
                journal_mode=None,
                create_tables=False,
                results=False,
            )
        self.runner.prepare()
        self.queue_path.touch(mode=0o600, exist_ok=True)
        self.stats_path.touch(mode=0o600, exist_ok=True)
        huey = SqliteHuey(
            QUEUE_NAME, filename=str(self.queue_path), utc=True, results=False
        )
        from huey.contrib.stats import database  # type: ignore[import-untyped]
        from huey.contrib.stats import enable_stats  # type: ignore[import-untyped]

        import peewee  # type: ignore[import-untyped]

        db = peewee.SqliteDatabase(
            str(self.stats_path), pragmas={"journal_mode": "wal"}
        )
        database.initialize(db)
        self.recorder = enable_stats(huey, db, capture_args=False)
        return huey

    @cached_property
    def tasks(self):
        tasks = {}
        for job in self.jobs.jobs:

            def execute(task=None, job=job):
                result = self.runner.run(job, task_id=task.id if task else "")
                if result["status"] not in {"succeeded", "skipped"}:
                    raise RuntimeError(
                        f"Job {job.name} {result['status']}; see {result['log']}"
                    )
                return result

            # Preserve the registered task names of queues created before the
            # worker moved from the CLI environment into the project.
            execute.__module__ = "plonex.services.cron"
            settings = dict(
                name=job.name,
                retries=job.retries,
                retry_delay=job.retry_delay,
                context=True,
            )
            decorator = (
                self.huey.periodic_task(job.matcher(), **settings)
                if job.enabled
                else self.huey.task(**settings)
            )
            tasks[job.name] = decorator(execute)
        return tasks

    def enqueue(self, name):
        task = self.tasks[self.jobs.get(name).name].s()
        self.huey.enqueue(task)
        return {"job": name, "task_id": task.id}

    def run_job(self, name):
        task = self.tasks[self.jobs.get(name).name].s()
        task.retries = 0  # Manual execution is one attempt, regardless of policy.
        self.huey.execute(task)
        return self.runner.history(task_id=task.id, limit=1)[0]

    def run_daemon(self, workers=None):
        from huey.consumer import Consumer  # type: ignore[import-untyped]

        workers = (
            self.service.options.get("cron_workers", 1) if workers is None else workers
        )
        if (
            isinstance(workers, bool)
            or not isinstance(workers, int)
            or not 1 <= workers <= 32
        ):
            raise ValueError("cron workers must be an integer from 1 to 32")
        runner = self.runner

        class JobConsumer(Consumer):
            def _handle_signal(self, signum, frame):
                runner.cancel_all()
                super()._handle_signal(signum, frame)

        with runner.lock("_daemon") as acquired:
            if not acquired:
                raise ValueError("A cron daemon is already running for this project")
            metadata = runner.folder / "daemon.json"
            write_if_changed(
                metadata,
                json.dumps(
                    {"pid": os.getpid(), "prefix": sys.prefix, "started": timestamp()}
                ),
            )
            try:
                self.tasks
                JobConsumer(
                    self.huey,
                    workers=workers,
                    worker_type="thread",
                    graceful_signal="TERM",
                    shutdown_timeout=10,
                ).run()
            finally:
                metadata.unlink(missing_ok=True)

    def worker_status(self):
        path = self.runner.folder / "locks/_daemon.lock"
        running = False
        if path.is_file():
            with path.open() as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    running = True
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)
        metadata = self.runner.folder / "daemon.json"
        try:
            details = json.loads(metadata.read_text()) if running else {}
        except (OSError, ValueError):
            details = {}
        if not isinstance(details, dict):
            details = {}
        return {"running": running, **details}

    def queue(self, limit=50):
        if not self.queue_path.is_file():
            return {
                "pending": [],
                "scheduled": [],
                "pending_count": 0,
                "scheduled_count": 0,
            }

        def item(data):
            task = self.huey.serializer.deserialize(data)
            job = task.name.removeprefix("plonex.services.cron.")
            return {
                "task_id": task.id,
                "job": job,
                "eta": task.eta.isoformat() if task.eta else None,
                "retries_remaining": task.retries,
                "revoked": bool(self.huey.is_revoked(task.id, peek=True)),
                "registered": any(
                    definition.name == job for definition in self.jobs.jobs
                ),
            }

        return {
            "pending": [
                item(data) for data in self.huey.storage.enqueued_items(limit=limit)
            ],
            "scheduled": [
                item(data) for data in self.huey.storage.scheduled_items(limit=limit)
            ],
            "pending_count": self.huey.pending_count(),
            "scheduled_count": self.huey.scheduled_count(),
        }

    def statistics(self, limit=50):
        result = {
            "counts": {},
            "tasks": [],
            "recent_events": [],
            "inflight": [],
            "throughput": {},
        }
        if not self.stats_path.is_file():
            return result
        if self.recorder is not None:
            return self.format_statistics(self.recorder, limit)
        from huey.contrib.stats import HueyStats  # type: ignore[import-untyped]
        from huey.contrib.stats import MODELS  # type: ignore[import-untyped]

        import peewee  # type: ignore[import-untyped]

        db = peewee.SqliteDatabase(self.stats_path.as_uri() + "?mode=ro", uri=True)
        stats = HueyStats(SimpleNamespace(name=QUEUE_NAME), db, create_tables=False)
        try:
            with db.bind_ctx(MODELS):
                result = self.format_statistics(stats, limit)
        finally:
            db.close()
        return safe_value(result)

    @staticmethod
    def format_statistics(stats, limit):
        tasks = stats.task_breakdown()
        events = stats.recent_events(limit=limit)
        # Huey's display name drops everything before the last dot. Job names
        # can themselves contain dots, so retain the complete configured name.
        for item in tasks:
            item["job"] = item["full"].removeprefix("plonex.services.cron.")
        for item in events:
            item["job"] = item["task_full"].removeprefix("plonex.services.cron.")
        return safe_value(
            {
                "counts": stats.window_counts(),
                "tasks": tasks,
                "recent_events": events,
                "inflight": stats.inflight(),
                "throughput": stats.throughput(),
            }
        )

    def status(self, limit=50):
        queue = self.queue(limit)
        return {
            "protocol": PROTOCOL_VERSION,
            "interpreter": sys.executable,
            "prefix": sys.prefix,
            "worker": self.worker_status(),
            "queue": queue,
            "statistics": self.statistics(limit),
            "recent_runs": self.runner.history(limit=limit),
        }

    def inspect(self, task_id):
        queue = self.queue(limit=None)
        stats = self.statistics(limit=2000)
        pending = [
            task
            for group in ("pending", "scheduled")
            for task in queue[group]
            if task["task_id"] == task_id
        ]
        events = [
            event for event in stats["recent_events"] if event["task_id"] == task_id
        ]
        runs = self.runner.history(task_id=task_id, limit=100)
        if not pending and not events and not runs:
            raise ValueError(f"Unknown task ID: {task_id}")
        return {"task_id": task_id, "queued": pending, "events": events, "runs": runs}

    def retry(self, task_id):
        runs = self.runner.history(task_id=task_id, limit=1)
        if not runs or runs[0]["status"] not in {"failed", "timed-out", "interrupted"}:
            raise ValueError(
                "Retry requires a recorded failed, timed-out, or interrupted task"
            )
        queue = self.queue(limit=None)
        if any(
            task["task_id"] == task_id
            for group in ("pending", "scheduled")
            for task in queue[group]
        ):
            raise ValueError("The task already has a pending or scheduled attempt")
        if self.runner.database.exists():
            with sqlite3.connect(
                self.runner.database.as_uri() + "?mode=ro", uri=True
            ) as db:
                if db.execute(
                    "SELECT 1 FROM runs WHERE task_id=? AND status='running'",
                    (task_id,),
                ).fetchone():
                    raise ValueError("The task is still running")
        task = self.enqueue(runs[0]["job"])
        return task | {"retry_of": task_id}

    def revoke(self, task_id, *, restore=False):
        self.inspect(task_id)
        if restore:
            self.huey.restore_by_id(task_id)
        else:
            self.huey.revoke_by_id(task_id)
        return {"task_id": task_id, "revoked": not restore}

    def close(self):
        if self.recorder is not None:
            self.recorder.close()
            self.recorder.db.close()
        if "huey" in self.__dict__:
            self.huey.storage.close()

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()


def main(argv=None):
    from plonex.services.cron import CronService

    parser = argparse.ArgumentParser(description="Plonex project queue runtime")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--config", action="append", default=[])
    parser.add_argument(
        "action",
        choices=(
            "probe",
            "daemon",
            "run",
            "enqueue",
            "status",
            "queue",
            "inspect",
            "retry",
            "revoke",
            "restore",
        ),
    )
    parser.add_argument("argument", nargs="?")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--overrides-stdin", action="store_true")
    args = parser.parse_args(argv)
    logging.getLogger("sh").setLevel(logging.WARNING)
    if args.limit < 1 or args.limit > 1000:
        parser.error("limit must be between 1 and 1000")
    if args.action == "probe":
        from huey.contrib.stats import enable_stats  # noqa: F401
        from importlib.metadata import version

        import peewee  # noqa: F401

        print(
            json.dumps(
                {
                    "protocol": PROTOCOL_VERSION,
                    "interpreter": sys.executable,
                    "prefix": sys.prefix,
                    "version": version("plonex"),
                }
            )
        )
        return
    read_only = args.action in {"status", "queue", "inspect"}
    overrides = (
        json.loads(sys.stdin.read())
        if args.overrides_stdin
        else json.loads(os.environ.pop("PLONEX_CRON_OVERRIDES", "{}"))
    )
    if not isinstance(overrides, dict):
        parser.error("configuration overrides must be a mapping")
    with inspect_only() if read_only else nullcontext():
        service = CronService(
            target=args.target.absolute(),
            config_files=args.config,
            cli_options=overrides,
        )
        service.options
    level = str(service.options.get("log_level", "info")).upper()
    if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        logging.getLogger("plonex").setLevel(level)
    try:
        with QueueRuntime(service, read_only=read_only) as runtime:
            if args.action == "daemon":
                runtime.run_daemon(args.workers)
                return
            if (
                args.action
                in {"run", "enqueue", "inspect", "retry", "revoke", "restore"}
                and not args.argument
            ):
                parser.error("this operation requires a job name or task ID")
            if args.action == "run":
                result = runtime.run_job(args.argument)
            elif args.action == "enqueue":
                result = runtime.enqueue(args.argument)
            elif args.action == "status":
                result = runtime.status(args.limit)
            elif args.action == "queue":
                result = runtime.queue(args.limit)
            elif args.action == "inspect":
                result = runtime.inspect(args.argument)
            elif args.action == "retry":
                result = runtime.retry(args.argument)
            else:
                result = runtime.revoke(args.argument, restore=args.action == "restore")
            print(json.dumps(safe_value(result), ensure_ascii=False, default=str))
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
