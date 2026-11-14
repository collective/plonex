from argparse import ArgumentParser
from argparse import Namespace
from argparse import REMAINDER
from argparse import SUPPRESS
from pathlib import Path
from plonex.cli.dependencies import _run_service_dependencies
from plonex.cli.describe import register_describe_sections
from plonex.services.compile import CompileService
from plonex.services.install import InstallService
from plonex.services.invocation import ServiceInvocation
from plonex.services.sources import SourcesService
from rich.console import Console


def _register_sources_subcommands(parser, add_subparser) -> None:
    sources_subs = parser.add_subparsers(dest="sources_action")
    update_parser = add_subparser(
        sources_subs, "update", help="Update configured sources"
    )
    update_parser.add_argument(
        "--force",
        action="store_true",
        dest="sources_force",
        help="Allow updating checkouts with local changes (asks for confirmation)",
    )
    update_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        dest="sources_yes",
        help="Skip confirmation for --force",
    )
    update_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    list_parser = add_subparser(
        sources_subs, "list", help="List configured sources and status"
    )
    list_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    missing_parser = add_subparser(
        sources_subs, "missing", help="Show configured sources that are missing"
    )
    missing_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    clone_missing_parser = add_subparser(
        sources_subs,
        "clone",
        help="Clone configured missing sources",
    )
    clone_missing_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    clone_missing_parser.add_argument(
        "-y",
        "--yes",
        help="Skip confirmation prompt",
        required=False,
        default=False,
        action="store_true",
        dest="sources_yes",
    )
    tainted_parser = add_subparser(
        sources_subs, "tainted", help="Show sources with local changes"
    )
    tainted_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    suggest_existing_parser = add_subparser(
        sources_subs,
        "suggest",
        help="Suggest source config entries for unmanaged existing checkouts",
    )
    suggest_apply_group = suggest_existing_parser.add_mutually_exclusive_group()
    suggest_apply_group.add_argument(
        "--apply",
        help="Write suggestions into etc/plonex.yml",
        required=False,
        default=False,
        action="store_true",
        dest="sources_apply",
    )
    suggest_apply_group.add_argument(
        "--apply-local",
        help="Write suggestions into etc/plonex-sources.local.yml",
        required=False,
        default=False,
        action="store_true",
        dest="sources_apply_local",
    )
    suggest_apply_group.add_argument(
        "--apply-profile",
        help=(
            "Write suggestions into the etc/plonex.yml of the first "
            "configured profile"
        ),  # noqa: E501
        required=False,
        default=False,
        action="store_true",
        dest="sources_apply_profile",
    )


def _dependency_options(parser, *, default=None) -> None:
    persist_group = parser.add_mutually_exclusive_group()
    persist_group.add_argument(
        "-p",
        "--persist",
        help="Persist missing constraints into project etc/constraints.d/",
        required=False,
        action="store_const",
        const="project",
        default=default,
        dest="persist_mode",
    )
    persist_group.add_argument(
        "--persist-local",
        help="Persist missing constraints into a local (git-ignored) constraints file",
        required=False,
        action="store_const",
        const="local",
        default=default,
        dest="persist_mode",
    )
    persist_group.add_argument(
        "--persist-profile",
        help=(
            "Persist missing constraints into the first configured "
            "profile's etc/constraints.d/"
        ),  # noqa: E501
        required=False,
        action="store_const",
        const="profile",
        default=default,
        dest="persist_mode",
    )
    parser.add_argument(
        "--update-sources",
        help="Update sources before installing dependencies",
        required=False,
        default=default,
        action="store_true",
        dest="update_sources",
    )


