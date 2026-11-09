from pathlib import Path
from plonex.base import BaseService
from plonex.services.registry import service_registry
from typing import Any

_SERVICE_REGISTRY = service_registry.services


def _normalize_template_kwargs(kwargs: dict[str, Any], target: Path) -> dict[str, Any]:
    normalized = dict(kwargs)

    if "source" in normalized and "source_path" not in normalized:
        normalized["source_path"] = normalized.pop("source")

    if "target" in normalized and "target_path" not in normalized:
        normalized["target_path"] = normalized.pop("target")

    source_path = normalized.get("source_path")
    if isinstance(source_path, str) and not source_path.startswith("resource://"):
        source_as_path = Path(source_path)
        if not source_as_path.is_absolute():
            normalized["source_path"] = target / source_as_path

    target_path = normalized.get("target_path")
    if isinstance(target_path, str):
        target_as_path = Path(target_path)
        if not target_as_path.is_absolute():
            normalized["target_path"] = target / target_as_path

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
        service_kwargs = _normalize_template_kwargs(service_kwargs, target)

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

    if not isinstance(services, list):
        raise ValueError("The 'services' option should be a list")

    for spec in services:
        service = _service_from_config(spec, target, dependency_for=service_name)
        if service is None:
            continue
        with service:
            service.run()
