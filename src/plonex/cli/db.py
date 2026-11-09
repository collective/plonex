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
