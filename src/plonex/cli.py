from argcomplete import autocomplete
from argparse import ArgumentParser
from importlib.metadata import version
from itertools import chain
from pathlib import Path
from plonex import logger
from plonex.compile import CompileService
from plonex.describe import DescribeService
from plonex.init import InitService
from plonex.install import InstallService
from plonex.robotserver import RobotServer
from plonex.robottest import RobotTest
from plonex.supervisor import Supervisor
from plonex.test import TestService
from plonex.upgrade import UpgradeService
from plonex.zeoclient import ZeoClient
from plonex.zeoserver import ZeoServer
from plonex.zopetest import ZopeTest
from rich_argparse import RawTextRichHelpFormatter
from textwrap import dedent

import logging
import os
import sys


def _group_subcommands_for_help(subs, groups: dict[str, list[str]]) -> None:
    """Reorder subcommand help entries and inject category headers."""
    choices_by_name = {action.dest: action for action in subs._choices_actions}
    grouped = []
    for title, names in groups.items():
        grouped.append(subs._ChoicesPseudoAction(f"\n{title}", [], ""))
        for name in names:
            action = choices_by_name.get(name)
            if action is not None:
                grouped.append(action)
    subs._choices_actions = grouped


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description=dedent(
            """\
            Plone Deployment CLI.

            Activate autocomplete with:

            eval "$(register-python-argcomplete plonex)"
            """
        ),
        prog="plonex",
        usage="%(prog)s [options]",
        formatter_class=RawTextRichHelpFormatter,
    )
    fmt = parser.formatter_class

    parser.add_argument(
        "-t",
        "--target",
        type=str,
        help="Path to the target folder",
        required=False,
        default=Path.cwd(),
        dest="target",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase verbosity",
        required=False,
        default=False,
        dest="verbose",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Decrease verbosity",
        required=False,
        default=False,
        dest="quiet",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Show the version of the package",
        required=False,
        default=False,
        dest="version",
    )

    subs = parser.add_subparsers(dest="action", title="Positional Arguments")

    # --- init ---
    init_parser = subs.add_parser(
        "init",
        description=(
            "Initialize the project in the specified target folder. "
            "This will create the necessary folders and configuration files."
        ),
        help="Initialize the project in the specified target folder.",
        formatter_class=fmt,
    )
    init_parser.add_argument(
        "target",
        type=str,
        help=(
            "Path where the project will be initialized. "
            "Defaults to the current working directory."
        ),
        default=str(Path.cwd()),
        nargs="?",
    )

    # --- compile ---
    subs.add_parser(
        "compile",
        description=(
            "Compile the configuration files in to var files. "
            "This will read the configuration files "
            "and generate the necessary var files."
        ),
        help="Compile the configuration files in to var files",
        formatter_class=fmt,
    )

    # --- describe ---
    subs.add_parser(
        "describe",
        help="Describe the current project configuration",
        formatter_class=fmt,
    )

    # --- robotserver ---
    robotserver_parser = subs.add_parser(
        "robotserver",
        help="Start the Robot Server",
        formatter_class=fmt,
    )
    robotserver_parser.add_argument(
        "-l",
        "--layer",
        type=str,
        help="Testing layer to use",
        required=False,
        default="Products.CMFPlone.testing.PRODUCTS_CMFPLONE_ROBOT_TESTING",
        dest="layer",
    )

    # --- robottest ---
    robottest_parser = subs.add_parser(
        "robottest",
        help="Run Robot Tests",
        formatter_class=fmt,
    )
    robottest_parser.add_argument(
        "paths",
        type=str,
        help="Paths to the Robot Test files",
        nargs="+",
    )
    robottest_parser.add_argument(
        "-b",
        "--browser",
        type=str,
        help="Browser to use for the tests (default: firefox)",
        required=False,
        default="firefox",
        dest="browser",
    )
    robottest_parser.add_argument(
        "-t",
        "--test",
        type=str,
        help="Name of the test(s) to run. It supports regular expressions.",
        required=False,
        default="",
        dest="test",
    )

    # --- zopetest ---
    zopetest_parser = subs.add_parser(
        "zopetest",
        help="Run Zope Tests",
        formatter_class=fmt,
    )
    zopetest_parser.add_argument(
        "package",
        type=str,
        help="Package to test",
    )
    zopetest_parser.add_argument(
        "-t",
        "--test",
        type=str,
        help="Name of the test(s) to run. It supports regular expressions.",
        required=False,
        default="",
        dest="test",
    )

    # --- install ---
    install_parser = subs.add_parser(
        "install",
        help="Add one or more packages to your requirements and install them",
        formatter_class=fmt,
    )
    install_parser.add_argument(
        "package",
        type=str,
        help="Packages to install",
        nargs="+",
    )

    # --- upgrade ---
    subs.add_parser(
        "upgrade",
        help="Run Plone upgrade steps",
        formatter_class=fmt,
    )

    # --- supervisor ---
    supervisor_parser = subs.add_parser(
        "supervisor", help="Manage supervisor", formatter_class=fmt
    )
    supervisor_subs = supervisor_parser.add_subparsers(
        dest="supervisor_action", help="Supervisor actions"
    )
    supervisor_subs.add_parser(
        "status", help="Status of supervisor (default)", formatter_class=fmt
    )
    supervisor_subs.add_parser("start", help="Start supervisor", formatter_class=fmt)
    supervisor_subs.add_parser("stop", help="Stop supervisor", formatter_class=fmt)
    supervisor_subs.add_parser(
        "restart", help="Restart supervisor", formatter_class=fmt
    )
    supervisor_subs.add_parser(
        "graceful", help="Graceful restart of supervisor", formatter_class=fmt
    )

    # --- zeoserver ---
    subs.add_parser("zeoserver", help="Start ZEO Server", formatter_class=fmt)

    # --- zeoclient ---
    zeoclient_parser = subs.add_parser(
        "zeoclient", help="Start ZEO Client", formatter_class=fmt
    )
    zeoclient_parser.add_argument(
        "-n",
        "--name",
        type=str,
        help="Name of the ZEO Client",
        required=False,
        default="zeoclient",
    )
    zeoclient_parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Path to the configuration file",
        required=False,
        dest="zeoclient_config",
        action="append",
    )
    zeoclient_parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="Port to run the ZEO Client (default: 8080)",
        required=False,
        default=0,
    )
    zeoclient_parser.add_argument(
        "--host",
        type=str,
        help="Host to run the ZEO Client (default: 0.0.0.0)",
        required=False,
        default="",
    )
    zeoclient_subs = zeoclient_parser.add_subparsers(
        dest="zeoclient_action", help="ZEO Client actions"
    )
    zeoclient_subs.add_parser(
        "console", help="Start the ZEO Client console (default behavior)"
    )
    zeoclient_subs.add_parser("fg", help="Start the ZEO Client in foreground")
    zeoclient_subs.add_parser("start", help="Start the ZEO Client in background")
    zeoclient_subs.add_parser("stop", help="Stop the ZEO Client in background")
    zeoclient_subs.add_parser("status", help="Status of the ZEO Client in background")
    zeoclient_subs.add_parser("debug", help="Start the ZEO Client in debug mode")

    # --- run ---
    run_parser = subs.add_parser(
        "run", help="Run an instance script", formatter_class=fmt
    )
    run_parser.add_argument(
        "args",
        nargs="*",
        help="Arguments to pass to the script",
    )

    # --- adduser ---
    adduser_parser = subs.add_parser(
        "adduser",
        help=(
            "Add a user. You need to provide at least a username, optionally a password"
        ),
        formatter_class=fmt,
    )
    adduser_parser.add_argument(
        "-c",
        "--config",
        type=str,
        help="Path to the configuration file",
        required=False,
        dest="zeoclient_config",
        action="append",
    )
    adduser_parser.add_argument("username", type=str, help="Username")
    adduser_parser.add_argument("password", type=str, help="Password", nargs="?")

    # --- db (backup / restore / pack) ---
    db_parser = subs.add_parser(
        "db",
        help="Database management commands (backup/restore/pack)",
        formatter_class=fmt,
    )
    db_subs = db_parser.add_subparsers(dest="db_action", help="Database actions")
    db_subs.add_parser("backup", help="Backup the services", formatter_class=fmt)
    db_subs.add_parser("restore", help="Restore the services", formatter_class=fmt)
    db_pack_parser = db_subs.add_parser("pack", help="Pack the DB", formatter_class=fmt)
    db_pack_parser.add_argument(
        "-d",
        "--days",
        type=int,
        help="Number of days to pack",
        required=False,
        default=7,
    )

    # --- dependencies ---
    dependencies_parser = subs.add_parser(
        "dependencies",
        help="Install the dependencies",
        formatter_class=fmt,
    )
    dependencies_parser.add_argument(
        "-p",
        "--persist",
        help="Persist the constraints",
        required=False,
        dest="persist_constraints",
        default=False,
        action="store_true",
    )

    # --- test ---
    subs.add_parser(
        "test",
        help="Run the tests for the given package",
        formatter_class=fmt,
    )

    # Argcomplete introspects parser internals and expects only real subcommands.
    # Keep custom help grouping for human-facing --help, but disable it during
    # completion runs to avoid KeyError on pseudo header entries.
    if "_ARGCOMPLETE" not in os.environ:
        _group_subcommands_for_help(
            subs,
            {
                "Setup and information commands:": [
                    "compile",
                    "dependencies",
                    "describe",
                    "init",
                    "install",
                    "upgrade",
                ],
                "Runtime Commands:": [
                    "adduser",
                    "run",
                    "supervisor",
                    "zeoclient",
                    "zeoserver",
                ],
                "Database commands:": [
                    "db",
                ],
                "Test commands:": [
                    "robotserver",
                    "robottest",
                    "test",
                    "zopetest",
                ],
            },
        )

    autocomplete(parser)
    return parser


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
            "Could not find the `etc/plonex.yml` file please run `plonex init %s` "
            "or specify a different target with the `--target` option."
        ),
        args.target,
    )
    sys.exit(1)


