"""Presentation of shell jobs, separate from terminal and process management."""

from dataclasses import dataclass
from plonex.presentation import MarkdownTable
from rich.console import Console
from rich.text import Text
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plonex.cli.jobs import ShellJob


@dataclass
class JobPresenter:
    console: Console

    def show(self, jobs: list["ShellJob"], *, markdown: bool = False) -> None:
        rows = []
        for job in jobs:
            code = job.process.poll()
            state = "Running" if code is None else f"Exited ({code})"
            style = (
                "green"
                if code is None
                else "cyan" if code == 0 else "yellow" if code < 0 else "red"
            )
            rows.append(
                (
                    Text(f"%{job.number}", style="cyan"),
                    job.service_name,
                    Text(state, style=style),
                    str(job.process.pid),
                    job.label,
                    str(job.log_path),
                )
            )
        MarkdownTable(("Job", "Service", "State", "PID", "Command", "Log"), rows).show(
            self.console, markdown=markdown
        )
