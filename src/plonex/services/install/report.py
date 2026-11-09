"""Turn uv's installation events into a concise report of actual operations."""

from dataclasses import dataclass
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion
from packaging.version import Version
from rich.console import Console
from rich.text import Text

import re

_EVENT = re.compile(
    r"^\s*([+~-])\s+([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)(?:\s+\((.*)\))?\s*$"
)
_ROUTINE = re.compile(
    r"^\s*(?:Using (?:Python|CPython|PyPy)\b|Resolved in\b|"
    r"(?:Resolved|Prepared|Installed|Uninstalled|Audited|Checked) \d+ packages?\b|"
    r"(?:Downloading|Downloaded|Building|Built)\s)"
)
_ACTIVITY = re.compile(r"^\s*(?:Installed|Uninstalled) [1-9]\d* packages?\b")


@dataclass(frozen=True)
class PackageChange:
    name: str
    action: str
    before: str | None = None
    after: str | None = None

    def text(self) -> Text:
        styles = {
            "Added": "green",
            "Removed": "red",
            "Upgraded": "cyan",
            "Downgraded": "yellow",
            "Reinstalled": "magenta",
        }
        result = Text(self.action, style=styles.get(self.action, "yellow"))
        result.append(f" {self.name}")
        if self.before and self.after and self.before != self.after:
            result.append(f": {self.before} → {self.after}")
        else:
            result.append(f"=={self.after or self.before}")
        return result


@dataclass(frozen=True)
class DependencyReport:
    changes: tuple[PackageChange, ...] = ()
    diagnostics: tuple[str, ...] = ()
    installer_activity: bool = False

    @classmethod
    def from_output(cls, output: str) -> "DependencyReport":
        added: dict[str, tuple[str, str | None]] = {}
        removed: dict[str, tuple[str, str | None]] = {}
        reinstalls: dict[str, str] = {}
        diagnostics = []
        activity = False
        for line in output.splitlines():
            match = _EVENT.fullmatch(line)
            if match:
                sign, name, version, origin = match.groups()
                name = canonicalize_name(name)
                if sign == "+":
                    added[name] = (version, origin)
                elif sign == "-":
                    removed[name] = (version, origin)
                else:
                    reinstalls[name] = version
                continue
            activity |= bool(_ACTIVITY.match(line)) or line.lstrip().startswith(
                ("+ ", "- ", "~ ")
            )
            if line.strip() and not _ROUTINE.match(line):
                diagnostics.append(line)

        changes = []
        for name in sorted(added.keys() | removed.keys() | reinstalls.keys()):
            if name in added and name in removed:
                after, new_origin = added[name]
                before, old_origin = removed[name]
                if before == after:
                    action = (
                        "Changed source" if old_origin != new_origin else "Reinstalled"
                    )
                else:
                    try:
                        old_version, new_version = Version(before), Version(after)
                        if new_version > old_version:
                            action = "Upgraded"
                        elif new_version < old_version:
                            action = "Downgraded"
                        else:
                            action = "Updated"
                    except InvalidVersion:
                        action = "Updated"
                changes.append(PackageChange(name, action, before, after))
            elif name in added:
                changes.append(PackageChange(name, "Added", after=added[name][0]))
            elif name in removed:
                changes.append(PackageChange(name, "Removed", before=removed[name][0]))
            else:
                changes.append(
                    PackageChange(name, "Reinstalled", after=reinstalls[name])
                )
        return cls(tuple(changes), tuple(diagnostics), activity)

    def show(self, console: Console, *, diagnostics: bool = True) -> None:
        if diagnostics:
            for message in self.diagnostics:
                console.print(message, markup=False, highlight=False)
        for change in self.changes:
            console.print(change.text())
        if not self.changes:
            console.print(
                "Dependencies updated."
                if self.installer_activity
                else "No package changes."
            )
