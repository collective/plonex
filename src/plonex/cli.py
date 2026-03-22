from argcomplete import autocomplete
from argparse import ArgumentParser
from argparse import SUPPRESS
from dataclasses import fields
from importlib.metadata import version
from itertools import chain
from pathlib import Path
from plonex import logger
from plonex.base import BaseService
from plonex.compile import CompileService
from plonex.describe import DescribeService
from plonex.directory import DirectoryService
from plonex.init import InitService
from plonex.install import InstallService
from plonex.robotserver import RobotServer
from plonex.robottest import RobotTest
from plonex.supervisor import Supervisor
from plonex.template import TemplateService
from plonex.test import TestService
from plonex.upgrade import UpgradeService
from plonex.zeoclient import ZeoClient
from plonex.zeoserver import ZeoServer
from plonex.zopetest import ZopeTest
from rich_argparse import RawTextRichHelpFormatter
from textwrap import dedent
from typing import Any

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


def _service_name(service_class) -> str | None:
    for cls_field in fields(service_class):
        if cls_field.name == "name" and isinstance(cls_field.default, str):
            return cls_field.default or None
    return None


def _service_registry() -> dict[str, type[BaseService]]:
    service_classes = [
        CompileService,
        DescribeService,
        DirectoryService,
        InitService,
        InstallService,
        RobotServer,
        RobotTest,
        Supervisor,
        TestService,
        UpgradeService,
        ZeoClient,
        ZeoServer,
        ZopeTest,
    ]
    registry: dict[str, type[BaseService]] = {}
    for service_class in service_classes:
        service_name = _service_name(service_class)
        if service_name:
            registry[service_name] = service_class
    registry["template"] = TemplateService
    return registry


def _normalize_template_kwargs(kwargs: dict[str, Any], target: Path) -> dict[str, Any]:
    normalized = dict(kwargs)

    if "source" in normalized and "source_path" not in normalized:
        normalized["source_path"] = normalized.pop("source")

    if "target" in normalized and "target_path" not in normalized:
        normalized["target_path"] = normalized.pop("target")

    source_path = normalized.get("source_path")
    if isinstance(source_path, str) and not source_path.startswith("resource://"):
        source_as_path = Path(source_path)
        if not source_as_path.is_absolute():
            normalized["source_path"] = target / source_as_path

    target_path = normalized.get("target_path")
    if isinstance(target_path, str):
        target_as_path = Path(target_path)
        if not target_as_path.is_absolute():
            normalized["target_path"] = target / target_as_path

    return normalized


def _match_service_dependency(
    service_kwargs: dict[str, Any],
    dependency_for: str | None,
) -> bool:
    run_for = service_kwargs.get("run_for")
    if dependency_for is None:
        return True
    if run_for is None:
        return False
    if isinstance(run_for, str):
        return run_for == dependency_for
    if isinstance(run_for, list):
        return dependency_for in run_for
    raise ValueError("The 'run_for' option should be a string or a list of strings")


def _service_from_config(
    spec: dict[str, Any],
    target: Path,
    dependency_for: str | None = None,
) -> BaseService | None:
    if not isinstance(spec, dict):
        raise ValueError("Each service entry should be a mapping")
    if len(spec) != 1:
        raise ValueError("Each service entry should contain exactly one service key")

    service_name, service_config = next(iter(spec.items()))
    if service_config is None:
        service_kwargs: dict[str, Any] = {}
    elif isinstance(service_config, dict):
        service_kwargs = dict(service_config)
    else:
        raise ValueError(
            f"Service {service_name!r} configuration should be a mapping or null"
        )

    if not _match_service_dependency(service_kwargs, dependency_for):
        return None

    service_kwargs.pop("run_for", None)

    registry = _service_registry()
    service_class = registry.get(service_name)
    if service_class is None:
        known_services = ", ".join(sorted(registry))
        raise ValueError(
            f"Unknown service {service_name!r}. Known services: {known_services}"
        )

    if service_name == "template":
        service_kwargs = _normalize_template_kwargs(service_kwargs, target)

    service_kwargs.setdefault("target", target)

    try:
        return service_class(**service_kwargs)
    except TypeError as exc:
        raise ValueError(
            f"Invalid configuration for service {service_name!r}: {exc}"
        ) from exc


