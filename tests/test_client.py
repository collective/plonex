from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.zeoclient import ZeoClient
from unittest import mock

import inspect


read_expected = ReadExpected(Path(__file__).parent / "expected" / "zeoclient")


@contextmanager
def temp_client(**kwargs):
    with temp_cwd():
        # Create a fake virtualenv folder structure
        (Path.cwd() / ".venv" / "bin").mkdir(parents=True)
        (Path.cwd() / ".venv" / "bin" / "activate").touch()
        (Path.cwd() / "etc").mkdir(parents=True)
        (Path.cwd() / "etc" / "plonex.yml").write_text("---")
        with ZeoClient(**kwargs) as client:
            yield client


class TestZeoClient(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(ZeoClient.__init__)
        self.assertListEqual(
            list(signature.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "run_mode",
                "tmp_folder",
                "var_folder",
            ],
        )

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
            self.assertEqual(zope_conf.read_text().rstrip(), expected.rstrip())

    def test_broken_config_files(self):
        """Test the config files method with a broken file"""
        # mock Logger.error to check the error messages
        with mock.patch("logging.Logger.warning") as mock_error:
            with temp_client(config_files=["bogus"]) as client:
                bogus_path = Path("bogus").absolute()
                self.assertEqual(client.config_files, ["bogus"])
                client.options
            mock_error.assert_called_once_with(
                "Config file %r does not exist", bogus_path
            )

        path = Path(__file__).parent / "sample_confs" / "zeoclient_bogus.yml"
        with mock.patch("logging.Logger.error") as mock_error:
            with temp_client(config_files=[path]) as client:
                self.assertEqual(client.config_files, [path])
            mock_error.assert_called_once_with(
                "The config file %r should contain a dict", path
            )

    def test_options_from_config_files(self):
        """Test the options from the config files"""
        path = Path(__file__).parent / "sample_confs" / "zeoclient.yml"
        with temp_client(config_files=[path]) as client:
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
                    "zope_conf_additional",
                    "var_folder",
                    "target",
                },
            )
            self.assertEqual(
                client.options["blobstorage"], str(client.var_folder / "blobstorage")
            )
            self.assertEqual(client.options["foo"], "bar")
            self.assertEqual(client.options["http_address"], "0.0.0.0")
            self.assertEqual(client.options["http_port"], 8080)
            self.assertEqual(
                client.options["zeo_address"], str(client.var_folder / "zeosocket.sock")
            )

    def test_zcml_additional(self):
        """Test the zcml_additional method"""
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zcmls"
        zcml_additional = [
            str(sample_folder / "foo.zcml.j2"),
            str(sample_folder / "bar.zcml.j2"),
        ]
        with temp_client(
            cli_options={"zcml_additional": zcml_additional, "bar_value": "baz"},
        ) as client:
            packages_include_folder = client.tmp_folder / "etc" / "package-includes"
            self.assertIn(
                "<!-- baz --/>",
                (packages_include_folder / "bar-configure.zcml").read_text(),
            )

    def test_zope_conf_additional(self):
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zope_confs"
        zope_conf_additionals = [
            str(sample_folder / "bar.conf.j2"),
            str(sample_folder / "foo.conf.j2"),
        ]
        with temp_client(
            cli_options={
                "zope_conf_additional": zope_conf_additionals,
                "bar_value": "baz",
            }
        ) as client:
            zope_conf = client.tmp_folder / "etc" / "zope.conf"
            self.assertIn(
                "".join(
                    (
                        f"# {zope_conf_additionals[0]}\n",
                        "%import bar\n",
                    )
                ),
                zope_conf.read_text(),
            )

    def test_zcml_additional_must_be_list(self):
        with self.assertRaises(ValueError):
            with temp_client(cli_options={"zcml_additional": "bogus"}):
                pass

    def test_zcml_additional_removes_existing_package_include_files(self):
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zcmls"
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / "etc").mkdir(parents=True)
            (cwd / "etc" / "plonex.yml").write_text("---")
            stale_dir = cwd / "tmp" / "zeoclient" / "etc" / "package-includes"
            stale_dir.mkdir(parents=True)
            (stale_dir / "old.zcml").write_text("stale")
            with ZeoClient(
                cli_options={"zcml_additional": [str(sample_folder / "foo.zcml.j2")]}
            ):
                self.assertFalse((stale_dir / "old.zcml").exists())

    def test_zcml_additional_creates_chameleon_cache(self):
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zcmls"
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / "etc").mkdir(parents=True)
            (cwd / "etc" / "plonex.yml").write_text("---")
            cache_path = cwd / "var" / "cache"
            with ZeoClient(
                cli_options={
                    "zcml_additional": [str(sample_folder / "foo.zcml.j2")],
                    "environment_vars": {"CHAMELEON_CACHE": str(cache_path)},
                }
            ):
                self.assertTrue(cache_path.exists())

    def test_zcml_additional_adds_zcml_suffix(self):
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zcmls"
        source = sample_folder / "plain"
        source.write_text("<configure />")
        try:
            with temp_client(cli_options={"zcml_additional": [str(source)]}) as client:
                self.assertTrue(
                    (
                        client.tmp_folder
                        / "etc"
                        / "package-includes"
                        / "plain-configure.zcml"
                    ).exists()
                )
        finally:
            source.unlink()

    def test_pid_file_without_var_folder_raises(self):
        with temp_client() as client:
            client.var_folder = None
            with self.assertRaises(ValueError):
                _ = client.pid_file

    def test_zope_conf_additional_must_be_list(self):
        with temp_client() as client:
            client.options["zope_conf_additional"] = "bogus"
            with self.assertRaises(ValueError):
                _ = client.zope_conf_additional

    def test_generate_password(self):
        with temp_client() as client:
            password = client._generate_password()
            self.assertEqual(len(password), 16)

    def test_command_exits_when_pid_is_running(self):
        with temp_client() as client:
            pid_dir = client.var_folder / client.name
            pid_dir.mkdir(parents=True, exist_ok=True)
            client.pid_file.write_text("123")
            with mock.patch("plonex.zeoclient.os.kill", return_value=None):
                with self.assertRaises(SystemExit):
                    _ = client.command

    def test_command_ignores_stale_pid(self):
        with temp_client() as client:
            pid_dir = client.var_folder / client.name
            pid_dir.mkdir(parents=True, exist_ok=True)
            client.pid_file.write_text("123")
            with mock.patch("plonex.zeoclient.os.kill", side_effect=OSError):
                command = client.command
            self.assertEqual(
                command, [str(client.tmp_folder / "bin" / "instance"), client.run_mode]
            )

    def test_adduser_with_generated_password(self):
        with temp_client() as client:
            with mock.patch.object(
                client, "_generate_password", return_value="secret"
            ), mock.patch.object(client, "execute_command") as mock_run, mock.patch(
                "builtins.print"
            ) as mock_print:
                client.adduser("admin")
            mock_run.assert_called_once()
            mock_print.assert_called_once_with(
                "Please take note of the admin password: secret"
            )

    def test_adduser_keyboard_interrupt(self):
        with temp_client() as client:
            with mock.patch.object(client.logger, "info") as mock_info:
                with mock.patch.object(
                    client, "execute_command", side_effect=KeyboardInterrupt
                ):
                    client.adduser("admin", "secret")
            mock_info.assert_called_once()

    def test_run_script_success(self):
        with temp_client() as client:
            mock_command = mock.Mock(return_value="ok")
            with mock.patch.object(client.logger, "info") as mock_info:
                with mock.patch(
                    "plonex.zeoclient.sh.Command", return_value=mock_command
                ):
                    client.run_script(["script.py"])
            mock_info.assert_called_once_with("ok")

    def test_run_script_error_with_stderr(self):
        with temp_client() as client:

            class ScriptError(Exception):

                def __init__(self):
                    self.stderr = b"boom"

            with mock.patch.object(client.logger, "error") as mock_error:
                with mock.patch(
                    "plonex.zeoclient.sh.Command",
                    return_value=mock.Mock(side_effect=ScriptError()),
                ):
                    client.run_script(["script.py"])
            self.assertEqual(mock_error.call_count, 2)

    def test_run_script_error_without_stderr(self):
        with temp_client() as client:
            with mock.patch.object(client.logger, "error") as mock_error:
                with mock.patch(
                    "plonex.zeoclient.sh.Command",
                    return_value=mock.Mock(side_effect=Exception("boom")),
                ):
                    client.run_script(["script.py"])
            mock_error.assert_called_once()
