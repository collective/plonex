from argparse import ArgumentParser
from pathlib import Path
from plonedeployment import logger
from plonedeployment import zeoclient
from plonedeployment.zeoserver import ZeoServer


parser = ArgumentParser(
    description="Plone Deployment CLI",
    epilog="This is the epilog",
    prog="plonedeployment",
    usage="%(prog)s [options]",
)

parser.add_argument(
    "action",
    choices=["zeoserver", "zeoclient", "adduser"],
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
        zeoclient.run()
    elif args.action == "adduser":
        logger.debug("Adding a user")
        pass


if __name__ == "__main__":
    main()
