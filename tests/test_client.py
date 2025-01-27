from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.zeoclient import ZeoClient
from unittest import mock


read_expected = ReadExpected(Path(__file__).parent / "expected" / "zeoclient")


@contextmanager
def temp_client(**kwargs):
    with temp_cwd():
        # Create a fake virtualenv folder structure
        (Path.cwd() / ".venv" / "bin").mkdir(parents=True)
        (Path.cwd() / ".venv" / "bin" / "activate").touch()
        with ZeoClient(**kwargs) as client:
            yield client


class TestZeoClient(PloneXTestCase):

    def test_constructor(self):
        """Test the constructor for the zeosclient object"""
        with temp_client() as client:
            client = ZeoClient()
            cwd = Path.cwd()

            # We have some folders
            self.assertEqual(client.target, cwd)
            self.assertEqual(client.tmp_folder, cwd / "tmp" / "zeoclient")
            self.assertEqual(client.var_folder, cwd / "var")

            # that have been created
            self.assertTrue(client.target.exists())
            self.assertTrue(client.tmp_folder.exists())
            self.assertTrue(client.var_folder.exists())

    def test_constructor_with_params(self):
        """Test the constructor with parameters"""
        with temp_cwd() as temp_dir:
            (temp_dir / "another_place" / ".venv" / "bin").mkdir(parents=True)
            (temp_dir / "another_place" / ".venv" / "bin" / "activate").touch()
            with ZeoClient(
                target=temp_dir / "another_place",
                tmp_folder=temp_dir / "another_tmp",
                var_folder=temp_dir / "another_var",
            ) as client:
                self.assertEqual(client.target, temp_dir / "another_place")
                self.assertEqual(client.tmp_folder, temp_dir / "another_tmp")
                self.assertEqual(client.var_folder, temp_dir / "another_var")

    def test_zope_conf(self):
        """Test the zope.conf file"""
        with temp_client() as client:
            zope_conf = client.tmp_folder / "etc" / "zope.conf"
            expected = read_expected("test_zope_conf", client)
            self.assertEqual(zope_conf.read_text(), expected)

    def test_broken_config_files(self):
        """Test the config files method with a broken file"""
        # mock Logger.error to check the error messages
        with mock.patch("logging.Logger.error") as mock_error:
            with temp_client(config_files=["bogus"]) as client:
                self.assertEqual(client.config_files, [Path("bogus")])
            mock_error.assert_called_once_with(
                "Config file %r is not valid", Path("bogus")
            )

        path = Path(__file__).parent / "sample_confs" / "zeoclient_bogus.yml"
        with mock.patch("logging.Logger.error") as mock_error:
            with temp_client(config_files=[str(path)]) as client:
                self.assertEqual(client.config_files, [path])
            mock_error.assert_called_once_with(
                "The config file %r should contain a dict", path
            )

    def test_options_from_config_files(self):
        """Test the options from the config files"""
        path = Path(__file__).parent / "sample_confs" / "zeoclient.yml"
        with temp_client(config_files=[str(path)]) as client:
            self.assertListEqual(client.config_files, [path])
            self.assertSetEqual(
                set(client.options),
                {
                    "blobstorage",
                    "foo",
                    "http_address",
                    "http_port",
                    "zcml_additional",
                    "zeo_address",
                },
            )
            self.assertEqual(
                client.options["blobstorage"], client.var_folder / "blobstorage"
            )
            self.assertEqual(client.options["foo"], "bar")
            self.assertEqual(client.options["http_address"], "0.0.0.0")
            self.assertEqual(client.options["http_port"], 8080)
            self.assertEqual(
                client.options["zeo_address"], client.var_folder / "zeosocket.sock"
            )
