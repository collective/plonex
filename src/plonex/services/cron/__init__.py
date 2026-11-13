from dataclasses import dataclass
from dataclasses import field
from functools import cached_property
from pathlib import Path
from plonex.base import BaseService
from plonex.presentation import MarkdownTable
from plonex.services.cron.model import JobSet
from plonex.services.cron.runner import JobRunner
from rich.console import Console
from threading import Lock
from typing import Any

import json
import os
import shlex
import subprocess


@dataclass(kw_only=True)
class CronService(BaseService):
    name: str = "cron"
    _runner_instance: JobRunner | None = field(default=None, init=False, repr=False)
    _runner_guard: Any = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self):
        self.target = self._ensure_dir(self.target.absolute())

    @cached_property
    def options_defaults(self):
        defaults = super().options_defaults
        defaults.update(cron_jobs={}, cron_timezone="UTC", cron_workers=1)
        return defaults

    @property
    def jobs(self):
        return JobSet.from_options(self.options)

    @property
    def runner(self) -> JobRunner:
        with self._runner_guard:
            if self._runner_instance is None:
                self._runner_instance = JobRunner(self)
            return self._runner_instance

    def run_list(self):
        from plonex.inspection import redact_tokens

        rows = []
        for job in self.jobs.jobs:
            last = self.runner.history(job.name, limit=1)
            rows.append(
                (
                    job.name,
                    job.schedule,
                    job.timezone,
                    "enabled" if job.enabled else "manual only",
                    job.callable or shlex.join(redact_tokens(list(job.command))),
                    last[0]["status"] if last else "never run",
                )
            )
        if not rows:
            Console().print("No project jobs are configured.")
            return
        MarkdownTable(
            ("Job", "Schedule", "Timezone", "State", "Action", "Last result"),
            rows,
            title="Scheduled jobs",
        ).show(Console())

    def run_job(self, name):
        self.jobs.get(name)
        result = self.invoke_runtime("run", name, prepare=True)
        Console().print(
            f"{name}: {result['status']} — log: {result['log']}", markup=False
        )
        if result["status"] in {"failed", "timed-out", "interrupted"}:
            code = result["exit_code"]
            raise SystemExit(code if code and code > 0 else 1)
        return result

    def run_history(self, name="", limit=50, *, output_format="terminal"):
        if name:
            self.jobs.get(name)
        history = self.runner.history(name, limit)
        if output_format == "json":
            Console().print(
                json.dumps(history, indent=2),
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
            return
        if not history:
            Console().print("No job execution history.")
            return
        rows = [
            (
                row["job"],
                row.get("task_id") or "—",
                str(row.get("attempt") or "—"),
                row["started"],
                row["status"],
            )
            for row in history
        ]
        MarkdownTable(
            ("Job", "Task ID", "Attempt", "Started (UTC)", "Result"),
            rows,
            title="Job history",
        ).show(Console())

    def runtime_probe(self):
        from plonex.services.cron.installation import PROTOCOL_VERSION
        from plonex.services.cron.installation import runtime_command

        command = runtime_command(self.target, self.config_files) + ["probe"]
        try:
            process = subprocess.run(
                command, cwd=self.target, capture_output=True, text=True, timeout=15
            )
            payload = json.loads(process.stdout) if process.returncode == 0 else {}
            if (
                isinstance(payload, dict)
                and isinstance(payload.get("prefix"), str)
                and payload.get("protocol") == PROTOCOL_VERSION
                and Path(payload["prefix"]).resolve()
                == (self.target / ".venv").resolve()
            ):
                return payload
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return None

    def ensure_runtime(self):
        if self.runtime_probe() is not None:
            return
        if not self.jobs.jobs:
            raise ValueError(
                "No project jobs are configured. "
                "Add cron_jobs before preparing a worker."
            )
        from plonex.preparation.dependencies import DependencyTasks
        from plonex.services.install import InstallService

        service = InstallService(
            target=self.target,
            config_files=self.config_files,
            cli_options={"cron_jobs": self.options.get("cron_jobs", {})},
            dont_ask=True,
        )
        DependencyTasks(self.target, service=service).graph.run()
        if self.runtime_probe() is None:
            raise ValueError(
                "Project job runtime is unavailable. "
                "Run 'plonex dependencies install' and check the target interpreter."
            )

    def invoke_runtime(self, action, argument="", *, prepare=False, limit=50):
        from plonex.services.cron.installation import runtime_command

        if not 1 <= limit <= 1000:
            raise ValueError("Queue limit must be between 1 and 1000")
        if prepare:
            self.ensure_runtime()
        elif self.runtime_probe() is None:
            if not self.jobs.jobs:
                raise ValueError("No project jobs are configured.")
            raise ValueError(
                "Project job runtime is not installed. "
                "Run 'plonex dependencies install'."
            )
        command = runtime_command(self.target, self.config_files) + [action]
        if argument:
            command.append(argument)
        command.extend(["--limit", str(limit)])
        if self.cli_options:
            command.append("--overrides-stdin")
        process = subprocess.run(
            command,
            cwd=self.target,
            text=True,
            capture_output=True,
            input=json.dumps(self.cli_options) if self.cli_options else None,
        )
        if process.returncode:
            raise ValueError(
                process.stderr.strip()
                or f"Queue operation failed (exit {process.returncode})"
            )
        try:
            result = json.loads(process.stdout)
            if not isinstance(result, dict):
                raise ValueError("Expected a mapping")
            return result
        except ValueError as error:
            raise ValueError("Project job runtime returned invalid JSON") from error

    def enqueue(self, name):
        self.jobs.get(name)
        result = self.invoke_runtime("enqueue", name, prepare=True)
        Console().print(f"Queued {name}: {result['task_id']}", markup=False)
        return result

    def run_daemon(self, workers=None):
        from plonex.services.cron.installation import runtime_command

        if workers is not None and (
            isinstance(workers, bool)
            or not isinstance(workers, int)
            or not 1 <= workers <= 32
        ):
            raise ValueError("cron workers must be an integer from 1 to 32")
        if not self.jobs.jobs:
            raise ValueError(
                "No project jobs are configured. "
                "Add cron_jobs before starting a worker."
            )
        self.ensure_runtime()
        command = runtime_command(self.target, self.config_files) + ["daemon"]
        if workers is not None:
            command.extend(["--workers", str(workers)])
        if self.cli_options:
            os.execve(
                command[0],
                command,
                dict(os.environ)
                | {"PLONEX_CRON_OVERRIDES": json.dumps(self.cli_options)},
            )
        else:
            os.execv(command[0], command)

    def run(self):
        self.run_daemon(None)

    def show_queue(
        self, action="status", task_id="", *, limit=50, output_format="terminal"
    ):
        payload = self.invoke_runtime(
            action,
            task_id,
            limit=limit,
            prepare=action in {"retry", "revoke", "restore"},
        )
        if output_format == "json":
            Console().print(
                json.dumps(payload, indent=2),
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
            return payload
        if action == "status":
            queue, stats = payload["queue"], payload["statistics"]
            state = "running" if payload["worker"]["running"] else "stopped"
            Console().print(
                f"Worker: {state} · Pending: {queue['pending_count']} · "
                f"Scheduled: {queue['scheduled_count']} · "
                f"Recorded in flight: {len(stats['inflight'])}"
            )
            rows = [
                (
                    item["job"],
                    str(item["completed"]),
                    str(item["errors"]),
                    str(item["retries"]),
                )
                for item in stats["tasks"]
            ]
            MarkdownTable(
                ("Job", "Completed", "Errors", "Retries"), rows, "Queue statistics"
            ).show(Console())
        elif action == "queue":
            rows = [
                (
                    item["task_id"],
                    item["job"],
                    "revoked" if item["revoked"] else state,
                    item["eta"] or "now",
                )
                for group, state in (("pending", "pending"), ("scheduled", "scheduled"))
                for item in payload[group]
            ]
            MarkdownTable(("Task ID", "Job", "State", "Due"), rows, "Queue tasks").show(
                Console()
            )
        elif action == "inspect":
            Console().print(
                json.dumps(payload, indent=2),
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        elif action == "retry":
            Console().print(
                f"Queued retry: {payload['task_id']} (job: {payload['job']})",
                markup=False,
            )
        else:
            state = (
                "restored" if action == "restore" else "revoked for future execution"
            )
            Console().print(
                f"{payload['task_id']}: {state}",
                markup=False,
            )
        return payload

    def run_logs(self, name, tail=50):
        from pathlib import Path

        self.jobs.get(name)
        history = self.runner.history(name, 1)
        if not history:
            Console().print(f"{name}: no execution log yet", markup=False)
            return
        path = Path(history[0]["log"])
        with path.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 65536))
            lines = handle.read().decode(errors="replace").splitlines()[-tail:]
        Console().print("\n".join(lines), markup=False, highlight=False)

    def configure_supervisor(self, programs_folder):
        path = programs_folder / "plonex-cron.conf"
        if not self.jobs.jobs:
            path.unlink(missing_ok=True)
            return
        from plonex.services.cron.installation import runtime_command

        command = runtime_command(self.target, self.config_files) + ["daemon"]
        log = self.var_folder / "log" / "cron.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "# Generated by plonex; change cron_jobs in YAML.\n"
            "[program:plonex-cron]\n"
            f"command={shlex.join(command)}\n"
            f"directory={self.target}\n"
            "autostart=true\nautorestart=true\nstartsecs=2\npriority=30\n"
            "stopasgroup=true\nkillasgroup=true\nstopwaitsecs=20\n"
            f"stdout_logfile={log}\nstdout_logfile_maxbytes=20MB\n"
            "stdout_logfile_backups=5\nredirect_stderr=true\n"
        )
        # Supervisor interpolates percent signs in all option values.
        programs_folder.mkdir(parents=True, exist_ok=True)
        from plonex.files import write_if_changed

        write_if_changed(path, text.replace("%", "%%"))
