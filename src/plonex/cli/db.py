def register_db_parsers(subs, add_subparser) -> None:
    """Register database-related CLI parsers."""
    db_parser = add_subparser(
        subs,
        "db",
        help="Database management commands (backup/restore/pack)",
    )
    db_subs = db_parser.add_subparsers(dest="db_action", help="Database actions")
    add_subparser(db_subs, "backup", help="Backup the services")
    add_subparser(db_subs, "restore", help="Restore the services")
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
