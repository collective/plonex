"""Project command aliases, expanded as argument lists rather than shell code."""

from argparse import ArgumentParser
from argparse import REMAINDER
from pathlib import Path
from plonex.base import BaseService
from plonex.cli.commands import validate_command_args
from typing import Any

import re
import shlex
import sys


def split_command(tokens: list[str], default_target: Path | None = None):
    """Read global options without mistaking a command's -t for --target."""
    probe = ArgumentParser(add_help=False)
    target = default_target or Path.cwd()
    # Incomplete flags are normal during completion; the real parser validates them.
    probe.add_argument("-t", "--target", nargs="?", const=target, default=target)
    for short, long in (("-v", "--verbose"), ("-q", "--quiet"), ("-V", "--version")):
        probe.add_argument(short, long, action="store_true")
    probe.add_argument("command", nargs=REMAINDER)
    args, _ = probe.parse_known_args(tokens)
    start = len(tokens) - len(args.command)
    return Path(args.target), tokens[:start], args.command


def normalize_aliases(raw: Any) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("The 'aliases' option must be a mapping of names to commands")
    aliases = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]*", name
        ):
            raise ValueError(f"Invalid command alias name: {name!r}")
        if isinstance(value, str):
            tokens = shlex.split(value)
        elif isinstance(value, list) and all(isinstance(token, str) for token in value):
            tokens = list(value)
        else:
            raise ValueError(
                f"Alias {name!r} must be a command string or list of tokens"
            )
        if tokens and tokens[0] == "plonex":
            tokens = tokens[1:]
        if not tokens or not tokens[0]:
            raise ValueError(f"Alias {name!r} must contain a command")
        aliases[name] = tokens
    return aliases


def load_aliases(target: Path) -> dict[str, list[str]]:
    target = target.expanduser().absolute()
    for root in (target, *target.parents):
        if (root / "etc" / "plonex.yml").is_file():
            options = BaseService(target=root).options
            return normalize_aliases(options.get("aliases"))
    return {}


def expand_aliases(tokens: list[str], aliases: dict[str, list[str]]) -> list[str]:
    expanded = list(tokens)
    seen: list[str] = []
    while True:
        _, prefix, command = split_command(expanded)
        if not command or command[0] not in aliases:
            return expanded
        name = command[0]
        if name in seen:
            raise ValueError("Command alias cycle: " + " -> ".join([*seen, name]))
        seen.append(name)
        expanded = [*prefix, *aliases[name], *command[1:]]


class AliasArgumentParser(ArgumentParser):
    """Expand aliases before normal parsing, including argcomplete parsing."""

    command_aliases: dict[str, list[str]]

    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        return validate_command_args(self, parsed)

    def parse_known_args(self, args=None, namespace=None):
        if getattr(self, "command_aliases", None):
            try:
                args = expand_aliases(
                    list(sys.argv[1:] if args is None else args), self.command_aliases
                )
            except ValueError as exc:
                self.error(str(exc))
        return super().parse_known_args(args, namespace)
