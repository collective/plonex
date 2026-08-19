from .utils import PloneXTestCase
from .utils import temp_cwd
from plonex.services.zopetest import ZopeTest

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

    def test_command(self):
        """Test that command builds the zope-testrunner command"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest(package="my.package") as svc:
                cmd = svc.command
                self.assertListEqual(
                    cmd,
                    [
                        str(svc.virtualenv_dir / "bin" / "zope-testrunner"),
                        "--all",
                        "--quiet",
                        "-pvc",
                        "--package",
                        "my.package",
                        "--auto-path",
                    ],
                )

    def test_command_with_test(self):
        """Test that command builds the zope-testrunner command with a test"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with ZopeTest(package="my.package", test="my.test") as svc:
                cmd = svc.command
                self.assertListEqual(
                    cmd,
                    [
                        str(svc.virtualenv_dir / "bin" / "zope-testrunner"),
                        "--all",
                        "--quiet",
                        "-pvc",
                        "--package",
                        "my.package",
                        "--auto-path",
                        "-t",
                        "my.test",
                    ],
                )