def _run_service_dependencies(target: Path, service_name: str) -> None:
    with BaseService(target=target) as svc:
        services = svc.options.get("services") or []

    if not isinstance(services, list):
        raise ValueError("The 'services' option should be a list")

    for spec in services:
        service = _service_from_config(spec, target, dependency_for=service_name)
        if service is None:
            continue
        with service:
            service.run()


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

    def _add_subparser(subparsers, *args, **kwargs):
        """Helper to create a subparser that already includes
        the common -v/--verbose and -q/--quiet options.
        """
        subparser = subparsers.add_parser(*args, **kwargs)
        subparser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="Increase verbosity",
            required=False,
            default=SUPPRESS,
            dest="verbose",
        )
        subparser.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            help="Decrease verbosity",
            required=False,
            default=SUPPRESS,
            dest="quiet",
        )
        return subparser

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
    init_parser = _add_subparser(
        subs,
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
    _add_subparser(
        subs,
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
    _add_subparser(
        subs,
        "describe",
        help="Describe the current project configuration",
        formatter_class=fmt,
    )

    # --- robotserver ---
    robotserver_parser = _add_subparser(
        subs,
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
    robottest_parser = _add_subparser(
        subs,
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
    zopetest_parser = _add_subparser(
        subs,
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
    install_parser = _add_subparser(
        subs,
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
    _add_subparser(
        subs,
        "upgrade",
        help="Run Plone upgrade steps",
        formatter_class=fmt,
    )

    # --- supervisor ---
    supervisor_parser = _add_subparser(
        subs, "supervisor", help="Manage supervisor", formatter_class=fmt
    )
    supervisor_subs = supervisor_parser.add_subparsers(
        dest="supervisor_action", help="Supervisor actions"
    )
    _add_subparser(
        supervisor_subs,
        "status",
        help="Status of supervisor (default)",
        formatter_class=fmt,
    )
    _add_subparser(
        supervisor_subs, "start", help="Start supervisor", formatter_class=fmt
    )
    _add_subparser(supervisor_subs, "stop", help="Stop supervisor", formatter_class=fmt)
    _add_subparser(
        supervisor_subs, "restart", help="Restart supervisor", formatter_class=fmt
    )
    _add_subparser(
        supervisor_subs,
        "graceful",
        help="Graceful restart of supervisor",
        formatter_class=fmt,
    )

    # --- zeoserver ---
    _add_subparser(subs, "zeoserver", help="Start ZEO Server", formatter_class=fmt)

    # --- zeoclient ---
    zeoclient_parser = _add_subparser(
        subs, "zeoclient", help="Start ZEO Client", formatter_class=fmt
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
    _add_subparser(
        zeoclient_subs,
        "console",
        help="Start the ZEO Client console (default behavior)",
    )
    _add_subparser(zeoclient_subs, "fg", help="Start the ZEO Client in foreground")
    _add_subparser(zeoclient_subs, "start", help="Start the ZEO Client in background")
    _add_subparser(zeoclient_subs, "stop", help="Stop the ZEO Client in background")
    _add_subparser(
        zeoclient_subs, "status", help="Status of the ZEO Client in background"
    )  # noqa: E501
    _add_subparser(zeoclient_subs, "debug", help="Start the ZEO Client in debug mode")

    # --- run ---
    run_parser = _add_subparser(
        subs, "run", help="Run an instance script", formatter_class=fmt
    )
    run_parser.add_argument(
        "args",
        nargs="*",
        help="Arguments to pass to the script",
    )

    # --- adduser ---
    adduser_parser = _add_subparser(
        subs,
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
    db_parser = _add_subparser(
        subs,
        "db",
        help="Database management commands (backup/restore/pack)",
        formatter_class=fmt,
    )
    db_subs = db_parser.add_subparsers(dest="db_action", help="Database actions")
    _add_subparser(db_subs, "backup", help="Backup the services", formatter_class=fmt)
    _add_subparser(db_subs, "restore", help="Restore the services", formatter_class=fmt)
    db_pack_parser = _add_subparser(
        db_subs,
        "pack",
        help="Pack the DB",
        formatter_class=fmt,
    )
    db_pack_parser.add_argument(
        "-d",
        "--days",
        type=int,
        help="Number of days to pack",
        required=False,
        default=7,
    )

    # --- dependencies ---
    dependencies_parser = _add_subparser(
        subs,
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
    _add_subparser(
        subs,
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
        _run_service_dependencies(target, "compile")
        with CompileService(target=target) as svc:
            svc.run()

    elif args.action == "describe":
        _run_service_dependencies(target, "describe")
        with DescribeService(target=target) as svc:
            svc.run()

    elif args.action == "robotserver":
        _run_service_dependencies(target, "robotserver")
        with RobotServer(target=target, layer=args.layer) as svc:
            svc.run()

    elif args.action == "robottest":
        _run_service_dependencies(target, "robottest")
        with RobotTest(
            target=target,
            paths=args.paths,
            browser=args.browser,
            test=args.test,
        ) as svc:
            svc.run()

    elif args.action == "zopetest":
        _run_service_dependencies(target, "zopetest")
        with ZopeTest(
            target=target,
            package=args.package,
            test=args.test,
        ) as svc:
            svc.run()

    elif args.action == "zeoserver":
        _run_service_dependencies(target, "zeoserver")
        logger.debug("Starting ZEO Server")
        with ZeoServer(target=target) as svc:
            svc.run()

    elif args.action == "zeoclient":
        _run_service_dependencies(target, "zeoclient")
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
        _run_service_dependencies(target, "run")
        with ZeoClient(target=target) as svc:
            svc.run_script(args.args or [])

    elif args.action == "adduser":
        _run_service_dependencies(target, "adduser")
        config_files = getattr(args, "zeoclient_config", []) or []
        with ZeoClient(target=target, config_files=config_files) as svc:
            svc.adduser(args.username, args.password)

    elif args.action == "supervisor":
        _run_service_dependencies(target, "supervisor")
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
        _run_service_dependencies(target, "db")
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
        _run_service_dependencies(target, "dependencies")
        with InstallService(target=target) as svc:
            svc.run(save_constraints=args.persist_constraints)

    elif args.action == "test":
        _run_service_dependencies(target, "test")
        with TestService() as svc:
            svc.run()

    elif args.action == "install":
        _run_service_dependencies(target, "install")
        with InstallService() as svc:
            svc.add_packages(args.package)
        with InstallService() as svc:
            svc.run()

    elif args.action == "upgrade":
        _run_service_dependencies(target, "upgrade")
        with UpgradeService(target=target) as svc:
            svc.run()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
