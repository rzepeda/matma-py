"""Resolve syntactic import identities against indexed modules, without imports."""

from __future__ import annotations


def _parent_package(mod: dict) -> str:
    name: str = mod["module_name"]
    return name if mod["is_package"] else name.rpartition(".")[0]


def _absolute_import(mod: dict, entry: dict) -> str | None:
    if entry["form"] == "import" or entry["level"] == 0:
        return entry["module"]
    package = _parent_package(mod)
    segments = package.split(".") if package else []
    levels = entry["level"] - 1
    if not segments or levels >= len(segments):
        return None
    stem = segments[: len(segments) - levels]
    if entry["module"]:
        stem.extend(entry["module"].split("."))
    return ".".join(stem)


def resolve_imports(files: list[dict], diagnostics: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """Enrich imports with target source/symbol and known package re-exports.

    An unresolved external import is deliberately *not* an internal graph edge.
    Phase 3 uses these bindings plus actual reference evidence for graph edges.
    """
    by_name: dict[str, dict] = {}
    collisions: set[str] = set()
    symbols: dict[str, str] = {}
    ambiguous_symbols: set[str] = set()
    for module in files:
        name = module["module_name"]
        if name in by_name and by_name[name]["source_file"] != module["source_file"]:
            collisions.add(name)
            diagnostics.append({
                "code": "module_collision", "severity": "error", "file": module["source_file"],
                "line": None, "column": None,
                "message": f"Module identity {name!r} also maps to {by_name[name]['source_file']}",
            })
        else:
            by_name[name] = module
        for symbol in module["symbols"]:
            key = f"{name}.{symbol['qualname']}"
            if key in symbols and symbols[key] != module["source_file"]:
                ambiguous_symbols.add(key)
            else:
                symbols[key] = module["source_file"]
    for name in collisions:
        by_name.pop(name, None)
    for symbol in ambiguous_symbols:
        symbols.pop(symbol, None)
    for name in collisions:
        for symbol in tuple(symbols):
            if symbol.startswith(name + "."):
                symbols.pop(symbol, None)

    def locate(module_name: str, imported_name: str, visited: frozenset[tuple[str, str]] = frozenset()) -> tuple[str, str | None] | None:
        """Return source import module name and optional target symbol identity."""
        if (module_name, imported_name) in visited:
            return None
        direct_module = f"{module_name}.{imported_name}" if module_name else imported_name
        if direct_module in by_name:
            return direct_module, None
        direct_symbol = f"{module_name}.{imported_name}" if module_name else imported_name
        if direct_symbol in symbols and module_name in by_name:
            return module_name, direct_symbol
        pkg = by_name.get(module_name)
        if not pkg or not pkg["is_package"]:
            return None
        for imported in pkg["imports"]:
            if imported["scope"] or imported["bound_name"] != imported_name:
                continue
            if imported["form"] == "import":
                candidate = imported["module"]
                if candidate in by_name:
                    return candidate, None
                continue
            base = _absolute_import(pkg, imported)
            if base is None:
                continue
            if imported["name"] == "*":
                continue
            found = locate(base, imported["name"], visited | {(module_name, imported_name)})
            if found:
                return found
        return None

    for mod in files:
        for imported in mod["imports"]:
            base = _absolute_import(mod, imported)
            imported["absolute_module"] = base
            imported["resolved_module"] = None
            imported["resolved_symbol"] = None
            imported["resolved_source"] = None
            imported["resolution"] = "external_or_unresolved"
            if base is None:
                imported["resolution"] = "invalid_relative_import"
                diagnostics.append({
                    "code": "invalid_relative_import", "severity": "error", "file": mod["source_file"],
                    "line": imported["line"], "column": imported["column"],
                    "message": "Relative import exceeds the module's package root",
                })
                continue
            if imported["form"] == "import":
                target = (base, None) if base in by_name else None
            else:
                target = locate(base, imported["name"])
                if target is None and base in by_name:
                    # from package import * or unknown attributes still imports package.
                    target = (base, None)
            if target is None and any(base == name or base.startswith(name + ".") for name in by_name):
                diagnostics.append({
                    "code": "unresolved_internal_import", "severity": "warning",
                    "file": mod["source_file"], "line": imported["line"],
                    "column": imported["column"],
                    "message": f"Could not statically resolve internal import {base!r}",
                })
            if target:
                target_mod, symbol = target
                imported["resolution"] = "internal"
                imported["resolved_module"] = target_mod
                imported["resolved_symbol"] = symbol
                imported["resolved_source"] = by_name[target_mod]["source_file"]

    # An initializer's re-exports are recorded explicitly but not automatically
    # attributed as used dependencies to sibling classes.
    for mod in files:
        if mod["is_package"]:
            mod["reexports"] = [
                {"name": imp["bound_name"], "module": imp["resolved_module"],
                 "symbol": imp["resolved_symbol"], "type_only": imp["type_only"]}
                for imp in mod["imports"] if imp["scope"] is None and imp["resolution"] == "internal"
            ]
        else:
            mod["reexports"] = []

    return {name: item["source_file"] for name, item in sorted(by_name.items())}, dict(sorted(symbols.items()))
