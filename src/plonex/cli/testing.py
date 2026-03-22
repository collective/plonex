def register_test_parsers(subs, add_subparser) -> None:
    """Register test-related CLI parsers."""
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

    add_subparser(
        subs,
        "test",
        help="Run the tests for the given package",
    )
