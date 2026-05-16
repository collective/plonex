from .utils import PloneXTestCase
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.services.adduser import AddUser
from unittest import mock

import inspect


@contextmanager
def temp_adduser(**kwargs):
    with temp_cwd():
        (Path.cwd() / ".venv" / "bin").mkdir(parents=True)
        (Path.cwd() / ".venv" / "bin" / "activate").touch()
        (Path.cwd() / "etc").mkdir(parents=True)
        (Path.cwd() / "etc" / "plonex.yml").write_text("---")
        with AddUser(**kwargs) as svc:
            yield svc


class TestAddUser(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(AddUser.__init__)
        self.assertListEqual(
            list(signature.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "tmp_folder",
                "var_folder",
                "zope_conf_template",
                "site_zcml_template",
                "username",
                "password",
            ],
        )

    def test_constructor(self):
        """Test that AddUser reuses the zconsole tmp folder by default"""
        with temp_adduser() as svc:
            cwd = Path.cwd()

            self.assertEqual(svc.target, cwd)
            # AddUser reuses the zconsole tmp folder
            self.assertEqual(svc.tmp_folder, cwd / "tmp" / "zconsole")
            self.assertEqual(svc.var_folder, cwd / "var")

            self.assertTrue(svc.target.exists())
            self.assertTrue(svc.tmp_folder.exists())
            self.assertTrue(svc.var_folder.exists())

    def test_constructor_explicit_tmp_folder(self):
        """Test that an explicit tmp_folder overrides the zconsole default"""
        with temp_cwd() as temp_dir:
            (temp_dir / ".venv" / "bin").mkdir(parents=True)
            (temp_dir / ".venv" / "bin" / "activate").touch()
            (temp_dir / "etc").mkdir(parents=True)
            (temp_dir / "etc" / "plonex.yml").write_text("---")
            svc = AddUser(tmp_folder=temp_dir / "custom_tmp")
            self.assertEqual(svc.tmp_folder, temp_dir / "custom_tmp")

    def test_run_with_generated_password(self):
        """Test that run() generates a password and prints it"""
        with temp_adduser(username="admin") as svc:
            with (
                mock.patch.object(svc, "_generate_password", return_value="secret"),
                mock.patch.object(svc, "execute_command") as mock_run,
                mock.patch("builtins.print") as mock_print,
            ):
                svc.run()
            mock_run.assert_called_once()
            mock_print.assert_called_once_with(
                "Please take note of the admin password: secret"
            )

    def test_run_with_explicit_password(self):
        """Test that run() with an explicit password does not print it"""
        with temp_adduser(username="admin", password="secret") as svc:
            with (
                mock.patch.object(svc, "execute_command"),
                mock.patch("builtins.print") as mock_print,
            ):
                svc.run()
            mock_print.assert_not_called()

    def test_run_keyboard_interrupt(self):
        """Test that run() handles KeyboardInterrupt gracefully"""
        with temp_adduser(username="admin", password="secret") as svc:
            with mock.patch.object(svc.logger, "info") as mock_info:
                with mock.patch.object(
                    svc, "execute_command", side_effect=KeyboardInterrupt
                ):
                    svc.run()
            mock_info.assert_called_once()
