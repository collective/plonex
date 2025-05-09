from .utils import PloneXTestCase
from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonex.init import InitService

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
