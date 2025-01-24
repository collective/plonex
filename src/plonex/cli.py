from argcomplete import autocomplete
from argparse import ArgumentParser
from importlib.metadata import version
from itertools import chain
from pathlib import Path
from plonex import logger
from plonex.install import InstallService
from plonex.supervisor import Supervisor
from plonex.zeoclient import ZeoClient
from plonex.zeoserver import ZeoServer
from rich.console import Console
from rich_argparse import RawTextRichHelpFormatter

import requests


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
    default=8080,
)

zeoclient_parser.add_argument(
    "--host",
    type=str,
    help="Host to run the ZEO Client (default: 0.0.0.0)",
    required=False,
    default="0.0.0.0",
)

zeoclient_subparsers = zeoclient_parser.add_subparsers(
    dest="zeoclient_action", help="ZEO Client actions"
)

# optional actions for the zeoclient are:
# console
# start
# debug
# stop
# status
# run
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

zeoclient_debug_parser = zeoclient_subparsers.add_parser(
    "debug", help="Start the ZEO Client in debug mode"
)


adduser_parser = action_subparsers.add_parser(
    "adduser", help="Add a user", formatter_class=parser.formatter_class
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
adduser_parser.add_argument("password", type=str, help="Password")

backup_parser = action_subparsers.add_parser(
    "backup", help="Backup the services", formatter_class=parser.formatter_class
)

restore_parser = action_subparsers.add_parser(
    "restore", help="Restore the services", formatter_class=parser.formatter_class
)

pack_parser = action_subparsers.add_parser(
    "pack", help="Pack the DB", formatter_class=parser.formatter_class
)

dependencies_parser = action_subparsers.add_parser(
    "dependencies",
    help="Install the dependencies",
    formatter_class=parser.formatter_class,
)


autocomplete(parser)


def _ask_for_plone_version() -> str:
    console = Console()
    return (
        console.input("Please select the Plone version (default: 6.0-latest):")
        or "6.0-latest"
    )


def _check_folders(path: str) -> None:
    """Check that we have the necessary folders"""
    plone_version = None

    expected_folders = [
        Path(f"{path}/tmp"),
        Path(f"{path}/etc"),
        Path(f"{path}/etc/constraints.d"),
        Path(f"{path}/etc/requirements.d"),
        Path(f"{path}/var"),
        Path(f"{path}/var/blobstorage"),
        Path(f"{path}/var/cache"),
        Path(f"{path}/var/filestorage"),
        Path(f"{path}/var/log"),
    ]

    for folder in expected_folders:
        if not folder.exists():
            logger.info(f"Creating {folder}")
            folder.mkdir(parents=True)
        else:
            logger.debug(f"{folder} already exists")

    # Ensure that in the etc folder we have a plonex.yml file
    etc_folder = Path(f"{path}/etc")
    plonex_config = etc_folder / "plonex.yml"
    if not plonex_config.exists():
        logger.info(f"Creating {plonex_config}")
        plonex_version = version("plonex")
        plonex_config.write_text(
            "\n".join(
                (
                    "---",
                    f'plonex_version: "{plonex_version}"',
                    "",
                )
            )
        )

    # Ensure we have the requirements.d/000-plonex.txt
    # and constraints.d/000-plonex.txt files
    requirements_d = etc_folder / "requirements.d"
    if not (requirements_d / "000-plonex.txt").exists():
        requirements_txt = "\n".join(
            (
                "Plone",
                "plone.recipe.zope2instance",
                "supervisor",
            )
        )
        logger.info("Creating %s", requirements_d / "000-plonex.txt")
        (requirements_d / "000-plonex.txt").write_text(requirements_txt)

    constraints_d = etc_folder / "constraints.d"
    if not (constraints_d / "000-plonex.txt").exists():
        if plone_version is None:
            plone_version = _ask_for_plone_version()
        logger.info("Fetching the constraints.txt file for Plone %s", plone_version)
        constraints_txt = requests.get(
            f"https://dist.plone.org/release/{plone_version}/constraints.txt"
        ).text
        logger.info("Creating %s", constraints_d / "000-plonex.txt")
        (constraints_d / "000-plonex.txt").write_text(constraints_txt)


def main() -> None:
    args = parser.parse_args()

    if args.version:
        print(version("plonex"))
        return

    if args.action == "init":
        _check_folders(path=args.target)
        logger.info("Project initialized")
        return

    target = Path(args.target)
    for folder in chain([target], target.parents):
        if (folder / "etc" / "plonex.yml").exists():
            break
    else:
        logger.error(
            "Could not find the etc/plonex.yml file. "
            "Please run plonex init in the project root"
        )
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
        with ZeoClient(
            name=args.name,
            target=target,
            config_files=config_files,
            run_mode=zeoclient_action,  # type: ignore
            cli_options={"http_port": args.port, "http_host": args.host},
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
        logger.info("TODO: Manage the backup of the services")
        pass
    elif args.action == "restore":
        logger.info("TODO: Manage the restore of the services")
        pass
    elif args.action == "pack":
        logger.info("TODO: Manage the pack of DB")
        pass
    elif args.action == "dependencies":
        with InstallService(target=target) as install:
            install.run()
    elif args.action is None:
        parser.print_help()


if __name__ == "__main__":
    main()
