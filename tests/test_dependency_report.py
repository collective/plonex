from .test_install import temp_install
from io import StringIO
from pathlib import Path
from plonex.services.install import InstallService
from plonex.services.install.report import DependencyReport
from rich.console import Console
from unittest import mock
from zipfile import ZipFile

import pytest
import shutil
import subprocess
import sys


def render(output):
    stream = StringIO()
    DependencyReport.from_output(output).show(Console(file=stream, width=160))
    return stream.getvalue()


def test_no_changes_only_displays_a_single_line():
    assert render("Checked 15 packages in 14ms\n") == "No package changes.\n"


@pytest.mark.parametrize(
    "output, expected",
    [
        (" + Foo.Bar==1.0\n", "Added foo-bar==1.0"),
        (" - Foo_Bar==1.0\n", "Removed foo-bar==1.0"),
        (" ~ Foo.Bar==1.0 (from file:///tmp/foo)\n", "Reinstalled foo-bar==1.0"),
        (" - Foo.Bar==1.0\n + foo-bar==2.0\n", "Upgraded foo-bar: 1.0 → 2.0"),
        (" + Foo.Bar==1.9\n - foo-bar==1.10\n", "Downgraded foo-bar: 1.10 → 1.9"),
        (" - Foo.Bar==2.0rc1\n + foo-bar==2.0\n", "Upgraded foo-bar: 2.0rc1 → 2.0"),
        (" - foo==1.0\n + foo==1.0\n", "Reinstalled foo==1.0"),
        (
            " - foo==1.0 (from file:///old)\n + foo==1.0 (from file:///new)\n",
            "Changed source foo==1.0",
        ),
        (" - foo==legacy-a\n + foo==legacy-b\n", "Updated foo: legacy-a → legacy-b"),
        (" - foo==1.0\n + foo==1.0.0\n", "Updated foo: 1.0 → 1.0.0"),
    ],
)
def test_report_describes_actual_package_operations(output, expected):
    assert render(output).strip() == expected


def test_report_omits_routine_output_but_preserves_warnings_and_context():
    output = (
        "Using Python 3.13 environment at: /tmp/.venv\n"
        "Resolved 500 packages in 8s\nPrepared 2 packages in 1s\n"
        "Downloading demo\n Downloaded demo\nBuilding demo\n Built demo\n"
        "Uninstalled 1 package in 2ms\nInstalled 2 packages in 3ms\n"
        "warning: demo does not provide extra [test]\n"
        "  required by my-project\n"
        " - Zope.Sendmail==7.2\n + zope-sendmail==7.3\n + New.Pkg==1.0\n"
    )
    assert render(output).splitlines() == [
        "warning: demo does not provide extra [test]",
        "  required by my-project",
        "Added new-pkg==1.0",
        "Upgraded zope-sendmail: 7.2 → 7.3",
    ]


def test_unknown_installer_activity_does_not_claim_no_packages_changed():
    result = render("Installed 2 packages in 1ms\n + future-format @ file:///tmp/foo\n")
    assert "future-format" in result
    assert "Dependencies updated." in result
    assert "No package changes" not in result


def test_summary_handles_editable_requirements_without_printing_the_freeze(capsys):
    with temp_install() as install:
        frozen = "accesscontrol==7.7\nacquisition==6.2\n-e /tmp/local-project\n"
        install.constrainst_txt.write_text("accesscontrol==7.7\nacquisition==6.2\n")
        with (
            mock.patch.object(install, "run_command"),
            mock.patch.object(
                install, "execute_command", return_value=frozen
            ) as execute,
        ):
            install.run()
        assert execute.call_args.kwargs["capture_output"] is True
        assert (install.tmp_folder / "installed.txt").read_text() == frozen
    assert capsys.readouterr().out == "No package changes.\n"


