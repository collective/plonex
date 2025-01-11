from contextlib import chdir
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex import logger
from tempfile import TemporaryDirectory

import logging
import unittest


@dataclass(kw_only=True)
class DummyLogger:

    debugs: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def debug(self, *args):
        self.debugs.append(args)

    def info(self, *args):
        self.infos.append(args)

    def error(self, *args):
        self.errors.append(args)


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
        text = (self.expected_folder / name).read_text().strip()

        # Replace the placeholders in the text
        if "CONF_PATH" in text:
            text = text.replace("CONF_PATH", str(service.etc_folder))
        if "TARGET_PATH" in text:
            text = text.replace("TARGET_PATH", str(service.target))

        return text


class PloneXTestCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        # Silence the logger
        logger.setLevel(logging.CRITICAL)
