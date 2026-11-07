"""Phase 4: deterministic, truthful templates and non-destructive filesystem writes."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from matma.scaffolding.templates import render_test_module, render_mock_module
from matma.scaffolding.writer import (
    ScaffoldError, ScaffoldPlan, make_plan, preflight_scaffolds, write_scaffolds,
)


def module(name: str, symbols: list[dict] | None = None, *, testable: bool = True) -> dict:
    source = f"src/pkg/{name}.py"
    return {
        "source_file": source, "module_name": f"pkg.{name}", "testable": testable,
        "symbols": symbols or [],
        "mirrors": {
            "unit_test": f"tests/unit/mirror/src/pkg/test_{name}.py" if testable else None,
            "interaction_test": f"tests/interaction/mirror/src/pkg/test_{name}_interaction.py" if testable else None,
            "mock_file": f"tests/mocks/mirror/src/pkg/mock_{name}.py" if testable else None,
            "manifest": f"tests/mirror/src/pkg/{name}.auto.yaml",
        },
    }


def symbol(name: str, kind: str, *, line: int, scope: str | None = None) -> dict:
    return {"name": name.split(".")[-1], "qualname": name, "kind": kind,
            "line": line, "column": 0, "scope": scope}


def example_module() -> dict:
    return module("service", [
        symbol("calculate", "function", line=1),
        symbol("async_fetch", "async_function", line=4),
        symbol("Worker", "class", line=10),
        symbol("Worker.__init__", "method", line=11, scope="Worker"),
        symbol("Worker.run", "async_method", line=15, scope="Worker"),
        symbol("calculate.local", "nested_function", line=20, scope="calculate"),
        symbol("Worker.Inner", "nested_class", line=24, scope="Worker"),
        symbol("Worker.Inner.step", "method", line=25, scope="Worker.Inner"),
    ])


@pytest.mark.parametrize("tier", ["unit", "interaction"])
def test_both_tiers_cover_each_addressable_symbol_with_failing_pytest(tier: str) -> None:
    code, omitted = render_test_module(example_module(), tier)
    ast.parse(code)
    assert len([n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)]) == 7
    assert "pytest.fail(" in code
    assert code.count("pytest.fail(") == 7
    assert code.count("def test_matma_") == 7
    assert "pkg.service.Worker.run (async_method)" in code
    assert omitted == [symbol("calculate.local", "nested_function", line=20, scope="calculate")]
    assert "non-addressable" in code.lower()
    assert "import pkg.service" not in code  # never execute application modules to fail truthfully


def test_dynamic_or_non_addressable_only_module_fails_in_both_tiers() -> None:
    mod = module("empty")
    for tier in ("unit", "interaction"):
        code, omitted = render_test_module(mod, tier)
        assert "test_matma_" + tier + "_module_behavior" in code
        assert code.count("pytest.fail(") == 1
        assert not omitted


def test_identifiers_are_deterministic_unique_and_ascii() -> None:
    mod = module("x", [symbol("A.B", "method", line=1, scope="A"),
                       symbol("A_B", "function", line=2), symbol("A", "class", line=0)])
    a, _ = render_test_module(mod, "unit")
    b, _ = render_test_module(mod, "unit")
    assert a == b
    names = [n.name for n in ast.parse(a).body if isinstance(n, ast.FunctionDef)]
    assert len(names) == len(set(names)) == 3
    assert all(name.isascii() for name in names)


def test_mock_factory_does_not_import_application_until_called(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = module("service", [symbol("Service", "class", line=1),
                             symbol("fetch", "async_function", line=2)])
    code, omitted = render_mock_module(mod)
    ast.parse(code)
    consumer = ModuleType("my_consumer")
    original = object()
    consumer.Service = original
    monkeypatch.setitem(sys.modules, "my_consumer", consumer)
    namespace: dict = {}
    exec(compile(code, "generated_mock.py", "exec"), namespace)
    assert not omitted
    assert "pkg.service" not in sys.modules  # lazy spec resolution at invocation
    with namespace["patch_at_lookup"]("my_consumer", "Service", autospec=False) as patched:
        assert consumer.Service is patched
    assert consumer.Service is original
    with pytest.raises(ValueError):
        namespace["patch_at_lookup"]("", "Service")


def test_mock_autospec_handles_class_and_async_function(monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = ModuleType("pkg")
    pkg.__path__ = []
    app = ModuleType("pkg.service")
    class Example:
        def apply(self, value: int) -> int:
            return value + 1
    async def fetch(value: int) -> int:
        return value
    app.Service = Example
    app.fetch = fetch
    monkeypatch.setitem(sys.modules, "pkg", pkg)
    monkeypatch.setitem(sys.modules, "pkg.service", app)
    code, _ = render_mock_module(module("service", [
        symbol("Service", "class", line=1), symbol("fetch", "async_function", line=2)
    ]))
    namespace: dict = {}
    exec(code, namespace)
    factories = {k: v for k, v in namespace.items() if k.startswith("autospec_")}
    assert len(factories) == 2
    class_factory = next(v for k, v in factories.items() if "service_" in k and "fetch" not in k)
    instance = class_factory()
    assert callable(instance.apply)
    instance.apply(3)
    instance.apply.assert_called_once_with(3)
    assert hasattr(next(v for k, v in factories.items() if "fetch" in k)(), "assert_awaited")


def test_mock_factories_do_not_fabricate_unresolved_import_targets() -> None:
    mod = module("external", [symbol("do", "function", line=1)])
    mod["imports"] = [{"resolution": "external_or_unresolved", "module": "remote"}]
    code, _ = render_mock_module(mod)
    assert "remote" not in code
    assert "create_autospec" in code


def test_plan_only_creates_selected_tests_and_direct_dependency_mocks() -> None:
    work = module("work", [symbol("run", "function", line=1)])
    dep = module("dep", [symbol("Worker", "class", line=1)])
    unrelated = module("unrelated", [symbol("a", "function", line=1)])
    inspected = {"files": [work, dep, unrelated], "target": work["source_file"]}
    graph = {"dependencies": {work["source_file"]: [{"source_file": dep["source_file"]}],
                              dep["source_file"]: [], unrelated["source_file"]: []}}
    plan = make_plan(inspected, graph, target="pkg.work")
    assert plan.selected_sources == [work["source_file"]]
    assert plan.mock_sources == [dep["source_file"], work["source_file"]]
    assert len(plan.files) == 4
    assert not any("test_dep" in filename or "test_unrelated" in filename for filename in plan.files)
    assert not any("mock_unrelated" in filename for filename in plan.files)


def test_non_testable_dependency_is_reported_without_fake_mock() -> None:
    work = module("work", [symbol("run", "function", line=1)])
    init = module("__init__", testable=False)
    inspected = {"files": [work, init], "target": work["source_file"]}
    plan = make_plan(inspected, {"dependencies": {work["source_file"]: [
        {"source_file": init["source_file"]}]}}, target="work")
    assert plan.mock_sources == [work["source_file"]]
    assert plan.warnings and "non-testable" in plan.warnings[0]


def test_target_non_testable_initializer_is_rejected() -> None:
    init = module("__init__", testable=False)
    with pytest.raises(ScaffoldError, match="no independent testable behavior"):
        make_plan({"files": [init], "target": init["source_file"]},
                  {"dependencies": {}}, target="pkg")


def test_writer_preserves_handwritten_files_and_is_idempotent(tmp_path: Path) -> None:
    work = module("work", [symbol("work", "function", line=1)])
    plan = make_plan({"files": [work], "target": None}, {"dependencies": {}}, target=None)
    unit = tmp_path / work["mirrors"]["unit_test"]
    unit.parent.mkdir(parents=True)
    unit.write_bytes(b"# do not overwrite\r\n")
    planned, existing = preflight_scaffolds(tmp_path, "tests", plan)
    assert len(planned) == 2 and existing == [work["mirrors"]["unit_test"]]
    first = write_scaffolds(tmp_path, "tests", plan)
    assert len(first["created"]) == 2
    assert len(first["existing"]) == 1
    assert unit.read_bytes() == b"# do not overwrite\r\n"
    files_before = {path: (tmp_path / path).stat().st_mtime_ns for path in plan.files}
    second = write_scaffolds(tmp_path, "tests", plan)
    assert second["created"] == []
    assert len(second["existing"]) == 3
    assert files_before == {path: (tmp_path / path).stat().st_mtime_ns for path in plan.files}


def test_writer_checks_all_destinations_before_creating_any(tmp_path: Path) -> None:
    work = module("work", [symbol("run", "function", line=1)])
    plan = make_plan({"files": [work], "target": None}, {"dependencies": {}}, target=None)
    bad = tmp_path / work["mirrors"]["interaction_test"]
    bad.mkdir(parents=True)
    with pytest.raises(ScaffoldError, match="not a regular file"):
        write_scaffolds(tmp_path, "tests", plan)
    assert not (tmp_path / work["mirrors"]["unit_test"]).exists()


def test_writer_blocks_symlink_destination_and_ancestor(tmp_path: Path) -> None:
    work = module("work", [symbol("run", "function", line=1)])
    plan = make_plan({"files": [work], "target": None}, {"dependencies": {}}, target=None)
    outside = tmp_path / "elsewhere.py"
    outside.write_text("# user-owned\n")
    target = tmp_path / work["mirrors"]["unit_test"]
    target.parent.mkdir(parents=True)
    try:
        target.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable on this filesystem")
    with pytest.raises(ScaffoldError, match="symlinked"):
        write_scaffolds(tmp_path, "tests", plan)
    assert outside.read_text() == "# user-owned\n"


def test_writer_rejects_path_traversal_and_cross_tier_paths(tmp_path: Path) -> None:
    for rel in ("tests/unit/mirror/../../../escape.py", "tests/random.py", "../outside.py"):
        plan = ScaffoldPlan(files={rel: "bad"}, selected_sources=[], mock_sources=[],
                            omitted_symbols=[], warnings=[])
        with pytest.raises(ScaffoldError):
            preflight_scaffolds(tmp_path, "tests", plan)
    assert not (tmp_path / "tests").exists()


def test_plan_rejects_case_colliding_outputs() -> None:
    m1 = module("foo", [symbol("foo", "function", line=1)])
    m2 = module("Foo", [symbol("Foo", "function", line=1)])
    with pytest.raises(ScaffoldError, match="collision"):
        make_plan({"files": [m1, m2], "target": None}, {"dependencies": {}}, target=None)
