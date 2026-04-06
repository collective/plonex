from .utils import DummyLogger
from .utils import temp_cwd
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from plonex.profile import ProfileService
from textwrap import dedent
from unittest import mock

import inspect
import os
import sys
import unittest


@dataclass(kw_only=True)
class DummyService(BaseService):

    logger: DummyLogger = field(default_factory=DummyLogger)  # type: ignore


@dataclass(kw_only=True)
class EmptyCommandService(DummyService):

    @property
    def command(self):
        return []


@dataclass(kw_only=True)
class StreamingService(DummyService):

    stream_output = True


class TestBaseService(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.service = BaseService()
        self.temp_dir = self.enterContext(temp_cwd())

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(BaseService.__init__)
        self.assertListEqual(
            list(signature.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
            ],
        )

    def test_ensure_dir_with_path(self):
        """Test the ensure path method"""
        foo_path = self.temp_dir / "foo"

        path = self.service._ensure_dir(foo_path)
        self.assertEqual(path, foo_path)
        self.assertTrue(foo_path.exists())
        self.assertTrue(foo_path.is_dir())

        # Rerunning the method should not raise an error
        path = self.service._ensure_dir("foo")

    def test_ensure_dir_with_str(self):
        """Test the ensure path method passing a string"""
        foo_path = self.temp_dir / "foo"

        path = self.service._ensure_dir(str(foo_path))
        self.assertEqual(path, foo_path)
        self.assertTrue(foo_path.exists())
        self.assertTrue(foo_path.is_dir())

    def test_ensure_dir_with_existing_dir(self):
        """Test the ensure path method with an existing directory"""
        foo_path = self.temp_dir / "foo"
        foo_path.mkdir()

        path = self.service._ensure_dir(foo_path)
        self.assertEqual(path, foo_path)
        self.assertTrue(foo_path.exists())
        self.assertTrue(foo_path.is_dir())

    def test_ensure_dir_with_existing_file(self):
        """Test the ensure path method with an existing file"""

        foo_path = self.temp_dir / "foo"
        foo_path.touch()

        with self.assertRaises(ValueError):
            self.service._ensure_dir(foo_path)

    def test_entered_only_when_inactive(self):
        """Test the active only decorator when the context manager is not active"""
        client = BaseService()
        with self.assertRaises(RuntimeError):
            client.entered_only(lambda self: None)(client)

    def test_run(self):
        """Test the run method"""
        with DummyService() as service:
            service.run()

    def test_keyboard_interrupt_logs(self):
        """Test the KeyboardInterrupt exception"""
        with DummyService() as service:
            with mock.patch.object(
                service, "execute_command", side_effect=KeyboardInterrupt
            ):
                service.run()

            self.assertEqual(
                service.logger.infos,
                [
                    ("Stopping %r", "true"),
                ],
            )

    def test_executable_dir(self):
        """Test the executable_dir property"""
        self.assertEqual(BaseService().executable_dir, Path(sys.executable).parent)

    def test_additional_plonex_options(self):
        """Test that we can add additional options from etc/plonex.*.yml files"""

        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        plonex_path = etc_path / "plonex.test.yml"

        default_options = DummyService().options
        self.assertDictEqual(default_options, {"target": str(self.temp_dir)})

        plonex_path.write_text(
            dedent(
                """---
            test_option: 42
            """
            )
        )

        self.assertDictEqual(
            DummyService().options, {"test_option": 42, **default_options}
        )
        self.assertDictEqual(
            DummyService(cli_options={"test_option": 44}).options,
            {"test_option": 44, **default_options},
        )

    def test_additional_plonex_options_bogus(self):
        """Test that we can add additional options from etc/plonex.*.yml files"""

        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()

        default_options = DummyService().options

        plonex_path = etc_path / "plonex.test.yml"
        plonex_path.write_text(
            dedent(
                """---
            - test_option:
                - 42
            """
            )
        )
        service = DummyService()
        self.assertDictEqual(service.options, default_options)
        self.assertListEqual(
            service.logger.errors,
            [("The config file %r should contain a dict", plonex_path)],
        )

    # --- plonex_options ---

    def test_plonex_options_no_file(self):
        """plonex_options logs a warning and returns {} when plonex.yml is absent"""
        service = DummyService()
        self.assertDictEqual(service.plonex_options, {})
        self.assertEqual(len(service.logger.warnings), 1)

    def test_plonex_options_with_file(self):
        """plonex_options reads and returns the contents of plonex.yml"""
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("key: value\n")
        service = DummyService()
        self.assertEqual(service.plonex_options, {"key": "value"})

    def test_plonex_options_merge_profiles_before_local(self):
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        profile = self.temp_dir / "profiles" / "base"
        (profile / "etc").mkdir(parents=True)
        (profile / "etc" / "plonex.yml").write_text("http_port: 8080\ninstance: base\n")
        (etc_path / "plonex.yml").write_text(
            dedent(
                f"""---
                profiles:
                  - {profile}
                http_port: 8081
                """
            )
        )
        service = DummyService()
        self.assertEqual(service.plonex_options["http_port"], 8081)
        self.assertEqual(service.plonex_options["instance"], "base")

    def test_plonex_options_profile_relative_to_target(self):
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        profile = self.temp_dir / "profiles" / "base"
        (profile / "etc").mkdir(parents=True)
        (profile / "etc" / "plonex.yml").write_text("profile_option: true\n")
        (etc_path / "plonex.yml").write_text(
            "profiles:\n  - profiles/base\nlocal_option: true\n"
        )
        service = DummyService()
        self.assertTrue(service.plonex_options["profile_option"])
        self.assertTrue(service.plonex_options["local_option"])

    def test_plonex_options_profile_can_chain_other_profiles(self):
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        base_profile = self.temp_dir / "profiles" / "base"
        child_profile = self.temp_dir / "profiles" / "child"
        (base_profile / "etc").mkdir(parents=True)
        (child_profile / "etc").mkdir(parents=True)
        (base_profile / "etc" / "plonex.yml").write_text("base_only: true\n")
        (child_profile / "etc" / "plonex.yml").write_text(
            "profiles:\n  - ../base\nchild_only: true\n"
        )
        (etc_path / "plonex.yml").write_text("profiles:\n  - profiles/child\n")
        service = DummyService()
        self.assertTrue(service.plonex_options["base_only"])
        self.assertTrue(service.plonex_options["child_only"])

    def test_plonex_options_profile_plus_services_extends(self):
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        base_profile = self.temp_dir / "profiles" / "base"
        child_profile = self.temp_dir / "profiles" / "child"
        (base_profile / "etc").mkdir(parents=True)
        (child_profile / "etc").mkdir(parents=True)
        (base_profile / "etc" / "plonex.yml").write_text("services:\n  - zeoserver\n")
        (child_profile / "etc" / "plonex.yml").write_text(
            "profiles:\n  - ../base\n+services:\n  - zeoclient\n"
        )
        (etc_path / "plonex.yml").write_text("profiles:\n  - profiles/child\n")

        service = DummyService()
        self.assertEqual(service.plonex_options["services"], ["zeoserver", "zeoclient"])

    def test_plonex_options_profile_minus_services_removes(self):
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        base_profile = self.temp_dir / "profiles" / "base"
        child_profile = self.temp_dir / "profiles" / "child"
        (base_profile / "etc").mkdir(parents=True)
        (child_profile / "etc").mkdir(parents=True)
        (base_profile / "etc" / "plonex.yml").write_text(
            "services:\n  - zeoserver\n  - zeoclient\n"
        )
        (child_profile / "etc" / "plonex.yml").write_text(
            "profiles:\n  - ../base\n-services:\n  - zeoclient\n"
        )
        (etc_path / "plonex.yml").write_text("profiles:\n  - profiles/child\n")

        service = DummyService()
        self.assertEqual(service.plonex_options["services"], ["zeoserver"])

    def test_plonex_options_profile_invalid_shape_logs_error(self):
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("profiles:\n  nested: nope\n")
        service = DummyService()
        self.assertEqual(service.plonex_options["profiles"], {"nested": "nope"})
        self.assertTrue(
            any("'profiles' option" in str(error) for error in service.logger.errors)
        )

    def test_plonex_options_profile_git_url_uses_cloned_source(self):
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        cloned_profile = self.temp_dir / "cloned-profile"
        (cloned_profile / "etc").mkdir(parents=True)
        (cloned_profile / "etc" / "plonex.yml").write_text("remote: true\n")
        (etc_path / "plonex.yml").write_text(
            "profiles:\n  - https://github.com/example/plonex-profile.git\n"
        )
        with mock.patch.object(
            ProfileService,
            "_clone_remote_source",
            return_value=cloned_profile,
        ) as mock_clone:
            service = DummyService()
            self.assertTrue(service.plonex_options["remote"])
        mock_clone.assert_called_once()

    # --- config_files_options_mapping ---

    def test_config_files_options_missing_file(self):
        """config_files_options_mapping logs a warning for a missing config file"""
        missing = self.temp_dir / "missing.yml"
        service = DummyService(config_files=[missing])
        mapping = service.config_files_options_mapping
        self.assertDictEqual(mapping[missing.absolute()], {})
        self.assertEqual(len(service.logger.warnings), 1)

    def test_config_files_options_bogus_file(self):
        """config_files_options_mapping logs an error when the file is not a dict"""
        config = self.temp_dir / "config.yml"
        config.write_text("- item1\n- item2\n")
        service = DummyService(config_files=[config])
        mapping = service.config_files_options_mapping
        self.assertDictEqual(mapping[config.absolute()], {})
        self.assertEqual(len(service.logger.errors), 1)

    def test_config_files_options(self):
        """config_files_options merges options from all config files"""
        config1 = self.temp_dir / "config1.yml"
        config2 = self.temp_dir / "config2.yml"
        config1.write_text("key1: val1\n")
        config2.write_text("key2: val2\n")
        service = DummyService(config_files=[config1, config2])
        self.assertEqual(service.config_files_options, {"key1": "val1", "key2": "val2"})

    # --- options +/- prefix merging ---

    def test_options_plus_prefix_list(self):
        """The + prefix extends a list option"""
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("items:\n  - a\n  - b\n")
        (etc_path / "plonex.extra.yml").write_text("+items:\n  - c\n")
        service = DummyService()
        self.assertEqual(service.options["items"], ["a", "b", "c"])

    def test_options_plus_prefix_dict(self):
        """The + prefix merges into a dict option"""
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("mapping:\n  key1: val1\n")
        (etc_path / "plonex.extra.yml").write_text("+mapping:\n  key2: val2\n")
        service = DummyService()
        self.assertDictEqual(
            service.options["mapping"], {"key1": "val1", "key2": "val2"}
        )

    def test_options_plus_prefix_unsupported_type(self):
        """The + prefix on a scalar option logs an error"""
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("count: 1\n")
        (etc_path / "plonex.extra.yml").write_text("+count:\n  - extra\n")
        service = DummyService()
        _ = service.options
        self.assertTrue(
            any("Cannot add to option" in str(e) for e in service.logger.errors)
        )

    def test_options_minus_prefix_list(self):
        """The - prefix removes an item from a list option"""
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("items:\n  - a\n  - b\n  - c\n")
        (etc_path / "plonex.extra.yml").write_text("-items:\n  - b\n")
        service = DummyService()
        self.assertEqual(service.options["items"], ["a", "c"])

    def test_options_minus_prefix_dict(self):
        """The - prefix removes a key from a dict option"""
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("mapping:\n  key1: val1\n  key2: val2\n")
        (etc_path / "plonex.extra.yml").write_text("-mapping:\n  - key1\n")
        service = DummyService()
        self.assertDictEqual(service.options["mapping"], {"key2": "val2"})

    def test_options_minus_prefix_list_item_not_found(self):
        """Warning when removing a non-existent item from a list option"""
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("items:\n  - a\n")
        (etc_path / "plonex.extra.yml").write_text("-items:\n  - z\n")
        service = DummyService()
        _ = service.options
        self.assertTrue(
            any("Cannot remove item" in str(w) for w in service.logger.warnings)
        )

    def test_options_minus_prefix_dict_key_not_found(self):
        """Warning when removing a non-existent key from a dict option"""
        etc_path = self.temp_dir / "etc"
        etc_path.mkdir()
        (etc_path / "plonex.yml").write_text("mapping:\n  key1: val1\n")
        (etc_path / "plonex.extra.yml").write_text("-mapping:\n  - missing_key\n")
        service = DummyService()
        _ = service.options
        self.assertTrue(
            any("Cannot remove item" in str(w) for w in service.logger.warnings)
        )

    # --- mkdtemp ---

    def test_mkdtemp(self):
        """mkdtemp creates a temporary directory prefixed with the service name"""
        service = BaseService(name="myservice")
        temp = service.mkdtemp()
        try:
            self.assertTrue(temp.exists())
            self.assertIn("myservice-", temp.name)
        finally:
            temp.rmdir()

    # --- virtualenv_dir ---

    def test_virtualenv_dir_not_found(self):
        """virtualenv_dir logs an error and exits when .venv is absent"""
        service = BaseService()
        with mock.patch("plonex.base.logger") as mock_logger:
            with self.assertRaises(SystemExit) as cm:
                _ = service.virtualenv_dir
        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called_once()

    # --- run_command ---

    def test_run_command_called_process_error(self):
        """run_command logs the error and exits with the process return code"""
        with DummyService() as service:

            class FakeError(Exception):

                def __init__(self, exit_code: int):
                    super().__init__(exit_code)
                    self.exit_code = exit_code

            error = FakeError(2)
            with mock.patch("plonex.base.sh.ErrorReturnCode", FakeError):
                with mock.patch.object(service, "execute_command", side_effect=error):
                    with self.assertRaises(SystemExit) as cm:
                        service.run_command(["false"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn((error,), service.logger.errors)

    # --- __enter__ / __exit__ ---

    def test_enter_with_environment_vars(self):
        """__enter__ sets environment variables defined in options"""
        service = DummyService(
            cli_options={"environment_vars": {"PLONEX_TEST_VAR": "hello"}}
        )
        with mock.patch.dict(os.environ, {}):
            with service:
                self.assertEqual(os.environ.get("PLONEX_TEST_VAR"), "hello")

    def test_enter_with_environment_vars_non_string_value(self):
        """__enter__ converts non-string env var values to strings"""
        service = DummyService(
            cli_options={"environment_vars": {"PLONEX_TEST_INT": 42}}
        )
        with mock.patch.dict(os.environ, {}):
            with service:
                self.assertEqual(os.environ.get("PLONEX_TEST_INT"), "42")

    def test_enter_with_environment_vars_override(self):
        """__enter__ logs an info message when overriding an existing env var"""
        with mock.patch.dict(os.environ, {"PLONEX_TEST_OVERRIDE": "old"}):
            service = DummyService(
                cli_options={"environment_vars": {"PLONEX_TEST_OVERRIDE": "new"}}
            )
            with service:
                self.assertEqual(os.environ["PLONEX_TEST_OVERRIDE"], "new")
        self.assertTrue(
            any(
                "Overriding existing environment variable" in str(i)
                for i in service.logger.infos
            )
        )

    def test_enter_with_pre_services(self):
        """__enter__ runs each pre_service inside its own context manager"""
        pre = mock.MagicMock()
        pre.__enter__ = mock.MagicMock(return_value=pre)
        pre.__exit__ = mock.MagicMock(return_value=False)
        service = DummyService()
        service.pre_services = [pre]
        with service:
            pre.run.assert_called_once()

    def test_exit_with_post_services(self):
        """__exit__ runs each post_service inside its own context manager"""
        post = mock.MagicMock()
        post.__enter__ = mock.MagicMock(return_value=post)
        post.__exit__ = mock.MagicMock(return_value=False)
        service = DummyService()
        service.post_services = [post]
        with service:
            pass
        post.run.assert_called_once()

    # --- options: non-dict in additional_plonex_options ---

    def test_options_with_non_dict_in_additional_plonex_options(self):
        """options logs an error when additional_plonex_options provides a non-dict"""
        service = DummyService()
        fake_path = Path("/mock/plonex.fake.yml")
        # Pre-populate the cached_property to inject a non-dict value
        service.__dict__["additional_plonex_options"] = {fake_path: ["a", "b"]}
        _ = service.options
        self.assertTrue(
            any("should contain a dict" in str(e) for e in service.logger.errors)
        )

    def test_additional_plonex_options_with_missing_globbed_file(self):
        """additional_plonex_options logs a warning for missing glob results"""
        service = DummyService()
        missing = self.temp_dir / "etc" / "plonex.missing.yml"
        with mock.patch("pathlib.Path.glob", side_effect=[[missing], [], []]):
            mapping = service.additional_plonex_options
        self.assertDictEqual(mapping[missing], {})
        self.assertTrue(
            any("does not exist" in str(w) for w in service.logger.warnings)
        )

    def test_options_logs_too_many_iterations(self):
        """options logs an error when template resolution does not converge"""

        class _Template:

            def __init__(self):
                self.counter = 0

            def render(self, **kwargs):
                self.counter += 1
                return f"counter: {self.counter}\n"

        fake_env = mock.Mock()
        fake_env.from_string.return_value = _Template()
        service = DummyService()
        with mock.patch("plonex.base.Environment", return_value=fake_env):
            options = service.options
        self.assertEqual(options, {"counter": 10})
        self.assertTrue(
            any("Too many iterations" in str(error) for error in service.logger.errors)
        )

    def test_options_normalize_supervisor_graceful_interval(self):
        service = DummyService(cli_options={"supervisor_graceful_interval": "2.5"})
        self.assertEqual(service.options["supervisor_graceful_interval"], 2.5)

    def test_options_invalid_supervisor_graceful_interval_falls_back(self):
        service = DummyService(cli_options={"supervisor_graceful_interval": -1})
        self.assertEqual(service.options["supervisor_graceful_interval"], 1.0)
        self.assertTrue(
            any(
                "supervisor_graceful_interval" in str(error)
                for error in service.logger.errors
            )
        )

    # --- run with empty command ---

    def test_run_with_empty_command(self):
        """run() returns early without calling run_command when command is empty"""
        with EmptyCommandService() as service:
            with mock.patch.object(service, "run_command") as mock_run_cmd:
                service.run()
            mock_run_cmd.assert_not_called()

    # --- virtualenv_dir success ---

    def test_virtualenv_dir_success(self):
        """virtualenv_dir returns the .venv path when bin/activate exists"""
        venv_bin = self.temp_dir / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "activate").touch()
        service = BaseService()
        self.assertEqual(service.virtualenv_dir, (self.temp_dir / ".venv").absolute())

    # --- console property ---

    def test_console_property(self):
        """console property returns a rich Console instance"""
        from rich.console import Console

        service = BaseService()
        self.assertIsInstance(service.console, Console)

    # --- print property ---

    def test_print_property_info_enabled(self):
        """print returns console.print when INFO logging is enabled"""
        service = BaseService()
        with mock.patch.object(service.logger, "isEnabledFor", return_value=True):
            print_fn = service.print
        self.assertEqual(print_fn, service.console.print)

    def test_print_property_info_disabled(self):
        """print returns a no-op callable when INFO logging is disabled"""
        service = BaseService()
        with mock.patch.object(service.logger, "isEnabledFor", return_value=False):
            print_fn = service.print
        # Must be callable and not raise
        print_fn("ignored")
        self.assertIsNot(print_fn, service.console.print)

    # --- ask_for_value ---

    def test_ask_for_value_no_default(self):
        """ask_for_value appends a colon and returns the user's input"""
        service = BaseService()
        with mock.patch.object(service.console, "input", return_value="typed") as m:
            result = service.ask_for_value("Enter value")
        self.assertEqual(result, "typed")
        m.assert_called_with("Enter value:")

    def test_ask_for_value_with_default(self):
        """ask_for_value shows the default in brackets and returns it on empty input"""
        service = BaseService()
        with mock.patch.object(service.console, "input", return_value="") as m:
            result = service.ask_for_value("Enter value", default="fallback")
        self.assertEqual(result, "fallback")
        m.assert_called_with("Enter value [fallback]:")
