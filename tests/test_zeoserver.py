from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.zeoserver import ZeoServer
from unittest import mock

import inspect


read_expected = ReadExpected(Path(__file__).parent / "expected" / "zeoserver")


@contextmanager
def temp_zeo():
    with temp_cwd():
        (Path.cwd() / ".venv" / "bin").mkdir(parents=True)
        (Path.cwd() / ".venv" / "bin" / "activate").touch()
        with ZeoServer() as zeo:
            yield zeo


class TestZeoServer(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(ZeoServer.__init__)
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
            ],
        )

    def test_constructor(self):
        """Test the constructor for the zeoserver object"""
        with temp_zeo() as zeo:
            cwd = Path.cwd()

            # We have some folders
            self.assertEqual(zeo.target, cwd)
            self.assertEqual(zeo.tmp_folder, cwd / "tmp" / "zeoserver")
            self.assertEqual(zeo.var_folder, cwd / "var")

            # that have been created
            self.assertTrue(zeo.target.exists())
            self.assertTrue(zeo.tmp_folder.exists())
            self.assertTrue(zeo.var_folder.exists())

    def test_constructor_with_params(self):
        """Test the constructor with parameters"""
        with temp_cwd() as temp_dir:
            (temp_dir / "another_place" / ".venv" / "bin").mkdir(parents=True)
            (temp_dir / "another_place" / ".venv" / "bin" / "activate").touch()
            zeo = ZeoServer(
                target=temp_dir / "another_place",
                tmp_folder=temp_dir / "another_tmp",
                var_folder=temp_dir / "another_var",
            )
            self.assertEqual(zeo.target, temp_dir / "another_place")
            self.assertEqual(zeo.tmp_folder, temp_dir / "another_tmp")
            self.assertEqual(zeo.var_folder, temp_dir / "another_var")

    def test_entered_only_when_inactive(self):
        """Test the active only method"""
        with temp_cwd() as temp_dir:
            (temp_dir / ".venv" / "bin").mkdir(parents=True)
            (temp_dir / ".venv" / "bin" / "activate").touch()
            zeo = ZeoServer()
            with self.assertRaises(RuntimeError):
                ZeoServer.entered_only(lambda self: None)(zeo)

    def test_entered_only_when_active(self):
        """Test the active only method"""
        with temp_zeo() as zeo:
            self.assertIsNone(ZeoServer.entered_only(lambda self: None)(zeo))

    def test_zeo_conf(self):
        """Test the zeo conf method"""
        with temp_zeo() as zeo:
            zeo_conf = zeo.tmp_folder / "etc" / "zeo.conf"
            expected = read_expected("test_zeo_conf", zeo)
            self.assertEqual(zeo_conf.read_text(), expected)

    def test_command(self):
        """Test the command method"""
        with temp_zeo() as zeo:
            self.assertEqual(
                zeo.command,
                [
                    str(zeo.virtualenv_dir / "bin" / "runzeo"),
                    "-C",
                    str(zeo.tmp_folder / "etc" / "zeo.conf"),
                ],
            )

    def test_run_pack(self):
        """Test the zeo pack command"""
        with temp_zeo() as zeo:
            with mock.patch.object(zeo, "run_command") as mock_run:
                zeo.run_pack(days=3)
            mock_run.assert_called_once_with(
                [
                    zeo.virtualenv_dir / "bin" / "zeopack",
                    "-u",
                    zeo.options["zeo_address"],
                    "-d",
                    3,
                ]
            )

    def test_run_pack_uses_zeo_address_from_plonex_local(self):
        """run_pack uses zeo_address loaded from plonex.local.yml"""
        with temp_cwd() as temp_dir:
            (temp_dir / ".venv" / "bin").mkdir(parents=True)
            (temp_dir / ".venv" / "bin" / "activate").touch()
            (temp_dir / "etc").mkdir(parents=True)
            custom_socket = temp_dir / "components" / "zeo" / "var" / "zeo.socket"
            (temp_dir / "etc" / "plonex.local.yml").write_text(
                "zeo_address: " + str(custom_socket) + "\n"
            )

            with ZeoServer(target=temp_dir) as zeo:
                with mock.patch.object(zeo, "run_command") as mock_run:
                    zeo.run_pack(days=5)

            mock_run.assert_called_once_with(
                [
                    temp_dir / ".venv" / "bin" / "zeopack",
                    "-u",
                    str(custom_socket),
                    "-d",
                    5,
                ]
            )

    def test_run_backup(self):
        """Test the backup command"""
        with temp_zeo() as zeo:
            with mock.patch.object(zeo, "run_command") as mock_run:
                zeo.run_backup()
            mock_run.assert_called_once_with(
                [
                    zeo.virtualenv_dir / "bin" / "repozo",
                    "-Bv",
                    "-r",
                    zeo.var_folder / "backup",
                    "-f",
                    zeo.var_folder / "filestorage" / "Data.fs",
                ]
            )
