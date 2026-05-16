from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.services.zconsole import ZConsole

import inspect


read_expected = ReadExpected(Path(__file__).parent / "expected" / "zconsole")


@contextmanager
def temp_zconsole(**kwargs):
    with temp_cwd():
        (Path.cwd() / ".venv" / "bin").mkdir(parents=True)
        (Path.cwd() / ".venv" / "bin" / "activate").touch()
        (Path.cwd() / "etc").mkdir(parents=True)
        (Path.cwd() / "etc" / "plonex.yml").write_text("---")
        with ZConsole(**kwargs) as svc:
            yield svc


class TestZConsole(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(ZConsole.__init__)
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
                "action",
                "args",
            ],
        )

    def test_constructor(self):
        """Test the constructor for the ZConsole object"""
        with temp_zconsole() as svc:
            cwd = Path.cwd()

            self.assertEqual(svc.target, cwd)
            self.assertEqual(svc.tmp_folder, cwd / "tmp" / "zconsole")
            self.assertEqual(svc.var_folder, cwd / "var")

            self.assertTrue(svc.target.exists())
            self.assertTrue(svc.tmp_folder.exists())
            self.assertTrue(svc.var_folder.exists())

    def test_constructor_with_params(self):
        """Test the constructor with parameters"""
        with temp_cwd() as temp_dir:
            (temp_dir / "another_place" / ".venv" / "bin").mkdir(parents=True)
            (temp_dir / "another_place" / ".venv" / "bin" / "activate").touch()
            svc = ZConsole(
                target=temp_dir / "another_place",
                tmp_folder=temp_dir / "another_tmp",
                var_folder=temp_dir / "another_var",
            )
            self.assertEqual(svc.target, temp_dir / "another_place")
            self.assertEqual(svc.tmp_folder, temp_dir / "another_tmp")
            self.assertEqual(svc.var_folder, temp_dir / "another_var")

    def test_zope_conf_debug_mode(self):
        """Test that debug mode generates the correct zope.conf"""
        with temp_zconsole(action="debug") as svc:
            zope_conf = svc.tmp_folder / "etc" / "zope.conf"
            self.assertEqual(
                zope_conf.read_text(),
                read_expected("test_zope_conf_debug", svc),
            )

    def test_zope_conf_run_mode(self):
        """Test that run mode generates the correct zope.conf"""
        with temp_zconsole(action="run") as svc:
            zope_conf = svc.tmp_folder / "etc" / "zope.conf"
            self.assertEqual(
                zope_conf.read_text(),
                read_expected("test_zope_conf_run", svc),
            )

    def test_command_debug(self):
        """Test the command property for debug action"""
        with temp_zconsole(action="debug") as svc:
            assert svc.tmp_folder is not None
            self.assertEqual(
                svc.command,
                [
                    str(svc.virtualenv_dir / "bin" / "zconsole"),
                    "debug",
                    str(svc.tmp_folder / "etc" / "zope.conf"),
                ],
            )

    def test_command_run(self):
        """Test the command property for run action"""
        with temp_zconsole(action="run") as svc:
            assert svc.tmp_folder is not None
            self.assertEqual(
                svc.command,
                [
                    str(svc.virtualenv_dir / "bin" / "zconsole"),
                    "run",
                    str(svc.tmp_folder / "etc" / "zope.conf"),
                ],
            )

    def test_command_with_args(self):
        """Test the command property with extra args"""
        with temp_zconsole(args=["script.py"]) as svc:
            self.assertIn("script.py", svc.command)
