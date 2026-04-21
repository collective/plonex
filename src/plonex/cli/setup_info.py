def _register_sources_subcommands(parser) -> None:
    sources_subs = parser.add_subparsers(dest="sources_action")
    update_parser = sources_subs.add_parser("update", help="Update configured sources")
    update_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    list_parser = sources_subs.add_parser(
        "list", help="List configured sources and status"
    )
    list_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    missing_parser = sources_subs.add_parser(
        "missing", help="Show configured sources that are missing"
    )
    missing_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    clone_missing_parser = sources_subs.add_parser(
        "clone-missing", help="Clone configured missing sources"
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
    force_update_parser = sources_subs.add_parser(
        "force-update",
        help="Force update configured sources",
    )
    force_update_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    force_update_parser.add_argument(
        "-y",
        "--yes",
        help="Skip confirmation prompt",
        required=False,
        default=False,
        action="store_true",
        dest="sources_yes",
    )
    tainted_parser = sources_subs.add_parser(
        "tainted", help="Show sources with local changes"
    )
    tainted_parser.add_argument(
        "glob",
        help="Glob pattern to filter sources (e.g., 'foo' matches '*foo*')",
        default=None,
        nargs="?",
    )
    suggest_existing_parser = sources_subs.add_parser(
        "suggest-existing",
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
        help="Write suggestions into the etc/plonex.yml of the first configured profile",  # noqa: E501
        required=False,
        default=False,
        action="store_true",
        dest="sources_apply_profile",
    )


def register_setup_parsers(subs, add_subparser) -> None:
    """Register setup and information CLI parsers."""
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
    describe_parser.add_argument(
        "--html",
        help="Export the generated description as HTML",
        required=False,
        default=False,
        action="store_true",
        dest="describe_html",
    )
    describe_parser.add_argument(
        "--browse",
        help="Open the generated HTML description in a browser",
        required=False,
        default=False,
        action="store_true",
        dest="describe_browse",
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

    add_subparser(
        subs,
        "upgrade",
        help="Run Plone upgrade steps",
    )

    dependencies_parser = add_subparser(
        subs,
        "dependencies",
        help="Install the dependencies",
    )
    persist_group = dependencies_parser.add_mutually_exclusive_group()
    persist_group.add_argument(
        "-p",
        "--persist",
        help="Persist missing constraints into project etc/constraints.d/",
        required=False,
        action="store_const",
        const="project",
        default=None,
        dest="persist_mode",
    )
    persist_group.add_argument(
        "--persist-local",
        help="Persist missing constraints into a local (git-ignored) constraints file",
        required=False,
        action="store_const",
        const="local",
        dest="persist_mode",
    )
    persist_group.add_argument(
        "--persist-profile",
        help="Persist missing constraints into the first configured profile's etc/constraints.d/",  # noqa: E501
        required=False,
        action="store_const",
        const="profile",
        dest="persist_mode",
    )
    dependencies_parser.add_argument(
        "--update-sources",
        help="Update sources before installing dependencies",
        required=False,
        default=None,
        action="store_true",
        dest="update_sources",
    )
    dependencies_parser.add_argument(
        "--sync",
        help="Synchronize virtualenv packages with compiled requirements",
        required=False,
        default=False,
        action="store_true",
        dest="sync",
    )

    sources_parser = add_subparser(
        subs,
        "sources",
        help="Manage project sources (uses Gitman under the hood)",
    )
    _register_sources_subcommands(sources_parser)
