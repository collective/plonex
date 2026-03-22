from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from plonex.init import InitService
from unittest import mock

import inspect


read_expected = ReadExpected(Path(__file__).parent / "expected" / "install")


@contextmanager
def temp_init(**kwargs):
    with temp_cwd():
        with InitService(**kwargs) as client:
            yield client


class TestInit(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(InitService.__init__)
        self.assertListEqual(
            list(signature.parameters),
            ["self", "name", "target", "cli_options", "config_files"],
        )

    def test_options_defaults(self):
        """Test that options_defaults includes init defaults."""
        with temp_cwd():
            svc = InitService()
            defaults = svc.options_defaults
            self.assertIn("plonex_version", defaults)
            self.assertIn("plone_version", defaults)
            self.assertEqual(defaults["plonex_version"], version("plonex"))
            self.assertEqual(defaults["plone_version"], "6.1-latest")

    def test_post_init_creates_pre_services(self):
        """Test that __post_init__ creates pre_services for new project"""
        with temp_cwd():
            svc = InitService()
            self.assertEqual(len(svc.pre_services), 2)
            names = [svc.name for svc in svc.pre_services]
            self.assertIn("plonex", names)
            self.assertIn("requirements", names)

    def test_post_init_skips_existing_files(self):
        """Test that __post_init__ skips creating pre_services for existing files"""
        with temp_cwd() as cwd:
            etc = cwd / "etc"
            etc.mkdir()
            (etc / "plonex.yml").write_text("---\n")
            (etc / "requirements.d").mkdir()
            (etc / "requirements.d" / "000-plonex.txt").write_text("plone\n")
            (etc / "constraints.d").mkdir()
            (etc / "constraints.d" / "000-plonex.txt").write_text("# constraints\n")
            svc = InitService()
            # No pre_services should be created
            self.assertEqual(len(svc.pre_services), 0)

    def test_constructor(self):
        """Test that the context manager sets up the init service"""
        with temp_init() as svc:
            self.assertTrue(svc.target.exists())
            # plonex.yml should have been created
            self.assertTrue((svc.target / "etc" / "plonex.yml").exists())

    def test_generated_plonex_yml_contains_services_proposal(self):
        """Test that init template proposes service-driven supervisor entries."""
        with temp_init() as svc:
            content = (svc.target / "etc" / "plonex.yml").read_text()
            self.assertIn("plone_version: 6.1-latest", content)
            self.assertNotIn("plonex_base_constraint:", content)
            self.assertIn("services:", content)
            self.assertIn(
                "resource://plonex.supervisor.templates:program.conf.j2", content
            )
            self.assertIn("tmp/supervisor/etc/supervisor/zeoserver.conf", content)
            self.assertIn("tmp/supervisor/etc/supervisor/zeoclient.conf", content)

    def test_legacy_constraints_file_sets_default_plone_version(self):
        with temp_cwd() as cwd:
            etc = cwd / "etc"
            (etc / "constraints.d").mkdir(parents=True)
            (etc / "plonex.yml").write_text("{}\n")
            (etc / "constraints.d" / "000-plonex.txt").write_text("Plone==6.1.4\n")
            svc = InitService()

            with mock.patch.object(svc.logger, "warning") as mock_warning:
                self.assertEqual(svc.options["plone_version"], "6.1.4")

            self.assertTrue(
                any(
                    "Ignoring legacy constraints file" in str(call)
                    for call in mock_warning.call_args_list
                )
            )

    def test_plonex_yml_overrides_legacy_constraints_file(self):
        with temp_cwd() as cwd:
            etc = cwd / "etc"
            (etc / "constraints.d").mkdir(parents=True)
            (etc / "plonex.yml").write_text("plone_version: 6.1.6\n")
            (etc / "constraints.d" / "000-plonex.txt").write_text("Plone==6.1.4\n")
            svc = InitService()

            with mock.patch.object(svc.logger, "warning") as mock_warning:
                self.assertEqual(svc.options["plone_version"], "6.1.6")

            self.assertTrue(
                any(
                    "Ignoring legacy constraints file" in str(call)
                    for call in mock_warning.call_args_list
                )
            )

    def test_plonex_base_constraint_overrides_legacy_constraints_file(self):
        with temp_cwd() as cwd:
            etc = cwd / "etc"
            (etc / "constraints.d").mkdir(parents=True)
            (etc / "plonex.yml").write_text("plonex_base_constraint: etc/custom.txt\n")
            (etc / "constraints.d" / "000-plonex.txt").write_text("Plone==6.1.4\n")
            svc = InitService()

            with mock.patch.object(svc.logger, "warning") as mock_warning:
                self.assertEqual(
                    svc.options["plonex_base_constraint"], "etc/custom.txt"
                )

            self.assertTrue(
                any(
                    "Ignoring legacy constraints file" in str(call)
                    for call in mock_warning.call_args_list
                )
            )

    def test_run_creates_gitignore(self):
        """Test that run() creates a .gitignore file"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            with mock.patch("plonex.init.InstallService") as MockInstall, mock.patch(
                "plonex.init.Supervisor"
            ) as MockSupervisor:
                MockInstall.return_value.__enter__ = mock.Mock(
                    return_value=MockInstall.return_value
                )
                MockInstall.return_value.__exit__ = mock.Mock(return_value=False)
                MockSupervisor.return_value.__enter__ = mock.Mock(
                    return_value=MockSupervisor.return_value
                )
                MockSupervisor.return_value.__exit__ = mock.Mock(return_value=False)
                with mock.patch.object(InitService, "execute_command"):
                    with InitService() as svc:
                        svc.run()
            self.assertTrue((cwd / ".gitignore").exists())

    def test_run_skips_gitignore_if_exists(self):
        """Test that run() does not overwrite an existing .gitignore"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / ".gitignore").write_text("existing\n")
            with mock.patch("plonex.init.InstallService") as MockInstall, mock.patch(
                "plonex.init.Supervisor"
            ) as MockSupervisor:
                MockInstall.return_value.__enter__ = mock.Mock(
                    return_value=MockInstall.return_value
                )
                MockInstall.return_value.__exit__ = mock.Mock(return_value=False)
                MockSupervisor.return_value.__enter__ = mock.Mock(
                    return_value=MockSupervisor.return_value
                )
                MockSupervisor.return_value.__exit__ = mock.Mock(return_value=False)
                (cwd / ".git").mkdir()
                with mock.patch.object(InitService, "execute_command"):
                    with InitService() as svc:
                        svc.run()
            # existing .gitignore should not be overwritten
            self.assertEqual((cwd / ".gitignore").read_text(), "existing\n")
