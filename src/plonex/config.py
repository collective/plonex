from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Mapping

import shlex


@dataclass(frozen=True)
class OptionSpec:

    name: str
    default: Any = None
    normalize: Callable[[Any], Any] | None = None


def _normalize_non_negative_float(option_name: str, value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"The '{option_name}' option should be a number") from exc
    if result < 0:
        raise ValueError(
            f"The '{option_name}' option should be greater than or equal to 0"
        )
    return result


def _normalize_sources(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("The 'sources' option should be a mapping")
    return dict(value)


def _normalize_bool_option(option_name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"The '{option_name}' option should be a boolean")


def _normalize_pip_requirements(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError(
        "The 'pip_requirements' option should be a string or a list of strings"
    )


SUPPORTED_OPTION_SPECS: dict[str, OptionSpec] = {
    "default_action": OptionSpec(name="default_action"),
    "default_actions": OptionSpec(name="default_actions"),
    "log_level": OptionSpec(name="log_level"),
    "plone_version": OptionSpec(name="plone_version"),
    "plonex_base_constraint": OptionSpec(name="plonex_base_constraint"),
    "profiles": OptionSpec(name="profiles"),
    "pip_requirements": OptionSpec(
        name="pip_requirements",
        default=["Plone", "rich", "supervisor", "ZEO"],
        normalize=_normalize_pip_requirements,
    ),
    "sources": OptionSpec(name="sources", default={}, normalize=_normalize_sources),
    "sources_location": OptionSpec(name="sources_location", default="src"),
    "sources_update_before_dependencies": OptionSpec(
        name="sources_update_before_dependencies",
        default=False,
        normalize=lambda value: _normalize_bool_option(
            "sources_update_before_dependencies", value
        ),
    ),
    "supervisor_graceful_interval": OptionSpec(
        name="supervisor_graceful_interval",
        default=1.0,
        normalize=lambda value: _normalize_non_negative_float(
            "supervisor_graceful_interval", value
        ),
    ),
}


def normalize_options(options: Mapping[str, Any], logger) -> dict[str, Any]:
    normalized = dict(options)

    for key, spec in SUPPORTED_OPTION_SPECS.items():
        if key not in normalized or spec.normalize is None:
            continue
        try:
            normalized[key] = spec.normalize(normalized[key])
        except ValueError as exc:
            logger.error(str(exc))
            normalized[key] = spec.default
    return normalized


def normalize_default_actions(options: Mapping[str, Any]) -> list[list[str]] | None:
    raw_default_actions = options.get("default_actions")
    raw_default_action = options.get("default_action")
    if raw_default_actions is None and raw_default_action is None:
        return None

    def normalize_action(action: Any) -> list[str]:
        if isinstance(action, str):
            tokens = shlex.split(action)
        elif isinstance(action, list) and all(isinstance(item, str) for item in action):
            tokens = list(action)
        else:
            raise ValueError(
                "Each default action should be a string or a list of strings"
            )
        if not tokens:
            raise ValueError("Default actions cannot be empty")
        return tokens

    if raw_default_actions is not None:
        if isinstance(raw_default_actions, str):
            return [normalize_action(raw_default_actions)]
        if isinstance(raw_default_actions, list):
            if not raw_default_actions:
                raise ValueError("The 'default_actions' option cannot be empty")
            return [normalize_action(action) for action in raw_default_actions]
        raise ValueError(
            "The 'default_actions' option should be a string, a list of strings, "
            "or a list of actions"
        )

    if isinstance(raw_default_action, str):
        return [normalize_action(raw_default_action)]
    if isinstance(raw_default_action, list):
        if not raw_default_action:
            raise ValueError("The 'default_actions' option cannot be empty")
        return [normalize_action(raw_default_action)]

    raise ValueError(
        "The 'default_action' option should be a string or a list of strings"
    )
