from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.install import InstallService


read_expected = ReadExpected(Path(__file__).parent / "expected" / "install")


@contextmanager
def temp_install(**kwargs):
    with temp_cwd():
        with InstallService(**kwargs) as client:
            yield client


class TestSupervisor(PloneXTestCase):

    def test_constructor(self):
        """Test the constructor for the zeosclient object"""
        with temp_cwd() as temp_dir:
            install = InstallService()

            self.assertEqual(install.target, Path(temp_dir))
            self.assertEqual(install.etc_folder, Path(temp_dir) / "etc")
            self.assertEqual(install.tmp_folder, Path(temp_dir) / "tmp")
            self.assertEqual(
                install.constraints_d_folder, Path(temp_dir) / "etc" / "constraints.d"
            )
            self.assertEqual(
                install.requirements_d_folder, Path(temp_dir) / "etc" / "requirements.d"
            )
