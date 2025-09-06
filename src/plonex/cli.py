from argcomplete import autocomplete
from argparse import ArgumentParser
from importlib.metadata import version
from itertools import chain
from pathlib import Path
from plonex import logger
from plonex.describe import DescribeService
from plonex.init import InitService
from plonex.install import InstallService
from plonex.supervisor import Supervisor
from plonex.test import TestService
from plonex.zeoclient import ZeoClient
from plonex.zeoserver import ZeoServer
from rich_argparse import RawTextRichHelpFormatter

import sys


parser = ArgumentParser(
    description="""Plone Deployment CLI.

Activate autocomplete with:

eval "$(register-python-argcomplete plonex)"
""",
    prog="plonex",
    usage="%(prog)s [options]",
    formatter_class=RawTextRichHelpFormatter,
)
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

action_subparsers = parser.add_subparsers(dest="action")

init_parser = action_subparsers.add_parser(
    "init",
    description=(
        "Initialize the project in the specified target folder. "
        "This will create the necessary folders and configuration files."
    ),
    help=("Initialize the project in the specified target folder."),
    formatter_class=parser.formatter_class,
)

describe_parser = action_subparsers.add_parser(
    "describe",
    help="Describe the current project configuration",
    formatter_class=parser.formatter_class,
)

# init will accept one and only one positional target argument,
# which defaults to the current working directory
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

install_parser = action_subparsers.add_parser(
    "install",
    help="Add one or more packages to your requirements and install them",
    formatter_class=parser.formatter_class,
)

install_parser.add_argument(
    "package",
    type=str,
    help="Packages to install",
    nargs="+",
)

supervisor_parser = action_subparsers.add_parser(
    "supervisor", help="Manage supervisor", formatter_class=parser.formatter_class
)
supervisor_subparsers = supervisor_parser.add_subparsers(
    dest="supervisor_action", help="Supervisor actions"
)

# The possible actions for the supervisor are:
#
# - start
# - stop
# - restart
# - status
# - graceful
supervisor_start_parser = supervisor_subparsers.add_parser(
    "start", help="Start supervisor"
)
supervisor_start_parser.add_argument(
    "--foo",
    action="help",
    default="==SUPPRESS==",
    help="Show this help message and exit",
)
supervisor_subparsers.add_parser(
    "stop", help="Stop supervisor", formatter_class=parser.formatter_class
)
supervisor_subparsers.add_parser(
    "restart", help="Restart supervisor", formatter_class=parser.formatter_class
)
supervisor_subparsers.add_parser(
    "status", help="Status of supervisor", formatter_class=parser.formatter_class
)
supervisor_subparsers.add_parser(
    "graceful",
    help="Graceful restart of supervisor",
    formatter_class=parser.formatter_class,
)

zeoserver_parser = action_subparsers.add_parser(
    "zeoserver", help="Start ZEO Server", formatter_class=parser.formatter_class
)

