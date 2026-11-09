"""Read-only inventory of common mxdev and Buildout configuration."""

from configparser import ConfigParser
from pathlib import Path
from plonex.inspection import safe_value

import configparser


def inspect_project(target):
    target = Path(target).absolute()
    findings = []
    notes = [
        "Inspection reads local configuration only; it does not install, "
        "fetch, or change files.",
        "Values are reported as written; includes, interpolation, "
        "and recipes are not executed.",
        "Review every source and recipe before migrating. "
        "No dependency ownership is changed.",
    ]
    for filename, kind in (("mx.ini", "mxdev"), ("buildout.cfg", "buildout")):
        path = target / filename
        if not path.is_file():
            continue
        parser = ConfigParser(
            interpolation=None, strict=False, empty_lines_in_values=False
        )
        try:
            with path.open(encoding="utf-8") as handle:
                parser.read_file(handle)
        except (OSError, UnicodeError, configparser.Error) as error:
            findings.append(
                {
                    "kind": kind,
                    "severity": "error",
                    "summary": f"Cannot parse {filename}: {type(error).__name__}",
                }
            )
            continue
        findings.append(
            {"kind": kind, "summary": f"Found {filename}", "file": filename}
        )
        if kind == "mxdev":
            notes.append(
                "To use mxdev outputs, run mxdev first and configure their "
                "generated requirements and constraints in Plonex; do not "
                "select the same source for both tools."
            )
            settings = parser["settings"] if parser.has_section("settings") else {}
            for option in (
                "requirements-in",
                "constraints-in",
                "requirements-out",
                "constraints-out",
                "version-overrides",
            ):
                value = settings.get(option, "")
                if value:
                    findings.append(
                        {
                            "kind": "mxdev setting",
                            "summary": f"{option}: {safe_value(value)}",
                            "option": option,
                            "value": safe_value(value),
                        }
                    )
            for name in parser.sections():
                if name in {"settings", "DEFAULT"}:
                    continue
                item = parser[name]
                repo = item.get("url", "")
                if not repo:
                    continue
                row = {
                    "name": name,
                    "repo": safe_value(repo),
                    "branch": item.get("branch", ""),
                    "tag": item.get("tag", ""),
                    "extras": item.get("extras", ""),
                    "install_mode": item.get("install-mode", ""),
                }
                findings.append(
                    {
                        "kind": "mxdev source",
                        "summary": f'{name}: {row["repo"]}',
                        "suggestion": "Review repo, revision, extras, and install "
                        "mode for a plonex sources entry.",
                        **row,
                    }
                )
        else:
            section = parser["buildout"] if parser.has_section("buildout") else {}
            for option in ("extends", "parts", "extensions", "develop", "versions"):
                value = section.get(option, "")
                if value:
                    findings.append(
                        {
                            "kind": "buildout setting",
                            "summary": f"{option}: {safe_value(value)}",
                            "option": option,
                            "value": safe_value(value),
                        }
                    )
            for name in parser.sections():
                item = parser[name]
                recipe = item.get("recipe", "")
                if recipe:
                    lowered = recipe.lower()
                    if "zeoserver" in lowered:
                        suggestion = "Compare with plonex db and ZEO configuration."
                    elif "zopeinstance" in lowered:
                        suggestion = "Compare with plonex instance configuration."
                    elif "supervisor" in lowered:
                        suggestion = "Compare with plonex Supervisor configuration."
                    elif "backup" in lowered:
                        suggestion = (
                            "Review database and blob backup requirements separately."
                        )
                    elif "recipe.egg" in lowered:
                        suggestion = (
                            "Review package requirements and generated scripts."
                        )
                    else:
                        suggestion = "Custom recipe: review its behavior manually."
                    findings.append(
                        {
                            "kind": "buildout recipe",
                            "summary": f"{name}: {safe_value(recipe)}",
                            "part": name,
                            "recipe": safe_value(recipe),
                            "suggestion": suggestion,
                        }
                    )
            if parser.has_section("sources"):
                for name, value in parser.items("sources", raw=True):
                    findings.append(
                        {
                            "kind": "buildout source",
                            "summary": f"{name}: {safe_value(value)}",
                            "name": name,
                            "value": safe_value(value),
                        }
                    )
    if not findings:
        notes.insert(0, "No mx.ini or buildout.cfg found in this directory.")
    return {"target": str(target), "findings": findings, "notes": notes}
