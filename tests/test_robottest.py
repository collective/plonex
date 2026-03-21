from .utils import PloneXTestCase
from .utils import temp_cwd
from plonex.robottest import RobotTest

import inspect


class TestRobotTest(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method"""
        sig = inspect.signature(RobotTest.__init__)
        self.assertListEqual(
            list(sig.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "layer",
                "paths",
                "browser",
                "test",
            ],
        )

    def test_options_defaults(self):
        """Test that options_defaults includes the expected environment variables"""
        with temp_cwd():
            svc = RobotTest()
            defaults = svc.options_defaults
            self.assertIn("environment_vars", defaults)
            env_vars = defaults["environment_vars"]
            self.assertEqual(env_vars["ZSERVER_HOST"], "127.0.0.2")
            self.assertEqual(env_vars["ZSERVER_PORT"], "55001")

    def test_command_basic(self):
        """Test that command returns the robot command with paths"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with RobotTest(paths=["tests/robot/test_login.robot"]) as svc:
                cmd = svc.command
                self.assertEqual(cmd[0], str(svc.virtualenv_dir / "bin" / "robot"))
                self.assertIn("--variable", cmd)
                self.assertIn("BROWSER:firefox", cmd)
                self.assertIn("tests/robot/test_login.robot", cmd)

    def test_command_with_test_filter(self):
        """Test that a test filter is included in the command"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with RobotTest(
                paths=["tests/robot/test_login.robot"],
                test="Login Test",
            ) as svc:
                cmd = svc.command
                self.assertIn("-t", cmd)
                self.assertIn("Login Test", cmd)

    def test_command_with_custom_browser(self):
        """Test that a custom browser is used in the command"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with RobotTest(paths=["test.robot"], browser="chrome") as svc:
                cmd = svc.command
                self.assertIn("BROWSER:chrome", cmd)

    def test_command_no_test_filter(self):
        """Test that -t is not included when no test filter is provided"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with RobotTest(paths=["test.robot"]) as svc:
                cmd = svc.command
                self.assertNotIn("-t", cmd)
