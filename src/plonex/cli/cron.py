from argparse import SUPPRESS


def positive(value):
    from argparse import ArgumentTypeError

    number = int(value)
    if number <= 0:
        raise ArgumentTypeError("must be a positive integer")
    return number


def register_cron_parsers(subs, add_subparser):
    parent = add_subparser(
        subs, "cron", help="Schedule, run, and inspect background jobs"
    )
    parent.add_argument(
        "--config",
        action="append",
        dest="cron_config",
        help="Additional configuration file",
    )
    children = parent.add_subparsers(dest="cron_action", title="Actions")
    descriptions = {
        "list": "List configured jobs and their latest results",
        "run": "Run one named job now",
        "enqueue": "Queue one named job for the daemon",
        "history": "Show persisted execution history",
        "logs": "Read a job's latest execution log",
        "daemon": "Run the Huey scheduler and workers in the foreground",
        "configure": "Render the Supervisor program without starting it",
        "status": "Show queue depths and execution statistics",
        "queue": "List pending and scheduled tasks",
        "inspect": "Show a task's attempts and events",
        "retry": "Enqueue another attempt of a failed task",
        "revoke": "Prevent a queued task from executing",
        "restore": "Restore a revoked task",
    }
    for action, help_text in descriptions.items():
        child = add_subparser(children, action, help=help_text)
        child.add_argument(
            "--config",
            action="append",
            dest="cron_config",
            default=SUPPRESS,
            help="Additional configuration file",
        )
        if action in {"run", "enqueue", "logs"}:
            child.add_argument("job", help="Configured job name")
        if action == "history":
            child.add_argument("job", nargs="?", default="")
            child.add_argument("--limit", type=positive, default=50)
            child.add_argument(
                "--format",
                choices=("terminal", "json"),
                default="terminal",
                dest="history_format",
            )
        if action == "logs":
            child.add_argument("--tail", type=positive, default=50)
        if action == "daemon":
            child.add_argument("--workers", type=positive, default=None)
        if action in {"inspect", "retry", "revoke", "restore"}:
            child.add_argument("task_id", help="Huey task ID")
        if action in {"status", "queue", "inspect", "retry", "revoke", "restore"}:
            child.add_argument(
                "--format",
                choices=("terminal", "json"),
                default="terminal",
                dest="queue_format",
            )
            child.add_argument("--limit", type=positive, default=50)
