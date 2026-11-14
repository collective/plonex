from argparse import ArgumentParser
from argparse import Namespace
from pathlib import Path
from plonex.cli.dependencies import _run_service_dependencies
from plonex.services.invocation import ServiceInvocation
from plonex.services.zeoserver import ZeoServer
from rich.console import Console
from typing import cast


def register_db_parsers(subs, add_subparser) -> None:
    """Register database-related CLI parsers."""
    db_parser = add_subparser(
        subs,
        "db",
        help="Start, back up, restore, or pack the database",
    )
    db_subs = db_parser.add_subparsers(dest="db_action", help="Database actions")
    start = db_subs.add_parser(
        "start",
        parents=[subs.choices["zeoserver"]],
        add_help=False,
        help="Start the ZEO database server in the foreground",
    )
    start.set_defaults(action="zeoserver")
    add_subparser(
        db_subs, "backup", help="Create an offline database and blob snapshot"
    )
    restore = add_subparser(db_subs, "restore", help="Restore to a new directory")
    restore.add_argument(
        "--to", dest="restore_destination", help="New recovery directory"
    )
    restore.add_argument(
        "--from", dest="restore_backup", help="Backup snapshot directory"
    )
    upgrade = db_subs.add_parser(
        "upgrade",
        parents=[subs.choices["upgrade"]],
        add_help=False,
        help="Run Plone database upgrade steps",
    )
    upgrade.set_defaults(action="upgrade")
    db_pack_parser = add_subparser(
        db_subs,
        "pack",
        help="Pack the DB",
    )
    db_pack_parser.add_argument(
        "-d",
        "--days",
        type=int,
        help="Number of days to pack",
        required=False,
        default=7,
    )


def _handle_db(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    db_action = getattr(args, "db_action", None)
    if db_action in {"backup", "restore"}:
        from plonex.files import read_only

        # Do not create missing storage directories or run mutating hooks before
        # backup validation; an absent blob directory must remain an error.
        with read_only():
            svc = cast(
                ZeoServer, ServiceInvocation.from_args(args, target).create(ZeoServer)
            )
            svc.options
        if db_action == "backup":
            path = svc.run_backup()
        else:
            path = svc.run_restore(
                destination=args.restore_destination, backup=args.restore_backup
            )
        Console().print(str(path), markup=False)
    elif db_action == "pack":
        _run_service_dependencies(target, "db")
        with ServiceInvocation.from_args(args, target).create(ZeoServer) as svc:
            svc.run_pack(days=args.days)
    else:
        parser.print_help()


ACTION_HANDLERS = {
    "db": _handle_db,
}
