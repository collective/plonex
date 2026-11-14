from argparse import ArgumentParser
from argparse import Namespace
from argparse import REMAINDER
from argparse import SUPPRESS
from pathlib import Path
from plonex.services.describe import DescribeService
from plonex.services.invocation import ServiceInvocation


def register_describe_sections(parser, add_subparser):
    from plonex.services.describe.report import SECTIONS

    def options(command, default=None):
        command.add_argument(
            "--format",
            choices=("terminal", "markdown", "html", "json"),
            default=default,
            dest="describe_format",
            help="Report output format",
        )
        command.add_argument(
            "--browse",
            action="store_true",
            default=default,
            dest="describe_browse",
            help="Open the generated HTML report",
        )
        command.add_argument(
            "--key", default=default, help="Configuration option to explain"
        )

    options(parser)
    children = parser.add_subparsers(dest="describe_section", title="Sections")
    for name, title in {"all": "Complete project report", **SECTIONS}.items():
        child = add_subparser(children, name, help=title)
        options(child, SUPPRESS)
        if name in {"configuration", "analytics"}:
            child.add_argument(
                "inspect_command",
                nargs=REMAINDER,
                help="Optional command to inspect, e.g. instance debug --port 8081",
            )


def _handle_describe(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    with ServiceInvocation.from_args(args, target).create(DescribeService) as svc:
        svc.run()


ACTION_HANDLERS = {
    "describe": _handle_describe,
}
