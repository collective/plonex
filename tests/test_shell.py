from .utils import temp_cwd
from argparse import Namespace
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from plonex.cli import main
from plonex.cli.parser import build_parser
from plonex.cli.shell import line_editing
from plonex.cli.shell import run_shell
from plonex.cli.shell import ShellCompleter
from unittest import mock

import io
import os
import subprocess
import sys
import unittest


class TestShell(unittest.TestCase):
    def setUp(self):
        self.target = self.enterContext(temp_cwd())
        self.stdout = self.enterContext(redirect_stdout(io.StringIO()))
        self.stderr = self.enterContext(redirect_stderr(io.StringIO()))
        self.enterContext(mock.patch("plonex.cli.shell.line_editing"))
        self.execute = self.enterContext(mock.patch("plonex.cli.shell.subprocess.run"))
        self.execute.return_value.returncode = 0

    def run_lines(self, *lines, **kwargs):
        with mock.patch("builtins.input", side_effect=[*lines, EOFError]):
            run_shell(self.target, **kwargs)

    def argv(self, *tokens):
        return [
            sys.executable,
            "-m",
            "plonex.cli",
            "--target",
            str(self.target),
            *tokens,
        ]

    def test_regular_commands_nested_actions_and_quoted_arguments(self):
        self.run_lines(
            "supervisor status",
            "test robot 'tests/my robot.robot' --test 'Login works'",
            'sources list "plone.*"',
            "instance run -- script.py --flag 'quoted value'",
        )
        expected = [
            self.argv("supervisor", "status"),
            self.argv("test", "robot", "tests/my robot.robot", "--test", "Login works"),
            self.argv("sources", "list", "plone.*"),
            self.argv("instance", "run", "--", "script.py", "--flag", "quoted value"),
        ]
        self.assertEqual(
            self.execute.call_args_list,
            [mock.call(command, cwd=self.target, check=False) for command in expected],
        )

    def test_global_defaults_and_per_command_overrides_do_not_leak(self):
        for setting, inherited, override in (
            ({"verbose": True}, "--verbose", "--quiet"),
            ({"quiet": True}, "--quiet", "--verbose"),
        ):
            with self.subTest(setting=setting):
                self.execute.reset_mock()
                self.run_lines(
                    "supervisor status",
                    f"supervisor status {override}",
                    "supervisor status",
                    **setting,
                )
                commands = [call.args[0] for call in self.execute.call_args_list]
                self.assertEqual(
                    commands,
                    [
                        self.argv(inherited, "supervisor", "status"),
                        self.argv("supervisor", "status", override),
                        self.argv(inherited, "supervisor", "status"),
                    ],
                )

    def test_target_override_is_per_command_and_plonex_prefix_is_optional(self):
        self.run_lines(
            "plonex --target /other/project supervisor status", "supervisor status"
        )
        commands = [call.args[0] for call in self.execute.call_args_list]
        self.assertEqual(
            commands,
            [
                self.argv("--target", "/other/project", "supervisor", "status"),
                self.argv("supervisor", "status"),
            ],
        )

    def test_help_errors_blank_lines_and_nested_shell_do_not_execute(self):
        self.run_lines(
            "",
            "   ",
            "# comment",
            "plonex",
            "help",
            "help exit",
            "help quit",
            "help dependencies install",
            "supervisor --help",
            "no-such-command",
            "dependencies install --bad-flag",
            "run 'unterminated",
            "shell",
            "exit invalid",
            "supervisor status",
        )
        self.assertEqual(self.execute.call_count, 1)
        self.assertIn("--persist-local", self.stdout.getvalue())
        self.assertIn("Shell commands:", self.stdout.getvalue())
        self.assertIn("invalid choice", self.stderr.getvalue())
        self.assertIn("No closing quotation", self.stderr.getvalue())
        self.assertIn("already in a plonex shell", self.stderr.getvalue())

    def test_exit_quit_and_eof_leave_without_running_more_commands(self):
        for ending in ("exit", "quit", EOFError):
            with self.subTest(ending=ending):
                self.run_lines(ending, "supervisor stop")
        self.execute.assert_not_called()

    def test_project_working_directory_is_restored_after_the_shell(self):
        with temp_cwd() as outside_project:

            def input_in_project(_prompt):
                self.assertEqual(Path.cwd(), self.target)
                return "exit"

            with mock.patch("builtins.input", side_effect=input_in_project):
                run_shell(self.target)
            self.assertEqual(Path.cwd(), outside_project)

    def test_interrupts_and_command_failures_return_to_prompt(self):
        self.execute.side_effect = [
            KeyboardInterrupt,
            OSError("cannot execute"),
            Namespace(returncode=3),
            Namespace(returncode=0),
        ]
        self.run_lines(KeyboardInterrupt, *["supervisor status"] * 4)
        self.assertEqual(self.execute.call_count, 4)
        self.assertIn("Command interrupted", self.stdout.getvalue())
        self.assertIn("cannot execute", self.stderr.getvalue())
        self.assertIn("status 3", self.stderr.getvalue())

    def test_url_fragments_and_shell_metacharacters_are_literal_arguments(self):
        self.run_lines(
            (
                "dependencies add 'Pkg @ "
                "git+https://example.org/Repo.git@Main#subdirectory=Dir'"
            ),
            "instance run script.py '$(touch marker)' ';' 'a|b' '$TOKEN'",
        )
        self.assertEqual(
            self.execute.call_args_list[0].args[0][-1],
            "Pkg @ git+https://example.org/Repo.git@Main#subdirectory=Dir",
        )
        self.assertEqual(
            self.execute.call_args_list[1].args[0][-4:],
            ["$(touch marker)", ";", "a|b", "$TOKEN"],
        )
        self.assertFalse((self.target / "marker").exists())

    def test_quoted_ampersand_is_an_argument_and_background_requires_a_terminal(self):
        self.run_lines(
            "instance run script.py '&'", "instance debug &", "supervisor status"
        )
        self.assertEqual(self.execute.call_count, 2)
        self.assertEqual(self.execute.call_args_list[0].args[0][-1], "&")
        self.assertIn("interactive terminal", self.stderr.getvalue())

    def test_explicit_background_start_does_not_resume_an_existing_job(self):
        with mock.patch("plonex.cli.shell.ShellJobs") as job_manager:
            jobs = job_manager.return_value.__enter__.return_value
            jobs.enabled = True
            jobs.launch.return_value = None
            self.run_lines("instance debug &", "instance debug &")
        jobs.builtin.assert_not_called()
        self.assertEqual(jobs.launch.call_count, 2)
        self.assertTrue(jobs.launch.call_args.kwargs["background"])


