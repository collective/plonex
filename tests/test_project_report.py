from plonex.cli.parser import build_parser
from plonex.services.describe import DescribeService
from plonex.services.describe.report import SECTIONS
from plonex.services.invocation import ServiceInvocation
from unittest import mock

import json
import os
import pytest
import yaml


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "plonex.yml").write_text(
        yaml.safe_dump(
            {
                "http_port": 8080,
                "plone_version": "6.2-latest",
                "environment_vars": {
                    "REPORT_SIDE_EFFECT": "must-not-be-exported",
                    "API_TOKEN": "private-value",
                },
                "sources": {"demo.pkg": {"repo": "https://example.org/demo.git"}},
            }
        )
    )
    (tmp_path / "etc" / "plonex.local.yml").write_text("http_port: 9000\n")
    return tmp_path


@pytest.mark.parametrize("section", ["all", *SECTIONS])
def test_every_report_section_has_canonical_cli_binding(project, section):
    args = build_parser(target=project).parse_args(
        ["project", "describe", section, "--format", "json"]
    )
    invocation = ServiceInvocation.from_args(args, project)
    service = invocation.create()
    assert service.section == section
    assert service.output_format == "json"
    with service:
        service.run()
    payload = json.loads(
        (service.describe_folder / f"{service.report_stem}.json").read_text()
    )
    assert [part["key"] for part in payload["sections"]] == (
        list(SECTIONS) if section == "all" else [section]
    )
    assert service.description_html_path.is_file()
    assert service.description_path.is_file()


def test_describe_never_installs_compiles_starts_services_or_exports_environment(
    project, monkeypatch
):
    monkeypatch.delenv("REPORT_SIDE_EFFECT", raising=False)
    with (
        mock.patch(
            "plonex.services.install.InstallService.ensure_virtualenv",
            side_effect=AssertionError("installed"),
        ),
        mock.patch(
            "plonex.services.compile.CompileService.run",
            side_effect=AssertionError("compiled"),
        ),
        mock.patch(
            "plonex.services.supervisor.Supervisor.run",
            side_effect=AssertionError("started"),
        ),
    ):
        with DescribeService(target=project, output_format="html") as service:
            service.run()
    assert "REPORT_SIDE_EFFECT" not in os.environ
    assert not (project / ".venv").exists()
    assert not (project / "var" / "requirements.txt").exists()
    assert not (project / "var" / "plonex.yml").exists()


def test_explain_command_shows_actual_runtime_defaults_and_cli_overrides(
    project, capsys
):
    args = build_parser(target=project).parse_args(
        [
            "project",
            "describe",
            "configuration",
            "--format",
            "json",
            "--key",
            "http_port",
            "instance",
            "debug",
            "--port",
            "9090",
        ]
    )
    with ServiceInvocation.from_args(args, project).create() as service:
        service.run()
    result = json.loads(capsys.readouterr().out)
    (detail,) = result["sections"][0]["details"]
    assert detail["value"] == 9090
    assert detail["source"] == "CLI overrides"
    assert [entry["value"] for entry in detail["history"]][-3:] == [8080, 9000, 9090]
    assert not (project / "tmp" / "fg" / "etc" / "zope.conf").exists()


def test_configuration_section_does_not_probe_unrelated_runtimes(project):
    with DescribeService(
        target=project, section="configuration", key="http_port"
    ) as service:
        with mock.patch.object(
            service, "execute_command", side_effect=AssertionError("unexpected probe")
        ):
            service.run()


def test_selected_section_does_not_overwrite_complete_report(project):
    with DescribeService(target=project) as full:
        full.run()
    original = full.description_html_path.read_text()
    with DescribeService(target=project, section="sources") as partial:
        partial.run()
    assert partial.description_html_path.name == "sources.html"
    assert full.description_html_path.read_text() == original


def test_html_is_semantic_responsive_searchable_and_escapes_values(project):
    local = project / "etc" / "plonex.local.yml"
    local.write_text(
        yaml.safe_dump(
            {
                "evil": "<script>alert('x')</script>",
                "API_TOKEN": "another-private-value",
            }
        )
    )
    with DescribeService(target=project) as service:
        service.run()
    html = service.description_html_path.read_text()
    assert 'name="viewport"' in html
    assert '<nav aria-label="Report sections">' in html
    assert 'id="filter"' in html
    assert 'scope="col"' in html
    assert "@media(max-width:800px)" in html
    assert "<script>alert('x')</script>" not in html
    assert "&lt;script&gt;" in html
    assert "another-private-value" not in html
    assert "private-value" not in service.description_path.read_text()
    assert "[redacted]" in html
    assert "https://cdn" not in html
    assert "<pre><code>" not in html
    assert service.description_html_path.stat().st_mode & 0o777 == 0o600


def test_browse_opens_the_selected_report(project):
    with mock.patch("plonex.services.describe.webbrowser.open") as browser:
        with DescribeService(
            target=project, section="analytics", browse_html=True
        ) as service:
            service.run()
    browser.assert_called_once_with(service.description_html_path.as_uri())


def test_unknown_key_and_section_have_actionable_errors(project):
    with DescribeService(
        target=project, section="configuration", key="not_configured"
    ) as service:
        with pytest.raises(ValueError, match="Unknown configuration key"):
            service.run()
    with DescribeService(target=project, section="../escape") as service:
        with pytest.raises(ValueError, match="Unknown description section"):
            service.run()


def test_derived_credentials_are_redacted_from_environment_and_all_exports(project):
    (project / "etc/plonex.local.yml").write_text(
        yaml.safe_dump(
            {
                "api_secret": "hidden-derived-value",
                "endpoint": "https://example.org/{{ api_secret }}",
                "environment_vars": {"ORDINARY_NAME": "{{ endpoint }}"},
            }
        )
    )
    for section in ("all", "environment", "configuration"):
        with DescribeService(target=project, section=section) as service:
            service.run()
        for path in (
            service.description_path,
            service.description_html_path,
            service.describe_folder / f"{service.report_stem}.json",
        ):
            assert "hidden-derived-value" not in path.read_text()


def test_explaining_an_instance_preserves_existing_runtime_includes(project):
    includes = project / "tmp/fg/etc/package-includes"
    includes.mkdir(parents=True)
    existing = includes / "custom-configure.zcml"
    existing.write_text("<configure />")
    cache = project / "var/new-chameleon-cache"
    (project / "etc/plonex.local.yml").write_text(
        yaml.safe_dump({"environment_vars": {"CHAMELEON_CACHE": str(cache)}})
    )
    args = build_parser(target=project).parse_args(
        [
            "project",
            "describe",
            "configuration",
            "instance",
            "debug",
        ]
    )
    with ServiceInvocation.from_args(args, project).create() as service:
        service.run()
    assert existing.read_text() == "<configure />"
    assert not cache.exists()