def wheel(folder, version, name="Demo.Package"):
    filename = name.lower().replace(".", "_").replace("-", "_")
    path = folder / f"{filename}-{version}-py3-none-any.whl"
    info = f"{filename}-{version}.dist-info"
    with ZipFile(path, "w") as archive:
        archive.writestr("demo.py", "VALUE = 1\n")
        archive.writestr(
            f"{info}/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        )
        archive.writestr(
            f"{info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: plonex-test\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{info}/RECORD", "")
    return path


@pytest.fixture
def offline_install(tmp_path, monkeypatch):
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UV_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("UV_NO_INDEX", "1")
    monkeypatch.setenv("UV_OFFLINE", "1")
    subprocess.run(
        [
            uv,
            "venv",
            "--python",
            sys.executable,
            "--no-python-downloads",
            str(tmp_path / ".venv"),
        ],
        check=True,
        capture_output=True,
    )
    (tmp_path / ".venv" / "bin" / "uv").symlink_to(Path(uv).resolve())
    base = tmp_path / "base.txt"
    base.write_text("")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "plonex.yml").write_text("{}\n")
    service = InstallService(
        target=tmp_path,
        dont_ask=True,
        cli_options={"plonex_base_constraint": str(base)},
    )
    (service.constraints_d_folder / "pins.txt").write_text(
        "demo-package>=0\nkeep-package>=0\n"
    )
    requirements = []

    def make_requirements():
        service.requirements_txt = service.var_folder / "requirements.txt"
        service.requirements_txt.write_text("\n".join(requirements) + "\n")

    with mock.patch.object(
        service, "make_requirements_txt", side_effect=make_requirements
    ):
        with service:
            yield service, requirements, tmp_path


def test_real_uv_install_upgrade_downgrade_reinstall_and_sync(offline_install, capsys):
    service, requirements, folder = offline_install
    first = wheel(folder, "1.0")
    second = wheel(folder, "2.0")
    requirements[:] = [str(first)]
    service.make_requirements_txt()
    service.run()
    captured = capsys.readouterr()
    assert captured.out == "Added demo-package==1.0\n"
    assert captured.err == ""

    service.run()
    captured = capsys.readouterr()
    assert captured.out == "No package changes.\n"
    assert captured.err == ""

    requirements[:] = [str(second)]
    service.make_requirements_txt()
    service.run()
    assert capsys.readouterr().out == "Upgraded demo-package: 1.0 → 2.0\n"

    requirements[:] = [str(first)]
    service.make_requirements_txt()
    service.run()
    assert capsys.readouterr().out == "Downgraded demo-package: 2.0 → 1.0\n"

    command = [*service.command, "--reinstall"]
    with mock.patch.object(
        type(service), "command", new_callable=mock.PropertyMock, return_value=command
    ):
        service.run()
    assert capsys.readouterr().out == "Reinstalled demo-package==1.0\n"

    requirements[:] = [str(wheel(folder, "1.0", name="Keep.Package"))]
    service.make_requirements_txt()
    service.run(sync=True)
    captured = capsys.readouterr()
    assert "Removed demo-package==1.0" in captured.out
    assert "Resolved" not in captured.out
    assert "# This file was autogenerated" not in captured.out
    assert service._dependency_output is None


def test_real_uv_failure_retains_resolver_diagnostics_without_a_success_summary(
    offline_install, capsys
):
    service, requirements, _ = offline_install
    requirements[:] = ["nonexistent-plonex-test-package==999"]
    service.make_requirements_txt()
    with pytest.raises(SystemExit) as error:
        service.run()
    assert error.value.code != 0
    captured = capsys.readouterr()
    assert "Dependency command failed" in captured.err
    assert "nonexistent-plonex-test-package" in captured.err
    assert "No package changes" not in captured.out
    assert not (service.tmp_folder / "installed.txt").exists()
    assert service._dependency_output is None


def test_verbose_keeps_raw_uv_output_but_never_prints_the_freeze(
    offline_install, capsys
):
    service, requirements, folder = offline_install
    requirements[:] = [str(wheel(folder, "1.0"))]
    service.make_requirements_txt()
    with mock.patch.object(service.logger, "isEnabledFor", return_value=True):
        service.run()
    captured = capsys.readouterr()
    assert "Added demo-package==1.0" in captured.out
    assert "Resolved" in captured.err
    assert "\ndemo-package @ file:" not in captured.out


def test_report_remains_available_in_quiet_mode(offline_install, capsys):
    service, requirements, folder = offline_install
    requirements[:] = [str(wheel(folder, "1.0"))]
    service.make_requirements_txt()
    with mock.patch.object(service, "command_output_enabled", False):
        service.run()
    captured = capsys.readouterr()
    assert captured.out == "Added demo-package==1.0\n"
    assert captured.err == ""
