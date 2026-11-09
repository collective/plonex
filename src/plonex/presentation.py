"""Consistent coloured terminal tables and portable Markdown export."""

from dataclasses import dataclass
from dataclasses import field
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from typing import Sequence


@dataclass
class MarkdownTable:
    columns: tuple[str, ...]
    rows: Sequence[tuple[str | Text, ...]] = field(default_factory=list)
    title: str | None = None

    @staticmethod
    def cell(value: str | Text) -> str:
        text = value.plain if isinstance(value, Text) else str(value)
        return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")

    def markdown(self) -> str:
        lines = [
            "| " + " | ".join(self.columns) + " |",
            "| " + " | ".join("---" for _ in self.columns) + " |",
        ]
        lines.extend(
            "| " + " | ".join(self.cell(value) for value in row) + " |"
            for row in self.rows
        )
        return "\n".join(lines)

    def show(self, console: Console, *, markdown: bool = False) -> None:
        if markdown:
            if self.title:
                console.print(f"## {self.title}\n", markup=False, highlight=False)
            console.print(
                self.markdown(), markup=False, highlight=False, soft_wrap=True
            )
            return
        table = Table(title=self.title, box=box.MARKDOWN, header_style="bold cyan")
        for column in self.columns:
            table.add_column(column, min_width=7 if column == "State" else None)
        for row in self.rows:
            table.add_row(
                *(
                    value if isinstance(value, Text) else Text(str(value))
                    for value in row
                )
            )
        console.print(table)
