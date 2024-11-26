from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.supervisor import Supervisor


read_expected = ReadExpected(Path(__file__).parent / "expected" / "supervisor")


@contextmanager
def temp_supervisor(**kwargs):
    with temp_cwd():
        with Supervisor(**kwargs) as client:
            yield client


class TestSupervisor(PloneXTestCase):

    def test_constructor(self):
        """Test the constructor for the zeosclient object"""
        with temp_cwd() as temp_dir:
            supervisor = Supervisor()

            self.assertEqual(supervisor.target, Path(temp_dir))
            self.assertEqual(supervisor.etc_folder, Path(temp_dir) / "etc")
            self.assertEqual(supervisor.tmp_folder, Path(temp_dir) / "tmp")
            self.assertEqual(supervisor.var_folder, Path(temp_dir) / "var")
            self.assertEqual(supervisor.log_folder, Path(temp_dir) / "var/log")

    def test_supervisor_conf(self):
        """Test the zope.conf file"""
        with temp_supervisor() as supervisor:
            self.assertTrue(supervisor.supervisord_conf.exists())
            expected = read_expected("test_supervisord_conf", supervisor)
            self.assertEqual(supervisor.supervisord_conf.read_text(), expected)
