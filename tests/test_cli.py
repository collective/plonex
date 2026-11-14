from .utils import temp_cwd
from argparse import ArgumentParser
from importlib.metadata import version
from pathlib import Path
from plonex.base import BaseService
from plonex.cli import _configure_logging
from plonex.cli import _resolve_target
from plonex.cli import build_parser
from plonex.cli import main
from plonex.cli.dependencies import _service_from_config
from runpy import run_path
from types import SimpleNamespace
from unittest import mock

import logging
import sys
import unittest


def _args(**kwargs):
    """Build a minimal namespace as if argparse had parsed the given flags."""
    defaults = {
        "action": None,
        "target": str(Path.cwd()),
        "verbose": False,
        "quiet": False,
        "version": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestBuildParser(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.parser = build_parser()

    def test_returns_argument_parser(self):
        self.assertIsInstance(self.parser, ArgumentParser)

    def test_prog(self):
        self.assertEqual(self.parser.prog, "plonex")

    def test_help_contains_command_categories(self):
        help_text = self.parser.format_help()
        self.assertIn("Positional Arguments:", help_text)
        self.assertIn("Setup and information commands:", help_text)
        self.assertIn("Runtime Commands:", help_text)
        self.assertIn("Test commands:", help_text)

    def test_help_grouping_disabled_during_argcomplete(self):
        with mock.patch("plonex.cli.autocomplete"):
            with mock.patch.dict("os.environ", {"_ARGCOMPLETE": "1"}, clear=False):
                parser = build_parser()
        help_text = parser.format_help()
        self.assertNotIn("Setup and information commands:", help_text)

    def test_top_level_flags(self):
        args = self.parser.parse_args(["-v"])
        self.assertTrue(args.verbose)

        args = self.parser.parse_args(["-q"])
        self.assertTrue(args.quiet)

        args = self.parser.parse_args(["-V"])
        self.assertTrue(args.version)

    def test_verbose_flag_after_top_level_command(self):
        args = self.parser.parse_args(["project", "compile", "-v"])
        self.assertEqual(args.action, "compile")
        self.assertTrue(args.verbose)

    def test_verbose_flag_after_nested_command(self):
        args = self.parser.parse_args(["supervisor", "status", "-v"])
        self.assertEqual(args.action, "supervisor")
        self.assertEqual(args.supervisor_action, "status")
        self.assertTrue(args.verbose)

    def test_quiet_flag_after_top_level_command(self):
        args = self.parser.parse_args(["project", "compile", "-q"])
        self.assertEqual(args.action, "compile")
        self.assertTrue(args.quiet)

    def test_quiet_flag_after_nested_command(self):
        args = self.parser.parse_args(["supervisor", "status", "-q"])
        self.assertEqual(args.action, "supervisor")
        self.assertEqual(args.supervisor_action, "status")
        self.assertTrue(args.quiet)

    def test_target_flag(self):
        args = self.parser.parse_args(["-t", "/some/path", "project", "compile"])
        self.assertEqual(args.target, "/some/path")

    # --- subcommands ---

    def test_action_init(self):
        args = self.parser.parse_args(["project", "init", "/tmp/project"])
        self.assertEqual(args.action, "init")
        self.assertEqual(args.target, "/tmp/project")

    def test_action_init_without_target(self):
        args = self.parser.parse_args(["project", "init"])
        self.assertEqual(args.action, "init")
        self.assertIsNone(args.target)

    def test_action_compile(self):
        args = self.parser.parse_args(["project", "compile"])
        self.assertEqual(args.action, "compile")

    def test_action_shell_accepts_global_flags_on_either_side(self):
        for tokens in (
            ["--target", "/my/project", "--verbose", "shell"],
            ["shell", "--target", "/my/project", "--verbose"],
        ):
            with self.subTest(tokens=tokens):
                args = self.parser.parse_args(tokens)
                self.assertEqual(args.action, "shell")
                self.assertEqual(args.target, "/my/project")
                self.assertTrue(args.verbose)

    def test_action_describe(self):
        args = self.parser.parse_args(["project", "describe"])
        self.assertEqual(args.action, "describe")

    def test_action_robotserver_default_layer(self):
        args = self.parser.parse_args(["test", "robot-server"])
        self.assertEqual(args.action, "robotserver")
        self.assertIn("ROBOT_TESTING", args.layer)

    def test_action_robotserver_custom_layer(self):
        args = self.parser.parse_args(
            ["test", "robot-server", "-l", "my.layer.TESTING"]
        )
        self.assertEqual(args.layer, "my.layer.TESTING")

    def test_action_robottest(self):
        args = self.parser.parse_args(["test", "robot", "tests/robot/test_login.robot"])
        self.assertEqual(args.action, "robottest")
        self.assertEqual(args.paths, ["tests/robot/test_login.robot"])
        self.assertEqual(args.browser, "firefox")

    def test_action_zopetest(self):
        args = self.parser.parse_args(["test", "zope", "my.package"])
        self.assertEqual(args.action, "zopetest")
        self.assertEqual(args.package, "my.package")

    def test_action_install(self):
        args = self.parser.parse_args(
            ["dependencies", "add", "my.package", "other.package"]
        )
        self.assertEqual(args.action, "install")
        self.assertEqual(args.package, ["my.package", "other.package"])

    def test_action_upgrade(self):
        args = self.parser.parse_args(["db", "upgrade"])
        self.assertEqual(args.action, "upgrade")

    def test_action_supervisor_default(self):
        args = self.parser.parse_args(["supervisor"])
        self.assertEqual(args.action, "supervisor")
        self.assertIsNone(args.supervisor_action)

    def test_action_supervisor_subcommands(self):
        for sub in ("start", "stop", "restart", "status", "graceful"):
            args = self.parser.parse_args(["supervisor", sub])
            self.assertEqual(args.supervisor_action, sub)

    def test_action_supervisor_graceful_interval(self):
        args = self.parser.parse_args(["supervisor", "graceful", "--interval", "2.5"])
        self.assertEqual(args.supervisor_action, "graceful")
        self.assertEqual(args.graceful_interval, 2.5)

    def test_action_supervisor_graceful_interval_omitted(self):
        args = self.parser.parse_args(["supervisor", "graceful"])
        self.assertEqual(args.supervisor_action, "graceful")
        self.assertIsNone(args.graceful_interval)

    def test_action_zeoserver(self):
        args = self.parser.parse_args(["db", "start"])
        self.assertEqual(args.action, "zeoserver")

    def test_action_runwsgi_defaults(self):
        args = self.parser.parse_args(["instance", "start"])
        self.assertEqual(args.action, "runwsgi")
        self.assertEqual(args.name, "runwsgi")
        self.assertEqual(args.port, 0)
        self.assertEqual(args.host, "")

    def test_action_runwsgi_options(self):
        args = self.parser.parse_args(
            ["instance", "start", "-n", "app1", "-p", "8082", "--host", "127.0.0.1"]
        )
        self.assertEqual(args.name, "app1")
        self.assertEqual(args.port, 8082)
        self.assertEqual(args.host, "127.0.0.1")

    def test_action_fg_defaults(self):
        args = self.parser.parse_args(["instance", "debug"])
        self.assertEqual(args.action, "fg")
        self.assertEqual(args.name, "fg")
        self.assertEqual(args.port, 0)
        self.assertEqual(args.host, "")

    def test_action_fg_options(self):
        args = self.parser.parse_args(
            ["instance", "debug", "-n", "app1", "-p", "8082", "--host", "127.0.0.1"]
        )
        self.assertEqual(args.name, "app1")
        self.assertEqual(args.port, 8082)
        self.assertEqual(args.host, "127.0.0.1")

    def test_action_console_is_interactive_only(self):
        args = self.parser.parse_args(["instance", "console"])
        self.assertEqual(args.action, "zconsole")
        for action in ("debug", "run"):
            with self.assertRaises(SystemExit):
                self.parser.parse_args(["instance", "console", action])

    def test_action_run(self):
        args = self.parser.parse_args(["instance", "run", "script.py"])
        self.assertEqual(args.action, "run")
        self.assertEqual(args.args, ["script.py"])

    def test_action_adduser(self):
        args = self.parser.parse_args(["instance", "add-user", "admin", "secret"])
        self.assertEqual(args.action, "adduser")
        self.assertEqual(args.username, "admin")
        self.assertEqual(args.password, "secret")

    def test_action_adduser_no_password(self):
        args = self.parser.parse_args(["instance", "add-user", "admin"])
        self.assertIsNone(args.password)

    def test_action_db_default(self):
        args = self.parser.parse_args(["db"])
        self.assertEqual(args.action, "db")
        self.assertIsNone(args.db_action)

    def test_action_db_backup(self):
        args = self.parser.parse_args(["db", "backup"])
        self.assertEqual(args.action, "db")
        self.assertEqual(args.db_action, "backup")

    def test_action_db_restore(self):
        args = self.parser.parse_args(["db", "restore"])
        self.assertEqual(args.action, "db")
        self.assertEqual(args.db_action, "restore")

    def test_action_db_pack_default_days(self):
        args = self.parser.parse_args(["db", "pack"])
        self.assertEqual(args.action, "db")
        self.assertEqual(args.db_action, "pack")
        self.assertEqual(args.days, 7)

    def test_action_db_pack_custom_days(self):
        args = self.parser.parse_args(["db", "pack", "-d", "3"])
        self.assertEqual(args.days, 3)

    def test_action_dependencies(self):
        args = self.parser.parse_args(["dependencies", "install"])
        self.assertEqual(args.action, "dependencies")
        self.assertIsNone(args.persist_mode)

    def test_action_dependencies_persist(self):
        args = self.parser.parse_args(["dependencies", "install", "--persist"])
        self.assertEqual(args.persist_mode, "project")

    def test_action_dependencies_persist_local(self):
        args = self.parser.parse_args(["dependencies", "install", "--persist-local"])
        self.assertEqual(args.persist_mode, "local")

    def test_action_dependencies_persist_profile(self):
        args = self.parser.parse_args(["dependencies", "install", "--persist-profile"])
        self.assertEqual(args.persist_mode, "profile")

    def test_action_dependencies_update_sources(self):
        args = self.parser.parse_args(["dependencies", "install", "--update-sources"])
        self.assertEqual(args.action, "dependencies")
        self.assertTrue(args.update_sources)

    def test_action_dependencies_sync(self):
        args = self.parser.parse_args(["dependencies", "sync"])
        self.assertEqual(args.action, "dependencies")
        self.assertTrue(args.sync)

    def test_action_sources_default(self):
        args = self.parser.parse_args(["sources"])
        self.assertEqual(args.action, "sources")
        self.assertIsNone(args.sources_action)

    def test_action_sources_update(self):
        args = self.parser.parse_args(["sources", "update"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "update")
        self.assertIsNone(args.glob)

    def test_action_sources_update_with_glob(self):
        args = self.parser.parse_args(["sources", "update", "foo"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "update")
        self.assertEqual(args.glob, "foo")

    def test_action_sources_force_update(self):
        args = self.parser.parse_args(["sources", "update", "--force", "--yes"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "update")
        self.assertTrue(args.sources_yes)

    def test_action_sources_tainted(self):
        args = self.parser.parse_args(["sources", "tainted"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "tainted")
        self.assertIsNone(args.glob)

    def test_action_sources_list(self):
        args = self.parser.parse_args(["sources", "list"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "list")
        self.assertIsNone(args.glob)

    def test_action_sources_missing(self):
        args = self.parser.parse_args(["sources", "missing"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "missing")
        self.assertIsNone(args.glob)

    def test_action_sources_clone_missing(self):
        args = self.parser.parse_args(["sources", "clone"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "clone")
        self.assertIsNone(args.glob)

    def test_action_sources_clone_missing_yes(self):
        args = self.parser.parse_args(["sources", "clone", "--yes"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "clone")
        self.assertTrue(args.sources_yes)
        self.assertIsNone(args.glob)

    def test_action_sources_suggest_existing(self):
        args = self.parser.parse_args(["sources", "suggest"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "suggest")

    def test_action_sources_suggest_existing_apply_local(self):
        args = self.parser.parse_args(["sources", "suggest", "--apply-local"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "suggest")
        self.assertTrue(args.sources_apply_local)

    def test_action_sources_suggest_existing_apply(self):
        args = self.parser.parse_args(["sources", "suggest", "--apply"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "suggest")
        self.assertTrue(args.sources_apply)

    def test_action_sources_suggest_existing_apply_profile(self):
        args = self.parser.parse_args(["sources", "suggest", "--apply-profile"])
        self.assertEqual(args.action, "sources")
        self.assertEqual(args.sources_action, "suggest")
        self.assertTrue(args.sources_apply_profile)


class TestResolveTarget(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.temp_dir = self.enterContext(temp_cwd())
        self.mock_logger = self.enterContext(mock.patch("plonex.cli.logger"))

    def test_nonexistent_target_exits(self):
        args = _args(target=str(self.temp_dir / "nowhere"))
        with self.assertRaises(SystemExit) as cm:
            _resolve_target(args)
        self.assertEqual(cm.exception.code, 1)

    def test_no_plonex_yml_exits(self):
        args = _args(target=str(self.temp_dir))
        with self.assertRaises(SystemExit) as cm:
            _resolve_target(args)
        self.assertEqual(cm.exception.code, 1)

    def test_finds_plonex_yml_in_target(self):
        etc = self.temp_dir / "etc"
        etc.mkdir()
        (etc / "plonex.yml").write_text("---")
        args = _args(target=str(self.temp_dir))
        result = _resolve_target(args)
        self.assertEqual(result, self.temp_dir.resolve())

    def test_finds_plonex_yml_in_parent(self):
        etc = self.temp_dir / "etc"
        etc.mkdir()
        (etc / "plonex.yml").write_text("---")
        subdir = self.temp_dir / "sub" / "dir"
        subdir.mkdir(parents=True)
        args = _args(target=str(subdir))
        result = _resolve_target(args)
        self.assertEqual(result, self.temp_dir.resolve())

    def test_returns_absolute_path(self):
        etc = self.temp_dir / "etc"
        etc.mkdir()
        (etc / "plonex.yml").write_text("---")
        args = _args(target=str(self.temp_dir))
        result = _resolve_target(args)
        self.assertTrue(result.is_absolute())


class TestConfigureLogging(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.temp_dir = self.enterContext(temp_cwd())
        # Restore logger level after each test
        from plonex import logger as plonex_logger

        self._original_level = plonex_logger.level
        self.addCleanup(plonex_logger.setLevel, self._original_level)
        self._command_output_enabled = BaseService.command_output_enabled
        self.addCleanup(
            setattr,
            BaseService,
            "command_output_enabled",
            self._command_output_enabled,
        )

    def test_verbose_sets_debug(self):
        from plonex import logger as plonex_logger

        _configure_logging(_args(verbose=True), self.temp_dir)
        self.assertEqual(plonex_logger.level, logging.DEBUG)

    def test_quiet_sets_warning(self):
        from plonex import logger as plonex_logger

        _configure_logging(_args(quiet=True), self.temp_dir)
        self.assertEqual(plonex_logger.level, logging.WARNING)
        self.assertFalse(BaseService.command_output_enabled)

    def test_default_enables_command_output(self):
        BaseService.command_output_enabled = False
        _configure_logging(_args(), self.temp_dir)
        self.assertTrue(BaseService.command_output_enabled)

    def test_config_file_log_level(self):
        from plonex import logger as plonex_logger

        with mock.patch("plonex.cli.InitService") as MockInit:
            MockInit.return_value.__enter__ = mock.Mock(
                return_value=MockInit.return_value
            )
            MockInit.return_value.__exit__ = mock.Mock(return_value=False)
            MockInit.return_value.options = {"log_level": "DEBUG"}
            _configure_logging(_args(), self.temp_dir)
        self.assertEqual(plonex_logger.level, logging.DEBUG)

    def test_config_file_invalid_log_level_logs_error(self):
        with mock.patch("plonex.cli.InitService") as MockInit:
            MockInit.return_value.__enter__ = mock.Mock(
                return_value=MockInit.return_value
            )
            MockInit.return_value.__exit__ = mock.Mock(return_value=False)
            MockInit.return_value.options = {"log_level": "BOGUS"}
            with mock.patch("plonex.cli.logger") as mock_logger:
                _configure_logging(_args(), self.temp_dir)
        mock_logger.error.assert_called_once()


class TestMain(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.temp_dir = self.enterContext(temp_cwd())
        self.preparation = self.enterContext(
            mock.patch("plonex.preparation.supervisor.SupervisorPreparation")
        )

    def _run(self, argv):
        with mock.patch.object(sys, "argv", ["plonex"] + argv):
            main()

    def test_version_flag(self):
        with mock.patch("builtins.print") as mock_print:
            self._run(["-V"])
        mock_print.assert_called_once_with(version("plonex"))

    def test_no_action_prints_help_by_default(self):
        with mock.patch("plonex.cli._resolve_target") as mock_rt:
            with mock.patch("plonex.cli._configure_logging"):
                with mock.patch("plonex.cli._load_default_actions") as mock_defaults:
                    with mock.patch("argparse.ArgumentParser.print_help") as mock_help:
                        mock_rt.return_value = self.temp_dir
                        mock_defaults.return_value = None
                        self._run([])
        mock_help.assert_called_once()

    def test_no_action_runs_configured_default_actions(self):
        etc = self.temp_dir / "etc"
        etc.mkdir(exist_ok=True)
        (etc / "plonex.yml").write_text(
            "\n".join(
                [
                    "default_actions:",
                    "  - supervisor start",
                    "  - instance start",
                    "",
                ]
            )
        )
        with mock.patch("plonex.cli._configure_logging"):
            with mock.patch(
                "plonex.cli.runtime._run_service_dependencies"
            ) as mock_deps:
                with mock.patch("plonex.cli.runtime.Supervisor") as MockSupervisor:
                    with mock.patch("plonex.cli.runtime.RunWSGI") as MockRunWSGI:
                        MockSupervisor.return_value.__enter__ = mock.Mock(
                            return_value=MockSupervisor.return_value
                        )
                        MockSupervisor.return_value.__exit__ = mock.Mock(
                            return_value=False
                        )
                        MockRunWSGI.return_value.__enter__ = mock.Mock(
                            return_value=MockRunWSGI.return_value
                        )
                        MockRunWSGI.return_value.__exit__ = mock.Mock(
                            return_value=False
                        )
                        with mock.patch.object(
                            sys, "argv", ["plonex", "-t", str(self.temp_dir)]
                        ):
                            main()
        self.assertEqual(
            mock_deps.call_args_list,
            [mock.call(self.temp_dir.resolve(), "runwsgi")],
        )
        MockSupervisor.return_value.run.assert_called_once()
        MockRunWSGI.return_value.run.assert_called_once()

    def test_action_init(self):
        target_str = str(self.temp_dir)
        with mock.patch("plonex.cli.InitService") as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run(["project", "init", target_str])
        MockSvc.assert_called_once_with(target=self.temp_dir)
        MockSvc.return_value.run.assert_called_once()

    def test_action_init_prompts_for_target(self):
        with mock.patch("plonex.cli.Console") as MockConsole:
            with mock.patch("plonex.cli.InitService") as MockSvc:
                MockConsole.return_value.input.return_value = ""
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                with mock.patch("pathlib.Path.cwd", return_value=self.temp_dir):
                    self._run(["project", "init"])
        MockConsole.return_value.input.assert_called_once_with(
            f"Please select the target folder (default: {self.temp_dir}): "
        )
        MockSvc.assert_called_once_with(target=self.temp_dir)
        MockSvc.return_value.run.assert_called_once()

    def _run_with_target(self, argv):
        """Helper: set up a valid target dir and run main with that --target."""
        etc = self.temp_dir / "etc"
        etc.mkdir(exist_ok=True)
        (etc / "plonex.yml").write_text("---")
        with mock.patch("plonex.cli._configure_logging"):
            with mock.patch.object(
                sys, "argv", ["plonex", "-t", str(self.temp_dir)] + argv
            ):
                main()

    def _run_service(self, argv, service_path):
        """Run main with a mocked service, return the mock."""
        with mock.patch(service_path) as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run_with_target(argv)
        return MockSvc

    def test_action_compile(self):
        svc = self._run_service(
            ["project", "compile"], "plonex.cli.setup_info.CompileService"
        )
        svc.return_value.run.assert_called_once()

    def test_shell_dispatch_preserves_target_and_flags_without_loading_environment(
        self,
    ):
        with (
            mock.patch("plonex.cli.shell.run_shell") as shell,
            mock.patch("plonex.cli.InitService") as init,
        ):
            self._run_with_target(["shell", "--verbose"])
        shell.assert_called_once_with(
            target=self.temp_dir.resolve(), verbose=True, quiet=False
        )
        init.assert_not_called()

    def test_invalid_constraints_exit_cleanly_for_explicit_and_default_actions(self):
        for argv, defaults in [
            (["dependencies", "install"], None),
            ([], [["dependencies", "install"]]),
        ]:
            with (
                self.subTest(argv=argv),
                mock.patch("plonex.cli._load_default_actions", return_value=defaults),
                mock.patch(
                    "plonex.cli._dispatch",
                    side_effect=ValueError(
                        "Constraint URL returned HTML instead of raw requirements"
                    ),
                ),
                mock.patch("plonex.cli.logger.error") as error,
            ):
                with self.assertRaises(SystemExit) as exc:
                    self._run_with_target(argv)
                self.assertEqual(exc.exception.code, 1)
                error.assert_called_once_with(
                    "Constraint URL returned HTML instead of raw requirements"
                )

    def test_action_describe(self):
        svc = self._run_service(
            ["project", "describe"], "plonex.cli.describe.DescribeService"
        )
        svc.return_value.run.assert_called_once()

    def test_action_describe_html_browse(self):
        with mock.patch("plonex.cli.describe.DescribeService") as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run_with_target(
                ["project", "describe", "--format", "html", "--browse"]
            )
        MockSvc.assert_called_once_with(
            target=self.temp_dir.resolve(),
            browse_html=True,
            output_format="html",
            section="all",
            key="",
            inspect_command=[],
        )
        MockSvc.return_value.run.assert_called_once()

    def test_action_upgrade(self):
        svc = self._run_service(["db", "upgrade"], "plonex.cli.runtime.UpgradeService")
        svc.return_value.run.assert_called_once()

    def test_action_zeoserver(self):
        svc = self._run_service(["db", "start"], "plonex.cli.runtime.ZeoServer")
        svc.return_value.run.assert_called_once()

    def test_action_db_backup(self):
        svc = self._run_service(["db", "backup"], "plonex.cli.db.ZeoServer")
        svc.return_value.run_backup.assert_called_once()

    def test_action_db_restore(self):
        svc = self._run_service(["db", "restore"], "plonex.cli.db.ZeoServer")
        svc.return_value.run_restore.assert_called_once_with(
            destination=None, backup=None
        )

    def test_action_db_pack(self):
        svc = self._run_service(["db", "pack", "-d", "3"], "plonex.cli.db.ZeoServer")
        svc.return_value.run_pack.assert_called_once_with(days=3)

    def test_action_db_without_subcommand_prints_help(self):
        with mock.patch("argparse.ArgumentParser.print_help") as mock_help:
            self._run_with_target(["db"])
        mock_help.assert_called_once()

    def test_action_runwsgi_host_port(self):
        with mock.patch("plonex.cli.runtime.RunWSGI") as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run_with_target(
                ["instance", "start", "--host", "127.0.0.1", "-p", "8082"]
            )
        _, kwargs = MockSvc.call_args
        self.assertEqual(kwargs["cli_options"]["http_address"], "127.0.0.1")
        self.assertEqual(kwargs["cli_options"]["http_port"], 8082)

    def test_action_fg_sets_debug_options(self):
        with mock.patch("plonex.cli.runtime.RunWSGI") as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run_with_target(["instance", "debug"])
        _, kwargs = MockSvc.call_args
        self.assertEqual(kwargs["cli_options"]["debug_mode"], "on")
        self.assertEqual(kwargs["cli_options"]["verbose_security"], "on")
        self.assertEqual(
            kwargs["cli_options"]["security_policy_implementation"], "python"
        )
        MockSvc.return_value.run.assert_called_once()

    def test_action_fg_default_name(self):
        with mock.patch("plonex.cli.runtime.RunWSGI") as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run_with_target(["instance", "debug"])
        _, kwargs = MockSvc.call_args
        self.assertEqual(kwargs["name"], "fg")

    def test_action_fg_host_port(self):
        with mock.patch("plonex.cli.runtime.RunWSGI") as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run_with_target(
                ["instance", "debug", "--host", "127.0.0.1", "-p", "8082"]
            )
        _, kwargs = MockSvc.call_args
        self.assertEqual(kwargs["cli_options"]["http_address"], "127.0.0.1")
        self.assertEqual(kwargs["cli_options"]["http_port"], 8082)

    def test_action_zconsole_default_action_is_debug(self):
        with mock.patch("plonex.cli.runtime.ZConsole") as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run_with_target(["instance", "console"])
        _, kwargs = MockSvc.call_args
        self.assertEqual(kwargs["action"], "debug")

    def test_action_adduser(self):
        with mock.patch("plonex.cli.runtime.AddUser") as MockSvc:
            MockSvc.return_value.__enter__ = mock.Mock(
                return_value=MockSvc.return_value
            )
            MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
            self._run_with_target(["instance", "add-user", "admin", "secret"])
        MockSvc.return_value.run.assert_called_once()

    def test_action_supervisor_start(self):
        with mock.patch("plonex.cli.runtime._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.runtime.Supervisor") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["supervisor", "start"])
        mock_deps.assert_not_called()
        self.preparation.return_value.run.assert_called_once()
        MockSvc.return_value.run.assert_called_once()

    def test_action_supervisor_stop(self):
        with mock.patch("plonex.cli.runtime._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.runtime.Supervisor") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["supervisor", "stop"])
        mock_deps.assert_not_called()
        MockSvc.return_value.run_stop.assert_called_once()

    def test_action_supervisor_restart(self):
        with mock.patch("plonex.cli.runtime._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.runtime.Supervisor") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["supervisor", "restart"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "supervisor")
        MockSvc.return_value.run_restart.assert_called_once()

    def test_action_supervisor_status(self):
        with mock.patch("plonex.cli.runtime._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.runtime.Supervisor") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["supervisor", "status"])
        mock_deps.assert_not_called()
        MockSvc.return_value.run_status.assert_called_once()

    def test_action_dependencies(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.InstallService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["dependencies", "install", "--persist"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "dependencies")
        MockSvc.return_value.run.assert_called_once_with(
            persist=True,
            persist_local=False,
            persist_profile=False,
            update_sources=None,
            sync=False,
        )

    def test_action_dependencies_with_update_sources(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.InstallService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["dependencies", "install", "--update-sources"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "dependencies")
        MockSvc.return_value.run.assert_called_once_with(
            persist=False,
            persist_local=False,
            persist_profile=False,
            update_sources=True,
            sync=False,
        )

    def test_action_dependencies_with_sync(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.InstallService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["dependencies", "sync"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "dependencies")
        MockSvc.return_value.run.assert_called_once_with(
            persist=False,
            persist_local=False,
            persist_profile=False,
            update_sources=None,
            sync=True,
        )

    def test_action_sources_update(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "update"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_update.assert_called_once_with(glob=None)

    def test_action_sources_update_with_glob(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "update", "foo"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_update.assert_called_once_with(glob="foo")

    def test_action_sources_force_update(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "update", "--force", "--yes"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_update.assert_called_once_with(
            force=True,
            assume_yes=True,
            glob=None,
        )

    def test_action_sources_tainted(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "tainted"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_show_tainted.assert_called_once_with(glob=None)

    def test_action_sources_list(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "list"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_list.assert_called_once_with(glob=None)

    def test_action_sources_missing(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "missing"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_show_missing.assert_called_once_with(glob=None)

    def test_action_sources_clone_missing(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "clone"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_clone_missing.assert_called_once_with(
            assume_yes=False,
            glob=None,
        )

    def test_action_sources_clone_missing_yes(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "clone", "--yes"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_clone_missing.assert_called_once_with(
            assume_yes=True,
            glob=None,
        )

    def test_action_sources_suggest_existing(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "suggest"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_suggest_existing.assert_called_once_with(
            apply=False,
            apply_local=False,
            apply_profile=False,
        )

    def test_action_sources_suggest_existing_apply_local(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "suggest", "--apply-local"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_suggest_existing.assert_called_once_with(
            apply=False,
            apply_local=True,
            apply_profile=False,
        )

    def test_action_sources_suggest_existing_apply(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "suggest", "--apply"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_suggest_existing.assert_called_once_with(
            apply=True,
            apply_local=False,
            apply_profile=False,
        )

    def test_action_sources_suggest_existing_apply_profile(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.SourcesService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["sources", "suggest", "--apply-profile"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "sources")
        MockSvc.return_value.run_suggest_existing.assert_called_once_with(
            apply=False,
            apply_local=False,
            apply_profile=True,
        )

    def test_action_supervisor_graceful(self):
        with mock.patch("plonex.cli.runtime._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.runtime.Supervisor") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["supervisor", "graceful", "--interval", "2.5"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "supervisor")
        MockSvc.return_value.run_graceful.assert_called_once_with(delay=2.5)

    def test_action_install(self):
        with mock.patch("plonex.cli.setup_info._run_service_dependencies") as mock_deps:
            with mock.patch("plonex.cli.setup_info.InstallService") as MockSvc:
                MockSvc.return_value.__enter__ = mock.Mock(
                    return_value=MockSvc.return_value
                )
                MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                self._run_with_target(["dependencies", "add", "my.package"])
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "install")
        self.assertEqual(
            MockSvc.call_args_list,
            [
                mock.call(target=self.temp_dir.resolve()),
                mock.call(target=self.temp_dir.resolve()),
            ],
        )
        MockSvc.return_value.add_packages.assert_called_once_with(["my.package"])
        MockSvc.return_value.run.assert_called_once()

    def test_action_supervisor_graceful_uses_configured_interval(self):
        etc = self.temp_dir / "etc"
        etc.mkdir(exist_ok=True)
        (etc / "plonex.yml").write_text("supervisor_graceful_interval: 4.0\n")
        with mock.patch("plonex.cli._configure_logging"):
            with mock.patch(
                "plonex.cli.runtime._run_service_dependencies"
            ) as mock_deps:
                with mock.patch("plonex.cli.runtime.Supervisor") as MockSvc:
                    MockSvc.return_value.__enter__ = mock.Mock(
                        return_value=MockSvc.return_value
                    )
                    MockSvc.return_value.__exit__ = mock.Mock(return_value=False)
                    MockSvc.return_value.graceful_interval = 4.0
                    with mock.patch.object(
                        sys,
                        "argv",
                        ["plonex", "-t", str(self.temp_dir), "supervisor", "graceful"],
                    ):
                        main()
        mock_deps.assert_called_once_with(self.temp_dir.resolve(), "supervisor")
        MockSvc.return_value.run_graceful.assert_called_once_with(delay=4.0)


class TestServiceFromConfig(unittest.TestCase):

    def test_template_alias_and_relative_paths(self):
        with temp_cwd() as cwd:
            template_path = cwd / "etc" / "templates" / "a.j2"
            template_path.parent.mkdir(parents=True)
            template_path.write_text("ok")
            spec = {
                "template": {
                    "source": "etc/templates/a.j2",
                    "target": "etc/a.conf",
                }
            }
            service = _service_from_config(spec, cwd)
            self.assertEqual(service.__class__.__name__, "TemplateService")
            self.assertEqual(service.source_path, cwd / "etc/templates/a.j2")
            self.assertEqual(service.target_path, cwd / "etc/a.conf")

    def test_dependency_filter_returns_none_for_other_services(self):
        with temp_cwd() as cwd:
            template_path = cwd / "etc" / "templates" / "a.j2"
            template_path.parent.mkdir(parents=True)
            template_path.write_text("ok")
            spec = {
                "template": {
                    "run_for": "supervisor",
                    "source": "etc/templates/a.j2",
                    "target": "etc/a.conf",
                }
            }
            service = _service_from_config(spec, cwd, dependency_for="runwsgi")
            self.assertIsNone(service)

    def test_dependency_filter_accepts_matching_service(self):
        with temp_cwd() as cwd:
            template_path = cwd / "etc" / "templates" / "a.j2"
            template_path.parent.mkdir(parents=True)
            template_path.write_text("ok")
            spec = {
                "template": {
                    "run_for": ["supervisor", "runwsgi"],
                    "source": "etc/templates/a.j2",
                    "target": "etc/a.conf",
                }
            }
            service = _service_from_config(spec, cwd, dependency_for="supervisor")
            self.assertIsNotNone(service)

    def test_unknown_service_raises(self):
        with temp_cwd() as cwd:
            with self.assertRaisesRegex(ValueError, "Unknown service"):
                _service_from_config({"nope": {}}, cwd)

    def test_module_main_guard(self):
        cli_path = (
            Path(__file__).parent.parent / "src" / "plonex" / "cli" / "__main__.py"
        )
        with mock.patch.object(sys, "argv", ["plonex", "-V"]):
            with mock.patch("builtins.print") as mock_print:
                run_path(str(cli_path), run_name="__main__")
        mock_print.assert_called_once_with(version("plonex"))
