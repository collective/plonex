from io import StringIO
from plonex.base import BaseService
from plonex.services.sources import SourcesService
from rich.console import Console
from rich.text import Text
from unittest import mock

import pytest
import subprocess


@pytest.fixture
def checkouts(tmp_path, monkeypatch):
    """Use real Git probes so accidental stdout and stderr echoing is visible."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COLUMNS", "200")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "plonex.yml").write_text("{}\n")
    paths = {}
    for name, branch in (("configured.pkg", "main"), ("local.pkg", "local-branch")):
        path = tmp_path / "src" / name
        path.mkdir(parents=True)
        for args in (
            ["init", "-q", "-b", branch],
            ["remote", "add", "origin", f"git@example.org:{name}.git"],
        ):
            subprocess.run(
                ["git", "-C", str(path), *args],
                check=True,
                capture_output=True,
                text=True,
            )
        (path / "untracked.txt").write_text("local modifications\n")
        paths[name] = path
    return tmp_path, paths


def make_service(target, *, sources=True):
    options = {
        "sources": (
            {
                "configured.pkg": {
                    "repo": "git@example.org:configured.pkg.git",
                    "rev": "main",
                }
            }
            if sources
            else {}
        )
    }
    return SourcesService(target=target, cli_options=options)


@pytest.mark.parametrize("output_enabled", [True, False])
def test_list_keeps_git_probe_output_inside_the_report(
    checkouts, capsys, output_enabled
):
    target, _ = checkouts
    with mock.patch.object(BaseService, "command_output_enabled", output_enabled):
        with make_service(target) as service:
            service.run_list()
    captured = capsys.readouterr()
    assert captured.err == ""
    output = captured.out
    assert output.lstrip().startswith("Sources")
    assert "\nmain\n" not in output
    assert "\nlocal-branch\n" not in output
    assert "\ngit@example.org:" not in output
    assert "?? untracked.txt" not in output
    assert "configured.pkg" in output
    assert "local.pkg" in output


def test_unmanaged_checkout_is_a_table_row_with_highlighted_yaml_suggestion(checkouts):
    target, _ = checkouts
    output = StringIO()
    console = Console(
        file=output, width=200, force_terminal=True, color_system="standard"
    )
    with make_service(target) as service:
        with mock.patch("plonex.services.sources.Console", return_value=console):
            service.run_list()
    rendered = output.getvalue()
    plain = Text.from_ansi(rendered).plain
    table, suggestion = plain.split("Legend:")
    local_row = next(line for line in table.splitlines() if "local.pkg" in line)
    assert "src/local.pkg" in local_row
    assert "unmanaged" in local_row
    assert "not configured" in local_row
    assert "branch:local-branch" in local_row
    assert "modified" in local_row
    assert "git@example.org:local.pkg.git" in local_row
    assert "⚠" in local_row
    assert "Suggested sources · etc/plonex.yml" in suggestion
    assert "local.pkg:" in suggestion
    assert "rev: local-branch" in suggestion
    assert "configured.pkg:" not in suggestion
    assert "install: true" in suggestion
    assert "\x1b[" in rendered


def test_list_shows_unmanaged_sources_without_any_configured_sources(checkouts):
    target, _ = checkouts
    output = StringIO()
    with make_service(target, sources=False) as service:
        with mock.patch(
            "plonex.services.sources.Console",
            return_value=Console(file=output, width=200, color_system=None),
        ):
            service.run_list()
    table = output.getvalue().split("Legend:")[0]
    assert "local.pkg" in table
    assert "configured.pkg" in table


@pytest.mark.parametrize(
    "pattern, expected, excluded",
    [
        ("local", "local.pkg", "configured.pkg"),
        ("configured", "configured.pkg", "local.pkg"),
    ],
)
def test_glob_filters_both_rows_and_suggestions(checkouts, pattern, expected, excluded):
    target, _ = checkouts
    output = StringIO()
    with make_service(target) as service:
        with mock.patch(
            "plonex.services.sources.Console",
            return_value=Console(file=output, width=200, color_system=None),
        ):
            service.run_list(glob=pattern)
    rendered = output.getvalue()
    assert expected in rendered
    assert excluded not in rendered


def test_no_matches_reports_empty_selection_without_suggestions(checkouts, capsys):
    target, _ = checkouts
    with make_service(target) as service:
        service.run_list(glob="absent*")
    assert capsys.readouterr().out.strip() == "No source checkouts match."


def test_missing_origin_does_not_leak_git_errors(checkouts, capsys):
    target, paths = checkouts
    subprocess.run(
        ["git", "-C", str(paths["local.pkg"]), "remote", "remove", "origin"],
        check=True,
        capture_output=True,
    )
    with make_service(target) as service:
        service.run_list()
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "No such remote" not in captured.out
    assert "local.pkg" in captured.out
