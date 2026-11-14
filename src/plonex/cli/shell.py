"""Interactive access to the regular plonex CLI."""

from argcomplete import CompletionFinder
from argparse import ArgumentParser
from argparse import Namespace
from contextlib import chdir
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.cli.aliases import split_command
from plonex.cli.jobs import JOB_COMMANDS
from plonex.cli.jobs import ShellJobs
from plonex.cli.parser import build_parser
from plonex.inspection import redact_tokens
from plonex.services.invocation import ServiceInvocation
from typing import Iterator
from typing import Protocol

import os
import re
import shlex
import subprocess
import sys


class ShellCompleter:
    """Reuse argcomplete for command, subcommand, option, and path completion."""

    def __init__(self, parser: ArgumentParser, *, target: Path | None = None):
        self.finder = CompletionFinder(parser)
        self.target = target
        self.matches: list[str] = []

    def __call__(self, text: str, state: int) -> str | None:
        if state == 0:
            if self.target is not None:
                # A configuration edit should take effect without restarting the shell.
                try:
                    self.finder = CompletionFinder(
                        build_parser(for_completion=True, target=self.target)
                    )
                except SystemExit:
                    return None
            prefix = text[: len(text) - len(text.lstrip())]
            command = text.lstrip()
            for optional_prefix in ("plonex ", "help "):
                if command.startswith(optional_prefix):
                    prefix += optional_prefix
                    start = len(optional_prefix)
                    command = command[start:]
                    break

            self.matches = []
            if not any(char.isspace() for char in command):
                self.matches.extend(
                    prefix + name + " "
                    for name in ("exit", "quit", "help", "history", *JOB_COMMANDS)
                    if name.startswith(command)
                )

            # argcomplete disables option completion after --; reset it for each line.
            self.finder.always_complete_options = True
            index = 0
            while (match := self.finder.rl_complete(command, index)) is not None:
                candidate = prefix + match
                if candidate not in self.matches:
                    self.matches.append(candidate)
                index += 1

        return self.matches[state] if state < len(self.matches) else None


class HistoryReadline(Protocol):
    def add_history(self, line: str) -> None: ...


@dataclass
class CommandHistory:
    """Keep project-specific command history without storing known credentials."""

    target: Path
    entries: list[str] = field(default_factory=list)
    readline: HistoryReadline | None = None

    @property
    def path(self) -> Path:
        return self.target / "var" / "plonex-shell-history"

    def load(self) -> None:
        try:
            self.entries = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            self.entries = []
        except (OSError, UnicodeError) as exc:
            print(f"Cannot read shell history: {exc}", file=sys.stderr)

    def record(self, line: str) -> None:
        line = line.strip()
        if not line or line.startswith("#") or "\n" in line:
            return
        try:
            tokens = shlex.split(line)
        except ValueError:
            return
        if redact_tokens(tokens) != tokens or any(
            re.search(r"password|passwd|secret|token|api[_-]?key", token, re.I)
            for token in tokens
        ):
            return
        self.entries.append(line)
        if self.readline is not None:
            self.readline.add_history(line)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as history:
                os.fchmod(history.fileno(), 0o600)
                history.write(line + "\n")
        except OSError as exc:
            print(f"Cannot save shell history: {exc}", file=sys.stderr)

    def show(self) -> None:
        for number, line in enumerate(self.entries, 1):
            print(f"{number:5}  {line}")


@contextmanager
def line_editing(history: CommandHistory | None = None) -> Iterator[None]:
    """Enable session history and parser completion when readline is available."""
    if not sys.stdin.isatty():
        yield
        return
    try:
        import readline
    except ImportError:
        yield
        return

    previous_completer = readline.get_completer()
    previous_delimiters = readline.get_completer_delims()
    previous_history = []
    if history is not None:
        previous_history = [
            readline.get_history_item(index)
            for index in range(1, readline.get_current_history_length() + 1)
        ]
        readline.clear_history()
        for item in history.entries:
            readline.add_history(item)
        readline.set_auto_history(False)
        history.readline = readline
    try:
        readline.set_completer_delims("")
        readline.set_completer(
            ShellCompleter(build_parser(for_completion=True), target=Path.cwd())
        )
        binding = (
            "bind ^I rl_complete"
            if "libedit" in (readline.__doc__ or "")
            else "tab: complete"
        )
        readline.parse_and_bind(binding)
        yield
    finally:
        if history is not None:
            history.readline = None
            readline.clear_history()
            for item in previous_history:
                readline.add_history(item)
            readline.set_auto_history(True)
        readline.set_completer(previous_completer)
        readline.set_completer_delims(previous_delimiters)


