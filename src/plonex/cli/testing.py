from argparse import REMAINDER


def register_test_parsers(subs, add_subparser) -> None:
    """Register test-related CLI parsers."""
    sources = add_subparser(
        subs, "test_sources", help="Run configured tests for selected sources"
    )
    sources.add_argument(
        "source_args",
        nargs=REMAINDER,
        help="Source names, followed by -- and optional runner arguments",
    )
    pytest_parser = add_subparser(
        subs, "pytest", help="Run pytest for an importable package or test path"
    )
    pytest_parser.add_argument("package", help="Python package or test path to run")
    pytest_parser.add_argument(
        "pytest_args",
        nargs=REMAINDER,
        help="Arguments passed to pytest after the package, e.g. -k login -x",
    )

    robotserver_parser = add_subparser(
        subs,
        "robotserver",
        help="Start the Robot Server",
    )
    robotserver_parser.add_argument(
        "-l",
        "--layer",
        type=str,
        help="Testing layer to use",
        required=False,
        default="Products.CMFPlone.testing.PRODUCTS_CMFPLONE_ROBOT_TESTING",
        dest="layer",
    )

    robottest_parser = add_subparser(
        subs,
        "robottest",
        help="Run Robot Tests",
    )
    robottest_parser.add_argument(
        "paths",
        type=str,
        help="Paths to the Robot Test files",
        nargs="+",
    )
    robottest_parser.add_argument(
        "-b",
        "--browser",
        type=str,
        help="Browser to use for the tests (default: firefox)",
        required=False,
        default="firefox",
        dest="browser",
    )
    robottest_parser.add_argument(
        "-t",
        "--test",
        type=str,
        help="Name of the test(s) to run. It supports regular expressions.",
        required=False,
        default="",
        dest="test",
    )

    zopetest_parser = add_subparser(
        subs,
        "zopetest",
        help="Run Zope Tests",
    )
    zopetest_parser.add_argument(
        "package",
        type=str,
        help="Package to test",
    )
    zopetest_parser.add_argument(
        "-t",
        "--test",
        type=str,
        help="Name of the test(s) to run. It supports regular expressions.",
        required=False,
        default="",
        dest="test",
    )
