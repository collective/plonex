"""Doit executes the DAG; Plonex owns inspectable, content-based receipts."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from graphlib import CycleError
from graphlib import TopologicalSorter
from pathlib import Path
from plonex.files import project_lock
from plonex.files import read_only
from plonex.files import write_if_changed
from plonex.inspection import safe_value
from typing import Any

import hashlib
import io
import json


def digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def file_digest(path: Path) -> str:
    if not path.is_file():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Task:
    name: str
    action: Callable[[], Any]
    inputs: Callable[[], dict[str, str]]
    outputs: Callable[[], dict[str, str]] = dict
    requires: tuple[str, ...] = ()
    affected: tuple[str, ...] = ()
    revision: str = "1"
    always: bool = False


@dataclass
class PlanEntry:
    task: str
    state: str
    reasons: list[str]
    requires: tuple[str, ...]
    affected: tuple[str, ...]


class Graph:
    def __init__(self, folder: Path):
        self.folder = folder
        self.tasks: dict[str, Task] = {}
        self.executed: list[str] = []
        self.changed: set[str] = set()
        self.error: BaseException | None = None
        self.previous: dict[str, dict] = {}
        self.validate: Callable[[], None] = lambda: None

    def add(self, task: Task):
        if task.name in self.tasks:
            raise ValueError(f"Duplicate preparation task: {task.name}")
        self.tasks[task.name] = task
        return task.name

    def ordered(self):
        for task in self.tasks.values():
            missing = set(task.requires) - self.tasks.keys()
            if missing:
                raise ValueError(
                    f"{task.name}: unknown prerequisites {sorted(missing)}"
                )
        try:
            return list(
                TopologicalSorter(
                    {task.name: task.requires for task in self.tasks.values()}
                ).static_order()
            )
        except CycleError as error:
            raise ValueError(
                f"Preparation dependency cycle: {error.args[1]}"
            ) from error

    def receipt_path(self, task: Task | str):
        name = task if isinstance(task, str) else task.name
        return self.folder / f"{digest(name)}.json"

    def receipt(self, task: Task | str):
        return self.read_receipt(self.receipt_path(task))

    def previous_receipt(self, task: Task | str):
        return self.receipt(task) or self.read_receipt(
            self.receipt_path(task).with_suffix(".previous.json")
        )

    @staticmethod
    def read_receipt(path):
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or value.get("schema") != 1:
                return None
            if not isinstance(value.get("inputs"), dict) or not isinstance(
                value.get("outputs"), dict
            ):
                return None
            return value
        except (FileNotFoundError, ValueError, TypeError):
            return None

    def status(self, task: Task):
        with read_only():
            return self._status(task)

    def _status(self, task: Task):
        before = self.receipt(task)
        if task.always:
            return ["explicit operation; always evaluated"]
        if before is None:
            return ["no successful preparation recorded"]
        reasons = []
        if before.get("revision") != task.revision:
            reasons.append("preparation implementation changed")
        current = task.inputs()
        for key in sorted(current.keys() | before["inputs"].keys()):
            if current.get(key) != before["inputs"].get(key):
                label = safe_value(key)
                action = (
                    "added"
                    if key not in before["inputs"]
                    else "removed" if key not in current else "changed"
                )
                reasons.append(f"{label}: {action}")
        outputs = task.outputs()
        for key in sorted(outputs.keys() | before["outputs"].keys()):
            if outputs.get(key) != before["outputs"].get(key):
                reasons.append(f"{safe_value(key)}: output missing or modified")
        return reasons

    def plan(self):
        entries = []
        pending = set()
        for name in self.ordered():
            task = self.tasks[name]
            reasons = self.status(task)
            state = "stale" if reasons else "current"
            if not reasons and pending.intersection(task.requires):
                state = "check after prerequisites"
                reasons = ["prerequisites may change inputs; recheck before execution"]
            if state != "current":
                pending.add(name)
            entries.append(
                PlanEntry(name, state, reasons, task.requires, task.affected)
            )
        return entries

    def remember(self, task: Task, inputs=None):
        outputs = task.outputs()
        if any(value == "missing" for value in outputs.values()):
            raise ValueError(f"{task.name}: expected output was not produced")
        payload = {
            "schema": 1,
            "task": task.name,
            "revision": task.revision,
            "inputs": task.inputs() if inputs is None else inputs,
            "outputs": outputs,
            "completed": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        write_if_changed(self.receipt_path(task), json.dumps(payload, indent=2))

    def execute(self, task: Task):
        # Invalidate first: even partial work followed by failure needs a retry.
        previous = self.previous_receipt(task) or {}
        journal = self.receipt_path(task).with_suffix(".previous.json")
        if previous:
            write_if_changed(journal, json.dumps(previous))
        self.previous[task.name] = previous
        old_outputs = previous.get("outputs", {})
        self.receipt_path(task).unlink(missing_ok=True)
        try:
            before = task.inputs()
            result = task.action()
            after = task.inputs()
            # Actions may discover/download inputs. Existing inputs may not change
            # underneath an action: never certify work against a newer edit.
            if any(
                after.get(key) != value
                for key, value in before.items()
                if value != "missing"
            ):
                raise ValueError(
                    f"{task.name}: inputs changed during preparation; retry"
                )
            self.remember(task, after)
            journal.unlink(missing_ok=True)
            self.executed.append(task.name)
            changed = (
                result.get("changed", False)
                if isinstance(result, dict) and "changed" in result
                else task.outputs() != old_outputs
            )
            if changed:
                self.changed.update(task.affected)
        except BaseException as error:
            self.receipt_path(task).unlink(missing_ok=True)
            self.error = error
            raise

    def run(self):
        self.ordered()  # Validate before creating state or executing any task.
        self.executed.clear()
        self.changed.clear()
        self.error = None
        with project_lock(self.folder):
            self.validate()
            self.run_locked()
            self.validate()
        return self.executed

    def run_locked(self):
        from doit.control import TaskControl  # type: ignore[import-untyped]
        from doit.dependency import Dependency  # type: ignore[import-untyped]
        from doit.dependency import JsonDB  # type: ignore[import-untyped]
        from doit.reporter import ConsoleReporter  # type: ignore[import-untyped]
        from doit.runner import Runner  # type: ignore[import-untyped]
        from doit.task import Stream  # type: ignore[import-untyped]
        from doit.task import Task as DoitTask  # type: ignore[import-untyped]

        # Receipts are the only durable state. Doit's DB is deliberately ephemeral
        # so read-only plans and execution use exactly the same freshness checks.
        class MemoryDB(JsonDB):
            def __init__(self, name, codec):
                self.name = name
                self._db = {}
                self.codec = codec

            def dump(self):
                pass

        tasks = []
        for task in self.tasks.values():
            tasks.append(
                DoitTask(
                    task.name,
                    actions=[lambda spec=task: self.execute(spec)],
                    task_dep=list(task.requires),
                    uptodate=[lambda spec=task: not self.status(spec)],
                    verbosity=2,
                )
            )
        control = TaskControl(tasks)
        control.process(list(self.tasks))
        output = io.StringIO()
        reporter = ConsoleReporter(output, {})
        result = Runner(Dependency(MemoryDB, ""), reporter, stream=Stream(2)).run_all(
            control.task_dispatcher()
        )
        if result:
            if self.error is not None:
                raise self.error
            raise ValueError(f"Preparation failed: {output.getvalue().strip()}")
