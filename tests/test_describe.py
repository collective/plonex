from .utils import PloneXTestCase
from .utils import temp_cwd
from pathlib import Path
from plonex.describe import DescribeService
from unittest import mock

import inspect


class TestDescribeService(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method"""
        sig = inspect.signature(DescribeService.__init__)
        self.assertListEqual(
            list(sig.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "describe_template",
            ],
        )

    def test_now_property(self):
        """Test that now returns a formatted datetime string"""
        with temp_cwd():
            svc = DescribeService()
            now = svc.now
            # Should be a string like "2026-03-21 12:34:56"
            self.assertRegex(now, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_developed_packages(self):
        """Test the developed_packages property with mocked InstallService"""
        with temp_cwd() as cwd:
            svc = DescribeService()
            with mock.patch("plonex.describe.InstallService") as MockInstall:
                MockInstall.return_value.__enter__ = mock.Mock(
                    return_value=MockInstall.return_value
                )
                MockInstall.return_value.__exit__ = mock.Mock(return_value=False)
                MockInstall.return_value.developed_packages_and_paths.return_value = {
                    "my.package → /path/to/my/package"
                }
                result = svc.developed_packages
            MockInstall.assert_called_once_with(target=cwd)
            self.assertEqual(result, ["my.package → /path/to/my/package"])

    def test_project_files(self):
        with temp_cwd() as cwd:
            svc = DescribeService()
            self.assertEqual(
                svc.project_files,
                [
                    ("Source configuration", cwd / "etc" / "plonex.yml"),
                    ("Source requirements", cwd / "etc" / "requirements.d"),
                    ("Source constraints", cwd / "etc" / "constraints.d"),
                    ("Compiled configuration", cwd / "var" / "plonex.yml"),
                    ("Compiled requirements", cwd / "var" / "requirements.txt"),
                    ("Compiled constraints", cwd / "var" / "constraints.txt"),
                    (
                        "Supervisor configuration",
                        cwd / "tmp" / "supervisor" / "etc" / "supervisord.conf",
                    ),
                    (
                        "Markdown description",
                        cwd / "var" / "plonex_description" / "index.md",
                    ),
                ],
            )

    def test_display_path(self):
        with temp_cwd() as cwd:
            svc = DescribeService()
            self.assertEqual(
                svc.display_path(cwd / "var" / "plonex.yml"), "var/plonex.yml"
            )
            self.assertEqual(
                svc.display_path(Path("/tmp/outside.txt")), "/tmp/outside.txt"
            )

    def test_supervisor_status(self):
        """Test the supervisor_status property with mocked Supervisor"""
        with temp_cwd() as cwd:
            svc = DescribeService()
            with mock.patch("plonex.describe.Supervisor") as MockSupervisor:
                MockSupervisor.return_value.__enter__ = mock.Mock(
                    return_value=MockSupervisor.return_value
                )
                MockSupervisor.return_value.__exit__ = mock.Mock(return_value=False)
                MockSupervisor.return_value.get_status.return_value = (
                    "Supervisord is not running"
                )
                result = svc.supervisor_status
            MockSupervisor.assert_called_once_with(target=cwd)
            self.assertEqual(result, "Supervisord is not running")

    def test_run(self):
        """Test that run() compiles, renders and prints the description"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("mykey: myvalue\n")
            (cwd / "etc" / "requirements.d").mkdir()
            (cwd / "etc" / "constraints.d").mkdir()
            developed_package_path = cwd / "src" / "my.package"
            developed_package_path.mkdir(parents=True)

            with mock.patch(
                "plonex.describe.InstallService.ensure_virtualenv",
                return_value=None,
            ), mock.patch("plonex.describe.Supervisor") as MockSupervisor, mock.patch(
                "plonex.describe.Console"
            ) as MockConsole:
                MockSupervisor.return_value.__enter__ = mock.Mock(
                    return_value=MockSupervisor.return_value
                )
                MockSupervisor.return_value.__exit__ = mock.Mock(return_value=False)
                MockSupervisor.return_value.get_status.return_value = "not running"

                with DescribeService() as svc:
                    with mock.patch.object(
                        DescribeService,
                        "developed_packages",
                        new_callable=mock.PropertyMock,
                        return_value=[f"my.package → {developed_package_path}"],
                    ):
                        svc.run()

                self.assertTrue((cwd / "var" / "plonex.yml").exists())
                self.assertTrue((cwd / "var" / "requirements.txt").exists())
                self.assertTrue((cwd / "var" / "constraints.txt").exists())
                rendered = (cwd / "var" / "plonex_description" / "index.md").read_text()
                self.assertIn(
                    f"[var/plonex.yml](file://{cwd / 'var' / 'plonex.yml'})",
                    rendered,
                )
                self.assertIn(
                    f"[var/requirements.txt](file://{cwd / 'var' / 'requirements.txt'})",  # noqa: E501
                    rendered,
                )
                self.assertIn(
                    f"[var/constraints.txt](file://{cwd / 'var' / 'constraints.txt'})",
                    rendered,
                )
                self.assertIn(
                    f"[etc/plonex.yml](file://{cwd / 'etc' / 'plonex.yml'})",
                    rendered,
                )
                self.assertIn(
                    f"`my.package` → [src/my.package](file://{developed_package_path})",
                    rendered,
                )
                MockConsole.return_value.print.assert_called_once()
