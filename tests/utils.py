from contextlib import chdir
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def temp_cwd():
    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        with chdir(temp_dir_path):
            yield temp_dir_path


@dataclass
class ReadExpected:

    expected_folder: Path

    def __call__(self, name, zeo):
        return (
            (self.expected_folder / name)
            .read_text()
            .replace("CONF_PATH", str(zeo.conf_folder))
            .replace("TARGET_PATH", str(zeo.target))
        ).strip()
