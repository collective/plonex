from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.supervisor import Supervisor
from unittest import mock
from unittest.mock import PropertyMock

import inspect


read_expected = ReadExpected(Path(__file__).parent / "expected" / "supervisor")


@contextmanager
def temp_supervisor(**kwargs):
    with temp_cwd() as cwd:
        # Create a fake virtualenv folder structure
        (cwd / ".venv" / "bin").mkdir(parents=True)
        (cwd / ".venv" / "bin" / "activate").touch()
        # with a fake supervisorctl executable that always exits with an error
        # in order to trigger the generation of the supervisor.conf file
        (cwd / ".venv" / "bin" / "supervisorctl").touch(mode=0o755)
        (cwd / ".venv" / "bin" / "supervisorctl").write_text("#!/usr/bin/env false")
        with Supervisor(**kwargs) as supervisor:
            yield supervisor


class TestSupervisor(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(Supervisor.__init__)
        self.assertListEqual(
            list(signature.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "supervisord_conf_template",
                "program_conf_template",
            ],
        )

    def test_constructor(self):
        """Test the constructor for the zeosclient object"""
        with temp_supervisor() as supervisor:
            cwd = Path.cwd()

            # We have some folders
            self.assertEqual(supervisor.target, Path(cwd))
            self.assertEqual(supervisor.etc_folder, Path(cwd) / "etc")
            self.assertEqual(supervisor.tmp_folder, Path(cwd) / "tmp" / "supervisor")
            self.assertEqual(supervisor.var_folder, Path(cwd) / "var")
            self.assertEqual(supervisor.log_folder, Path(cwd) / "var/log")

            # They exist
            self.assertTrue(supervisor.etc_folder.exists())
            self.assertTrue(supervisor.tmp_folder.exists())
            self.assertTrue(supervisor.var_folder.exists())
            self.assertTrue(supervisor.log_folder.exists())

            # We have some pre services
            pre_services_by_name = {
                service.name: service for service in supervisor.pre_services
            }
            self.assertListEqual(
                list(pre_services_by_name),
                [
                    "supervisord.conf",
                    "program.conf",
                ],
            )

    def test_supervisor_conf(self):
        """Test the supervisor.conf file"""
        with temp_supervisor() as supervisor:
            pre_services_by_name = {
                service.name: service for service in supervisor.pre_services
            }
            supervisord_conf = pre_services_by_name["supervisord.conf"]
            expected = read_expected("test_supervisord_conf", supervisor)
            self.assertEqual(supervisord_conf.target_path.read_text(), expected)

    def test_supervisord_conf_path(self):
        """Test the supervisord_conf property returns the correct path"""
        with temp_supervisor() as supervisor:
            self.assertEqual(
                supervisor.supervisord_conf,
                supervisor.etc_folder / "supervisord.conf",
            )

    def test_command(self):
        """Test the command property"""
        with temp_supervisor() as supervisor:
            cmd = supervisor.command
            self.assertEqual(
                cmd,
                [
                    str(supervisor.virtualenv_dir / "bin" / "supervisord"),
                    "-c",
                    str(supervisor.supervisord_conf),
                ],
            )

    def test_supervisord_property(self):
        """Test that supervisord property returns a sh.Command"""
        with temp_supervisor() as supervisor:
            with mock.patch("plonex.supervisor.sh.Command") as mock_command:
                cmd = supervisor.supervisord
            mock_command.assert_called_once_with(
                str(supervisor.virtualenv_dir / "bin" / "supervisord")
            )
            self.assertEqual(cmd, mock_command.return_value)

    def test_supervisorctl_property(self):
        """Test that supervisorctl property returns a sh.Command"""
        with temp_supervisor() as supervisor:
            with mock.patch("plonex.supervisor.sh.Command") as mock_command:
                cmd = supervisor.supervisorctl
            mock_command.assert_called_once_with(
                str(supervisor.virtualenv_dir / "bin" / "supervisorctl")
            )
            self.assertEqual(cmd, mock_command.return_value)

    def test_is_running_when_not_running(self):
        """Test is_running() returns False when supervisorctl exits with non-3 code"""
        with temp_supervisor() as supervisor:
            # supervisorctl exits with non-zero, so is_running should return False.
            self.assertFalse(supervisor.is_running())

    def test_is_running_when_running_with_failing_processes(self):
        """Test is_running() returns True when supervisorctl exits with code 3"""
        with temp_supervisor() as supervisor:

            class FakeError(Exception):

                def __init__(self, exit_code: int):
                    super().__init__(exit_code)
                    self.exit_code = exit_code

            with mock.patch("plonex.supervisor.sh.ErrorReturnCode", FakeError):
                error = FakeError(3)
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(side_effect=error),
                ):
                    self.assertTrue(supervisor.is_running())

    def test_is_running_when_running_successfully(self):
        """Test is_running() returns True when supervisorctl exits with code 0"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(
                Supervisor,
                "supervisorctl",
                new_callable=PropertyMock,
                return_value=mock.Mock(return_value="RUNNING"),
            ):
                self.assertTrue(supervisor.is_running())

    def test_initialize_configuration(self):
        """Test that initialize_configuration runs inside the context manager"""
        with temp_supervisor() as supervisor:
            # Should not raise
            supervisor.initialize_configuration()

    def test_get_status_when_not_running(self):
        """Test get_status() returns a message when supervisor is not running"""
        with temp_supervisor() as supervisor:
            # supervisorctl returns non-zero (not running)
            result = supervisor.get_status()
            self.assertEqual(result, "Supervisord is not running")

    def test_get_status_when_running(self):
        """Test get_status() returns supervisorctl output when running"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=True):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(return_value="myprogram RUNNING"),
                ):
                    result = supervisor.get_status()
            self.assertEqual(result, "myprogram RUNNING")

    def test_get_status_when_running_with_error(self):
        """Test get_status() when supervisorctl raises ErrorReturnCode"""
        with temp_supervisor() as supervisor:

            class FakeError(Exception):

                def __init__(self, stdout: bytes):
                    super().__init__(stdout)
                    self.stdout = stdout

            with mock.patch.object(supervisor, "is_running", return_value=True):
                with mock.patch("plonex.supervisor.sh.ErrorReturnCode", FakeError):
                    error = FakeError(b"some output")
                    with mock.patch.object(
                        Supervisor,
                        "supervisorctl",
                        new_callable=PropertyMock,
                        return_value=mock.Mock(side_effect=error),
                    ):
                        result = supervisor.get_status()
            self.assertEqual(result, "some output")

    def test_run_status(self):
        """Test run_status() when supervisor is not running"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "print") as mock_print:
                supervisor.run_status()
            mock_print.assert_called_once()

    def test_run_stop_when_not_running(self):
        """Test run_stop() when supervisor is not running does nothing"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=False):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(),
                ) as mock_ctl:
                    supervisor.run_stop()
                mock_ctl.return_value.assert_not_called()

    def test_run_stop_when_running(self):
        """Test run_stop() calls supervisorctl shutdown when running"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=True):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(return_value="Shut down"),
                ):
                    with mock.patch.object(supervisor, "print") as mock_print:
                        supervisor.run_stop()
                    mock_print.assert_called_once()

    def test_run_restart_when_not_running(self):
        """Test run_restart() when not running calls run()"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=False):
                with mock.patch.object(supervisor, "run") as mock_run:
                    supervisor.run_restart()
                mock_run.assert_called_once()

    def test_run_restart_when_running(self):
        """Test run_restart() calls supervisorctl restart all when running"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=True):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(return_value="myprogram started"),
                ):
                    with mock.patch.object(supervisor, "print") as mock_print:
                        supervisor.run_restart()
                    mock_print.assert_called_once()

    def test_run_reread_when_not_running(self):
        """Test run_reread() when not running does nothing"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=False):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(),
                ) as mock_ctl:
                    supervisor.run_reread()
                mock_ctl.return_value.assert_not_called()

    def test_run_reread_when_running(self):
        """Test run_reread() calls supervisorctl reread when running"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=True):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(
                        return_value="No config updates to processes"
                    ),
                ):
                    with mock.patch.object(supervisor, "print") as mock_print:
                        supervisor.run_reread()
                    mock_print.assert_called_once()

    def test_run_update_when_not_running(self):
        """Test run_update() when not running does nothing"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=False):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(),
                ) as mock_ctl:
                    supervisor.run_update()
                mock_ctl.return_value.assert_not_called()

    def test_run_update_when_running(self):
        """Test run_update() calls supervisorctl update when running"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=True):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(return_value="myprogram: updated"),
                ):
                    with mock.patch.object(supervisor, "print") as mock_print:
                        supervisor.run_update()
                    mock_print.assert_called_once()

    def test_reread_update_when_not_running(self):
        """Test reread_update() when not running does nothing"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=False):
                with mock.patch.object(
                    Supervisor,
                    "supervisorctl",
                    new_callable=PropertyMock,
                    return_value=mock.Mock(),
                ) as mock_ctl:
                    supervisor.reread_update()
                mock_ctl.return_value.assert_not_called()

    def test_reread_update_when_running(self):
        """Test reread_update() runs reread then update when running"""
        with temp_supervisor() as supervisor:
            with mock.patch.object(supervisor, "is_running", return_value=True):
                with mock.patch.object(
                    supervisor, "run_reread", return_value="reread"
                ) as reread:
                    with mock.patch.object(
                        supervisor, "run_update", return_value="update"
                    ) as update:
                        with mock.patch.object(supervisor, "print") as mock_print:
                            supervisor.reread_update()
            reread.assert_called_once()
            update.assert_called_once()
            self.assertEqual(mock_print.call_count, 2)
