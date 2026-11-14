"""Validated, explicit job declarations shared by CLI, reporting, and Huey."""

from dataclasses import dataclass
from dataclasses import field
from typing import Any
from zoneinfo import ZoneInfo

import json
import math
import re


@dataclass(frozen=True)
class Job:
    name: str
    schedule: str
    timezone: str = "UTC"
    enabled: bool = True
    command: tuple[str, ...] = ()
    callable: str = ""
    site: str = "/Plone"
    vhm: str = ""
    context: str = ""
    user: str = ""
    runtime: str = "cron"
    kwargs: dict[str, Any] = field(default_factory=dict)
    timeout: float = 3600
    lock: str = ""
    lock_timeout: float = 0
    retries: int = 0
    retry_delay: int = 60
    environment: dict[str, str] = field(default_factory=dict)

    def validate_schedule(self):
        """Validate Huey's numeric cron grammar without importing the worker."""
        for index, (value, lower, upper) in enumerate(
            zip(self.schedule.split(), (0, 0, 1, 1, 0), (59, 23, 31, 12, 7))
        ):
            for piece in value.split(","):
                if piece == "*":
                    continue
                if piece.isdigit() and lower <= int(piece) <= upper:
                    continue
                interval = re.fullmatch(r"\*/(\d+)", piece)
                if interval and int(interval[1]) > 0 and index != 4:
                    continue
                span = re.fullmatch(r"(\d+)-(\d+)(?:/(\d+))?", piece)
                if (
                    span
                    and lower <= int(span[1]) <= upper
                    and lower <= int(span[2]) <= upper
                    and int(span[3] or 1) > 0
                ):
                    continue
                raise ValueError(f"Invalid cron field: {piece!r}")
        ZoneInfo(self.timezone)

    def matcher(self):
        from datetime import timezone

        try:
            from huey import crontab  # type: ignore[import-untyped]
        except ImportError as error:
            raise ValueError(
                (
                    "The project jobs runtime requires Huey. "
                    "Run 'plonex dependencies install'."
                )
            ) from error

        match = crontab(*self.schedule.split(), strict=True)
        zone = ZoneInfo(self.timezone)

        def matches(timestamp):
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return match(timestamp.astimezone(zone))

        return matches


@dataclass(frozen=True)
class JobSet:
    jobs: tuple[Job, ...] = ()

    @classmethod
    def from_options(cls, options: dict) -> "JobSet":
        declarations = options.get("cron_jobs", {})
        if declarations is None:
            declarations = {}
        if not isinstance(declarations, dict):
            raise ValueError("cron_jobs must be a mapping of job names to declarations")
        result = []
        allowed = set(Job.__dataclass_fields__) - {"name"}
        for name, raw in declarations.items():
            if not isinstance(name, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]*", name
            ):
                raise ValueError(f"Invalid cron job name: {name!r}")
            if not isinstance(raw, dict):
                raise ValueError(f"Cron job {name!r} must be a mapping")
            unknown = set(raw) - allowed
            if unknown:
                raise ValueError(
                    f"Cron job {name!r}: unknown options {sorted(unknown)}"
                )
            values = dict(raw)
            schedule = values.get("schedule")
            if not isinstance(schedule, str) or len(schedule.split()) != 5:
                raise ValueError(
                    f"Cron job {name!r}: schedule must have five cron fields"
                )
            command = values.get("command", ())
            if "command" in values and (
                not isinstance(command, list)
                or not command
                or not all(isinstance(part, str) and part for part in command)
            ):
                raise ValueError(
                    f"Cron job {name!r}: command must be a non-empty argv list"
                )
            values["command"] = tuple(command)
            function = values.get("callable", "")
            if "callable" in values and (not isinstance(function, str) or not function):
                raise ValueError(f"Cron job {name!r}: callable must be module:function")
            if bool(command) == bool(function):
                raise ValueError(
                    f"Cron job {name!r}: choose exactly one of command or callable"
                )
            if function and not re.fullmatch(
                r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*",
                function,
            ):
                raise ValueError(f"Cron job {name!r}: callable must be module:function")
            if function and not values.get("user"):
                raise ValueError(f"Cron job {name!r}: a named Plone user is required")
            for key in (
                "site",
                "vhm",
                "context",
                "user",
                "runtime",
                "timezone",
                "lock",
            ):
                if key in values and not isinstance(values[key], str):
                    raise ValueError(f"Cron job {name!r}: {key} must be a string")
            if values.get("vhm"):
                parts = values["vhm"].split("/")
                if (
                    not function
                    or len(parts) < 4
                    or parts[:2] != ["", "VirtualHostBase"]
                    or parts[2] not in {"http", "https"}
                    or not parts[3]
                ):
                    raise ValueError(
                        f"Cron job {name!r}: vhm requires a callable and an absolute "
                        "VirtualHostBase path with protocol and host"
                    )
            if "enabled" in values and not isinstance(values["enabled"], bool):
                raise ValueError(f"Cron job {name!r}: enabled must be a boolean")
            for key in ("timeout", "lock_timeout", "retries", "retry_delay"):
                if key in values:
                    value = values[key]
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise ValueError(
                            f"Cron job {name!r}: {key} must be non-negative"
                        )
                    if key in ("retries", "retry_delay") and not isinstance(value, int):
                        raise ValueError(f"Cron job {name!r}: {key} must be an integer")
            if values.get("timeout", 3600) <= 0:
                raise ValueError(f"Cron job {name!r}: timeout must be positive")
            environment = values.get("environment", {})
            if not isinstance(environment, dict) or not all(
                isinstance(key, str)
                and bool(key)
                and isinstance(value, str)
                and "=" not in key
                and "\0" not in key
                and "\0" not in value
                for key, value in environment.items()
            ):
                raise ValueError(
                    f"Cron job {name!r}: environment must map names to strings"
                )
            if not isinstance(values.get("kwargs", {}), dict):
                raise ValueError(f"Cron job {name!r}: kwargs must be a mapping")
            if not all(isinstance(key, str) for key in values.get("kwargs", {})):
                raise ValueError(f"Cron job {name!r}: kwargs keys must be strings")
            try:
                json.dumps(values.get("kwargs", {}), allow_nan=False)
            except (ValueError, TypeError) as error:
                raise ValueError(
                    f"Cron job {name!r}: kwargs must be JSON serializable"
                ) from error
            values.setdefault("timezone", options.get("cron_timezone", "UTC"))
            if not isinstance(values["timezone"], str):
                raise ValueError(f"Cron job {name!r}: timezone must be an IANA name")
            if not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.-]*", values.get("runtime", "cron")
            ):
                raise ValueError(f"Cron job {name!r}: invalid runtime name")
            values.setdefault("lock", "plone" if function else name)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", values["lock"]):
                raise ValueError(f"Cron job {name!r}: invalid lock name")
            job = Job(name=name, **values)
            try:
                job.validate_schedule()
            except (ValueError, KeyError, ZeroDivisionError) as error:
                raise ValueError(
                    f"Cron job {name!r}: invalid schedule or timezone: {error}"
                ) from error
            result.append(job)
        return cls(tuple(result))

    def get(self, name: str) -> Job:
        for job in self.jobs:
            if job.name == name:
                return job
        raise ValueError(f"Unknown cron job {name!r}. Use 'plonex cron list'.")
