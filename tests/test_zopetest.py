from .utils import PloneXTestCase
from .utils import temp_cwd
from plonex.zopetest import ZopeTest
from unittest import mock

import inspect


class TestZopeTest(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method"""
        sig = inspect.signature(ZopeTest.__init__)
        self.assertListEqual(
            list(sig.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "package",
                "test",
            ],
        )

    def test_options_defaults(self):
        """Test that options_defaults includes the expected environment variables"""
        with temp_cwd():
            svc = ZopeTest()
            defaults = svc.options_defaults
            self.assertIn("environment_vars", defaults)
            env_vars = defaults["environment_vars"]
            self.assertEqual(env_vars["ZSERVER_HOST"], "127.0.0.2")
            self.assertEqual(env_vars["ZSERVER_PORT"], "55001")

    def test_package_path_no_package(self):
        """Test that package_path returns empty string when no package is set"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest() as svc:
                self.assertEqual(svc.package_path, "")

    def test_package_path_with_package(self):
        """Test that package_path calls python to find the package path"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest(package="os") as svc:
                with mock.patch("sh.Command") as MockCmd:
                    MockCmd.return_value.return_value = (
                        "/usr/lib/python3/os/__init__.py\n"
                    )
                    path = svc.package_path
                self.assertEqual(path, "/usr/lib/python3/os")

    def test_package_path_empty_origin(self):
        """Test that package_path returns empty string when origin is empty"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest(package="nonexistent.package") as svc:
                with mock.patch("sh.Command") as MockCmd:
                    MockCmd.return_value.return_value = ""
                    path = svc.package_path
                self.assertEqual(path, "")

    def test_command_no_package(self):
        """Test that command returns empty list when no package is set"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest() as svc:
                cmd = svc.command
                self.assertEqual(cmd, [])

    def test_command_no_package_logs_warning(self):
        """Test that command logs a warning when no package path is found"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest(package="missing.pkg") as svc:
                with mock.patch("sh.Command") as MockCmd:
                    MockCmd.return_value.return_value = ""
                    with mock.patch.object(svc.logger, "warning") as mock_warn:
                        cmd = svc.command
                    mock_warn.assert_called_once()
                self.assertEqual(cmd, [])

    def test_command_with_package(self):
        """Test that command builds the zope-testrunner command"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest(package="my.package") as svc:
                with mock.patch.object(
                    type(svc),
                    "package_path",
                    new_callable=lambda: property(lambda self: "/path/to/my/package"),
                ):
                    cmd = svc.command
                self.assertEqual(
                    cmd[0], str(svc.virtualenv_dir / "bin" / "zope-testrunner")
                )
                self.assertIn("--all", cmd)
                self.assertIn("-pvc", cmd)
                self.assertIn("/path/to/my/package", cmd)
                self.assertNotIn("-t", cmd)

    def test_command_with_package_and_test(self):
        """Test that -t is included when test filter is set"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest(package="my.package", test="MyTest") as svc:
                with mock.patch.object(
                    type(svc),
                    "package_path",
                    new_callable=lambda: property(lambda self: "/path/to/my/package"),
                ):
                    cmd = svc.command
                self.assertIn("-t", cmd)
                self.assertIn("MyTest", cmd)
