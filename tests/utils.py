from contextlib import chdir
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from plonedeployment import logger
from tempfile import TemporaryDirectory

import logging
import unittest


@contextmanager
def temp_cwd():
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        with chdir(temp_dir_path):
            yield temp_dir_path


@dataclass
class ReadExpected:

    expected_folder: Path

    def __call__(self, name, service):
        return (
            (self.expected_folder / name)
            .read_text()
            .replace("CONF_PATH", str(service.conf_folder))
            .replace("TARGET_PATH", str(service.target))
        ).strip()


class ZeoTestCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        # Silence the logger
        logger.setLevel(logging.CRITICAL)
