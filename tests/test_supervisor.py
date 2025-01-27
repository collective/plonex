from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.supervisor import Supervisor


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
