from .utils import temp_cwd
from plonedeployment.base import BaseService

import sys
import unittest


if sys.version_info < (3, 11):

    def _enterContext(self, context_manager):
        context_manager.__enter__()
        self.addCleanup(context_manager.__exit__, None, None, None)

    unittest.TestCase.enterContext = _enterContext


class TestBaseService(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.service = BaseService()
        self.temp_dir = self.enterContext(temp_cwd())

    def test_ensure_dir_with_path(self):
        """Test the ensure path method"""
        foo_path = self.temp_dir / "foo"

        path = self.service._ensure_dir(foo_path)
        self.assertEqual(path, foo_path)
        self.assertTrue(foo_path.exists())
        self.assertTrue(foo_path.is_dir())

        # Rerunning the method should not raise an error
        path = self.service._ensure_dir("foo")

    def test_ensure_dir_with_str(self):
        """Test the ensure path method passing a string"""
        foo_path = self.temp_dir / "foo"

        path = self.service._ensure_dir(str(foo_path))
        self.assertEqual(path, foo_path)
        self.assertTrue(foo_path.exists())
        self.assertTrue(foo_path.is_dir())

    def test_ensure_dir_with_existing_dir(self):
        """Test the ensure path method with an existing directory"""
        foo_path = self.temp_dir / "foo"
        foo_path.mkdir()

        path = self.service._ensure_dir(foo_path)
        self.assertEqual(path, foo_path)
        self.assertTrue(foo_path.exists())
        self.assertTrue(foo_path.is_dir())

    def test_ensure_dir_with_existing_file(self):
        """Test the ensure path method with an existing file"""

        foo_path = self.temp_dir / "foo"
        foo_path.touch()

        with self.assertRaises(ValueError):
            self.service._ensure_dir(foo_path)

    def test_active_only_when_inactive(self):
        """Test the active only decorator when the context manager is not active"""
        client = BaseService()
        with self.assertRaises(RuntimeError):
            client.active_only(lambda self: None)(client)

    def test_run(self):
        """Test the run method"""
        with BaseService() as service:
            service.run()

    def test_cleanup(self):
        """Test the cleanup method"""
        with BaseService() as service:
            conf_folder = service.conf_folder
            self.assertTrue(conf_folder.exists())
        self.assertFalse(conf_folder.exists())