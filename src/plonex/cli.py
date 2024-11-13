from argparse import ArgumentParser
from pathlib import Path
from plonex import logger
from plonex.install import InstallService
from plonex.supervisor import Supervisor
from plonex.zeoclient import ZeoClient
from plonex.zeoserver import ZeoServer


parser = ArgumentParser(
    description="Plone Deployment CLI",
    prog="plonex",
    usage="%(prog)s [options]",
)
action_subparsers = parser.add_subparsers(dest="action")

supervisor_parser = action_subparsers.add_parser("supervisor", help="Manage supervisor")
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
supervisor_subparsers.add_parser("stop", help="Stop supervisor")
supervisor_subparsers.add_parser("restart", help="Restart supervisor")
supervisor_subparsers.add_parser("status", help="Status of supervisor")
supervisor_subparsers.add_parser("graceful", help="Graceful restart of supervisor")

zeoserver_parser = action_subparsers.add_parser("zeoserver", help="Start ZEO Server")

zeoclient_parser = action_subparsers.add_parser("zeoclient", help="Start ZEO Client")
zeoclient_parser.add_argument(
    "-c",
    "--config",
    type=str,
    help="Path to the configuration file",
    required=False,
    dest="zeoclient_config",
    action="append",
)

adduser_parser = action_subparsers.add_parser("adduser", help="Add a user")

backup_parser = action_subparsers.add_parser("backup", help="Backup the services")

restore_parser = action_subparsers.add_parser("restore", help="Restore the services")

pack_parser = action_subparsers.add_parser("pack", help="Pack the DB")

dependencies_parser = action_subparsers.add_parser(
    "dependencies", help="Install the dependencies"
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


def main() -> None:
    args = parser.parse_args()

    _check_folders()

    if args.action == "zeoserver":
        logger.debug("Starting ZEO Server")
        with ZeoServer() as zeoserver:
            zeoserver.run()
    elif args.action == "zeoclient":
        logger.debug("Starting ZEO Client")

        # Get the configuration file
        config_files = getattr(args, "zeoclient_config", [])
        with ZeoClient(config_files=config_files) as zeoclient:
            zeoclient.run()
    elif args.action == "adduser":
        logger.info("TODO: Adding a user")
        pass
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


if __name__ == "__main__":
    main()