class TestShellCompletion(unittest.TestCase):
    def setUp(self):
        self.completer = ShellCompleter(build_parser(for_completion=True))

    def completions(self, text):
        matches = []
        for state in range(200):
            match = self.completer(text, state)
            if match is None:
                return matches
            matches.append(match.rstrip())
        self.fail("Completion did not terminate")

    def test_commands_builtins_subcommands_and_flags(self):
        for text, expected in (
            ("su", "supervisor"),
            ("ex", "exit"),
            ("qu", "quit"),
            ("he", "help"),
            ("supervisor st", "supervisor status"),
            ("dependencies sy", "dependencies sync"),
            ("--tar", "--target"),
            ("help sou", "help sources"),
            ("plonex su", "plonex supervisor"),
            ("  su", "  supervisor"),
            ("jo", "jobs"),
            ("atta", "attach"),
            ("lo", "logs"),
        ):
            with self.subTest(text=text):
                self.assertIn(expected, self.completions(text))

    def test_options_complete_again_after_previous_command_used_double_dash(self):
        self.completions("instance run -- script.py")
        self.assertIn(
            "dependencies install --update-sources",
            self.completions("dependencies install --up"),
        )

    def test_path_completion(self):
        with temp_cwd() as cwd:
            (cwd / "robot-test.robot").touch()
            self.assertIn(
                "test robot robot-test.robot", self.completions("test robot rob")
            )


