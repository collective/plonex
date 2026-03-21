from .utils import PloneXTestCase
from .utils import temp_cwd
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
        with temp_cwd():
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
            self.assertEqual(result, ["my.package → /path/to/my/package"])

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
        """Test that run() renders and prints the description"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()

            with mock.patch(
                "plonex.describe.InstallService"
            ) as MockInstall, mock.patch(
                "plonex.describe.Supervisor"
            ) as MockSupervisor:
                MockInstall.return_value.__enter__ = mock.Mock(
                    return_value=MockInstall.return_value
                )
                MockInstall.return_value.__exit__ = mock.Mock(return_value=False)
                MockInstall.return_value.developed_packages_and_paths.return_value = (
                    set()
                )
                MockSupervisor.return_value.__enter__ = mock.Mock(
                    return_value=MockSupervisor.return_value
                )
                MockSupervisor.return_value.__exit__ = mock.Mock(return_value=False)
                MockSupervisor.return_value.get_status.return_value = "not running"

                with DescribeService() as svc:
                    with mock.patch("plonex.describe.Console") as MockConsole:
                        svc.run()
                    MockConsole.return_value.print.assert_called_once()
