from argparse import ArgumentParser
from argparse import Namespace
from argparse import REMAINDER
from pathlib import Path
from plonex.cli.dependencies import _run_service_dependencies
from plonex.services.invocation import ServiceInvocation
from plonex.services.pytest import PytestService
from plonex.services.robottest import RobotTest
from plonex.services.zopetest import ZopeTest


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


def _handle_pytest(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "pytest")
    with ServiceInvocation.from_args(args, target).create(PytestService) as svc:
        svc.run()


def _handle_test_sources(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.services.sources.testing import run_selected_tests

    result = run_selected_tests(target, args.source_args)
    if result:
        raise SystemExit(result if result > 0 else 1)


def _handle_robottest(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "robottest")
    with ServiceInvocation.from_args(args, target).create(RobotTest) as svc:
        svc.run()


def _handle_zopetest(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    _run_service_dependencies(target, "zopetest")
    with ServiceInvocation.from_args(args, target).create(ZopeTest) as svc:
        svc.run()


ACTION_HANDLERS = {
    "pytest": _handle_pytest,
    "test_sources": _handle_test_sources,
    "robottest": _handle_robottest,
    "zopetest": _handle_zopetest,
}
