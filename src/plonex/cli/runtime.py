from argparse import ArgumentParser
from argparse import Namespace
from pathlib import Path
from plonex import logger
from plonex.cli.dependencies import _run_service_dependencies
from plonex.services.adduser import AddUser
from plonex.services.invocation import ServiceInvocation
from plonex.services.robotserver import RobotServer
from plonex.services.runwsgi import RunWSGI
from plonex.services.supervisor import Supervisor
from plonex.services.upgrade import UpgradeService
from plonex.services.zconsole import ZConsole
from plonex.services.zeoserver import ZeoServer
from rich.console import Console
from typing import cast


def register_runtime_parsers(subs, add_subparser) -> None:
    """Register runtime-related CLI parsers."""

    def add_runtime_options(parser, *, default_name: str):
        parser.add_argument(
            "-n",
            "--name",
            type=str,
            help="Name of the runtime service",
            required=False,
            default=default_name,
        )
        parser.add_argument(
            "-c",
            "--config",
            type=str,
            help="Path to the configuration file",
            required=False,
            dest="runtime_config",
            action="append",
        )
        parser.add_argument(
            "-p",
            "--port",
            type=int,
            help="HTTP port override (default from config)",
            required=False,
            default=0,
        )
        parser.add_argument(
            "--host",
            type=str,
            help="HTTP host override (default from config)",
            required=False,
            default="",
        )

    supervisor_parser = add_subparser(subs, "supervisor", help="Manage supervisor")
    supervisor_subs = supervisor_parser.add_subparsers(
        dest="supervisor_action", help="Supervisor actions"
    )
    add_subparser(
        supervisor_subs,
        "status",
        help="Status of supervisor",
    )
    start_parser = add_subparser(
        supervisor_subs, "start", help="Prepare and start supervisor"
    )
    start_parser.add_argument(
        "--plan", action="store_true", help="Explain preparation without executing it"
    )
    add_subparser(supervisor_subs, "stop", help="Stop supervisor")
    restart = add_subparser(supervisor_subs, "restart", help="Restart managed programs")
    restart.add_argument(
        "programs", nargs="*", help="Programs to restart (default: all)"
    )
    add_subparser(
        supervisor_subs, "reread", help="Reread Supervisor program declarations"
    )
    add_subparser(supervisor_subs, "update", help="Apply changed Supervisor programs")
    graceful_parser = add_subparser(
        supervisor_subs,
        "graceful",
        help="Graceful restart of supervisor",
    )
    graceful_parser.add_argument(
        "--interval",
        type=float,
        help="Seconds to wait between restarting services",
        required=False,
        default=None,
        dest="graceful_interval",
    )

    add_subparser(subs, "zeoserver", help="Start ZEO Server")

    runwsgi_parser = add_subparser(subs, "runwsgi", help="Start runwsgi")
    add_runtime_options(runwsgi_parser, default_name="runwsgi")
    runwsgi_parser.add_argument(
        "args",
        nargs="*",
        help="Arguments to pass to runwsgi",
    )

    zconsole_parser = add_subparser(subs, "zconsole", help="Run zconsole commands")
    add_runtime_options(zconsole_parser, default_name="zconsole")

    fg_parser = add_subparser(
        subs,
        "fg",
        help="Start runwsgi in foreground debug mode",
    )
    add_runtime_options(fg_parser, default_name="fg")
    fg_parser.add_argument(
        "--debugpy",
        type=int,
        metavar="PORT",
        help="Listen for a debugpy client on 127.0.0.1:PORT",
    )
    fg_parser.add_argument(
        "--wait-for-debugger",
        action="store_true",
        help="Wait for the debugpy client before starting the instance",
    )
    fg_parser.add_argument(
        "args",
        nargs="*",
        help="Arguments to pass to runwsgi",
    )

    run_parser = add_subparser(subs, "run", help="Run an instance script")
    run_parser.add_argument(
        "args",
        nargs="*",
        help="Arguments to pass to the script",
    )

    adduser_parser = add_subparser(
        subs,
        "adduser",
        help=(
            "Add a user. You need to provide at least a username, optionally a password"
        ),
    )
    adduser_parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Path to the configuration file",
        required=False,
        dest="runtime_config",
        action="append",
    )
    adduser_parser.add_argument("username", type=str, help="Username")
    adduser_parser.add_argument("password", type=str, help="Password", nargs="?")


def _handle_robotserver(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "robotserver")
    with ServiceInvocation.from_args(args, target).create(RobotServer) as svc:
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


def _handle_upgrade(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "upgrade")
    with ServiceInvocation.from_args(args, target).create(UpgradeService) as svc:
        svc.run()


ACTION_HANDLERS = {
    "robotserver": _handle_robotserver,
    "zeoserver": _handle_zeoserver,
    "runwsgi": _handle_runwsgi,
    "fg": _handle_fg,
    "zconsole": _handle_zconsole,
    "run": _handle_run,
    "adduser": _handle_adduser,
    "supervisor": _handle_supervisor,
    "upgrade": _handle_upgrade,
}
