from .test_install import mock_remote_constraints
from .test_install import stub_virtualenv
from io import StringIO
from plonex.services.install import InstallService
from plonex.services.sources import SourcesService
from plonex.services.sources.installation import local_package_name
from plonex.services.sources.installation import SourceInstallPlan
from rich.console import Console
from unittest import mock

import pytest
import shutil
import subprocess
import sys
import yaml


def make_project(path, name="Demo.Package"):
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "1.0"\n'
    )
    return path


def options_for(**source_options):
    return {
        "sources": {
            "checkout": {"repo": "https://example.org/repo.git", **source_options}
        }
    }


def test_sources_remain_checkout_only_by_default(tmp_path):
    assert not SourceInstallPlan.from_options(tmp_path, options_for()).installations
    assert not SourceInstallPlan.from_options(
        tmp_path, options_for(install=False, extras="ignored")
    ).installations


def test_editable_extras_paths_and_metadata(tmp_path):
    project = make_project(tmp_path / "vendor" / "A checkout" / "python")
    options = options_for(
        install=True,
        path="vendor/A checkout",
        subdirectory="python",
        extras=["Test_Suite", "test.suite", "Zope.Debug"],
    )
    plan = SourceInstallPlan.from_options(tmp_path, options)
    plan.validate()
    (installation,) = plan.installations
    assert installation.path == project
    assert installation.package_name == "demo-package"
    assert installation.requirement == (f"-e {project.as_uri()}[test-suite,zope-debug]")
    assert installation.description == "editable [test-suite,zope-debug]"
    assert plan.package_names == {"demo-package"}


def test_regular_install_uses_canonical_metadata_and_custom_root(tmp_path):
    project = make_project(tmp_path / "checkouts" / "checkout")
    options = options_for(install=True, editable=False, extras=["TEST"])
    options["sources_location"] = "checkouts"
    plan = SourceInstallPlan.from_options(tmp_path, options)
    plan.validate()
    (installation,) = plan.installations
    assert installation.requirement == f"demo-package[test] @ {project.as_uri()}"
    assert installation.description == "regular [test]"


@pytest.mark.parametrize(
    "source_options, message",
    [
        ({"install": "false"}, "'install' must be true or false"),
        ({"editable": "true"}, "'editable' must be true or false"),
        ({"extras": "test"}, "'extras' must be a list"),
        ({"extras": [1]}, "'extras' must be a list"),
        ({"extras": ["bad extra"]}, "invalid extra name"),
        ({"extras": [""]}, "invalid extra name"),
        ({"subdirectory": "/tmp/outside"}, "'subdirectory' must be a relative path"),
        ({"subdirectory": "../outside"}, "'subdirectory' must be a relative path"),
        ({"subdirectory": ""}, "'subdirectory' must be a relative path"),
        ({"subdirectory": 2}, "'subdirectory' must be a relative path"),
    ],
)
def test_bad_installation_options_are_actionable(tmp_path, source_options, message):
    options = options_for(**{"install": True, **source_options})
    with pytest.raises(ValueError, match=message):
        SourceInstallPlan.from_options(tmp_path, options)


def test_invalid_source_mapping_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        SourceInstallPlan.from_options(tmp_path, {"sources": {"bad": "repo"}})


def test_missing_selected_source_suggests_recovery(tmp_path):
    plan = SourceInstallPlan.from_options(tmp_path, options_for(install=True))
    with pytest.raises(ValueError, match="plonex sources clone"):
        plan.validate()


def test_non_python_source_suggests_subdirectory(tmp_path):
    (tmp_path / "src" / "checkout").mkdir(parents=True)
    plan = SourceInstallPlan.from_options(tmp_path, options_for(install=True))
    with pytest.raises(ValueError, match="Set 'subdirectory'"):
        plan.validate()


@pytest.mark.parametrize("character", ["#", "?"])
def test_uv_editable_path_limitation_has_a_useful_error(tmp_path, character):
    project = make_project(tmp_path / f"checkout {character}1")
    options = options_for(install=True, path=str(project))
    with pytest.raises(ValueError, match="Move the checkout or set 'editable: false'"):
        SourceInstallPlan.from_options(tmp_path, options).validate()
    options["sources"]["checkout"]["editable"] = False
    plan = SourceInstallPlan.from_options(tmp_path, options)
    plan.validate()
    assert f" @ {project.as_uri()}" in plan.installations[0].requirement


def test_duplicate_distribution_sources_fail_early(tmp_path):
    make_project(tmp_path / "src" / "one", "Demo.Pkg")
    make_project(tmp_path / "src" / "two", "demo_pkg")
    options = {"sources": {"one": {"install": True}, "two": {"install": True}}}
    with pytest.raises(
        ValueError, match="Multiple selected sources provide 'demo-pkg'"
    ):
        SourceInstallPlan.from_options(tmp_path, options).validate()


