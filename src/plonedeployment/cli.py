from argparse import ArgumentParser
from pathlib import Path
from plonedeployment import logger
from plonedeployment.supervisor import Supervisor
from plonedeployment.zeoclient import ZeoClient
from plonedeployment.zeoserver import ZeoServer


parser = ArgumentParser(
    description="Plone Deployment CLI",
    epilog="This is the epilog",
    prog="plonedeployment",
    usage="%(prog)s [options]",
)

parser.add_argument(
    "action",
    choices=["zeoserver", "zeoclient", "adduser", "start"],
    help="Action to perform",
)


def _check_folders() -> None:
    """Check that we have the necessary folders"""

    expected_folders = [
        Path("tmp"),
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
        with ZeoClient() as zeoclient:
            zeoclient.run()
    elif args.action == "adduser":
        logger.info("TODO: Adding a user")
        pass
    elif args.action == "start":
        with Supervisor() as supervisor:
            supervisor.run()
    elif args.action == "status":
        logger.info("TODO: Manage the status of the services")
        pass
    elif args.action == "stop":
        logger.info("TODO: Manage the stop of the services")
        pass
    elif args.action == "restart":
        logger.info("TODO: Manage the restart of the services")
        pass
    elif args.action == "graceful":
        logger.info("TODO: Manage the graceful restart of the services")
        pass
    elif args.action == "backup":
        logger.info("TODO: Manage the backup of the services")
        pass
    elif args.action == "restore":
        logger.info("TODO: Manage the restore of the services")
        pass
    elif args.action == "pack":
        logger.info("TODO: Manage the pack of DB")
        pass


if __name__ == "__main__":
    main()
