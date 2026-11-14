"""Public command families, sharing the existing parsers and service bindings."""

from argparse import _SubParsersAction
from argparse import ArgumentParser
from argparse import Namespace
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandGroup:
    name: str
    description: str
    commands: dict[str, str]


COMMAND_GROUPS = (
    CommandGroup(
        "project",
        "Initialize, inspect, diagnose, or edit a project",
        {
            "init": "init",
            "compile": "compile",
            "describe": "describe",
            "doctor": "doctor",
            "snapshot": "snapshot",
            "inspect-legacy": "inspect_legacy",
            "edit": "edit",
        },
    ),
    CommandGroup(
        "instance",
        "Run and maintain a Plone instance",
        {
            "start": "runwsgi",
            "debug": "fg",
            "console": "zconsole",
            "run": "run",
            "add-user": "adduser",
        },
    ),
    CommandGroup(
        "test",
        "Run tests or start a Robot testing server",
        {
            "pytest": "pytest",
            "zope": "zopetest",
            "robot": "robottest",
            "robot-server": "robotserver",
            "sources": "test_sources",
        },
    ),
)

FAMILY_ACTIONS = {
    "project": "project_action",
    "instance": "instance_action",
    "test": "test_action",
    "sources": "sources_action",
    "dependencies": "dependencies_action",
    "supervisor": "supervisor_action",
    "db": "db_action",
    "cron": "cron_action",
}


def show_family_help(parser, args):
    command = getattr(args, "action", None)
    if command not in FAMILY_ACTIONS or getattr(args, FAMILY_ACTIONS[command], None):
        return False
    for action in parser._actions:
        if isinstance(action, _SubParsersAction):
            action.choices[command].print_help()
            return True
    return False


def register_command_groups(subs, add_subparser) -> None:
    summaries = {action.dest: action.help for action in subs._choices_actions}
    for group in COMMAND_GROUPS:
        parser = add_subparser(subs, group.name, help=group.description)
        children = parser.add_subparsers(dest=f"{group.name}_action", title="Actions")
        for action, command in group.commands.items():
            original = subs.choices[command]
            child = children.add_parser(
                action,
                parents=[original],
                add_help=False,
                formatter_class=original.formatter_class,
                help=summaries[command],
                description=original.description,
            )
            # Preserve service names, invocation options, and run_for hook names.
            child.set_defaults(action=command)
            _rebase(child, f"{parser.prog} {action}")
    # Canonical families are the public API. Keep implementation identities in
    # service bindings, but remove their old flat command spellings completely.
    removed = set(shortcut_commands())
    for name in removed:
        subs.choices.pop(name, None)
    subs._choices_actions = [
        choice for choice in subs._choices_actions if choice.dest not in removed
    ]


def _rebase(parser, prog):
    parser.prog = prog
    for action in parser._actions:
        if isinstance(action, _SubParsersAction):
            action._prog_prefix = prog
            for name, child in action.choices.items():
                _rebase(child, f"{prog} {name}")


def shortcut_commands() -> dict[str, str]:
    return {
        command: f"{group.name} {action}"
        for group in COMMAND_GROUPS
        for action, command in group.commands.items()
    } | {
        "install": "dependencies add",
        "zeoserver": "db start",
        "upgrade": "db upgrade",
    }


def validate_command_args(parser: ArgumentParser, args: Namespace) -> Namespace:
    """Bind explicit dependency operations for execution and inspection."""
    if getattr(args, "action", None) not in {"dependencies", "install"}:
        return args
    explicit = getattr(args, "dependencies_action", None)
    operation = explicit
    args.sync = operation == "sync"
    args.show_outdated = operation == "outdated"
    return args
