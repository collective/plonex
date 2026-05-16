from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.services.runwsgi import RunWSGI
from unittest import mock

import inspect


read_expected = ReadExpected(Path(__file__).parent / "expected" / "runwsgi")


@contextmanager
def temp_runwsgi(**kwargs):
    with temp_cwd():
        (Path.cwd() / ".venv" / "bin").mkdir(parents=True)
        (Path.cwd() / ".venv" / "bin" / "activate").touch()
        (Path.cwd() / "etc").mkdir(parents=True)
        (Path.cwd() / "etc" / "plonex.yml").write_text("---")
        with RunWSGI(**kwargs) as svc:
            yield svc


class TestRunWSGI(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(RunWSGI.__init__)
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
                "args",
            ],
        )

    def test_constructor(self):
        """Test the constructor for the RunWSGI object"""
        with temp_runwsgi() as svc:
            cwd = Path.cwd()

            # We have some folders
            self.assertEqual(svc.target, cwd)
            self.assertEqual(svc.tmp_folder, cwd / "tmp" / "runwsgi")
            self.assertEqual(svc.var_folder, cwd / "var")

            # that have been created
            self.assertTrue(svc.target.exists())
            self.assertTrue(svc.tmp_folder.exists())
            self.assertTrue(svc.var_folder.exists())

    def test_constructor_with_params(self):
        """Test the constructor with parameters"""
        with temp_cwd() as temp_dir:
            (temp_dir / "another_place" / ".venv" / "bin").mkdir(parents=True)
            (temp_dir / "another_place" / ".venv" / "bin" / "activate").touch()
            svc = RunWSGI(
                target=temp_dir / "another_place",
                tmp_folder=temp_dir / "another_tmp",
                var_folder=temp_dir / "another_var",
            )
            self.assertEqual(svc.target, temp_dir / "another_place")
            self.assertEqual(svc.tmp_folder, temp_dir / "another_tmp")
            self.assertEqual(svc.var_folder, temp_dir / "another_var")

    def test_zope_conf(self):
        """Test that the zope.conf is generated correctly"""
        with temp_runwsgi() as svc:
            zope_conf = svc.tmp_folder / "etc" / "zope.conf"
            self.assertEqual(
                zope_conf.read_text(),
                read_expected("test_zope_conf", svc),
            )

    def test_wsgi_ini(self):
        """Test that wsgi.ini is generated"""
        with temp_runwsgi() as svc:
            assert svc.tmp_folder is not None
            wsgi_ini = svc.tmp_folder / "etc" / "wsgi.ini"
            self.assertTrue(wsgi_ini.exists())
            content = wsgi_ini.read_text()
            self.assertIn("listen = 0.0.0.0:8080", content)
            self.assertIn("threads = 4", content)
            self.assertIn(str(svc.tmp_folder / "etc" / "zope.conf"), content)

    def test_broken_config_files(self):
        """Test that broken config files are handled gracefully"""
        with mock.patch("logging.Logger.warning") as mock_warning:
            with temp_runwsgi(config_files=["bogus"]) as svc:
                bogus_path = Path("bogus").absolute()
                self.assertEqual(svc.config_files, ["bogus"])
        mock_warning.assert_called_once_with(
            "Config file %r does not exist", bogus_path
        )

        path = Path(__file__).parent / "sample_confs" / "zeoclient_bogus.yml"
        with mock.patch("logging.Logger.error") as mock_error:
            with temp_runwsgi(config_files=[path]) as svc:
                self.assertEqual(svc.config_files, [path])
        mock_error.assert_called_once_with(
            "The config file %r should contain a dict", path
        )

    def test_options_from_config_files(self):
        """Test the options from the config files"""
        path = Path(__file__).parent / "sample_confs" / "zeoclient.yml"
        with temp_runwsgi(config_files=[path]) as svc:
            self.assertListEqual(svc.config_files, [path])
            self.assertSetEqual(
                set(svc.options),
                {
                    "blobstorage",
                    "environment_vars",
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
                svc.options["blobstorage"], str(svc.var_folder / "blobstorage")
            )
            self.assertEqual(svc.options["foo"], "bar")
            self.assertEqual(svc.options["http_address"], "0.0.0.0")
            self.assertEqual(svc.options["http_port"], 8080)
            self.assertEqual(
                svc.options["zeo_address"], str(svc.var_folder / "zeosocket.sock")
            )

    def test_zcml_additional(self):
        """Test the zcml_additional option"""
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zcmls"
        zcml_additional = [
            str(sample_folder / "foo.zcml.j2"),
            str(sample_folder / "bar.zcml.j2"),
        ]
        with temp_runwsgi(
            cli_options={"zcml_additional": zcml_additional, "bar_value": "baz"},
        ) as svc:
            assert svc.tmp_folder is not None
            packages_include_folder = svc.tmp_folder / "etc" / "package-includes"
            self.assertIn(
                "<!-- baz --/>",
                (packages_include_folder / "bar-configure.zcml").read_text(),
            )

    def test_zope_conf_additional(self):
        """Test the zope_conf_additional option"""
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zope_confs"
        zope_conf_additionals = [
            str(sample_folder / "bar.conf.j2"),
            str(sample_folder / "foo.conf.j2"),
        ]
        with temp_runwsgi(
            cli_options={
                "zope_conf_additional": zope_conf_additionals,
                "bar_value": "baz",
            }
        ) as svc:
            assert svc.tmp_folder is not None
            zope_conf = svc.tmp_folder / "etc" / "zope.conf"
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
        """Test that zcml_additional must be a list"""
        with self.assertRaises(ValueError):
            with temp_runwsgi(cli_options={"zcml_additional": "bogus"}):
                pass

    def test_zcml_additional_removes_existing_package_include_files(self):
        """Test that stale package-include files are removed"""
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zcmls"
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / "etc").mkdir(parents=True)
            (cwd / "etc" / "plonex.yml").write_text("---")
            stale_dir = cwd / "tmp" / "runwsgi" / "etc" / "package-includes"
            stale_dir.mkdir(parents=True)
            (stale_dir / "old.zcml").write_text("stale")
            with RunWSGI(
                cli_options={"zcml_additional": [str(sample_folder / "foo.zcml.j2")]}
            ):
                self.assertFalse((stale_dir / "old.zcml").exists())

    def test_zcml_additional_creates_chameleon_cache(self):
        """Test that the CHAMELEON_CACHE directory is created"""
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zcmls"
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / "etc").mkdir(parents=True)
            (cwd / "etc" / "plonex.yml").write_text("---")
            cache_path = cwd / "var" / "cache"
            with RunWSGI(
                cli_options={
                    "zcml_additional": [str(sample_folder / "foo.zcml.j2")],
                    "environment_vars": {"CHAMELEON_CACHE": str(cache_path)},
                }
            ):
                self.assertTrue(cache_path.exists())

    def test_zcml_additional_adds_zcml_suffix(self):
        """Test that a plain file gets a -configure.zcml suffix"""
        sample_folder = Path(__file__).parent / "sample_confs" / "additional_zcmls"
        source = sample_folder / "plain"
        source.write_text("<configure />")
        try:
            with temp_runwsgi(cli_options={"zcml_additional": [str(source)]}) as svc:
                assert svc.tmp_folder is not None
                self.assertTrue(
                    (
                        svc.tmp_folder
                        / "etc"
                        / "package-includes"
                        / "plain-configure.zcml"
                    ).exists()
                )
        finally:
            source.unlink()

    def test_zope_conf_additional_must_be_list(self):
        """Test that zope_conf_additional must be a list"""
        with temp_runwsgi() as svc:
            svc.options["zope_conf_additional"] = "bogus"
            with self.assertRaises(ValueError):
                _ = svc.zope_conf_additional

    def test_generate_password(self):
        """Test that a password is generated with 16 characters"""
        with temp_runwsgi() as svc:
            password = svc._generate_password()
            self.assertEqual(len(password), 16)

    def test_command(self):
        """Test the command property"""
        with temp_runwsgi() as svc:
            assert svc.tmp_folder is not None
            self.assertEqual(
                svc.command,
                [
                    str(svc.virtualenv_dir / "bin" / "runwsgi"),
                    str(svc.tmp_folder / "etc" / "wsgi.ini"),
                ],
            )

    def test_command_with_args(self):
        """Test the command property with extra args"""
        with temp_runwsgi(args=["--reload"]) as svc:
            assert svc.tmp_folder is not None
            self.assertIn("--reload", svc.command)
