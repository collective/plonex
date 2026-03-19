from .utils import DummyLogger
from .utils import temp_cwd
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.directory import DirectoryService

import inspect
import unittest


@dataclass(kw_only=True)
class DummyDirectoryService(DirectoryService):

    logger: DummyLogger = field(default_factory=DummyLogger)  # type: ignore


class TestDirectoryService(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.temp_dir = self.enterContext(temp_cwd())

    # --- Initialisation ---

    def test_init_signature(self):
        """DirectoryService accepts the expected constructor arguments"""
        signature = inspect.signature(DirectoryService.__init__)
        self.assertListEqual(
            list(signature.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "path",
                "mode",
            ],
        )

    def test_name_default(self):
        """name defaults to 'directory'"""
        service = DirectoryService()
        self.assertEqual(service.name, "directory")

    def test_path_default(self):
        """path defaults to Path() (current directory)"""
        service = DirectoryService()
        self.assertEqual(service.path, Path())

    def test_mode_default(self):
        """mode defaults to None (no chmod applied)"""
        service = DirectoryService()
        self.assertIsNone(service.mode)

    def test_path_custom(self):
        """A custom path is stored as-is"""
        custom = self.temp_dir / "custom"
        service = DirectoryService(path=custom)
        self.assertEqual(service.path, custom)

    # --- run() requires context manager ---

    def test_run_outside_context_raises(self):
        """run() raises RuntimeError when called outside the context manager"""
        service = DirectoryService(path=self.temp_dir / "new_dir")
        with self.assertRaises(RuntimeError):
            service.run()

    # --- run() happy paths ---

    def test_run_creates_directory(self):
        """run() creates the target directory when it does not yet exist"""
        new_dir = self.temp_dir / "new_dir"
        self.assertFalse(new_dir.exists())
        with DummyDirectoryService(path=new_dir) as service:
            service.run()
        self.assertTrue(new_dir.exists())
        self.assertTrue(new_dir.is_dir())

    def test_run_creates_nested_directories(self):
        """run() creates all intermediate parent directories"""
        nested = self.temp_dir / "a" / "b" / "c"
        with DummyDirectoryService(path=nested) as service:
            service.run()
        self.assertTrue(nested.exists())

    def test_run_existing_directory_does_not_raise(self):
        """run() succeeds silently when the directory already exists"""
        existing = self.temp_dir / "exists"
        existing.mkdir()
        with DummyDirectoryService(path=existing) as service:
            service.run()
        self.assertTrue(existing.is_dir())

    def test_run_logs_info(self):
        """run() logs an info message with the target path"""
        new_dir = self.temp_dir / "logged_dir"
        with DummyDirectoryService(path=new_dir) as service:
            service.run()
        self.assertTrue(any(str(new_dir) in str(msg) for msg in service.logger.infos))

    # --- run() error path ---

    def test_run_sets_mode(self):
        """run() applies the configured mode to the directory"""
        new_dir = self.temp_dir / "moded_dir"
        with DummyDirectoryService(path=new_dir, mode=0o750) as service:
            service.run()
        self.assertEqual(new_dir.stat().st_mode & 0o777, 0o750)

    def test_run_without_mode_does_not_chmod(self):
        """run() leaves directory permissions unchanged when mode is None"""
        new_dir = self.temp_dir / "no_mode_dir"
        new_dir.mkdir(mode=0o755)
        original_mode = new_dir.stat().st_mode
        with DummyDirectoryService(path=new_dir) as service:
            service.run()
        self.assertEqual(new_dir.stat().st_mode, original_mode)

    def test_run_raises_when_path_is_a_file(self):
        """run() raises ValueError when path already exists as a file"""
        file_path = self.temp_dir / "a_file"
        file_path.touch()
        with DummyDirectoryService(path=file_path) as service:
            with self.assertRaises(ValueError):
                service.run()