class TestLineEditing(unittest.TestCase):
    def test_readline_settings_are_restored_even_on_error(self):
        for backend in ("GNU readline", "libedit readline"):
            with self.subTest(backend=backend):
                readline = mock.Mock()
                readline.__doc__ = backend
                with (
                    mock.patch("sys.stdin.isatty", return_value=True),
                    mock.patch.dict(sys.modules, {"readline": readline}),
                ):
                    with self.assertRaisesRegex(RuntimeError, "example"):
                        with line_editing():
                            raise RuntimeError("example")
                readline.set_completer.assert_called_with(
                    readline.get_completer.return_value
                )
                readline.set_completer_delims.assert_called_with(
                    readline.get_completer_delims.return_value
                )
                binding = (
                    "bind ^I rl_complete" if "libedit" in backend else "tab: complete"
                )
                readline.parse_and_bind.assert_called_once_with(binding)

    def test_shell_operates_without_readline(self):
        with (
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch.dict(sys.modules, {"readline": None}),
        ):
            with line_editing():
                pass


class TestShellProcess(unittest.TestCase):
    def test_real_shell_reloads_config_and_keeps_command_environment_isolated(self):
        self.check_real_session(default_action=False)

    def test_default_shell_reloads_config_and_keeps_command_environment_isolated(self):
        self.check_real_session(default_action=True)

    def check_real_session(self, *, default_action):
        with temp_cwd() as target:
            (target / "etc").mkdir()
            config = target / "etc" / "plonex.yml"
            config.write_text(
                ("default_action: shell\n" if default_action else "")
                + "environment_vars:\n  PLONEX_SHELL_TEST_VAR: from-config\n"
            )
            script = target / "inspect-shell.py"
            script.write_text(
                "import os\n"
                "from pathlib import Path\n"
                "from plonex.base import BaseService\n"
                "with BaseService() as service:\n"
                "    print('ENV=' + os.environ.get('PLONEX_SHELL_TEST_VAR', 'unset'))\n"
                "Path('etc/plonex.yml').write_text('{}\\n')\n"
            )
            commands = "\n".join(
                [
                    "instance run inspect-shell.py",
                    "instance run inspect-shell.py",
                    "no-such-command",
                    "--version",
                    "exit",
                    "",
                ]
            )
            # Stand in for Zope while exercising the real CLI and configuration.
            executable_folder = target / ".venv" / "bin"
            executable_folder.mkdir(parents=True)
            (executable_folder / "activate").touch()
            zconsole = executable_folder / "zconsole"
            zconsole.write_text(
                f"#!{sys.executable}\n"
                "import runpy, sys\n"
                "runpy.run_path(sys.argv[3], run_name='__main__')\n"
            )
            zconsole.chmod(0o755)
            env = dict(os.environ)
            env.pop("PLONEX_SHELL_TEST_VAR", None)
            result = subprocess.run(
                [sys.executable, "-m", "plonex.cli"]
                + ([] if default_action else ["shell"]),
                input=commands,
                text=True,
                capture_output=True,
                cwd=target,
                env=env,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ENV=from-config", result.stdout, result.stderr)
            self.assertIn("ENV=unset", result.stdout, result.stderr)
            self.assertIn("invalid choice", result.stderr)

    def test_shell_can_be_the_configured_default_action(self):
        with temp_cwd() as target:
            (target / "etc").mkdir()
            (target / "etc" / "plonex.yml").write_text("default_action: shell\n")
            with (
                mock.patch.object(sys, "argv", ["plonex"]),
                mock.patch("plonex.cli.run_shell") as shell,
            ):
                main()
            shell.assert_called_once_with(target=target, verbose=False, quiet=False)