def _configure_logging(args, target: Path) -> None:
    """Set the log level based on CLI flags and optional config-file setting."""
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        return
    if args.quiet:
        logger.setLevel(logging.WARNING)
        logging.getLogger("sh").setLevel(logging.WARNING)
        return

    logging.getLogger("sh").setLevel(logging.WARNING)
    with InitService(target=target) as init:
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        print(version("plonex"))
        return

    if args.action == "init":
        with InitService(target=args.target) as svc:
            svc.run()
        return

    target = _resolve_target(args)
    _configure_logging(args, target)

    if args.action == "compile":
        with CompileService(target=target) as svc:
            svc.run()

    elif args.action == "describe":
        with DescribeService(target=target) as svc:
            svc.run()

    elif args.action == "robotserver":
        with RobotServer(target=target, layer=args.layer) as svc:
            svc.run()

    elif args.action == "robottest":
        with RobotTest(
            target=target,
            paths=args.paths,
            browser=args.browser,
            test=args.test,
        ) as svc:
            svc.run()

    elif args.action == "zopetest":
        with ZopeTest(
            target=target,
            package=args.package,
            test=args.test,
        ) as svc:
            svc.run()

    elif args.action == "zeoserver":
        logger.debug("Starting ZEO Server")
        with ZeoServer(target=target) as svc:
            svc.run()

    elif args.action == "zeoclient":
        logger.debug("Starting ZEO Client")
        zeoclient_action = getattr(args, "zeoclient_action", "") or "console"
        config_files = getattr(args, "zeoclient_config", []) or []
        cli_options = {}
        if args.host:
            cli_options["http_host"] = args.host
        if args.port:
            cli_options["http_port"] = args.port
        with ZeoClient(
            name=args.name,
            target=target,
            config_files=config_files,
            run_mode=zeoclient_action,  # type: ignore
            cli_options=cli_options,
        ) as svc:
            svc.run()

    elif args.action == "run":
        with ZeoClient(target=target) as svc:
            svc.run_script(args.args or [])

    elif args.action == "adduser":
        config_files = getattr(args, "zeoclient_config", []) or []
        with ZeoClient(target=target, config_files=config_files) as svc:
            svc.adduser(args.username, args.password)

    elif args.action == "supervisor":
        supervisor_action = getattr(args, "supervisor_action", None) or "status"
        with Supervisor(target=target) as svc:
            if supervisor_action == "start":
                svc.run()
            elif supervisor_action == "stop":
                svc.run_stop()
            elif supervisor_action == "restart":
                svc.run_restart()
            elif supervisor_action == "status":
                svc.run_status()
            elif supervisor_action == "graceful":
                logger.info("TODO: Manage the graceful restart of the services")

    elif args.action == "db":
        db_action = getattr(args, "db_action", None)
        if db_action == "backup":
            with ZeoServer(target=target) as svc:
                svc.run_backup()
        elif db_action == "restore":
            logger.info("TODO: Manage the restore of the services")
        elif db_action == "pack":
            with ZeoServer(target=target) as svc:
                svc.run_pack(days=args.days)
        else:
            parser.print_help()

    elif args.action == "dependencies":
        with InstallService(target=target) as svc:
            svc.run(save_constraints=args.persist_constraints)

    elif args.action == "test":
        with TestService() as svc:
            svc.run()

    elif args.action == "install":
        with InstallService() as svc:
            svc.add_packages(args.package)
        with InstallService() as svc:
            svc.run()

    elif args.action == "upgrade":
        with UpgradeService(target=target) as svc:
            svc.run()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
