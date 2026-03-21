from .utils import PloneXTestCase
from .utils import temp_cwd
from plonex.robotserver import RobotServer

import inspect


class TestRobotServer(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method"""
        sig = inspect.signature(RobotServer.__init__)
        self.assertListEqual(
            list(sig.parameters),
            ["self", "name", "target", "cli_options", "config_files", "layer"],
        )

    def test_options_defaults(self):
        """Test that options_defaults includes the expected environment variables"""
        with temp_cwd():
            svc = RobotServer()
            defaults = svc.options_defaults
            self.assertIn("environment_vars", defaults)
            env_vars = defaults["environment_vars"]
            self.assertEqual(env_vars["ZSERVER_HOST"], "127.0.0.2")
            self.assertEqual(env_vars["ZSERVER_PORT"], "55001")
            self.assertEqual(env_vars["DIAZO_ALWAYS_CACHE_RULES"], "1")

    def test_command(self):
        """Test that command returns the expected robot-server arguments."""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with RobotServer() as svc:
                cmd = svc.command
                self.assertEqual(
                    cmd[0], str(svc.virtualenv_dir / "bin" / "robot-server")
                )
                self.assertIn("--debug-mode", cmd)
                self.assertIn("--verbose", cmd)
                self.assertIn(svc.layer, cmd)

    def test_command_custom_layer(self):
        """Test that a custom layer is used in the command"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with RobotServer(layer="my.custom.TESTING") as svc:
                cmd = svc.command
                self.assertIn("my.custom.TESTING", cmd)
