def register_runtime_parsers(subs, add_subparser) -> None:
    """Register runtime-related CLI parsers."""

    def add_runtime_options(parser, *, default_name: str):
        parser.add_argument(
            "-n",
            "--name",
            type=str,
            help="Name of the runtime service",
            required=False,
            default=default_name,
        )
        parser.add_argument(
            "-c",
            "--config",
            type=str,
            help="Path to the configuration file",
            required=False,
            dest="runtime_config",
            action="append",
        )
        parser.add_argument(
            "-p",
            "--port",
            type=int,
            help="HTTP port override (default from config)",
            required=False,
            default=0,
        )
        parser.add_argument(
            "--host",
            type=str,
            help="HTTP host override (default from config)",
            required=False,
            default="",
        )

    supervisor_parser = add_subparser(subs, "supervisor", help="Manage supervisor")
    supervisor_subs = supervisor_parser.add_subparsers(
        dest="supervisor_action", help="Supervisor actions"
    )
    add_subparser(
        supervisor_subs,
        "status",
        help="Status of supervisor",
    )
    start_parser = add_subparser(
        supervisor_subs, "start", help="Prepare and start supervisor"
    )
    start_parser.add_argument(
        "--plan", action="store_true", help="Explain preparation without executing it"
    )
    add_subparser(supervisor_subs, "stop", help="Stop supervisor")
    restart = add_subparser(supervisor_subs, "restart", help="Restart managed programs")
    restart.add_argument(
        "programs", nargs="*", help="Programs to restart (default: all)"
    )
    add_subparser(
        supervisor_subs, "reread", help="Reread Supervisor program declarations"
    )
    add_subparser(supervisor_subs, "update", help="Apply changed Supervisor programs")
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

    runwsgi_parser = add_subparser(subs, "runwsgi", help="Start runwsgi")
    add_runtime_options(runwsgi_parser, default_name="runwsgi")
    runwsgi_parser.add_argument(
        "args",
        nargs="*",
        help="Arguments to pass to runwsgi",
    )

    zconsole_parser = add_subparser(subs, "zconsole", help="Run zconsole commands")
    add_runtime_options(zconsole_parser, default_name="zconsole")

    fg_parser = add_subparser(
        subs,
        "fg",
        help="Start runwsgi in foreground debug mode",
    )
    add_runtime_options(fg_parser, default_name="fg")
    fg_parser.add_argument(
        "--debugpy",
        type=int,
        metavar="PORT",
        help="Listen for a debugpy client on 127.0.0.1:PORT",
    )
    fg_parser.add_argument(
        "--wait-for-debugger",
        action="store_true",
        help="Wait for the debugpy client before starting the instance",
    )
    fg_parser.add_argument(
        "args",
        nargs="*",
        help="Arguments to pass to runwsgi",
    )

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
        dest="runtime_config",
        action="append",
    )
    adduser_parser.add_argument("username", type=str, help="Username")
    adduser_parser.add_argument("password", type=str, help="Password", nargs="?")
