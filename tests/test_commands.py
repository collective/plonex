from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from plonex.cli import main
from plonex.cli.parser import build_parser
from plonex.cli.shell import ShellCompleter
from plonex.inspection import ServiceSnapshot
from plonex.services.invocation import ServiceInvocation
from plonex.services.registry import service_registry
from unittest import mock

import pytest
import sys


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "plonex.yml").write_text("{}\n")
    return tmp_path


@pytest.mark.parametrize(
    "canonical, shortcut",
    [
        (["project", "init", "/tmp/new-project"], ["init", "/tmp/new-project"]),
        (["project", "compile"], ["compile"]),
        (["project", "describe", "--format", "html"], ["describe"]),
        (["project", "edit", "--all"], ["edit", "--all"]),
        (["instance", "start", "--port", "8082"], ["runwsgi", "--port", "8082"]),
        (["instance", "debug", "--name", "special"], ["fg", "--name", "special"]),
        (["instance", "console"], ["zconsole"]),
        (
            ["instance", "run", "--", "task.py", "--flag"],
            ["run", "--", "task.py", "--flag"],
        ),
        (["instance", "add-user", "admin", "secret"], ["adduser", "admin", "secret"]),
        (["instance", "upgrade"], ["upgrade"]),
        (["db", "start"], ["zeoserver"]),
        (
            ["test", "pytest", "demo.pkg", "-k", "login", "--pdb"],
            ["pytest", "demo.pkg", "-k", "login", "--pdb"],
        ),
        (
            ["test", "zope", "demo.pkg", "-t", "filter"],
            ["zopetest", "demo.pkg", "-t", "filter"],
        ),
        (
            ["test", "robot", "test.robot", "--browser", "firefox"],
            ["robottest", "test.robot", "--browser", "firefox"],
        ),
        (
            ["test", "robot-server", "--layer", "my.layer"],
            ["robotserver", "--layer", "my.layer"],
        ),
    ],
)
def test_families_preserve_service_identity_configuration_and_arguments(
    project, canonical, shortcut
):
    parser = build_parser(target=project)
    actual = ServiceInvocation.from_args(parser.parse_args(canonical), project)
    assert actual.command == shortcut[0]
    assert actual.service_type is service_registry.get(shortcut[0])
    assert actual.target == project
    assert (
        actual.snapshot_environment(project / "snapshot.json")["PLONEX_JOB_NAME"]
        == actual.name
    )


@pytest.mark.parametrize(
    "tokens, sync, outdated",
    [
        (["dependencies", "install"], False, False),
        (["dependencies", "sync"], True, False),
        (["dependencies", "outdated"], False, True),
    ],
)
def test_dependency_actions_and_shortcuts_have_identical_modes(
    project, tokens, sync, outdated
):
    args = build_parser(target=project).parse_args(tokens)
    assert args.sync is sync
    assert args.show_outdated is outdated
    assert not hasattr(args, "legacy_dependency_mode")


@pytest.mark.parametrize("operation", ["install", "sync", "add"])
@pytest.mark.parametrize("position", ["after"])
def test_dependency_options_work_on_either_side_of_the_action(
    project, operation, position
):
    options = ["--update-sources", "--persist-local", "-v"]
    action = [operation, "Demo.Pkg"] if operation == "add" else [operation]
    tokens = [
        "dependencies",
        *(options + action if position == "before" else action + options),
    ]
    args = build_parser(target=project).parse_args(tokens)
    assert args.update_sources is True
    assert args.persist_mode == "local"
    assert args.verbose is True


@pytest.mark.parametrize(
    "tokens",
    [
        ["dependencies", "--sync", "--outdated"],
        ["dependencies", "--sync", "install"],
        ["dependencies", "--outdated", "sync"],
        ["dependencies", "--sync", "add", "Demo.Pkg"],
        ["dependencies", "--update-sources", "outdated"],
        ["dependencies", "--persist-local", "outdated"],
        ["dependencies", "outdated", "--update-sources"],
        ["dependencies", "install", "--sync"],
    ],
)
def test_conflicting_or_read_only_operations_are_rejected_before_execution(
    project, tokens
):
    with mock.patch("plonex.cli._run_service_dependencies") as dependencies:
        with mock.patch.object(sys, "argv", ["plonex", *tokens]):
            with pytest.raises(SystemExit) as error:
                main()
        assert error.value.code == 2
        dependencies.assert_not_called()


@pytest.mark.parametrize(
    "tokens", [["dependencies", "install"], ["dependencies", "sync"]]
)
def test_explicit_dependency_actions_dispatch_to_install_service(project, tokens):
    with (
        mock.patch("plonex.cli._configure_logging"),
        mock.patch("plonex.cli._run_service_dependencies") as dependencies,
        mock.patch("plonex.cli.InstallService") as service,
        mock.patch.object(sys, "argv", ["plonex", *tokens, "--update-sources"]),
    ):
        main()
    dependencies.assert_called_once_with(project, "dependencies")
    service.return_value.__enter__.return_value.run.assert_called_once_with(
        persist=False,
        persist_local=False,
        persist_profile=False,
        update_sources=True,
        sync=tokens[-1] == "sync",
    )


def test_outdated_dispatch_does_not_install(project):
    with (
        mock.patch("plonex.cli._configure_logging"),
        mock.patch("plonex.cli._run_service_dependencies"),
        mock.patch("plonex.cli.InstallService") as service,
        mock.patch.object(sys, "argv", ["plonex", "dependencies", "outdated"]),
    ):
        main()
    entered = service.return_value.__enter__.return_value
    entered.run_show_outdated.assert_called_once_with()
    entered.run.assert_not_called()


