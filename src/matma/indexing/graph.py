"""Typed, static Python module graph with weighted reverse impact levels.

A reference that uses an imported binding is an established dependency (L1).
An import with no corresponding reference is still an execution dependency,
but its importing module's unit tests first enter the result at L2.
The graph is file-owned; symbols and evidence are recorded without creating
additional graph nodes or test files for individual functions and classes.
"""

from __future__ import annotations

from collections import defaultdict
import heapq
from typing import Any


def _matches_reference(binding: dict[str, Any], reference: dict[str, Any]) -> bool:
    """Conservatively match a static reference to its imported local name.

    ``import pkg.service`` without an alias binds ``pkg`` but only a reference
    to ``pkg.service`` can confidently mark that particular import as used.
    ``import pkg.service as service`` binds ``service`` directly.
    """
    imported_scope = binding.get("scope")
    used_scope = reference.get("scope")
    if imported_scope and used_scope != imported_scope and not (
        isinstance(used_scope, str) and used_scope.startswith(imported_scope + ".")
    ):
        return False
    local = binding["bound_name"]
    if binding["form"] == "import" and not binding.get("asname"):
        local = binding["module"]
    name = reference["name"]
    return name == local or name.startswith(local + ".")


def _reference_kind(reference: dict[str, Any], binding: dict[str, Any]) -> str:
    if binding.get("type_only") or reference.get("type_only"):
        return "type_only"
    kind = reference.get("kind", "usage")
    if kind == "annotation":
        return "annotation"
    if kind in ("inheritance", "decorator"):
        return kind
    return "usage"


