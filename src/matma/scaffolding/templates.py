"""Pure, deterministic pytest and unittest.mock starter templates.

Templates never import/execute consumer modules during generation. Generated
files are immediately user-owned and deliberately contain failing pytest tests.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


CALLABLE_KINDS = frozenset({
    "function", "async_function", "class", "nested_class", "method", "async_method",
})


def _scaffolded_symbols(module: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep callable classes/methods; report non-addressable nested definitions.

    A class nested inside a class can be accessed by qualification. A class or
    function defined inside a function cannot be reliably imported by its
    qualified source name, so it remains inventoried but not individually
    scaffolded. The enclosing callable retains its own failing placeholder.
    """
    symbols = sorted(module["symbols"], key=lambda s: (s["line"], s["column"], s["qualname"]))
    kinds = {s["qualname"]: s["kind"] for s in symbols}
    selected: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    for symbol in symbols:
        kind = symbol["kind"]
        if kind not in CALLABLE_KINDS:
            omitted.append(symbol)
            continue
        ancestors = symbol["qualname"].split(".")[:-1]
        parent_qualnames = [".".join(ancestors[:i]) for i in range(1, len(ancestors) + 1)]
        if any(kinds.get(name) in ("function", "async_function", "nested_function", "nested_async_function", "method", "async_method")
               for name in parent_qualnames):
            omitted.append(symbol)
        else:
            selected.append(symbol)
    return selected, omitted


def _safe_identifier(symbol: dict[str, Any]) -> str:
    """Readable, bounded pytest function name with collision-resistant hash."""
    qualname = symbol["qualname"]
    slug = re.sub(r"[^a-z0-9]+", "_", qualname.casefold()).strip("_") or "symbol"
    digest = hashlib.sha256(f"{symbol['kind']}:{qualname}".encode("utf-8")).hexdigest()[:10]
    return f"{slug[:64]}_{digest}"


def render_test_module(module: dict[str, Any], tier: str) -> tuple[str, list[dict[str, Any]]]:
    if tier not in ("unit", "interaction"):
        raise ValueError(f"Unknown testing tier: {tier}")
    selected, omitted = _scaffolded_symbols(module)
    source = module["source_file"]
    qualified = module["module_name"]
    text = [
        repr(f"MATMA starter: {tier} tests for {source}.\n\n"
             "This file is yours after generation. MATMA NEVER rewrites it.\n"
             "Replace the failing placeholders with meaningful assertions."),
        "",
        "import pytest",
        "",
        f"# Test source module: {qualified!r} ({source!r})",
        "# Every placeholder intentionally FAILS until a developer implements it.",
        "# Business and regression tests are authored separately.",
        "",
    ]
    if not selected:
        # Even a source file with no addressable symbols has a truthful test
        # placeholder, rather than a passing empty test module.
        text.extend([
            f"def test_matma_{tier}_module_behavior() -> None:",
            '    """Verify relevant module behavior or import side effects."""',
            f"    pytest.fail({('MATMA: implement ' + tier + ' assertions for ' + qualified + ' (module behavior)')!r})",
            "",
        ])
    else:
        for symbol in selected:
            label = f"{qualified}.{symbol['qualname']} ({symbol['kind']})"
            text.extend([
                f"def test_matma_{tier}_{_safe_identifier(symbol)}() -> None:",
                f"    {('Verify ' + tier + ' behavior: ' + label)!r}",
                f"    pytest.fail({('MATMA: implement ' + tier + ' assertions for ' + label)!r})",
                "",
            ])
    if omitted:
        text += [
            "# Non-addressable nested definitions remain represented in the AST inventory.",
            "# Cover their behavior through the enclosing callable's tests:",
        ]
        for symbol in omitted:
            text.append(f"#   {symbol['kind']}: {symbol['qualname']}")
        text.append("")
    return "\n".join(text).rstrip() + "\n", omitted


def render_mock_module(module: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Mock factories only for static, addressable classes/functions.

    Importing this helper alone never executes consumer modules. Calling a
    factory resolves the real spec at runtime, which can execute imports; the
    developer controls when that happens and configures expected behavior.
    """
    selected, omitted = _scaffolded_symbols(module)
    addressable = [s for s in selected if s["kind"] in (
        "class", "nested_class", "function", "async_function",
    )]
    source = module["source_file"]
    qualified = module["module_name"]
    text = [
        repr(f"MATMA starter: centralized mock factories for {source}.\n\n"
             "This file is yours after generation. MATMA NEVER rewrites it.\n"
             "Factories import specs only when called. Configure all mock behavior\n"
             "and assertions explicitly; no success behavior is invented."),
        "",
        "from importlib import import_module",
        "from unittest.mock import create_autospec, patch",
        "from typing import Any",
        "",
        f"_SOURCE_MODULE = {qualified!r}",
        "",
        "",
        "def _resolve_spec(qualname: str) -> Any:",
        '    """Resolve an original symbol only when a test requests its spec."""',
        "    value: Any = import_module(_SOURCE_MODULE)",
        "    for name in qualname.split('.'):",
        "        value = getattr(value, name)",
        "    return value",
        "",
        "",
        "def patch_at_lookup(consumer_module: str, bound_name: str, *, autospec: bool = True) -> Any:",
        '    """Return a patcher for the name WHERE THE CONSUMER LOOKS IT UP.\n\n'
        '    Example: with patch_at_lookup("myapp.consumer", "Repository") as mock:\n'
        '        mock.return_value.fetch.return_value = desired_result\n'
        '    If the original import is an alias, patch the consumer alias.\n'
        '    Use autospec=False only if runtime introspection is unsafe.\n'
        '    """',
        "    if not consumer_module or not bound_name or bound_name.startswith('.'):",
        '        raise ValueError("Provide the consuming module and its bound name")',
        '    return patch(f"{consumer_module}.{bound_name}", autospec=autospec)',
        "",
    ]
    for symbol in addressable:
        factory = f"autospec_{_safe_identifier(symbol)}"
        use_instance = symbol["kind"] in ("class", "nested_class")
        text.extend([
            "",
            f"def {factory}() -> Any:",
            f"    {('Create an autospecced mock for ' + qualified + '.' + symbol['qualname'])!r}",
            f"    return create_autospec(_resolve_spec({symbol['qualname']!r}), instance={use_instance})",
        ])
    text.append("")
    return "\n".join(text).rstrip() + "\n", omitted
