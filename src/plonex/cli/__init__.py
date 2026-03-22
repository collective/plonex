from . import parser as _cli_parser
from .dependencies import _run_service_dependencies
from argcomplete import autocomplete
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

import logging
import sys


def build_parser():
    # Preserve compatibility with tests and callers that patch
    # plonex.cli.autocomplete before invoking build_parser().
    _cli_parser.autocomplete = autocomplete
    return _cli_parser.build_parser()


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