@pytest.mark.parametrize(
    "filename, content, expected",
    [
        ("pyproject.toml", '[tool.poetry]\nname="Demo.Poetry"', "demo-poetry"),
        ("setup.cfg", "[metadata]\nname=Demo.Cfg\n", "demo-cfg"),
        ("setup.py", 'raise RuntimeError()\nsetup(name="Demo.Legacy")', "demo-legacy"),
        ("setup.py", 'setuptools.setup(name="Demo.Legacy")', "demo-legacy"),
        ("setup.py", 'something_else(name="Not.The.Name")', "checkout-name"),
        ("setup.py", "setup(version='1.0')", "checkout-name"),
        ("setup.py", "setup(name=NAME)", "checkout-name"),
    ],
)
def test_static_metadata_never_executes_source_code(
    tmp_path, filename, content, expected
):
    project = tmp_path / "Checkout_Name"
    project.mkdir()
    (project / filename).write_text(content)
    assert local_package_name(project) == expected


@pytest.mark.parametrize("editable", [True, False])
def test_selected_sources_generate_requirements_and_override_all_pins(
    tmp_path, monkeypatch, editable
):
    monkeypatch.chdir(tmp_path)
    project = make_project(tmp_path / "src" / "checkout")
    options = options_for(install=True, editable=editable, extras=["TEST"])
    install = InstallService(target=tmp_path, cli_options=options, dont_ask=True)
    (install.constraints_d_folder / "local.txt").write_text("Demo_Package==1.2\n")
    with (
        stub_virtualenv(install),
        mock_remote_constraints(
            {install.plonex_base_constraint: "Demo.Package==1.1\nOther.Pkg==2.0\n"}
        ),
        install,
    ):
        lines = install.requirements_txt.read_text().splitlines()
        expected = (
            f"-e {project.as_uri()}[test]"
            if editable
            else f"demo-package[test] @ {project.as_uri()}"
        )
        assert expected in lines
        assert "demo-package==" not in install.constrainst_txt.read_text()
        assert "other-pkg==2.0" in install.constrainst_txt.read_text()
        expected_developed = {"demo-package"} if editable else set()
        assert install.developed_packages() == expected_developed
        if editable:
            assert install.developed_packages_and_paths() == {
                f"demo-package → {project}"
            }


def test_selected_sources_override_local_base_constraints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path / "src" / "checkout")
    base = tmp_path / "base.txt"
    base.write_text("Demo.Package==1.1\nOther.Pkg==2.0\n")
    install = InstallService(
        target=tmp_path,
        cli_options={**options_for(install=True), "plonex_base_constraint": str(base)},
    )
    (install.constraints_d_folder / "override.txt").write_text("Other.Pkg==3.0\n")
    with stub_virtualenv(install), install:
        assert "demo-package==" not in install.constrainst_txt.read_text()
        assert "other-pkg==3.0" in install.constrainst_txt.read_text()


@pytest.mark.parametrize("sync", [True, False])
def test_sources_are_cloned_before_validation_and_constraint_regeneration(
    tmp_path, monkeypatch, sync
):
    monkeypatch.chdir(tmp_path)
    install = InstallService(target=tmp_path, cli_options=options_for(install=True))

    def clone():
        make_project(tmp_path / "src" / "checkout", "Actual.Distribution")

    base_constraints = "Actual.Distribution==9.0\nOther.Pkg==2.0\n"
    with (
        stub_virtualenv(install),
        mock_remote_constraints({install.plonex_base_constraint: base_constraints}),
        install,
    ):
        assert "actual-distribution==9.0" in install.constrainst_txt.read_text()
        with (
            mock.patch.object(install, "update_gitman_sources", side_effect=clone),
            mock.patch.object(install, "run_command") as run,
            mock.patch.object(
                install, "execute_command", return_value="other-pkg==2.0\n"
            ),
        ):
            install.run(update_sources=True, sync=sync)
        assert "actual-distribution==" not in install.constrainst_txt.read_text()
        assert "-e file:" in install.requirements_txt.read_text()
        assert run.call_count == (2 if sync else 1)


def test_missing_source_does_not_reach_uv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    install = InstallService(target=tmp_path, cli_options=options_for(install=True))
    with stub_virtualenv(install), mock_remote_constraints(), install:
        with mock.patch.object(install, "run_command") as run:
            with pytest.raises(
                ValueError, match="Selected source 'checkout' is missing"
            ):
                install.run()
        run.assert_not_called()


def test_regular_local_install_is_not_suggested_as_a_release_pin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    make_project(tmp_path / "src" / "checkout")
    install = InstallService(
        target=tmp_path, cli_options=options_for(install=True, editable=False)
    )
    with stub_virtualenv(install), mock_remote_constraints(), install:
        with (
            mock.patch.object(install, "run_command"),
            mock.patch.object(
                install, "execute_command", return_value="Demo.Package==1.0\n"
            ),
            mock.patch.object(install.logger, "warning") as warning,
        ):
            install.run(persist_local=True)
        warning.assert_not_called()
        assert not (
            install.constraints_d_folder / "999-autoinstalled.local.txt"
        ).exists()