zeoclient_parser = action_subparsers.add_parser(
    "zeoclient", help="Start ZEO Client", formatter_class=parser.formatter_class
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

zeoclient_subparsers = zeoclient_parser.add_subparsers(
    dest="zeoclient_action", help="ZEO Client actions"
)

# optional actions for the zeoclient are:
# - console
# - start
# - debug
# - stop
# - status
# - run
# If not specified, the default action is start

zeoclient_console_parser = zeoclient_subparsers.add_parser(
    "console", help="Start the ZEO Client console (default behavior)"
)

zeoclient_console_parser = zeoclient_subparsers.add_parser(
    "fg", help="Start the ZEO Client in foreground"
)

zeoclient_start_parser = zeoclient_subparsers.add_parser(
    "start", help="Start the ZEO Client in background"
)

zeoclient_stop_parser = zeoclient_subparsers.add_parser(
    "stop", help="Stop the ZEO Client in background"
)

zeoclient_status_parser = zeoclient_subparsers.add_parser(
    "status", help="Status of the ZEO Client in background"
)

zeoclient_debug_parser = zeoclient_subparsers.add_parser(
    "debug", help="Start the ZEO Client in debug mode"
)


adduser_parser = action_subparsers.add_parser(
    "adduser",
    help="Add a user. You need to provide at least a username, optionally a password",
    formatter_class=parser.formatter_class,
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

backup_parser = action_subparsers.add_parser(
    "backup", help="Backup the services", formatter_class=parser.formatter_class
)

restore_parser = action_subparsers.add_parser(
    "restore", help="Restore the services", formatter_class=parser.formatter_class
)

pack_parser = action_subparsers.add_parser(
    "pack", help="Pack the DB", formatter_class=parser.formatter_class
)

pack_parser.add_argument(
    "-d",
    "--days",
    type=int,
    help="Number of days to pack",
    required=False,
    default=7,
)

dependencies_parser = action_subparsers.add_parser(
    "dependencies",
    help="Install the dependencies",
    formatter_class=parser.formatter_class,
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

test_parser = action_subparsers.add_parser(
    "test",
    help="Run the tests for the given package",
    formatter_class=parser.formatter_class,
)

autocomplete(parser)


def main() -> None:
    args = parser.parse_args()

    if args.version:
        print(version("plonex"))
        return

    if args.verbose:
        logger.setLevel("DEBUG")
    elif args.quiet:
        logger.setLevel("WARNING")

    if args.action == "init":
        with InitService(target=args.target) as init:
            init.run()
        return

    target = Path(args.target)
    if not target.exists():
        logger.error("The target folder %r does not exist", args.target)
        sys.exit(1)

    for folder in chain([target], target.parents):
        plonex_yml = folder / "etc" / "plonex.yml"
        if plonex_yml.exists():
            break
    else:
        logger.error(
            (
                "Could not find the `etc/plonex.yml` file please run `plonex init %s` "
                "or specify a different target with the `--target` option."
            ),
            args.target,
        )
        sys.exit(1)

    if not args.verbose and not args.quiet:
        # Check if the log_level is set in the configuration file
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
                    logger.setLevel(log_level.upper())

    if args.action == "describe":
        with DescribeService(target=target) as describe:
            describe.run()
        return

    if args.action == "zeoserver":
        logger.debug("Starting ZEO Server")
        with ZeoServer(target=target) as zeoserver:
            zeoserver.run()
    elif args.action == "zeoclient":
        logger.debug("Starting ZEO Client")
        zeoclient_action = getattr(args, "zeoclient_action", "") or "console"
        # Get the configuration file
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
        ) as zeoclient:
            zeoclient.run()

    elif args.action == "adduser":
        config_files = getattr(args, "zeoclient_config", []) or []
        with ZeoClient(target=target, config_files=config_files) as zeoclient:
            zeoclient.adduser(args.username, args.password)
    elif args.action == "supervisor":
        supervisor_action = getattr(args, "supervisor_action", None)
        if supervisor_action is None:
            possible_actions = supervisor_parser._actions[-1].choices or []
            logger.error(
                "You must specify an action for the supervisor: %r",
                tuple(possible_actions),
            )
            return
        with Supervisor(target=target) as supervisor:
            if supervisor_action == "start":
                supervisor.run()
            elif supervisor_action == "stop":
                supervisor.run_stop()
            elif supervisor_action == "restart":
                supervisor.run_restart()
            elif args.supervisor_action == "status":
                supervisor.run_status()
            elif args.supervisor_action == "graceful":
                logger.info("TODO: Manage the graceful restart of the services")
    elif args.action == "backup":
        with ZeoServer(target=target) as zeoserver:
            zeoserver.run_backup()
        pass
    elif args.action == "restore":
        logger.info("TODO: Manage the restore of the services")
        pass
    elif args.action == "pack":
        with ZeoServer(target=target) as zeoserver:
            zeoserver.run_pack(days=args.days)
        pass
    elif args.action == "dependencies":
        with InstallService(target=target) as install:
            install.run(
                save_constraints=args.persist_constraints,
            )
    elif args.action == "test":
        with TestService() as test:
            test.run()
    elif args.action == "install":
        with InstallService() as install:
            install.add_packages(args.package)
        with InstallService() as install:
            install.run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