def register_setup_parsers(subs, add_subparser) -> None:
    """Register setup and information CLI parsers."""
    options_parser = add_subparser(
        subs, "options", help="Inspect resolved service options without running it"
    )
    options_parser.add_argument(
        "--markdown", action="store_true", help="Print portable Markdown"
    )
    options_parser.add_argument(
        "service_command",
        nargs=REMAINDER,
        help="Command and its normal flags, e.g. instance debug --port 8081",
    )
    shell_parser = add_subparser(
        subs,
        "shell",
        help="Open an interactive prompt for plonex commands",
        description=(
            "Run plonex commands interactively without repeating the plonex prefix. "
            "Use help for commands, exit or Ctrl-D to leave."
        ),
    )
    # Accept the target on either side of the shell subcommand.
    shell_parser.add_argument(
        "-t", "--target", help="Path to the target project", default=SUPPRESS
    )

    init_parser = add_subparser(
        subs,
        "init",
        description=(
            "Initialize the project in the specified target folder. "
            "This will create the necessary folders and configuration files."
        ),
        help="Initialize the project in the specified target folder.",
    )
    init_parser.add_argument(
        "target",
        type=str,
        help=(
            "Path where the project will be initialized. "
            "Defaults to the current working directory."
        ),
        default=None,
        nargs="?",
    )

    add_subparser(
        subs,
        "compile",
        description=(
            "Compile the configuration files in to var files. "
            "This will read the configuration files "
            "and generate the necessary var files."
        ),
        help="Compile the configuration files in to var files",
    )

    describe_parser = add_subparser(
        subs,
        "describe",
        help="Describe the current project configuration",
    )
    register_describe_sections(describe_parser, add_subparser)

    doctor = add_subparser(subs, "doctor", help="Diagnose project health")
    doctor.add_argument(
        "--format",
        choices=("terminal", "json"),
        default="terminal",
        dest="doctor_format",
        help="Diagnostic output format",
    )
    doctor.add_argument(
        "--strict", action="store_true", help="Treat warnings as an unsuccessful check"
    )

    snapshot = add_subparser(
        subs, "snapshot", help="Capture or compare deployment evidence"
    )
    snapshots = snapshot.add_subparsers(dest="snapshot_action", title="Actions")
    create = add_subparser(snapshots, "create", help="Capture the installed project")
    create.add_argument("--output", help="Write a new JSON file instead of stdout")
    compare = add_subparser(
        snapshots, "compare", help="Compare against a saved snapshot"
    )
    compare.add_argument("file", help="Previously saved snapshot JSON")
    compare.add_argument(
        "--format",
        choices=("terminal", "json"),
        default="terminal",
        dest="snapshot_format",
    )
    prepare = add_subparser(
        snapshots, "prepare", help="Recreate versions in a new virtualenv"
    )
    prepare.add_argument("file", help="Previously saved snapshot JSON")
    prepare.add_argument("--to", required=True, help="New virtualenv directory")
    prepare.add_argument("--python", help="Python interpreter matching the snapshot")

    legacy = add_subparser(
        subs, "inspect_legacy", help="Inspect mxdev or Buildout configuration"
    )
    legacy.add_argument(
        "--format",
        choices=("terminal", "json"),
        default="terminal",
        dest="legacy_format",
    )

    install_parser = add_subparser(
        subs,
        "install",
        help="Add one or more packages to your requirements and install them",
    )
    install_parser.add_argument(
        "package",
        type=str,
        help="Packages to install",
        nargs="+",
    )

    upgrade = add_subparser(
        subs,
        "upgrade",
        help="Run Plone upgrade steps",
    )
    upgrade.add_argument(
        "--url", dest="upgrade_url", help="URL of a running Plone instance"
    )

    dependencies_parser = add_subparser(
        subs,
        "dependencies",
        help="Install, sync, inspect, or add project dependencies",
    )
    dependency_subs = dependencies_parser.add_subparsers(
        dest="dependencies_action", title="Actions"
    )
    for action, description in (
        ("install", "Install configured requirements and selected sources"),
        ("sync", "Compile requirements and synchronize the virtualenv"),
    ):
        child = add_subparser(dependency_subs, action, help=description)
        _dependency_options(child)
    preview = add_subparser(
        dependency_subs,
        "preview",
        help="Preview dependency changes without installation",
    )
    preview.add_argument(
        "--online", action="store_true", help="Allow uv to query package indexes"
    )
    preview.add_argument(
        "--format",
        choices=("terminal", "json"),
        default="terminal",
        dest="preview_format",
    )
    add_subparser(dependency_subs, "outdated", help="List outdated installed packages")
    add = add_subparser(
        dependency_subs, "add", help="Add requirement specifications and install them"
    )
    add.add_argument("package", nargs="+", help="Requirement specifications to add")
    _dependency_options(add)
    add.set_defaults(action="install")

    sources_parser = add_subparser(
        subs,
        "sources",
        help="List, clone, update, or inspect source checkouts",
    )
    _register_sources_subcommands(sources_parser, add_subparser)

    edit_parser = add_subparser(
        subs,
        "edit",
        help="Open plonex configuration files in your favorite editor",
    )
    edit_parser.add_argument(
        "--all",
        help="Open all discovered configuration files (bypass interactive menu)",
        required=False,
        default=False,
        action="store_true",
        dest="open_all",
    )
    edit_parser.add_argument(
        "--editor",
        help="Editor to use (overrides plonex.yml options.editor and $EDITOR env var)",
        required=False,
        default=None,
        dest="editor",
    )


def _handle_compile(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "compile")
    with ServiceInvocation.from_args(args, target).create(CompileService) as svc:
        svc.run()


