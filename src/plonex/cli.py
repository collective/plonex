from argparse import ArgumentParser
from itertools import chain
from pathlib import Path
from plonex import logger
from plonex.install import InstallService
from plonex.supervisor import Supervisor
from plonex.zeoclient import ZeoClient
from plonex.zeoserver import ZeoServer
from rich_argparse import RichHelpFormatter


parser = ArgumentParser(
    description="Plone Deployment CLI",
    prog="plonex",
    usage="%(prog)s [options]",
    formatter_class=RichHelpFormatter,
)
action_subparsers = parser.add_subparsers(dest="action")

init_parser = action_subparsers.add_parser(
    "init", help="Initialize the project", formatter_class=parser.formatter_class
)

supervisor_parser = action_subparsers.add_parser(
    "supervisor", help="Manage supervisor", formatter_class=parser.formatter_class
)
supervisor_subparsers = supervisor_parser.add_subparsers(
    dest="supervisor_action", help="Supervisor actions"
)
# The possible actions for the supervisor are start, stop, restart, status, graceful
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
    "-c",
    "--config",
    type=str,
    help="Path to the configuration file",
    required=False,
    dest="zeoclient_config",
    action="append",
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


def _check_folders() -> None:
    """Check that we have the necessary folders"""

    expected_folders = [
        Path("tmp"),
        Path("etc"),
        Path("var"),
        Path("var/blobstorage"),
        Path("var/cache"),
        Path("var/filestorage"),
        Path("var/log"),
    ]

    for folder in expected_folders:
        if not folder.exists():
            logger.info(f"Creating {folder}")
            folder.mkdir(parents=True)
        else:
            logger.debug(f"{folder} already exists")

    # Ensure that in the etc folder we have a plonex.yml file
    etc_folder = Path("etc")
    plonex_config = etc_folder / "plonex.yml"
    if not plonex_config.exists():
        logger.info(f"Creating {plonex_config}")
        plonex_config.write_text("---\n")


def main() -> None:
    args = parser.parse_args()
    if args.action == "init":
        _check_folders()
        logger.info("Project initialized")
        return

    cwd = Path.cwd()

    for target in chain([cwd], cwd.parents):
        if (target / "etc" / "plonex.yml").exists():
            break
    else:
        logger.error(
            "Could not find the etc/plonex.yml file. "
            "Please run plonex init in the project root"
        )
        return

    if args.action == "zeoserver":
        logger.debug("Starting ZEO Server")
        with ZeoServer(target) as zeoserver:
            zeoserver.run()
    elif args.action == "zeoclient":
        logger.debug("Starting ZEO Client")
        # Get the configuration file
        config_files = getattr(args, "zeoclient_config", []) or []
        with ZeoClient(target, config_files=config_files) as zeoclient:
            zeoclient.run()
    elif args.action == "adduser":
        config_files = getattr(args, "zeoclient_config", []) or []
        with ZeoClient(target, config_files=config_files) as zeoclient:
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
        with Supervisor() as supervisor:
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
        with InstallService() as install:
            install.run()
    elif args.action is None:
        logger.error("Not handling action: %r", args.action)


if __name__ == "__main__":
    main()
