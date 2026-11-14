from . import parser as _cli_parser
from .commands import show_family_help
from .cron import ACTION_HANDLERS as CRON_HANDLERS
from .db import ACTION_HANDLERS as DB_HANDLERS
from .describe import ACTION_HANDLERS as DESCRIBE_HANDLERS
from .options import ACTION_HANDLERS as OPTIONS_HANDLERS
from .runtime import ACTION_HANDLERS as RUNTIME_HANDLERS
from .setup_info import ACTION_HANDLERS as SETUP_INFO_HANDLERS
from .shell import ACTION_HANDLERS as SHELL_HANDLERS
from .testing import ACTION_HANDLERS as TESTING_HANDLERS
from argcomplete import autocomplete
from argparse import ArgumentParser
from argparse import Namespace
from importlib.metadata import version
from itertools import chain
from pathlib import Path
from plonex import logger
from plonex.base import BaseService
from plonex.config import normalize_default_actions
from plonex.environment import load_project_environment
from plonex.services.edit import EditService
from plonex.services.init import InitService
from plonex.services.invocation import ServiceInvocation
from rich.console import Console
from typing import Callable

import logging
import sys


def build_parser(*, target: Path | None = None):
    # Preserve compatibility with tests and callers that patch
    # plonex.cli.autocomplete before invoking build_parser().
    _cli_parser.autocomplete = autocomplete
    return _cli_parser.build_parser(target=target)


def _prompt_init_target(default_target: Path | None = None) -> Path:
    default_path = default_target or Path.cwd()
    console = Console()
    try:
        response = console.input(
            f"Please select the target folder (default: {default_path}): "
        ).strip()
    except EOFError:
        response = ""
    return Path(response) if response else default_path


def _resolve_target(args) -> Path:
    """Resolve and validate the target folder from parsed args.

    Walks up from args.target looking for etc/plonex.yml.
    Calls sys.exit(1) on error.
    """
    target = Path(args.target)
    if not target.exists():
        logger.error("The target folder %r does not exist", args.target)
        sys.exit(1)

    for folder in chain([target], target.parents):
        if (folder / "etc" / "plonex.yml").exists():
            resolved = folder.resolve()
            logger.debug("Using target folder %r", str(resolved))
            return resolved

    logger.error(
        (
            "Could not find the `etc/plonex.yml` file please run `plonex "
            "project init %s` "
            "or specify a different target with the `--target` option."
        ),
        args.target,
    )
    sys.exit(1)


def _load_project_environment(target: Path) -> None:
    try:
        load_project_environment(target)
    except (OSError, ValueError) as exc:
        logger.error(str(exc))
        sys.exit(1)


def _configure_logging(args, target: Path) -> None:
    """Set the log level based on CLI flags and optional config-file setting."""
    BaseService.command_output_enabled = not args.quiet
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        return
    if args.quiet:
        logger.setLevel(logging.WARNING)
        logging.getLogger("sh").setLevel(logging.WARNING)
        return

    logging.getLogger("sh").setLevel(logging.WARNING)
    init = InitService(target=target)
    log_level = init.options.get("log_level")
    if log_level:
        log_level = log_level.upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            logger.error(
                (
                    "Invalid log level %r "
                    "in the configuration file. Accepted values are: %r"
                ),
                log_level,
                ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
            )
        else:
            logger.setLevel(log_level)


def _load_default_actions(target: Path) -> list[list[str]] | None:
    init = InitService(target=target)
    return normalize_default_actions(init.options)


_ACTION_HANDLERS: dict[str, Callable[[Namespace, ArgumentParser, Path], None]] = {
    **CRON_HANDLERS,
    **DB_HANDLERS,
    **DESCRIBE_HANDLERS,
    **OPTIONS_HANDLERS,
    **RUNTIME_HANDLERS,
    **SETUP_INFO_HANDLERS,
    **SHELL_HANDLERS,
    **TESTING_HANDLERS,
}


def _dispatch(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    if show_family_help(parser, args):
        return
    handler = _ACTION_HANDLERS.get(args.action)
    if handler is not None:
        handler(args, parser, target)
    else:
        parser.print_help()


def main() -> None:
    from contextlib import nullcontext
    from plonex.cli.aliases import split_command
    from plonex.files import read_only

    _, _, command = split_command(sys.argv[1:])
    inspecting = "--plan" in sys.argv[1:] or command[:2] in (
        ["project", "doctor"],
        ["project", "snapshot"],
        ["project", "inspect-legacy"],
        ["dependencies", "preview"],
    )
    with read_only() if inspecting else nullcontext():
        parser = build_parser()
        args = parser.parse_args()

    if args.version:
        print(version("plonex"))
        return

    if show_family_help(parser, args):
        return

    if args.action == "init":
        init_target = Path(args.target) if args.target else _prompt_init_target()
        _load_project_environment(init_target)
        with ServiceInvocation.from_args(args, init_target).create(InitService) as svc:
            svc.run()
        return

    if args.action == "edit":
        # Edit can run without a fully initialized project
        target = Path(args.target)
        if not target.exists():
            logger.error("The target folder %r does not exist", args.target)
            sys.exit(1)
        _load_project_environment(target)
        edit_service = ServiceInvocation.from_args(args, target).create(EditService)
        with edit_service:
            edit_service.run()
        return

    if args.action == "inspect_legacy":
        target = Path(args.target).expanduser().absolute()
        if not target.is_dir():
            raise SystemExit(f"Project directory does not exist: {target}")
        _ACTION_HANDLERS["inspect_legacy"](args, parser, target)
        return
    target = _resolve_target(args)
    if args.action == "shell":
        _ACTION_HANDLERS["shell"](args, parser, target)
        return
    _load_project_environment(target)
    if args.action not in {"doctor", "snapshot"} and not (
        args.action == "dependencies" and args.dependencies_action == "preview"
    ):
        with read_only() if getattr(args, "plan", False) else nullcontext():
            _configure_logging(args, target)
    if args.action:
        try:
            _dispatch(args, parser, target)
        except (FileNotFoundError, ValueError) as exc:
            logger.error(str(exc))
            sys.exit(1)
        return

    try:
        default_actions = _load_default_actions(target)
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    if not default_actions:
        parser.print_help()
        return

    for action_tokens in default_actions:
        default_args = parser.parse_args(
            action_tokens,
            namespace=Namespace(**vars(args)),
        )
        try:
            _dispatch(default_args, parser, target)
        except (FileNotFoundError, ValueError) as exc:
            logger.error(str(exc))
            sys.exit(1)


if __name__ == "__main__":
    main()
