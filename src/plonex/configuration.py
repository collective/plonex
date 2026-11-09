"""Configuration provenance recorded by the real merge, before interpolation."""

from copy import deepcopy
from dataclasses import dataclass
from jinja2 import Environment
from jinja2 import meta
from typing import Any

import re
import yaml


def paths(values: dict, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    result = {}
    for key, value in values.items():
        path = (*prefix, str(key))
        result[path] = value
        if isinstance(value, dict):
            result.update(paths(value, path))
    return result


@dataclass(frozen=True)
class Definition:
    source: str
    operation: str
    value: Any


class TrackedOptions(dict):
    """Internal mapping; public resolved options remain ordinary dictionaries."""

    def __init__(self, values=None, *, source="", history=None):
        super().__init__(deepcopy(dict(values or {})))
        self.history = deepcopy(history or {})
        if source:
            self.history = {
                key: [Definition(source, "set", deepcopy(value))]
                for key, value in paths(self).items()
            }

    @classmethod
    def merged(cls, before, incoming, result, *, source="", prefixes=True):
        history = deepcopy(getattr(before, "history", {}))
        incoming_history = getattr(incoming, "history", {})
        before_paths, after_paths = paths(before), paths(result)
        for raw_key, value in incoming.items():
            key = str(raw_key)
            operation = "set"
            if prefixes and key.startswith(("+", "-")) and key[1:] in before:
                operation = "append" if key[0] == "+" else "remove"
                key = key[1:]
            relevant = {
                path
                for path in before_paths.keys() | after_paths.keys()
                if path[0] == key
            }
            definitions = incoming_history.get((str(raw_key),), [])
            label = source or (
                definitions[-1].source if definitions else "configuration"
            )
            for path in relevant:
                if operation == "append" and len(path) > 1:
                    if not isinstance(value, dict) or path[1] not in value:
                        continue
                if operation == "remove" and path in after_paths and len(path) > 1:
                    continue
                original_path = (str(raw_key), *path[1:])
                events = incoming_history.get(original_path, [])
                if operation == "set" and path in after_paths and events:
                    history.setdefault(path, []).extend(deepcopy(events))
                else:
                    state = "removed" if path not in after_paths else operation
                    history.setdefault(path, []).append(
                        Definition(label, state, deepcopy(after_paths.get(path)))
                    )
        return cls(result, history=history)

    def overlay(self, incoming, source=""):
        result = deepcopy(dict(self))
        result.update(deepcopy(dict(incoming)))
        return self.merged(self, incoming, result, source=source, prefixes=False)


@dataclass
class ConfigurationTrace:
    definitions: dict[tuple[str, ...], list[Definition]]
    raw: dict
    resolved: dict

    def safe_options(self) -> dict:
        """Resolved top-level values with secret derivations redacted too."""
        return {row["key"]: row["value"] for row in self.rows() if row["active"]}

    @property
    def references(self) -> dict[str, list[str]]:
        env = Environment()
        result = {}
        for key, value in self.raw.items():
            text = yaml.safe_dump(value)
            if "{{" not in text and "{%" not in text:
                continue
            result[str(key)] = sorted(meta.find_undeclared_variables(env.parse(text)))
        return result

    def rows(self, key: str = "", *, nested=False) -> list[dict]:
        from plonex.inspection import _SENSITIVE
        from plonex.inspection import safe_value

        current = paths(self.resolved)
        references = self.references
        sensitive = {str(name) for name in self.raw if _SENSITIVE.search(str(name))}
        for name, value in self.raw.items():
            text = yaml.safe_dump(value)
            expressions = re.findall(r"{{.*?}}|{%.*?%}", text, re.DOTALL)
            if any(_SENSITIVE.search(expression) for expression in expressions):
                sensitive.add(str(name))
        for _ in range(len(references) + 1):
            sensitive.update(
                name
                for name, inputs in references.items()
                if any(item in sensitive for item in inputs)
            )
        result = []
        for path, definitions in sorted(self.definitions.items()):
            display = ".".join(path)
            if key and display != key and not display.startswith(key + "."):
                continue
            if not key and not nested and len(path) > 1:
                continue

            # Redact using the original nesting, including sensitive ancestor keys.
            def redact(value):
                if path[0] in sensitive:
                    return "[redacted]"
                wrapped = value
                for component in reversed(path):
                    wrapped = {component: wrapped}
                redacted = safe_value(wrapped)
                for component in path:
                    if not isinstance(redacted, dict):
                        break
                    redacted = redacted[component]
                return redacted

            events = [
                {
                    "source": event.source,
                    "operation": event.operation,
                    "value": redact(event.value),
                }
                for event in definitions
            ]
            result.append(
                {
                    "key": display,
                    "value": redact(current.get(path)),
                    "source": definitions[-1].source,
                    "history": events,
                    "active": path in current,
                    "references": references.get(path[0], []),
                }
            )
        return result
