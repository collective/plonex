from argcomplete import autocomplete
from argparse import ArgumentParser
from argparse import SUPPRESS
from pathlib import Path
from plonex.cli.db import register_db_parsers
from plonex.cli.runtime import register_runtime_parsers
from plonex.cli.setup_info import register_setup_parsers
from plonex.cli.testing import register_test_parsers
from rich_argparse import RawTextRichHelpFormatter
from textwrap import dedent

import os


def _group_subcommands_for_help(subs, groups: dict[str, list[str]]) -> None:
    """Reorder subcommand help entries and inject category headers."""
    choices_by_name = {action.dest: action for action in subs._choices_actions}
    grouped = []
    for title, names in groups.items():
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


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description=dedent(
            """\
            Plone Deployment CLI.

            Activate autocomplete with:

            eval "$(register-python-argcomplete plonex)"
            """
        ),
        prog="plonex",
        usage="%(prog)s [options]",
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

    subs = parser.add_subparsers(dest="action", title="Positional Arguments")

    register_setup_parsers(subs, _add_subparser)
    register_runtime_parsers(subs, _add_subparser)
    register_db_parsers(subs, _add_subparser)
    register_test_parsers(subs, _add_subparser)

    # Argcomplete introspects parser internals and expects only real subcommands.
    # Keep custom help grouping for human-facing --help, but disable it during
    # completion runs to avoid KeyError on pseudo header entries.
    if "_ARGCOMPLETE" not in os.environ:
        _group_subcommands_for_help(
            subs,
            {
                "Setup and information commands:": [
                    "compile",
                    "dependencies",
                    "describe",
                    "init",
                    "install",
                    "upgrade",
                ],
                "Runtime Commands:": [
                    "adduser",
                    "run",
                    "supervisor",
                    "zeoclient",
                    "zeoserver",
                ],
                "Database commands:": [
                    "db",
                ],
                "Test commands:": [
                    "robotserver",
                    "robottest",
                    "zopetest",
                ],
            },
        )

    autocomplete(parser)
    return parser
