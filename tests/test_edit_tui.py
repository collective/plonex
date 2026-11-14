from io import StringIO
from plonex.services.edit.tui import FilePicker
from rich.console import Console
from unittest.mock import patch

import os
import pty
import pytest
import termios


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ([b"\r"], [0]),
        ([b"\x1b[B", b"\r"], [1]),
        ([b" ", b"a", b"j", b"\r"], [1]),
        ([b"j", b"k", b"q"], []),
        ([b"\x1b"], []),
    ],
)
def test_picker_keyboard_and_terminal_restoration(tmp_path, keys, expected):
    files = [tmp_path / f"file{index}.yml" for index in range(3)]
    master, slave = pty.openpty()
    try:
        with os.fdopen(os.dup(slave), "r") as terminal:
            before = termios.tcgetattr(slave)
            console = Console(file=StringIO(), force_terminal=True, width=80, height=24)
            picker = FilePicker(files, tmp_path, console)
            with (
                patch("sys.stdin", terminal),
                patch.object(picker, "read_key", side_effect=keys),
            ):
                assert picker.choose() == [files[index] for index in expected]
            assert termios.tcgetattr(slave) == before
    finally:
        os.close(master)
        os.close(slave)


def test_picker_scrolls_and_displays_literal_paths(tmp_path):
    files = [tmp_path / f"[file{index}].yml" for index in range(20)]
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=80, height=12)
    picker = FilePicker(files, tmp_path, console)
    picker.cursor = 18
    console.print(picker.render())
    text = output.getvalue()
    assert "[file18].yml" in text
    assert "[file0].yml" not in text
    assert "of 20" in text


def test_arrow_sequence_is_read_from_terminal():
    master, slave = pty.openpty()
    try:
        import tty

        tty.setcbreak(slave)
        os.write(master, b"\x1b[B")
        assert FilePicker.read_key(slave) == b"\x1b[B"
    finally:
        os.close(master)
        os.close(slave)
