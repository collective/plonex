def register_runtime_parsers(subs, add_subparser) -> None:
    """Register runtime-related CLI parsers."""
    supervisor_parser = add_subparser(subs, "supervisor", help="Manage supervisor")
    supervisor_subs = supervisor_parser.add_subparsers(
        dest="supervisor_action", help="Supervisor actions"
    )
    add_subparser(
        supervisor_subs,
        "status",
        help="Status of supervisor (default)",
    )
    add_subparser(supervisor_subs, "start", help="Start supervisor")
    add_subparser(supervisor_subs, "stop", help="Stop supervisor")
    add_subparser(supervisor_subs, "restart", help="Restart supervisor")
    graceful_parser = add_subparser(
        supervisor_subs,
        "graceful",
        help="Graceful restart of supervisor",
    )
    graceful_parser.add_argument(
        "--interval",
        type=float,
        help="Seconds to wait between restarting services",
        required=False,
        default=None,
        dest="graceful_interval",
    )

    add_subparser(subs, "zeoserver", help="Start ZEO Server")

    zeoclient_parser = add_subparser(subs, "zeoclient", help="Start ZEO Client")
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
    zeoclient_subs = zeoclient_parser.add_subparsers(
        dest="zeoclient_action", help="ZEO Client actions"
    )
    add_subparser(
        zeoclient_subs,
        "console",
        help="Start the ZEO Client console (default behavior)",
    )
    add_subparser(zeoclient_subs, "fg", help="Start the ZEO Client in foreground")
    add_subparser(zeoclient_subs, "start", help="Start the ZEO Client in background")
    add_subparser(zeoclient_subs, "stop", help="Stop the ZEO Client in background")
    add_subparser(
        zeoclient_subs, "status", help="Status of the ZEO Client in background"
    )
    add_subparser(zeoclient_subs, "debug", help="Start the ZEO Client in debug mode")

    run_parser = add_subparser(subs, "run", help="Run an instance script")
    run_parser.add_argument(
        "args",
        nargs="*",
        help="Arguments to pass to the script",
    )

    adduser_parser = add_subparser(
        subs,
        "adduser",
        help=(
            "Add a user. You need to provide at least a username, optionally a password"
        ),
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