def _handle_doctor(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.files import read_only
    from plonex.services.doctor import Doctor

    with read_only():
        service = ServiceInvocation.from_args(args, target).create(Doctor)
        result = service.run(output_format=args.doctor_format)
    if result["summary"]["error"] or (args.strict and result["summary"]["warning"]):
        raise SystemExit(1)


def _handle_snapshot(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.inspection import safe_value
    from plonex.services.snapshot import capture
    from plonex.services.snapshot import differences
    from plonex.services.snapshot import load
    from plonex.services.snapshot import prepare
    from plonex.services.snapshot import write_new

    import json

    if not args.snapshot_action:
        raise ValueError(
            "Use 'plonex project snapshot create', 'compare', or 'prepare'."
        )
    if args.snapshot_action == "prepare":
        path = prepare(target, load(args.file), args.to, python=args.python)
        Console().print(f"Prepared environment: {path}", markup=False)
        return
    snapshot = capture(target)
    if args.snapshot_action == "create":
        if args.output:
            Console().print(f"Saved snapshot: {write_new(args.output, snapshot)}")
        else:
            Console().print(
                json.dumps(snapshot, indent=2), markup=False, soft_wrap=True
            )
        return
    changes = safe_value(differences(load(args.file), snapshot))
    if args.snapshot_format == "json":
        Console().print(
            json.dumps({"differences": changes}, indent=2), markup=False, soft_wrap=True
        )
    elif changes:
        for change in changes:
            before = json.dumps(change["before"], ensure_ascii=False)
            after = json.dumps(change["after"], ensure_ascii=False)
            Console().print(
                f"{change['change']}: {change['path']} — {before} → {after}",
                markup=False,
            )
    else:
        Console().print("Project matches the snapshot.")
    if changes:
        raise SystemExit(1)


def _handle_inspect_legacy(
    args: Namespace, parser: ArgumentParser, target: Path
) -> None:
    from plonex.services.legacy import inspect_project

    import json

    report = inspect_project(target)
    if args.legacy_format == "json":
        Console().print(json.dumps(report, indent=2), markup=False, soft_wrap=True)
    else:
        for item in report["findings"]:
            Console().print(f"{item['kind']}: {item['summary']}", markup=False)
            if item.get("suggestion"):
                Console().print(f"  {item['suggestion']}", markup=False)
        for note in report["notes"]:
            Console().print(note, markup=False)
    if any(item.get("severity") == "error" for item in report["findings"]):
        raise SystemExit(1)


def _handle_dependencies(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    if getattr(args, "dependencies_action", None) == "preview":
        from plonex.services.install.preview import preview_dependencies

        result = preview_dependencies(
            target, online=args.online, output_format=args.preview_format
        )
        if not result["resolved"]:
            raise SystemExit(1)
        return
    _run_service_dependencies(target, "dependencies")
    persist_mode = getattr(args, "persist_mode", None)
    with ServiceInvocation.from_args(args, target).create(InstallService) as svc:
        if getattr(args, "show_outdated", False):
            svc.run_show_outdated()
        else:
            svc.run(
                persist=persist_mode == "project",
                persist_local=persist_mode == "local",
                persist_profile=persist_mode == "profile",
                update_sources=getattr(args, "update_sources", None),
                sync=getattr(args, "sync", False),
            )


def _handle_sources(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "sources")
    sources_action = getattr(args, "sources_action", None) or "update"
    glob_pattern = getattr(args, "glob", None)
    with ServiceInvocation.from_args(args, target).create(SourcesService) as svc:
        if sources_action == "update":
            if getattr(args, "sources_force", False):
                svc.run_update(
                    force=True,
                    assume_yes=getattr(args, "sources_yes", False),
                    glob=glob_pattern,
                )
            else:
                svc.run_update(glob=glob_pattern)
        elif sources_action == "list":
            svc.run_list(glob=glob_pattern)
        elif sources_action == "missing":
            svc.run_show_missing(glob=glob_pattern)
        elif sources_action == "clone":
            svc.run_clone_missing(
                assume_yes=getattr(args, "sources_yes", False), glob=glob_pattern
            )
        elif sources_action == "tainted":
            svc.run_show_tainted(glob=glob_pattern)
        elif sources_action == "suggest":
            svc.run_suggest_existing(
                apply=getattr(args, "sources_apply", False),
                apply_local=getattr(args, "sources_apply_local", False),
                apply_profile=getattr(args, "sources_apply_profile", False),
            )
        else:
            parser.print_help()


def _handle_install(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "install")
    with ServiceInvocation.from_args(args, target).create(InstallService) as svc:
        svc.add_packages(args.package)
    with ServiceInvocation.from_args(args, target).create(InstallService) as svc:
        if getattr(args, "dependencies_action", None) == "add":
            persist_mode = getattr(args, "persist_mode", None)
            svc.run(
                persist=persist_mode == "project",
                persist_local=persist_mode == "local",
                persist_profile=persist_mode == "profile",
                update_sources=getattr(args, "update_sources", None),
                sync=False,
            )
        else:
            svc.run()


ACTION_HANDLERS = {
    "compile": _handle_compile,
    "doctor": _handle_doctor,
    "snapshot": _handle_snapshot,
    "inspect_legacy": _handle_inspect_legacy,
    "dependencies": _handle_dependencies,
    "sources": _handle_sources,
    "install": _handle_install,
}
