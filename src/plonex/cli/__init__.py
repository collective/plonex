from . import parser as _cli_parser
from .commands import show_family_help
from .dependencies import _run_service_dependencies
from .shell import run_shell
from argcomplete import autocomplete
from argparse import ArgumentParser
from argparse import Namespace
from importlib.metadata import version
from itertools import chain
from pathlib import Path
from plonex import logger
from plonex.base import BaseService
from plonex.config import normalize_default_actions
from plonex.services.adduser import AddUser
from plonex.services.compile import CompileService
from plonex.services.cron import CronService
from plonex.services.describe import DescribeService
from plonex.services.edit import EditService
from plonex.services.init import InitService
from plonex.services.install import InstallService
from plonex.services.invocation import ServiceInvocation
from plonex.services.pytest import PytestService
from plonex.services.robotserver import RobotServer
from plonex.services.robottest import RobotTest
from plonex.services.runwsgi import RunWSGI
from plonex.services.sources import SourcesService
from plonex.services.supervisor import Supervisor
from plonex.services.upgrade import UpgradeService
from plonex.services.zconsole import ZConsole
from plonex.services.zeoserver import ZeoServer
from plonex.services.zopetest import ZopeTest
from rich.console import Console
from typing import Callable
from typing import cast

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


def _handle_shell(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    run_shell(target=target, verbose=args.verbose, quiet=args.quiet)


def _handle_options(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.inspection import ServiceSnapshot

    tokens = args.service_command or []
    if not tokens:
        raise ValueError("Usage: plonex options [--markdown] COMMAND [arguments]")
    service_args = parser.parse_args(
        tokens,
        namespace=Namespace(target=target, verbose=args.verbose, quiet=args.quiet),
    )
    service_target = _resolve_target(service_args)
    invocation = ServiceInvocation.from_args(service_args, service_target)
    service = invocation.create()
    ServiceSnapshot.capture(service, parameters=invocation.parameters).show(
        markdown=args.markdown
    )


def _handle_compile(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "compile")
    with ServiceInvocation.from_args(args, target).create(CompileService) as svc:
        svc.run()


def _handle_describe(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    with ServiceInvocation.from_args(args, target).create(DescribeService) as svc:
        svc.run()


def _handle_doctor(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.files import read_only
    from plonex.services.doctor import Doctor

    with read_only():
        service = ServiceInvocation.from_args(args, target).create(Doctor)
        result = service.run(output_format=args.doctor_format)
    if result["summary"]["error"] or (args.strict and result["summary"]["warning"]):
        raise SystemExit(1)


def _handle_snapshot(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.inspection import safe_value
    from plonex.services.snapshot import capture
    from plonex.services.snapshot import differences
    from plonex.services.snapshot import load
    from plonex.services.snapshot import prepare
    from plonex.services.snapshot import write_new

    import json

    if not args.snapshot_action:
        raise ValueError(
            "Use 'plonex project snapshot create', 'compare', or 'prepare'."
        )
    if args.snapshot_action == "prepare":
        path = prepare(target, load(args.file), args.to, python=args.python)
        Console().print(f"Prepared environment: {path}", markup=False)
        return
    snapshot = capture(target)
    if args.snapshot_action == "create":
        if args.output:
            Console().print(f"Saved snapshot: {write_new(args.output, snapshot)}")
        else:
            Console().print(
                json.dumps(snapshot, indent=2), markup=False, soft_wrap=True
            )
        return
    changes = safe_value(differences(load(args.file), snapshot))
    if args.snapshot_format == "json":
        Console().print(
            json.dumps({"differences": changes}, indent=2), markup=False, soft_wrap=True
        )
    elif changes:
        for change in changes:
            before = json.dumps(change["before"], ensure_ascii=False)
            after = json.dumps(change["after"], ensure_ascii=False)
            Console().print(
                f"{change['change']}: {change['path']} — {before} → {after}",
                markup=False,
            )
    else:
        Console().print("Project matches the snapshot.")
    if changes:
        raise SystemExit(1)


def _handle_inspect_legacy(
    args: Namespace, parser: ArgumentParser, target: Path
) -> None:
    from plonex.services.legacy import inspect_project

    import json

    report = inspect_project(target)
    if args.legacy_format == "json":
        Console().print(json.dumps(report, indent=2), markup=False, soft_wrap=True)
    else:
        for item in report["findings"]:
            Console().print(f"{item['kind']}: {item['summary']}", markup=False)
            if item.get("suggestion"):
                Console().print(f"  {item['suggestion']}", markup=False)
        for note in report["notes"]:
            Console().print(note, markup=False)
    if any(item.get("severity") == "error" for item in report["findings"]):
        raise SystemExit(1)


def _handle_cron(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    if args.cron_action in {"run", "daemon", "configure"}:
        _run_service_dependencies(target, "cron")
    with ServiceInvocation.from_args(args, target).create(CronService) as svc:
        action = args.cron_action
        if action == "list":
            svc.run_list()
        elif action == "run":
            svc.run_job(args.job)
        elif action == "enqueue":
            svc.enqueue(args.job)
        elif action == "history":
            svc.run_history(args.job, args.limit, output_format=args.history_format)
        elif action == "logs":
            svc.run_logs(args.job, args.tail)
        elif action == "daemon":
            svc.run_daemon(args.workers)
        elif action in {"status", "queue", "inspect", "retry", "revoke", "restore"}:
            svc.show_queue(
                action,
                getattr(args, "task_id", ""),
                limit=args.limit,
                output_format=args.queue_format,
            )
        elif action == "configure":
            folder = target / "tmp" / "supervisor" / "etc" / "supervisor"
            svc.configure_supervisor(folder)
            path = folder / "plonex-cron.conf"
            Console().print(
                (
                    str(path)
                    if path.exists()
                    else "No project jobs; no cron program configured."
                ),
                markup=False,
            )


def _handle_robotserver(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "robotserver")
    with ServiceInvocation.from_args(args, target).create(RobotServer) as svc:
        svc.run()


def _handle_pytest(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "pytest")
    with ServiceInvocation.from_args(args, target).create(PytestService) as svc:
        svc.run()


def _handle_test_sources(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.services.sources.testing import run_selected_tests

    result = run_selected_tests(target, args.source_args)
    if result:
        raise SystemExit(result if result > 0 else 1)


def _handle_robottest(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "robottest")
    with ServiceInvocation.from_args(args, target).create(RobotTest) as svc:
        svc.run()


def _handle_zopetest(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "zopetest")
    with ServiceInvocation.from_args(args, target).create(ZopeTest) as svc:
        svc.run()


def _handle_zeoserver(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "zeoserver")
    logger.debug("Starting ZEO Server")
    with ServiceInvocation.from_args(args, target).create(ZeoServer) as svc:
        svc.run()


def _handle_runwsgi(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "runwsgi")
    logger.debug("Starting runwsgi")
    with ServiceInvocation.from_args(args, target).create(RunWSGI) as svc:
        svc.run()


def _handle_fg(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "fg")
    logger.debug("Starting foreground instance (debug mode)")
    with ServiceInvocation.from_args(args, target).create(RunWSGI) as svc:
        svc.run()


def _handle_zconsole(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "zconsole")
    with ServiceInvocation.from_args(args, target).create(ZConsole) as svc:
        svc.run()


def _handle_run(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "run")
    with ServiceInvocation.from_args(args, target).create(ZConsole) as svc:
        svc.run()


def _handle_adduser(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "adduser")
    with ServiceInvocation.from_args(args, target).create(AddUser) as svc:
        svc.run()


def _handle_supervisor(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.files import read_only

    supervisor_action = getattr(args, "supervisor_action", None) or "status"
    if supervisor_action == "start":
        from plonex.preparation.supervisor import SupervisorPreparation

        preparation = SupervisorPreparation(target)
        if getattr(args, "plan", False):
            preparation.show_plan()
            return
        preparation.run()
    elif supervisor_action not in {"status", "stop"}:
        _run_service_dependencies(target, "supervisor")
    with read_only():
        service = cast(
            Supervisor, ServiceInvocation.from_args(args, target).create(Supervisor)
        )
    if supervisor_action in {"start", "status", "stop"}:
        service.pre_services = []
        service._render_configuration = False
    with service as svc:
        if supervisor_action == "start":
            was_running = svc.is_running()
            svc.run()
            if was_running and preparation.graph.changed:
                Console().print(
                    "Prepared changes affect: "
                    + ", ".join(sorted(preparation.graph.changed))
                    + ". Restart affected running programs explicitly to load them.",
                    markup=False,
                )
        elif supervisor_action == "stop":
            svc.run_stop()
        elif supervisor_action == "restart":
            if args.programs:
                svc.run_restart(args.programs)
            else:
                svc.run_restart()
        elif supervisor_action == "status":
            svc.run_status()
        elif supervisor_action == "graceful":
            interval = getattr(args, "graceful_interval", None)
            svc.run_graceful(
                delay=svc.graceful_interval if interval is None else interval
            )
        elif supervisor_action == "reread":
            svc.run_reread()
        elif supervisor_action == "update":
            svc.run_update()


def _handle_db(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    db_action = getattr(args, "db_action", None)
    if db_action in {"backup", "restore"}:
        from plonex.files import read_only

        # Do not create missing storage directories or run mutating hooks before
        # backup validation; an absent blob directory must remain an error.
        with read_only():
            svc = cast(
                ZeoServer, ServiceInvocation.from_args(args, target).create(ZeoServer)
            )
            svc.options
        if db_action == "backup":
            path = svc.run_backup()
        else:
            path = svc.run_restore(
                destination=args.restore_destination, backup=args.restore_backup
            )
        Console().print(str(path), markup=False)
    elif db_action == "pack":
        _run_service_dependencies(target, "db")
        with ServiceInvocation.from_args(args, target).create(ZeoServer) as svc:
            svc.run_pack(days=args.days)
    else:
        parser.print_help()


def _handle_dependencies(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    if getattr(args, "dependencies_action", None) == "preview":
        from plonex.services.install.preview import preview_dependencies

        result = preview_dependencies(
            target, online=args.online, output_format=args.preview_format
        )
        if not result["resolved"]:
            raise SystemExit(1)
        return
    _run_service_dependencies(target, "dependencies")
    persist_mode = getattr(args, "persist_mode", None)
    with ServiceInvocation.from_args(args, target).create(InstallService) as svc:
        if getattr(args, "show_outdated", False):
            svc.run_show_outdated()
        else:
            svc.run(
                persist=persist_mode == "project",
                persist_local=persist_mode == "local",
                persist_profile=persist_mode == "profile",
                update_sources=getattr(args, "update_sources", None),
                sync=getattr(args, "sync", False),
            )


def _handle_sources(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "sources")
    sources_action = getattr(args, "sources_action", None) or "update"
    glob_pattern = getattr(args, "glob", None)
    with ServiceInvocation.from_args(args, target).create(SourcesService) as svc:
        if sources_action == "update":
            if getattr(args, "sources_force", False):
                svc.run_update(
                    force=True,
                    assume_yes=getattr(args, "sources_yes", False),
                    glob=glob_pattern,
                )
            else:
                svc.run_update(glob=glob_pattern)
        elif sources_action == "list":
            svc.run_list(glob=glob_pattern)
        elif sources_action == "missing":
            svc.run_show_missing(glob=glob_pattern)
        elif sources_action == "clone":
            svc.run_clone_missing(
                assume_yes=getattr(args, "sources_yes", False), glob=glob_pattern
            )
        elif sources_action == "tainted":
            svc.run_show_tainted(glob=glob_pattern)
        elif sources_action == "suggest":
            svc.run_suggest_existing(
                apply=getattr(args, "sources_apply", False),
                apply_local=getattr(args, "sources_apply_local", False),
                apply_profile=getattr(args, "sources_apply_profile", False),
            )
        else:
            parser.print_help()


def _handle_install(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "install")
    with ServiceInvocation.from_args(args, target).create(InstallService) as svc:
        svc.add_packages(args.package)
    with ServiceInvocation.from_args(args, target).create(InstallService) as svc:
        if getattr(args, "dependencies_action", None) == "add":
            persist_mode = getattr(args, "persist_mode", None)
            svc.run(
                persist=persist_mode == "project",
                persist_local=persist_mode == "local",
                persist_profile=persist_mode == "profile",
                update_sources=getattr(args, "update_sources", None),
                sync=False,
            )
        else:
            svc.run()


def _handle_upgrade(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "upgrade")
    with ServiceInvocation.from_args(args, target).create(UpgradeService) as svc:
        svc.run()


_ACTION_HANDLERS: dict[str, Callable[[Namespace, ArgumentParser, Path], None]] = {
    "options": _handle_options,
    "pytest": _handle_pytest,
    "test_sources": _handle_test_sources,
    "shell": _handle_shell,
    "compile": _handle_compile,
    "describe": _handle_describe,
    "doctor": _handle_doctor,
    "snapshot": _handle_snapshot,
    "inspect_legacy": _handle_inspect_legacy,
    "cron": _handle_cron,
    "robotserver": _handle_robotserver,
    "robottest": _handle_robottest,
    "zopetest": _handle_zopetest,
    "zeoserver": _handle_zeoserver,
    "runwsgi": _handle_runwsgi,
    "fg": _handle_fg,
    "zconsole": _handle_zconsole,
    "run": _handle_run,
    "adduser": _handle_adduser,
    "supervisor": _handle_supervisor,
    "db": _handle_db,
    "dependencies": _handle_dependencies,
    "sources": _handle_sources,
    "install": _handle_install,
    "upgrade": _handle_upgrade,
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
        with ServiceInvocation.from_args(args, init_target).create(InitService) as svc:
            svc.run()
        return

    if args.action == "edit":
        # Edit can run without a fully initialized project
        target = Path(args.target)
        if not target.exists():
            logger.error("The target folder %r does not exist", args.target)
            sys.exit(1)
        edit_service = ServiceInvocation.from_args(args, target).create(EditService)
        with edit_service:
            edit_service.run()
        return

    if args.action == "inspect_legacy":
        target = Path(args.target).expanduser().absolute()
        if not target.is_dir():
            raise SystemExit(f"Project directory does not exist: {target}")
        _handle_inspect_legacy(args, parser, target)
        return
    target = _resolve_target(args)
    if args.action == "shell":
        _handle_shell(args, parser, target)
        return
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
