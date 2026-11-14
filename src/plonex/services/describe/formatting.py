"""Safe, self-contained HTML formatting for report values."""

from html import escape
from markupsafe import Markup
from pygments.lexers import YamlLexer  # type: ignore[import-untyped]
from pygments.token import STANDARD_TYPES  # type: ignore[import-untyped]

import hashlib
import json
import re
import yaml

_VARIABLE = re.compile(r"{{\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*}}")
_MISSING = object()


def _reference(name, values):
    value = values
    for part in name.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _format_data(value):
    """Recognize structured values without interpreting ordinary prose as YAML."""
    if isinstance(value, (dict, list)):
        return yaml.safe_dump(
            value, sort_keys=False, allow_unicode=True, default_flow_style=False
        ).rstrip("\n"), YamlLexer(stripnl=False, ensurenl=False)
    if not isinstance(value, str):
        return str(value), None
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, (dict, list)):
        return yaml.safe_dump(
            data, sort_keys=False, allow_unicode=True, default_flow_style=False
        ).rstrip("\n"), YamlLexer(stripnl=False, ensurenl=False)
    if "\n" in value:
        try:
            data = yaml.safe_load(_VARIABLE.sub("PLONEX_VARIABLE", value))
        except yaml.YAMLError:
            data = None
        if isinstance(data, (dict, list)):
            # Preserve the source text, including comments and variable syntax.
            return value, YamlLexer(stripnl=False, ensurenl=False)
    return value, None


def variable_definitions(report, references, origins):
    """Build destinations for references present in the redacted report."""
    names = sorted(set(_VARIABLE.findall(json.dumps(report, ensure_ascii=False))))
    result = {}
    for name in names:
        value = _reference(name, references)
        if value is _MISSING or name not in origins:
            continue
        anchor = "variable-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
        result[name] = {"anchor": anchor, "value": value, "source": origins[name]}
    return result


def render_value(value, references, origins=None, destinations=None):
    """Format values as escaped HTML and annotate simple configuration references."""
    text, lexer = _format_data(value)
    matches = list(_VARIABLE.finditer(text))
    if lexer is None and not matches:
        return None

    # Lex the entire value once: restarting a lexer inside a quoted string
    # changes its state and formatters can add newlines to partial fragments.
    tokens = list(lexer.get_tokens_unprocessed(text)) if lexer else []

    def fragment(start, end):
        if not lexer:
            return escape(text[start:end])
        parts = []
        for position, token, content in tokens:
            left = max(start, position)
            right = min(end, position + len(content))
            if left >= right:
                continue
            css_token = token
            while css_token not in STANDARD_TYPES:
                css_token = css_token.parent
            css = STANDARD_TYPES[css_token]
            value = escape(text[left:right])
            parts.append(f'<span class="{css}">{value}</span>' if css else value)
        return "".join(parts)

    result = []
    start = 0
    for match in matches:
        result.append(fragment(start, match.start()))
        resolved = _reference(match.group(1), references)
        if resolved is _MISSING:
            result.append(escape(match.group()))
        else:
            rendered = (
                yaml.safe_dump(
                    resolved,
                    sort_keys=False,
                    allow_unicode=True,
                    default_flow_style=False,
                ).rstrip("\n")
                if isinstance(resolved, (dict, list))
                else str(resolved)
            )
            name = match.group(1)
            source = (origins or {}).get(name, "")
            title = escape(
                f"{name}: {rendered}" + (f"\nDefined in: {source}" if source else ""),
                quote=True,
            )
            destination = (destinations or {}).get(name)
            href = "#" + destination["anchor"] if destination else None
            if href:
                result.append(
                    f'<a class="variable" href="{escape(href, quote=True)}" '
                    f'title="{title}" aria-label="{title}">{escape(match.group())}</a>'
                )
            else:
                result.append(
                    f'<span class="variable" tabindex="0" title="{title}" '
                    f'aria-label="{title}">{escape(match.group())}</span>'
                )
        start = match.end()
    result.append(fragment(start, len(text)))
    tag = "pre" if lexer else "span"
    return Markup(
        f'<{tag} class="formatted-value"><code>{"".join(result)}</code></{tag}>'
    )
