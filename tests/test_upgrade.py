from .utils import PloneXTestCase
from .utils import temp_cwd
from plonex.upgrade import UpgradeService
from unittest import mock

import inspect


class TestUpgradeService(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method"""
        sig = inspect.signature(UpgradeService.__init__)
        self.assertListEqual(
            list(sig.parameters),
            ["self", "name", "target", "cli_options", "config_files"],
        )

    def test_run(self):
        """Test that run() calls run_command with the right upgrade commands"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with UpgradeService() as svc:
                with mock.patch.object(svc, "run_command") as mock_run:
                    svc.run()
                self.assertEqual(mock_run.call_count, 2)
                first_call_args = mock_run.call_args_list[0][0][0]
                self.assertIn("upgrade", str(first_call_args[0]))
                self.assertIn("plone_upgrade", first_call_args[1])
