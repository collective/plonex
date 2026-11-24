from pathlib import Path
from plonex.base import BaseService
from plonex.services.registry import service_registry
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlsplit

_SERVICE_REGISTRY = service_registry.services


def _normalize_template_kwargs(kwargs: dict[str, Any], target: Path) -> dict[str, Any]:
    normalized = dict(kwargs)

    if "source" in normalized and "source_path" not in normalized:
        normalized["source_path"] = normalized.pop("source")

    if "target" in normalized and "target_path" not in normalized:
        normalized["target_path"] = normalized.pop("target")

    for key in ("source_path", "target_path"):
        value = normalized.get(key)
        if not isinstance(value, str) or value.startswith("resource://"):
            continue
        if value.startswith("file:"):
            uri = urlsplit(value)
            if uri.netloc not in ("", "localhost") or uri.query or uri.fragment:
                raise ValueError(f"Invalid local file URI: {value}")
            value = unquote(uri.path)
        path = Path(value).expanduser()
        normalized[key] = path if path.is_absolute() else target / path

    return normalized


def _match_service_dependency(
    service_kwargs: dict[str, Any],
    dependency_for: str | None,
) -> bool:
    run_for = service_kwargs.get("run_for")
    if dependency_for is None:
        return True
    if run_for is None:
        return False
    if isinstance(run_for, str):
        return run_for == dependency_for
    if isinstance(run_for, list):
        return dependency_for in run_for
    raise ValueError("The 'run_for' option should be a string or a list of strings")


def _service_from_config(
    spec: dict[str, Any],
    target: Path,
    dependency_for: str | None = None,
    config_directory: Path | None = None,
) -> BaseService | None:
    if not isinstance(spec, dict):
        raise ValueError("Each service entry should be a mapping")
    if len(spec) != 1:
        raise ValueError("Each service entry should contain exactly one service key")

    service_name, service_config = next(iter(spec.items()))
    if service_config is None:
        service_kwargs: dict[str, Any] = {}
    elif isinstance(service_config, dict):
        service_kwargs = dict(service_config)
    else:
        raise ValueError(
            f"Service {service_name!r} configuration should be a mapping or null"
        )

    if not _match_service_dependency(service_kwargs, dependency_for):
        return None

    service_kwargs.pop("run_for", None)

    service_class = _SERVICE_REGISTRY.get(service_name)
    if service_class is None:
        known_services = ", ".join(sorted(_SERVICE_REGISTRY))
        raise ValueError(
            f"Unknown service {service_name!r}. Known services: {known_services}"
        )

    if service_name == "template":
        service_kwargs = _normalize_template_kwargs(
            service_kwargs, config_directory or target
        )

    service_kwargs.setdefault("target", target)

    try:
        return service_class(**service_kwargs)
    except TypeError as exc:
        raise ValueError(
            f"Invalid configuration for service {service_name!r}: {exc}"
        ) from exc


def _run_service_dependencies(target: Path, service_name: str) -> None:
    with BaseService(target=target) as svc:
        services = svc.options.get("services") or []
        definitions = svc.configuration_trace.definitions.get(("services",), [])

    if not isinstance(services, list):
        raise ValueError("The 'services' option should be a list")

    # Trace events contain the list after each append or removal. Keep the
    # defining directory alongside each entry as those operations are applied.
    previous: list = []
    directories: list[Path] = []
    for definition in definitions:
        current = definition.value if isinstance(definition.value, list) else []
        source = Path(definition.source)
        directory = source.parent if source.is_file() else target
        if definition.operation == "append" and current[: len(previous)] == previous:
            directories.extend([directory] * (len(current) - len(previous)))
        elif definition.operation == "remove":
            remaining = iter(zip(previous, directories))
            kept = []
            for item in current:
                for old_item, old_directory in remaining:
                    if old_item == item:
                        kept.append(old_directory)
                        break
            directories = kept
        else:
            directories = [directory] * len(current)
        previous = current

    for index, spec in enumerate(services):
        directory = directories[index] if index < len(directories) else target
        service = _service_from_config(
            spec, target, dependency_for=service_name, config_directory=directory
        )
        if service is None:
            continue
        with service:
            service.run()
