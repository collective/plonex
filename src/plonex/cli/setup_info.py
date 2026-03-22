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

    add_subparser(
        subs,
        "describe",
        help="Describe the current project configuration",
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
    dependencies_parser.add_argument(
        "-p",
        "--persist",
        help="Persist the constraints",
        required=False,
        dest="persist_constraints",
        default=False,
        action="store_true",
    )
