from argcomplete import autocomplete
from argparse import ArgumentParser
from argparse import SUPPRESS
from pathlib import Path
from plonex.cli.aliases import AliasArgumentParser
from plonex.cli.aliases import load_aliases
from plonex.cli.aliases import split_command
from plonex.cli.commands import register_command_groups
from plonex.cli.cron import register_cron_parsers
from plonex.cli.db import register_db_parsers
from plonex.cli.jobs import JOB_COMMANDS
from plonex.cli.runtime import register_runtime_parsers
from plonex.cli.setup_info import register_setup_parsers
from plonex.cli.testing import register_test_parsers
from rich_argparse import RawTextRichHelpFormatter
from textwrap import dedent

import os
import shlex
import sys


def _group_subcommands_for_help(subs, groups: dict[str, list[str]]) -> None:
    """Reorder subcommand help entries and inject category headers."""
    choices_by_name = {action.dest: action for action in subs._choices_actions}
    grouped = []
    for title, names in groups.items():
        if not names:
            continue
        grouped.append(subs._ChoicesPseudoAction(f"\n{title}", [], ""))
        for name in names:
            action = choices_by_name.get(name)
            if action is not None:
                grouped.append(action)
    subs._choices_actions = grouped


def _add_common_flags(subparser) -> None:
    subparser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase verbosity",
        required=False,
        default=SUPPRESS,
        dest="verbose",
    )
    subparser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Decrease verbosity",
        required=False,
        default=SUPPRESS,
        dest="quiet",
    )


def _add_subparser(subparsers, *args, **kwargs):
    """Create a subparser and attach common CLI flags."""
    kwargs.setdefault("formatter_class", RawTextRichHelpFormatter)
    subparser = subparsers.add_parser(*args, **kwargs)
    _add_common_flags(subparser)
    return subparser


def build_parser(
    *, for_completion: bool = False, target: Path | None = None
) -> ArgumentParser:
    parser = AliasArgumentParser(
        description=dedent("""\
            Plone Deployment CLI.

            Activate autocomplete with:

            eval "$(register-python-argcomplete plonex)"
            """),
        prog="plonex",
        usage="%(prog)s [global options] COMMAND [ACTION] [options]",
        formatter_class=RawTextRichHelpFormatter,
    )
    parser.add_argument(
        "-t",
        "--target",
        type=str,
        help="Path to the target folder",
        required=False,
        default=Path.cwd(),
        dest="target",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Increase verbosity",
        required=False,
        default=False,
        dest="verbose",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Decrease verbosity",
        required=False,
        default=False,
        dest="quiet",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Show the version of the package",
        required=False,
        default=False,
        dest="version",
    )

    subs = parser.add_subparsers(
        dest="action", title="Positional Arguments", metavar="COMMAND"
    )

    register_setup_parsers(subs, _add_subparser)
    register_runtime_parsers(subs, _add_subparser)
    register_db_parsers(subs, _add_subparser)
    register_test_parsers(subs, _add_subparser)
    register_cron_parsers(subs, _add_subparser)
    register_command_groups(subs, _add_subparser)

    try:
        tokens = sys.argv[1:]
        # Shell completion invokes the entry point without its command-line args.
        if "_ARGCOMPLETE" in os.environ:
            try:
                words = shlex.split(os.environ.get("COMP_LINE", ""))
                start = int(os.environ["_ARGCOMPLETE"])
                tokens = words[start:]
            except ValueError:
                pass
        alias_target = target if target is not None else split_command(tokens)[0]
        # A doctor must be usable even when project configuration is broken or
        # an uncached remote profile cannot be loaded without network access.
        _, _, command = split_command(tokens, alias_target)
        aliases = (
            {}
            if command[:2]
            in (
                ["project", "doctor"],
                ["project", "snapshot"],
                ["project", "inspect-legacy"],
                ["dependencies", "preview"],
            )
            else load_aliases(alias_target)
        )
        reserved = set(subs.choices) | {"help", "exit", "quit", "plonex", *JOB_COMMANDS}
        for name, command in aliases.items():
            if name in reserved:
                raise ValueError(
                    f"Command alias {name!r} conflicts with a built-in command"
                )
            subs.add_parser(name, help=f"Alias for: {shlex.join(command)}")
        parser.command_aliases = aliases
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    # Argcomplete introspects parser internals and expects only real subcommands.
    # Keep custom help grouping for human-facing --help, but disable it during
    # completion runs to avoid KeyError on pseudo header entries.
    if not for_completion and "_ARGCOMPLETE" not in os.environ:
        _group_subcommands_for_help(
            subs,
            {
                "Setup and information commands:": [
                    "project",
                    "options",
                    "shell",
                    "dependencies",
                    "sources",
                ],
                "Runtime Commands:": [
                    "instance",
                    "supervisor",
                    "cron",
                ],
                "Database commands:": [
                    "db",
                ],
                "Test commands:": [
                    "test",
                ],
                "Project aliases:": list(aliases),
            },
        )

    autocomplete(parser)
    return parser
