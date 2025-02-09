from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.install import InstallService

import inspect


read_expected = ReadExpected(Path(__file__).parent / "expected" / "install")


@contextmanager
def temp_install(**kwargs):
    with temp_cwd():
        kwargs["dont_ask"] = True
        with InstallService(**kwargs) as client:
            yield client


class TestInit(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method

        We want to be sure that our dataclass accepts a predefined list of arguments
        """
        signature = inspect.signature(InstallService.__init__)
        self.assertListEqual(
            list(signature.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "dont_ask",
            ],
        )

    def test_constructor(self):
        """Test the constructor for the zeosclient object"""
        with temp_cwd() as temp_dir:
            install = InstallService(dont_ask=True)

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
        """Check that we can properly merge the requirements files"""
        with temp_cwd():
            install = InstallService(dont_ask=True)

            (install.requirements_d_folder / "foo.txt").write_text("foo")
            (install.requirements_d_folder / "bar.txt").write_text("bar")
            (install.constraints_d_folder / "foo.txt").write_text("foo==1.0.0")
            (install.constraints_d_folder / "bar_obsolete.txt").write_text("bar==0.8.0")
            (install.constraints_d_folder / "bar.txt").write_text("bar==1.0.0")
            (install.constraints_d_folder / "bar_py38.txt").write_text(
                "bar==0.9.0; python_version == '3.8'"
            )
            with install:
                self.assertListEqual(
                    install.requirements_txt.read_text().splitlines(),
                    [
                        "# This file is generated by plonex",
                        f"-r {str(install.requirements_d_folder)}/bar.txt",
                        f"-r {str(install.requirements_d_folder)}/foo.txt",
                    ],
                )
                self.assertListEqual(
                    install.constrainst_txt.read_text().splitlines(),
                    [
                        "# This file is generated by plonex",
                        "bar==1.0.0",
                        'bar==0.9.0; python_version == "3.8"',
                        "foo==1.0.0",
                    ],
                )
