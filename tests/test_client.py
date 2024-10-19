from .utils import ReadExpected
from .utils import temp_cwd
from .utils import ZeoTestCase
from contextlib import contextmanager
from pathlib import Path
from plonedeployment.zeoclient import ZeoClient


read_expected = ReadExpected(Path(__file__).parent / "expected" / "zeoclient")


@contextmanager
def temp_client():
    with temp_cwd():
        with ZeoClient() as client:
            yield client


class TestZeoClient(ZeoTestCase):

    def test_constructor(self):
        """Test the constructor for the zeosclient object"""
        with temp_cwd() as temp_dir:
            zeo = ZeoClient()

            self.assertEqual(zeo.target, Path(temp_dir))
            self.assertEqual(zeo.tmp_folder, Path(temp_dir) / "tmp")
            self.assertEqual(zeo.var_folder, Path(temp_dir) / "var")
            self.assertIsNone(zeo.zope_conf)
            self.assertIsNone(zeo.wsgi_ini)
            self.assertIsNone(zeo.interpreter)
            self.assertIsNone(zeo.instance)

    def test_constructor_with_params(self):
        """Test the constructor with parameters"""
        with temp_cwd() as temp_dir:
            zeo = ZeoClient(
                temp_dir / "another_place",
                tmp_folder=temp_dir / "another_tmp",
                var_folder=temp_dir / "another_var",
            )
            self.assertEqual(zeo.target, temp_dir / "another_place")
            self.assertEqual(zeo.tmp_folder, temp_dir / "another_tmp")
            self.assertEqual(zeo.var_folder, temp_dir / "another_var")
            self.assertIsNone(zeo.zope_conf)
            self.assertIsNone(zeo.wsgi_ini)
            self.assertIsNone(zeo.interpreter)
            self.assertIsNone(zeo.instance)

    def test_zope_conf(self):
        """Test the zope.conf file"""
        with temp_client() as client:
            self.assertTrue(client.zope_conf.exists())
            expected = read_expected("test_zope_conf", client)
            self.assertEqual(client.zope_conf.read_text(), expected)
