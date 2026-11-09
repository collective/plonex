"""Bind CLI arguments to the existing service dataclasses in one place."""

from argparse import Namespace
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from pathlib import Path
from plonex.base import BaseService
from plonex.services.registry import service_registry
from typing import Any


@dataclass(frozen=True)
class ServiceInvocation:
    command: str
    target: Path
    kwargs: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_args(cls, args: Namespace, target: Path) -> "ServiceInvocation":
        command = args.action
        service_registry.get(command)
        kwargs: dict[str, Any] = {"target": target}
        if command in {"runwsgi", "fg", "zconsole", "adduser"}:
            kwargs["config_files"] = getattr(args, "runtime_config", None) or []
            kwargs["cli_options"] = {}
            if command != "adduser":
                kwargs["name"] = args.name
                if args.host:
                    kwargs["cli_options"]["http_address"] = args.host
                if args.port:
                    kwargs["cli_options"]["http_port"] = args.port
                kwargs["args"] = getattr(args, "args", None) or []
        if command == "fg":
            debugpy_port = getattr(args, "debugpy", None)
            wait = getattr(args, "wait_for_debugger", False)
            if debugpy_port is not None and not 1 <= debugpy_port <= 65535:
                raise ValueError("debugpy port must be between 1 and 65535")
            if wait and debugpy_port is None:
                raise ValueError("--wait-for-debugger requires --debugpy PORT")
            if debugpy_port is not None:
                kwargs["cli_options"].update(
                    debugpy_port=debugpy_port, debugpy_wait=wait
                )
            kwargs["cli_options"].update(
                debug_mode="on",
                verbose_security="on",
                security_policy_implementation="python",
            )
        if command == "zconsole":
            kwargs["action"] = getattr(args, "zconsole_action", None) or "debug"
        if command == "run":
            kwargs.update(action="run", args=args.args or [])
        if command == "adduser":
            kwargs.update(username=args.username, password=args.password)
        if command == "describe":
            kwargs.update(
                browse_html=bool(args.describe_browse),
                output_format=getattr(args, "describe_format", None) or "terminal",
                section=getattr(args, "describe_section", None) or "all",
                key=getattr(args, "key", None) or "",
                inspect_command=getattr(args, "inspect_command", None) or [],
            )
        if command == "cron":
            kwargs["config_files"] = getattr(args, "cron_config", None) or []
        if command == "upgrade" and getattr(args, "upgrade_url", None):
            kwargs["cli_options"] = {"upgrade_url": args.upgrade_url}
        if command == "robotserver":
            kwargs["layer"] = args.layer
        if command == "robottest":
            kwargs.update(paths=args.paths, browser=args.browser, test=args.test)
        if command == "zopetest":
            kwargs.update(package=args.package, test=args.test)
        if command == "pytest":
            kwargs.update(package=args.package, args=args.pytest_args)
        if command == "edit":
            kwargs["open_all"] = args.open_all
            kwargs["cli_options"] = {"editor": args.editor} if args.editor else {}
        parameters = {
            key: value
            for key, value in vars(args).items()
            if key not in {"target", "action"}
        }
        return cls(command, target, kwargs, parameters)

    @property
    def service_type(self) -> type[BaseService]:
        return service_registry.get(self.command)

    @property
    def name(self) -> str:
        default = next(
            item.default for item in fields(self.service_type) if item.name == "name"
        )
        return str(self.kwargs.get("name", default))

    def create(self, service_type=None) -> BaseService:
        """An override preserves existing CLI mock and extension points."""
        service = (service_type or self.service_type)(**self.kwargs)
        service._invocation_parameters = self.parameters
        return service

    def snapshot_environment(self, path: Path) -> dict[str, str]:
        service_type = self.service_type
        identity = f"{service_type.__module__}.{service_type.__qualname__}"
        return {
            "PLONEX_JOB_SNAPSHOT": str(path),
            "PLONEX_JOB_SERVICE": identity,
            "PLONEX_JOB_NAME": self.name,
        }