def build_graph(files: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic typed dependencies and shortest reverse distances.

    The import resolver has already assigned ``resolved_source`` to each
    statically resolved internal import. External/dynamic imports are never
    fabricated into graph edges. No filesystem operations occur here.
    """
    modules = {item["source_file"]: item for item in files}
    by_module_name = {item["module_name"]: item for item in files}
    dependencies: dict[str, list[dict[str, Any]]] = {}
    externals: dict[str, list[dict[str, Any]]] = {}
    reverse: dict[str, dict[str, int]] = defaultdict(dict)

    for source_file in sorted(modules):
        module = modules[source_file]
        by_target: dict[str, dict[str, Any]] = {}
        external_imports: list[dict[str, Any]] = []
        imports = sorted(module["imports"], key=lambda imp: (
            imp["line"], imp["column"], imp["form"], imp.get("module") or "", imp["name"]
        ))
        for imported in imports:
            target = imported.get("resolved_source")
            if imported.get("resolution") != "internal" or target not in modules:
                external_imports.append({
                    "module": imported.get("absolute_module"),
                    "name": imported["name"],
                    "line": imported["line"],
                    "scope": imported.get("scope"),
                    "type_only": bool(imported.get("type_only")),
                    "resolution": imported.get("resolution", "external_or_unresolved"),
                })
                continue
            if target == source_file:
                continue
            referenced = [
                ref for ref in module["references"]
                if _matches_reference(imported, ref)
            ]
            kinds: set[str] = set()
            if referenced:
                kinds = {_reference_kind(ref, imported) for ref in referenced}
                weight = 1
            else:
                kinds = {"type_only_import" if imported.get("type_only") else "import_only"}
                weight = 2
            row = by_target.setdefault(target, {
                "module_name": modules[target]["module_name"],
                "source_file": target,
                "kinds": set(),
                "symbols": set(),
                "evidence": [],
                "weight": weight,
            })
            row["weight"] = min(row["weight"], weight)
            row["kinds"].update(kinds)
            if imported.get("resolved_symbol"):
                row["symbols"].add(imported["resolved_symbol"])
            row["evidence"].append({
                "import": imported.get("absolute_module"),
                "name": imported["name"],
                "bound_name": imported["bound_name"],
                "line": imported["line"],
                "scope": imported.get("scope"),
                "type_only": bool(imported.get("type_only")),
                "used": bool(referenced),
                "reference_lines": sorted(set(r["line"] for r in referenced)),
            })

            # ``import package; package.ExportedClass()`` directly uses the
            # referenced class even when __init__.py re-exports it from an
            # implementation module. Trace only the exports actually accessed;
            # never attribute every initializer import to a sibling class.
            package = modules[target]
            if package.get("is_package") and imported["form"] == "import":
                local_name = imported.get("asname") or imported["module"]
                for exported in package.get("reexports", []):
                    origin = by_module_name.get(exported.get("module"))
                    if origin is None or origin["source_file"] in (target, source_file):
                        continue
                    access = f"{local_name}.{exported['name']}"
                    actual_uses = [ref for ref in referenced if ref["name"] == access
                                   or ref["name"].startswith(access + ".")]
                    if not actual_uses:
                        continue
                    origin_file = origin["source_file"]
                    indirect = by_target.setdefault(origin_file, {
                        "module_name": origin["module_name"],
                        "source_file": origin_file,
                        "kinds": set(), "symbols": set(), "evidence": [], "weight": 1,
                    })
                    indirect["weight"] = 1
                    indirect["kinds"].add("reexport_usage")
                    if exported.get("symbol"):
                        indirect["symbols"].add(exported["symbol"])
                    indirect["evidence"].append({
                        "import": imported.get("absolute_module"),
                        "name": exported["name"],
                        "bound_name": local_name,
                        "line": imported["line"],
                        "scope": imported.get("scope"),
                        "type_only": bool(imported.get("type_only")),
                        "used": True,
                        "reference_lines": sorted(set(r["line"] for r in actual_uses)),
                    })

        resolved: list[dict[str, Any]] = []
        for target, row in sorted(by_target.items()):
            resolved.append({
                "module_name": row["module_name"],
                "source_file": row["source_file"],
                "weight": row["weight"],
                "kinds": sorted(row["kinds"]),
                "symbols": sorted(row["symbols"]),
                "evidence": sorted(row["evidence"], key=lambda ev: (
                    ev["line"], ev["name"], ev["scope"] or ""
                )),
            })
            old = reverse[target].get(source_file)
            if old is None or row["weight"] < old:
                reverse[target][source_file] = row["weight"]
        dependencies[source_file] = resolved
        externals[source_file] = sorted(external_imports, key=lambda imp: (
            imp["line"], imp["name"], imp["module"] or ""
        ))

    levels: dict[str, dict[str, list[str]]] = {}
    for target in sorted(modules):
        # Dijkstra over reversed, nonnegative weighted edges. The weight is 1
        # for proven usage and 2 for conservative import-only relationships.
        distances: dict[str, int] = {target: 0}
        queue: list[tuple[int, str]] = [(0, target)]
        while queue:
            depth, current = heapq.heappop(queue)
            if depth != distances[current]:
                continue
            for dependent, weight in sorted(reverse[current].items()):
                candidate = depth + weight
                if candidate < distances.get(dependent, float("inf")):
                    distances[dependent] = candidate
                    heapq.heappush(queue, (candidate, dependent))
        by_depth: dict[str, list[str]] = defaultdict(list)
        for dependent, depth in sorted(distances.items()):
            if dependent != target:
                by_depth[f"level_{depth}"].append(dependent)
        levels[target] = {
            key: sorted(value)
            for key, value in sorted(by_depth.items(), key=lambda item: int(item[0].split("_")[1]))
        }

    return {
        "dependencies": dependencies,
        "external_dependencies": externals,
        "dependents": levels,
        "summary": {
            "modules": len(files),
            "internal_edges": sum(len(items) for items in dependencies.values()),
            "external_imports": sum(len(items) for items in externals.values()),
            "import_only_edges": sum(any(k in ("import_only", "type_only_import") for k in item["kinds"])
                                     and item["weight"] == 2
                                     for deps in dependencies.values() for item in deps),
        },
    }
