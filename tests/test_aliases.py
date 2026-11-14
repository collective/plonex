from .utils import temp_cwd
from argparse import Namespace
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from plonex.cli import main
from plonex.cli.aliases import expand_aliases
from plonex.cli.aliases import load_aliases
from plonex.cli.aliases import normalize_aliases
from plonex.cli.aliases import split_command
from plonex.cli.parser import build_parser
from plonex.cli.shell import run_shell
from plonex.cli.shell import ShellCompleter
from unittest import mock

import io
import sys
import unittest


class TestAliases(unittest.TestCase):
    def setUp(self):
        self.target = self.enterContext(temp_cwd())
        (self.target / "etc").mkdir()
        self.config = self.target / "etc" / "plonex.yml"
        self.config.write_text(
            (
                "aliases:\n  start: supervisor start\n  test_whatever: test "
                "pytest my.package\n  chained: start\n"
            )
        )

    def test_string_token_list_optional_prefix_and_quoted_values(self):
        self.assertEqual(
            normalize_aliases(
                {
                    "start": "plonex supervisor start",
                    "tests": ["test", "pytest", "my.package", "-k", "two words"],
                    "filter": "test pytest my.package -k 'two words'",
                }
            ),
            {
                "start": ["supervisor", "start"],
                "tests": ["test", "pytest", "my.package", "-k", "two words"],
                "filter": ["test", "pytest", "my.package", "-k", "two words"],
            },
        )
        self.assertEqual(normalize_aliases(None), {})

    def test_invalid_definitions_fail_with_actionable_errors(self):
        for value in (
            [],
            {"": "supervisor start"},
            {"two words": "supervisor start"},
            {"bad": ""},
            {"bad": []},
            {"bad": "plonex"},
            {"bad": 42},
            {"bad": ["test", "pytest", 42]},
            {False: "supervisor start"},
            {"bad": "pytest 'unterminated"},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_aliases(value)

    def test_target_detection_does_not_consume_a_test_filter_or_pytest_options(self):
        for tokens, expected in (
            (["--target", "/project", "start"], Path("/project")),
            (["--target=/project", "-v", "start"], Path("/project")),
            (["-t/project", "start"], Path("/project")),
            (["-qv", "start"], self.target),
            (["test", "zope", "my.package", "-t", "my_filter"], self.target),
            (["test", "pytest", "my.package", "--target", "plugin_value"], self.target),
        ):
            with self.subTest(tokens=tokens):
                self.assertEqual(split_command(tokens, self.target)[0], expected)

    def test_extra_arguments_chains_global_options_and_original_tokens_are_preserved(
        self,
    ):
        aliases = load_aliases(self.target)
        tokens = ["--target", str(self.target), "-q", "chained", "--verbose"]
        original = list(tokens)
        self.assertEqual(
            expand_aliases(tokens, aliases),
            [
                "--target",
                str(self.target),
                "-q",
                "supervisor",
                "start",
                "--verbose",
            ],
        )
        self.assertEqual(tokens, original)
        self.assertEqual(
            expand_aliases(["test_whatever", "-k", "a or b"], aliases),
            ["test", "pytest", "my.package", "-k", "a or b"],
        )

    def test_cycles_are_detected_even_with_global_options_in_the_alias(self):
        aliases = {"a": ["-q", "b"], "b": ["a"]}
        with self.assertRaisesRegex(ValueError, "a -> b -> a"):
            expand_aliases(["a"], aliases)

    def test_parser_expands_aliases_before_validating_arguments(self):
        parser = build_parser(target=self.target)
        start = parser.parse_args(["start", "-v"])
        self.assertEqual(start.action, "supervisor")
        self.assertEqual(start.supervisor_action, "start")
        self.assertTrue(start.verbose)
        tests = parser.parse_args(["test_whatever", "-k", "login", "-v"])
        self.assertEqual(tests.action, "pytest")
        self.assertEqual(tests.package, "my.package")
        self.assertEqual(tests.pytest_args, ["-k", "login", "-v"])
        self.assertFalse(tests.verbose)

    def test_aliases_appear_in_help_and_complete_the_expanded_command(self):
        parser = build_parser(target=self.target)
        self.assertIn("Project aliases:", parser.format_help())
        self.assertIn("Alias for: supervisor start", parser.format_help())
        completer = ShellCompleter(
            build_parser(for_completion=True, target=self.target)
        )
        for text, expected in (("sta", "start"), ("start --v", "start --verbose")):
            with self.subTest(text=text):
                self.assertEqual(completer(text, 0).rstrip(), expected)

    def test_external_completion_loads_aliases_from_the_explicit_target(self):
        with (
            temp_cwd(),
            mock.patch.dict(
                "os.environ",
                {
                    "_ARGCOMPLETE": "1",
                    "COMP_LINE": f"plonex --target {self.target} sta",
                },
            ),
            mock.patch("plonex.cli.parser.autocomplete"),
        ):
            parser = build_parser()
            self.assertEqual(parser.parse_args(["start"]).action, "supervisor")

    def test_completion_accepts_an_incomplete_target_flag(self):
        self.assertEqual(split_command(["--target"], self.target)[0], self.target)

    def test_builtin_and_shell_commands_cannot_be_overridden(self):
        for name in (
            "supervisor",
            "test",
            "shell",
            "exit",
            "quit",
            "help",
            "plonex",
            "jobs",
            "attach",
            "bg",
            "logs",
            "kill",
        ):
            self.config.write_text(f"aliases:\n  {name}: supervisor start\n")
            with self.subTest(name=name), redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as exc:
                    build_parser(target=self.target)
                self.assertEqual(exc.exception.code, 2)
                self.assertIn("conflicts with a built-in command", errors.getvalue())

    def test_profiles_local_overrides_and_child_directory_discovery(self):
        profile = self.target / "profiles" / "base"
        (profile / "etc").mkdir(parents=True)
        (profile / "etc" / "plonex.yml").write_text(
            "aliases:\n  start: supervisor start\n  tests: test pytest base.package\n"
        )
        self.config.write_text("profiles: [profiles/base]\n")
        (self.target / "etc" / "plonex.local.yml").write_text(
            "+aliases:\n  tests: test pytest local.package\n  stop: supervisor stop\n"
        )
        subdirectory = self.target / "src"
        subdirectory.mkdir()
        self.assertEqual(
            load_aliases(subdirectory),
            {
                "start": ["supervisor", "start"],
                "tests": ["test", "pytest", "local.package"],
                "stop": ["supervisor", "stop"],
            },
        )

    def test_main_uses_aliases_for_an_explicit_target(self):
        with (
            mock.patch.object(
                sys, "argv", ["plonex", "--target", str(self.target), "start"]
            ),
            mock.patch("plonex.cli.runtime._run_service_dependencies"),
            mock.patch("plonex.cli.runtime.Supervisor") as supervisor,
            mock.patch("plonex.preparation.supervisor.SupervisorPreparation"),
        ):
            main()
        supervisor.return_value.__enter__.return_value.run.assert_called_once()

    def test_default_actions_can_refer_to_aliases(self):
        self.config.write_text(self.config.read_text() + "default_action: start\n")
        with (
            mock.patch.object(sys, "argv", ["plonex"]),
            mock.patch("plonex.cli.runtime._run_service_dependencies"),
            mock.patch("plonex.cli.runtime.Supervisor") as supervisor,
            mock.patch("plonex.preparation.supervisor.SupervisorPreparation"),
        ):
            main()
        supervisor.return_value.__enter__.return_value.run.assert_called_once()

    def test_shell_picks_up_new_aliases_without_restarting(self):
        responses = iter(["supervisor status", "added", "exit"])

        def next_input(_prompt):
            line = next(responses)
            if line == "added":
                self.config.write_text("aliases:\n  added: supervisor status\n")
            return line

        with (
            mock.patch("plonex.cli.shell.line_editing"),
            mock.patch("builtins.input", side_effect=next_input),
            mock.patch(
                "plonex.cli.shell.subprocess.run", return_value=Namespace(returncode=0)
            ) as execute,
            redirect_stdout(io.StringIO()),
        ):
            run_shell(self.target)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(execute.call_args.args[0][-1], "added")

    def test_completion_reloads_aliases_after_a_configuration_edit(self):
        completer = ShellCompleter(
            build_parser(for_completion=True, target=self.target), target=self.target
        )
        self.assertEqual(completer("sta", 0).strip(), "start")
        self.config.write_text("aliases:\n  added: supervisor status\n")
        self.assertEqual(completer("adde", 0).strip(), "added")

    def test_invalid_alias_edits_do_not_close_shell_or_break_later_completion(self):
        responses = iter(["supervisor status", "invalid", "added", "exit"])

        def next_input(_prompt):
            line = next(responses)
            if line == "invalid":
                self.config.write_text("aliases: [invalid]\n")
            elif line == "added":
                self.config.write_text("aliases:\n  added: supervisor status\n")
            return line

        completer = ShellCompleter(
            build_parser(for_completion=True, target=self.target), target=self.target
        )
        self.config.write_text("aliases: [invalid]\n")
        with redirect_stderr(io.StringIO()):
            self.assertIsNone(completer("sta", 0))
        self.config.write_text("{}\n")
        with (
            mock.patch("plonex.cli.shell.line_editing"),
            mock.patch("builtins.input", side_effect=next_input),
            mock.patch(
                "plonex.cli.shell.subprocess.run", return_value=Namespace(returncode=0)
            ) as execute,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            run_shell(self.target)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(completer("adde", 0).strip(), "added")

    def test_shell_recovers_from_an_alias_cycle(self):
        self.config.write_text("aliases:\n  a: b\n  b: a\n")
        with (
            mock.patch("plonex.cli.shell.line_editing"),
            mock.patch(
                "builtins.input", side_effect=["a", "supervisor status", "exit"]
            ),
            mock.patch(
                "plonex.cli.shell.subprocess.run", return_value=Namespace(returncode=0)
            ) as execute,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as errors,
        ):
            run_shell(self.target)
        self.assertEqual(execute.call_count, 1)
        self.assertIn("alias cycle", errors.getvalue())
