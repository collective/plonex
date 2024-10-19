from .utils import ReadExpected
from .utils import temp_cwd
from contextlib import contextmanager
from pathlib import Path
from plonedeployment import logger
from plonedeployment.zeoserver import ZeoServer

import logging
import unittest


read_expected = ReadExpected(Path(__file__).parent / "expected" / "zeoserver")


@contextmanager
def temp_zeo():
    with temp_cwd():
        with ZeoServer() as zeo:
            yield zeo


class TestZeoServer(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        # Silence the logger
        logger.setLevel(logging.CRITICAL)

    def test_constructor(self):
        """Test the constructor for the zeoserver object"""
        with temp_cwd() as temp_dir:
            zeo = ZeoServer()
            self.assertEqual(zeo.target, Path(temp_dir))
            self.assertEqual(zeo.tmp_folder, Path(temp_dir) / "tmp")
            self.assertEqual(zeo.var_folder, Path(temp_dir) / "var")
            self.assertEqual(zeo.zeo_conf, None)
            self.assertEqual(zeo.runzeo, None)

    def test_constructor_with_params(self):
        """Test the constructor with parameters"""
        with temp_cwd() as temp_dir:
            zeo = ZeoServer(
                temp_dir / "another_place",
                tmp_folder=temp_dir / "another_tmp",
                var_folder=temp_dir / "another_var",
            )
            self.assertEqual(zeo.target, temp_dir / "another_place")
            self.assertEqual(zeo.tmp_folder, temp_dir / "another_tmp")
            self.assertEqual(zeo.var_folder, temp_dir / "another_var")
            self.assertEqual(zeo.zeo_conf, None)
            self.assertEqual(zeo.runzeo, None)

    def test_ensure_dir_with_path(self):
        """Test the ensure path method"""
        with temp_cwd() as temp_dir:
            zeo = ZeoServer()
            foo_path = temp_dir / "foo"

            path = zeo._ensure_dir(foo_path)
            self.assertEqual(path, foo_path)
            self.assertTrue(foo_path.exists())
            self.assertTrue(foo_path.is_dir())

            # Rerunning the method should not raise an error
            path = zeo._ensure_dir("foo")

    def test_ensure_dir_with_str(self):
        """Test the ensure path method passing a string"""
        with temp_cwd() as temp_dir:
            zeo = ZeoServer()
            foo_path = temp_dir / "foo"

            path = zeo._ensure_dir(str(foo_path))
            self.assertEqual(path, foo_path)
            self.assertTrue(foo_path.exists())
            self.assertTrue(foo_path.is_dir())

    def test_ensure_dir_with_existing_dir(self):
        """Test the ensure path method with an existing directory"""
        with temp_cwd() as temp_dir:
            zeo = ZeoServer()
            foo_path = temp_dir / "foo"
            foo_path.mkdir()

            path = zeo._ensure_dir(foo_path)
            self.assertEqual(path, foo_path)
            self.assertTrue(foo_path.exists())
            self.assertTrue(foo_path.is_dir())

    def test_ensure_dir_with_existing_file(self):
        """Test the ensure path method with an existing file"""
        with temp_cwd() as temp_dir:
            zeo = ZeoServer()
            foo_path = temp_dir / "foo"
            foo_path.touch()

            with self.assertRaises(ValueError):
                zeo._ensure_dir(foo_path)

    def test_active_only_when_inactive(self):
        """Test the active only method"""
        with temp_cwd():
            zeo = ZeoServer()
            with self.assertRaises(RuntimeError):
                ZeoServer.active_only(lambda self: None)(zeo)

    def test_active_only_when_active(self):
        """Test the active only method"""
        with temp_zeo() as zeo:
            self.assertIsNone(ZeoServer.active_only(lambda self: None)(zeo))

    def test_zeo_conf(self):
        """Test the zeo conf method"""
        with temp_zeo() as zeo:
            self.assertTrue(zeo.zeo_conf.exists())
            # Read the file "expected/zeoserver/test_zeo_conf"
            # and compare it with the generated file
            expected = read_expected("test_zeo_conf", zeo)
            self.assertEqual(zeo.zeo_conf.read_text(), expected)