def test_local_source_selection_respects_profile_and_local_options(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    profile = tmp_path / "profiles" / "dev" / "etc"
    profile.mkdir(parents=True)
    (profile / "plonex.yml").write_text(yaml.safe_dump(options_for(install=True)))
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "plonex.yml").write_text("profiles: [profiles/dev]\n")
    project = make_project(tmp_path / "src" / "checkout")
    service = InstallService(target=tmp_path)
    assert service.source_install_plan.installations[0].path == project
    (etc / "plonex.local.yml").write_text(yaml.safe_dump(options_for(install=False)))
    assert not InstallService(target=tmp_path).source_install_plan.installations


def test_sources_list_shows_installation_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    options = options_for(install=True, extras=["TEST"], subdirectory="python")
    options["sources"]["reference"] = {"repo": "https://example.org/reference.git"}
    with SourcesService(target=tmp_path, cli_options=options) as service:
        with mock.patch("plonex.services.sources.Console") as console:
            service.run_list()
    table = console.return_value.print.call_args_list[0].args[0]
    columns = {column.header: column for column in table.columns}
    assert [str(cell) for cell in columns["Install"]._cells] == [
        "editable [test]",
        "checkout only",
    ]
    assert "project:src/checkout/python" in list(columns["Details"]._cells)[0]
    output = StringIO()
    Console(file=output, width=240, color_system=None).print(table)
    assert "editable [test]" in output.getvalue()


def test_legacy_editable_metadata_resolves_relative_to_target(tmp_path, monkeypatch):
    make_project(tmp_path / "src" / "checkout")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    service = InstallService(
        target=tmp_path, cli_options={"pip_requirements": ["-e src/checkout"]}
    )
    assert service.developed_packages() == {"demo-package"}
    assert service.developed_packages_and_paths() == {
        f"demo-package → {tmp_path / 'src' / 'checkout'}"
    }


def test_gitman_and_installation_use_the_same_custom_checkout_path(tmp_path):
    project = tmp_path / "vendor" / "my-checkout"
    options = options_for(install=True, path="vendor/my-checkout", extras=["test"])
    service = SourcesService(target=tmp_path, cli_options=options)
    compiled = service.compiled_gitman_options
    assert compiled["sources"] == [
        {
            "name": str(project),
            "type": "git",
            "repo": "https://example.org/repo.git",
            "rev": "main",
        }
    ]
    assert service.source_install_plan.installations[0].path == project
    assert service.configured_checkouts() == {"checkout": project}


@pytest.mark.parametrize("editable", [True, False])
def test_generated_requirements_resolve_with_uv_offline(tmp_path, editable):
    """Exercise uv's real parser/resolver, including extras and paths with spaces."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    extra = make_project(tmp_path / "extra source", "Test.Extra")
    project = make_project(tmp_path / "A checkout")
    (project / "demo.py").write_text("VALUE = 1\n")
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires=["setuptools>=61"]\n'
        'build-backend="setuptools.build_meta"\n'
        '[project]\nname="Demo.Package"\nversion="1.0"\n'
        f'[project.optional-dependencies]\ntest=["Test.Extra @ {extra.as_uri()}"]\n'
        '[tool.setuptools]\npy-modules=["demo"]\n'
    )
    plan = SourceInstallPlan.from_options(
        tmp_path,
        options_for(
            install=True, editable=editable, path=str(project), extras=["TEST"]
        ),
    )
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(plan.installations[0].requirement + "\n")
    compiled = tmp_path / "compiled.txt"
    result = subprocess.run(
        [
            uv,
            "pip",
            "compile",
            str(requirements),
            "--python",
            sys.executable,
            "--no-index",
            "--no-build-isolation",
            "--cache-dir",
            str(tmp_path / "cache"),
            "--output-file",
            str(compiled),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    output = compiled.read_text()
    assert (
        f"-e {project.as_uri()}" if editable else f"demo-package @ {project.as_uri()}"
    ) in output
    assert f"test-extra @ {extra.as_uri()}" in output


def test_explicit_distribution_name_supports_dynamic_metadata(tmp_path):
    path = tmp_path / "src/checkout"
    path.mkdir(parents=True)
    (path / "setup.py").write_text(
        'from setuptools import setup\nname = "Real.Pkg"\nsetup(name=name)\n'
    )
    plan = SourceInstallPlan.from_options(
        tmp_path, options_for(install=True, distribution="Real.Pkg")
    )
    plan.validate()
    assert plan.installations[0].package_name == "real-pkg"
    assert plan.package_names == {"real-pkg"}


def test_invalid_explicit_distribution_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="distribution name"):
        SourceInstallPlan.from_options(
            tmp_path, options_for(install=True, distribution="not valid!")
        )
