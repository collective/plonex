"""A keyboard-driven Rich file picker for project configuration."""

from pathlib import Path
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import os
import select
import sys
import termios
import tty


class FilePicker:
    def __init__(self, files: list[Path], target: Path, console: Console):
        self.files = files
        self.target = target
        self.console = console
        self.cursor = 0

    def render(self) -> Panel:
        table = Table.grid(padding=(0, 1), expand=True)
        table.add_column(width=2)
        table.add_column(ratio=1, overflow="ellipsis", no_wrap=True)
        # Leave room for the panel, title, and instructions on small terminals.
        page_size = max(1, self.console.height - 8)
        start = max(0, min(self.cursor - page_size + 1, len(self.files) - page_size))
        end = min(len(self.files), start + page_size)
        for index in range(start, end):
            path = self.files[index]
            try:
                path = path.relative_to(self.target)
            except ValueError:
                pass
            focused = index == self.cursor
            style = "bold cyan" if focused else ""
            table.add_row(
                Text("›" if focused else " ", style=style),
                Text(str(path), style=style),
            )
        table.add_row("", "")
        table.add_row(
            "",
            Text("↑/↓ move  Enter open  q cancel", style="dim"),
        )
        title = "Edit project files"
        if len(self.files) > page_size:
            title += f" · {start + 1}–{end} of {len(self.files)}"
        return Panel(table, title=title, title_align="left", border_style="blue")

    @staticmethod
    def read_key(fd: int) -> bytes:
        key = os.read(fd, 1)
        if key == b"\x1b":
            # Arrow-key escape sequences can arrive in separate reads.
            while len(key) < 3 and select.select([fd], [], [], 0.05)[0]:
                key += os.read(fd, 1)
        return key

    def choose(self) -> list[Path]:
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            with Live(
                self.render(), console=self.console, screen=True, auto_refresh=False
            ) as live:
                while True:
                    key = self.read_key(fd)
                    if key in (b"", b"q", b"\x1b"):
                        return []
                    if key in (b"\x1b[A", b"k"):
                        self.cursor = max(0, self.cursor - 1)
                    elif key in (b"\x1b[B", b"j"):
                        self.cursor = min(len(self.files) - 1, self.cursor + 1)
                    elif key in (b"\r", b"\n"):
                        return [self.files[self.cursor]]
                    live.update(self.render(), refresh=True)
        except KeyboardInterrupt:
            return []
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
