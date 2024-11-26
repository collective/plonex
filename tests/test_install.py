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

    def test_requirements(self):
        # Prepare some fake requirements file
        with temp_cwd():
            install = InstallService()

            (install.requirements_d_folder / "foo.txt").write_text("foo")
            (install.requirements_d_folder / "bar.txt").write_text("bar")
            (install.constraints_d_folder / "foo.txt").write_text("foo==1.0.0")
            (install.constraints_d_folder / "bar.txt").write_text("bar==1.0.0")
            with install:
                self.assertListEqual(
                    install.requirements_txt.read_text().splitlines(),
                    [
                        f"-r {str(install.requirements_d_folder)}/bar.txt",
                        f"-r {str(install.requirements_d_folder)}/foo.txt",
                    ],
                )
                self.assertListEqual(
                    install.constrainst_txt.read_text().splitlines(),
                    ["bar==1.0.0", "foo==1.0.0"],
                )
