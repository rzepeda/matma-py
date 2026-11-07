"""Validate typed graph semantics and import-only L2 contracts."""
from __future__ import annotations

from copy import deepcopy

from matma.indexing.graph import build_graph


def make_module(name: str, imports=None, references=None):
    return {
        "source_file": f"src/{name}.py", "module_name": name,
        "imports": imports or [], "references": references or [],
        "symbols": [], "is_package": False, "testable": True,
        "mirrors": {"unit_test": f"tests/unit/mirror/src/test_{name}.py", "interaction_test": f"tests/interaction/mirror/src/test_{name}_interaction.py", "manifest": f"tests/mirror/src/{name}.auto.yaml", "mock_file": None},
        "dynamic_imports": [],
    }


def binding(target: str, *, alias: str | None = None, is_from: bool = True, type_only: bool = False, scope: str | None = None):
    return {
        "form": "from" if is_from else "import",
        "module": target,
        "name": "Base" if is_from else target,
        "asname": alias,
        "bound_name": alias or ("Base" if is_from else target.split(".")[0]),
        "level": 0,
        "line": 1, "column": 0, "scope": scope,
        "type_only": type_only, "absolute_module": target,
        "resolution": "internal", "resolved_source": f"src/{target}.py",
        "resolved_module": target, "resolved_symbol": f"{target}.Base" if is_from else None,
    }


def reference(name: str, kind: str = "usage", scope: str | None = None, type_only: bool = False):
    return {"name": name, "kind": kind, "line": 3, "column": 0, "scope": scope, "type_only": type_only}


def test_import_only_at_level_2_and_used_at_level_1():
    files = [
        make_module("base"),
        make_module("used", [binding("base")], [reference("Base")]),
        make_module("unused", [binding("base")]),
    ]
    graph = build_graph(files)
    assert graph["dependents"]["src/base.py"] == {
        "level_1": ["src/used.py"], "level_2": ["src/unused.py"],
    }
    assert graph["dependencies"]["src/unused.py"][0]["weight"] == 2
    assert graph["dependencies"]["src/unused.py"][0]["kinds"] == ["import_only"]
    assert graph["dependencies"]["src/used.py"][0]["weight"] == 1


def test_chain_diamond_distances_are_minimal_and_sorted():
    files = [
        make_module("base"),
        make_module("alpha", [binding("base")], [reference("Base")]),
        make_module("beta", [binding("base")], [reference("Base")]),
        make_module("top", [binding("alpha"), binding("beta")], [reference("Base")]),
    ]
    graph = build_graph(files)
    assert graph["dependents"]["src/base.py"] == {
        "level_1": ["src/alpha.py", "src/beta.py"], "level_2": ["src/top.py"],
    }


def test_cycle_does_not_reinclude_source():
    files = [make_module("a", [binding("b")], [reference("Base")]),
             make_module("b", [binding("a")], [reference("Base")])]
    graph = build_graph(files)
    assert graph["dependents"]["src/a.py"] == {"level_1": ["src/b.py"]}
    assert graph["dependents"]["src/b.py"] == {"level_1": ["src/a.py"]}


def test_scoped_import_not_used_from_other_function():
    files = [make_module("a"), make_module("b", [binding("a", scope="load")], [reference("Base", scope="other")])]
    graph = build_graph(files)
    assert graph["dependents"]["src/a.py"] == {"level_2": ["src/b.py"]}


def test_type_only_and_decorator_edge_kinds():
    files = [make_module("a"), make_module("b", [binding("a", type_only=True)], [reference("Base", "annotation", type_only=True)]),
             make_module("c", [binding("a")], [reference("Base", "decorator")])]
    graph = build_graph(files)
    assert graph["dependencies"]["src/b.py"][0]["kinds"] == ["type_only"]
    assert graph["dependencies"]["src/c.py"][0]["kinds"] == ["decorator"]
    assert graph["dependents"]["src/a.py"]["level_1"] == ["src/b.py", "src/c.py"]


def test_plain_import_requires_reference_to_complete_module_path():
    files = [make_module("a"), make_module("other", [binding("a", is_from=False)], [reference("a.submodule")])]
    graph = build_graph(files)
    assert graph["dependencies"]["src/other.py"][0]["kinds"] == ["usage"]


def test_external_references_are_not_internal_edges():
    m = make_module("a")
    b = binding("third_party")
    b.update(resolution="external_or_unresolved", resolved_source=None)
    m["imports"] = [b]
    graph = build_graph([m])
    assert graph["dependencies"]["src/a.py"] == []
    assert graph["external_dependencies"]["src/a.py"][0]["module"] == "third_party"


def test_weighted_transitive_import_only_sums_costs():
    files = [make_module("a"), make_module("b", [binding("a")]),
             make_module("c", [binding("b")], [reference("Base")])]
    graph = build_graph(files)
    assert graph["dependents"]["src/a.py"] == {"level_2": ["src/b.py"], "level_3": ["src/c.py"]}


def test_deterministic_graph_independent_of_module_order():
    files = [make_module("a"), make_module("b", [binding("a")]), make_module("c")]
    assert build_graph(files) == build_graph(list(reversed(deepcopy(files))))


def test_package_reexport_usage_follows_only_accessed_symbol():
    impl = make_module("impl")
    other = make_module("other")
    pkg = make_module("pkg")
    pkg["is_package"] = True
    pkg["source_file"] = "src/pkg/__init__.py"
    pkg["reexports"] = [
        {"name": "Service", "module": "impl", "symbol": "impl.Service", "type_only": False},
        {"name": "Ignored", "module": "other", "symbol": "other.Ignored", "type_only": False},
    ]
    client = make_module("client")
    import_pkg = binding("pkg", is_from=False)
    import_pkg["resolved_source"] = "src/pkg/__init__.py"
    client["imports"] = [import_pkg]
    client["references"] = [reference("pkg.Service")]
    graph = build_graph([impl, other, pkg, client])
    assert graph["dependents"]["src/impl.py"]["level_1"] == ["src/client.py"]
    assert graph["dependents"]["src/other.py"] == {}
    assert "reexport_usage" in graph["dependencies"]["src/client.py"][0]["kinds"]
