from argparse import ArgumentParser
from argparse import Namespace
from pathlib import Path
from plonex.services.invocation import ServiceInvocation


def _handle_options(args: Namespace, parser: ArgumentParser, target: Path) -> None:
    from plonex.cli import _resolve_target
    from plonex.inspection import ServiceSnapshot

    tokens = args.service_command or []
    if not tokens:
        raise ValueError("Usage: plonex options [--markdown] COMMAND [arguments]")
    service_args = parser.parse_args(
        tokens,
        namespace=Namespace(target=target, verbose=args.verbose, quiet=args.quiet),
    )
    service_target = _resolve_target(service_args)
    invocation = ServiceInvocation.from_args(service_args, service_target)
    service = invocation.create()
    ServiceSnapshot.capture(service, parameters=invocation.parameters).show(
        markdown=args.markdown
    )


ACTION_HANDLERS = {
    "options": _handle_options,
}