def test_dependencies_add_persists_requirements_and_uses_install_options(project):
    with (
        mock.patch("plonex.cli._configure_logging"),
        mock.patch("plonex.cli._run_service_dependencies") as dependencies,
        mock.patch("plonex.cli.InstallService") as service,
        mock.patch.object(
            sys,
            "argv",
            [
                "plonex",
                "dependencies",
                "add",
                "Demo.Pkg[test]",
                "--persist-local",
                "--update-sources",
            ],
        ),
    ):
        main()
    dependencies.assert_called_once_with(project, "install")
    entered = service.return_value.__enter__.return_value
    entered.add_packages.assert_called_once_with(["Demo.Pkg[test]"])
    entered.run.assert_called_once_with(
        persist=False,
        persist_local=True,
        persist_profile=False,
        update_sources=True,
        sync=False,
    )


@pytest.mark.parametrize(
    "tokens, method, kwargs",
    [
        (
            ["update", "--force", "--yes"],
            "run_update",
            {"force": True, "assume_yes": True, "glob": None},
        ),
        (
            ["update", "--force"],
            "run_update",
            {"force": True, "assume_yes": False, "glob": None},
        ),
        (
            ["clone", "demo", "--yes"],
            "run_clone_missing",
            {"assume_yes": True, "glob": "demo"},
        ),
        (
            ["suggest", "--apply-local"],
            "run_suggest_existing",
            {"apply": False, "apply_local": True, "apply_profile": False},
        ),
    ],
)
def test_source_commands_preserve_confirmation_and_service_inspection(
    project, tokens, method, kwargs
):
    with (
        mock.patch("plonex.cli._configure_logging"),
        mock.patch("plonex.cli._run_service_dependencies"),
        mock.patch("plonex.cli.SourcesService") as service,
        mock.patch.object(sys, "argv", ["plonex", "sources", *tokens]),
    ):
        main()
    getattr(
        service.return_value.__enter__.return_value, method
    ).assert_called_once_with(**kwargs)
    assert service.return_value._invocation_parameters["sources_action"] == tokens[0]


@pytest.mark.parametrize("family", ["project", "instance", "test"])
def test_bare_families_print_their_help_outside_a_project(
    tmp_path, monkeypatch, family
):
    monkeypatch.chdir(tmp_path)
    with mock.patch.object(sys, "argv", ["plonex", family]):
        with redirect_stdout(StringIO()) as output:
            main()
    assert f"plonex {family}" in output.getvalue()


def test_root_help_identifies_shortcuts_and_all_command_families(project):
    help_text = build_parser(target=project).format_help()
    for name in (
        "project",
        "dependencies",
        "sources",
        "instance",
        "db",
        "test",
        "supervisor",
    ):
        assert name in help_text
    assert "Shortcut" not in help_text
    assert "cron" in help_text


def test_project_aliases_can_target_a_command_family(project):
    (project / "etc" / "plonex.yml").write_text(
        "aliases:\n  refresh: dependencies sync --update-sources\n"
    )
    args = build_parser(target=project).parse_args(["refresh", "--persist-local"])
    assert args.action == "dependencies"
    assert args.sync and args.update_sources
    assert args.persist_mode == "local"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("dependencies ", "dependencies sync "),
        ("dependencies sync --up", "dependencies sync --update-sources "),
        ("instance ", "instance debug "),
        ("test ", "test pytest "),
        ("project ", "project compile "),
        ("sources ", "sources clone "),
        ("sources update --fo", "sources update --force "),
    ],
)
def test_command_families_complete_in_the_interactive_shell(project, line, expected):
    completer = ShellCompleter(build_parser(for_completion=True, target=project))
    matches = []
    index = 0
    while (candidate := completer(line, index)) is not None:
        matches.append(candidate)
        index += 1
    assert expected.rstrip() in [match.rstrip() for match in matches]


def test_inspection_of_canonical_command_keeps_resolved_options_and_redacts_passwords(
    project,
):
    args = build_parser(target=project).parse_args(
        ["instance", "add-user", "admin", "private-password"]
    )
    invocation = ServiceInvocation.from_args(args, project)
    report = ServiceSnapshot.capture(
        invocation.create(), parameters=invocation.parameters
    )
    assert report.name == "adduser"
    assert "private-password" not in repr(report)


def test_dependency_actions_work_with_a_namespace_for_default_actions(project):
    args = build_parser(target=project).parse_args(
        ["dependencies", "sync"], namespace=Namespace(target=project, verbose=True)
    )
    assert args.sync


@pytest.mark.parametrize(
    "tokens",
    [
        [command]
        for command in (
            "init",
            "compile",
            "describe",
            "edit",
            "install",
            "runwsgi",
            "fg",
            "zconsole",
            "run",
            "adduser",
            "upgrade",
            "zeoserver",
            "pytest",
            "zopetest",
            "robottest",
            "robotserver",
        )
    ]
    + [
        ["dependencies", "--sync"],
        ["dependencies", "--outdated"],
        ["dependencies", "sync", "--sync"],
        ["sources", "clone-missing"],
        ["sources", "force-update"],
        ["sources", "suggest-existing"],
        ["instance", "console", "debug"],
        ["project", "describe", "--html"],
    ],
)
def test_removed_duplicate_cli_forms_are_rejected(project, tokens):
    with pytest.raises(SystemExit) as error:
        build_parser(target=project).parse_args(tokens)
    assert error.value.code == 2