@dataclass(kw_only=True)
class ShellSession:
    """One project prompt; services still execute in isolated CLI processes."""

    target: Path
    verbose: bool = False
    quiet: bool = False
    jobs: ShellJobs = field(init=False)
    history: CommandHistory = field(init=False)

    def run(self) -> None:
        print(f"plonex shell — {self.target}")
        print("Enter a command, help [command], or exit. Tab completes; Ctrl-D exits.")
        self.history = CommandHistory(self.target)
        self.history.load()
        with (
            chdir(self.target),
            ShellJobs(self.target) as self.jobs,
            line_editing(self.history),
        ):
            if self.jobs.enabled:
                print("Ctrl-Z returns to this prompt and leaves the command running.")
            self.prompt()

    def prompt(self) -> None:
        while True:
            try:
                line = input(f"plonex[{self.target.name}]> ")
            except EOFError:
                print()
                return
            except KeyboardInterrupt:
                print()
                continue
            try:
                self.history.record(line)
                if self.execute(line):
                    return
            except KeyboardInterrupt:
                print("\nCommand interrupted; returning to the prompt.")
            except SystemExit:
                # Configuration errors can be repaired while the prompt stays open.
                continue
            except (ValueError, OSError) as exc:
                print(str(exc), file=sys.stderr)

    def execute(self, line: str) -> bool:
        if not line.strip() or line.lstrip().startswith("#"):
            return False
        tokens = shlex.split(line)
        background = line.rstrip().endswith(" &")
        if background:
            tokens = tokens[:-1]
        if tokens and tokens[0] == "plonex":
            tokens = tokens[1:]
        if not tokens:
            return False
        if tokens[0] in {"exit", "quit"}:
            if len(tokens) == 1:
                return True
            print("Use exit or quit without arguments.", file=sys.stderr)
            return False
        if tokens[0] == "history":
            if len(tokens) == 1 and not background:
                self.history.show()
            else:
                print("Use history without arguments.", file=sys.stderr)
            return False
        if not background and self.jobs.builtin(tokens):
            return False
        command_target = split_command(tokens, self.target)[0]
        parser = build_parser(target=command_target)
        if tokens[0] == "help":
            if len(tokens) == 1:
                parser.print_help()
                print(
                    "Shell commands: help [command], history, exit, quit, "
                    "jobs, fg [JOB], attach [JOB], bg [JOB], "
                    "logs [JOB], kill [JOB], options [JOB|COMMAND]."
                )
                return False
            if len(tokens) == 2 and tokens[1] == "history":
                print("history lists this project’s saved shell commands.")
                return False
            if len(tokens) == 2 and tokens[1] in {"exit", "quit", "help"}:
                print(
                    "Use exit, quit, or Ctrl-D to leave; "
                    "help [command] displays command help."
                )
                return False
            if len(tokens) == 2 and tokens[1] in JOB_COMMANDS:
                if tokens[1] == "options":
                    print(
                        "options %1 shows a job's startup snapshot; "
                        "options COMMAND [flags] previews current service options. "
                        "Use --markdown for portable Markdown output."
                    )
                    return False
                print(
                    "jobs lists shell jobs; "
                    "attach/fg [JOB] returns to a job; "
                    "bg [JOB] keeps it running; "
                    "logs [JOB] shows recent output; "
                    "kill [JOB] stops it. Job IDs accept a % prefix."
                )
                return False
            tokens = tokens[1:] + ["--help"]

        try:
            args = parser.parse_args(tokens)
        except SystemExit:
            # argparse uses SystemExit for both help and usage errors.
            return False
        if args.action == "shell":
            print("You are already in a plonex shell.", file=sys.stderr)
            return False

        defaults = ["--target", str(self.target)]
        if not args.verbose and not args.quiet:
            if self.quiet:
                defaults.append("--quiet")
            elif self.verbose:
                defaults.append("--verbose")
        command = [sys.executable, "-m", "plonex.cli", *defaults, *tokens]
        display_tokens = redact_tokens(tokens)
        if args.action == "adduser" and args.password:
            display_tokens = [
                "[redacted]" if token == args.password else token
                for token in display_tokens
            ]
        if self.jobs.enabled or background:
            try:
                invocation = ServiceInvocation.from_args(args, command_target)
            except ValueError:
                invocation = None
            returncode = self.jobs.launch(
                command,
                shlex.join(display_tokens),
                background=background,
                invocation=invocation,
            )
        else:
            returncode = subprocess.run(
                command, cwd=self.target, check=False
            ).returncode
        if returncode:
            print(
                f"Command exited with status {returncode}.",
                file=sys.stderr,
            )
        return False


def run_shell(target: Path, *, verbose: bool = False, quiet: bool = False) -> None:
    """Compatibility entry point for the normal CLI handler."""
    ShellSession(target=target, verbose=verbose, quiet=quiet).run()


def _handle_shell(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    run_shell(target=target, verbose=args.verbose, quiet=args.quiet)


ACTION_HANDLERS = {
    "shell": _handle_shell,
}
