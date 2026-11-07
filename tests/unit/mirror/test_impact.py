"""Phase 5 reader contract: no AST or test execution, only persisted YAML."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

from matma.impact.reader import select_impact
from matma.indexing.manifests import HEADER, SCHEMA_VERSION


def write(root: Path, name: str, data: str) -> Path:
    out = root / name
    out.parent.mkdir(parents=True, exist_ok=True)
    # Exact newline bytes matter: the fixture's SHA-256 is calculated from LF
    # strings and Windows text mode would otherwise emit CRLF on disk.
    out.write_text(data, encoding="utf-8", newline="\n")
    return out


def owned(root: Path, name: str, payload: dict) -> Path:
    return write(root, name, HEADER + yaml.safe_dump(payload, sort_keys=False))


def fixture_project(tmp_path: Path) -> dict[str, str]:
    """Represent a pre-indexed weighted graph with both used and import-only edges."""
    contents = {
        "src/pricing.py": "def price(): return 10\n",
        "src/used.py": "from pricing import price\ndef calculate(): return price()\n",
        "src/unused.py": "import pricing\ndef unrelated(): return 1\n",
        "src/transitive.py": "import used\ndef calculate(): return used.calculate()\n",
    }
    for source, data in contents.items():
        write(tmp_path, source, data)
    names = {source: Path(source).stem for source in contents}
    expected = {}
    source_hashes = []
    for source, name in sorted(names.items()):
        source_hashes.append({"source_file": source, "sha256": hashlib.sha256(contents[source].encode()).hexdigest()})
        manifest_path = f"tests/mirror/src/{name}.auto.yaml"
        expected[source] = manifest_path
        if name == "pricing":
            dependents = {
                "level_1": [{"source_file": "src/used.py", "module_name": "used",
                             "unit_test": "tests/unit/mirror/src/test_used.py",
                             "interaction_test": "tests/interaction/mirror/src/test_used_interaction.py"}],
                "level_2": [{"source_file": "src/unused.py", "module_name": "unused",
                             "unit_test": "tests/unit/mirror/src/test_unused.py",
                             "interaction_test": "tests/interaction/mirror/src/test_unused_interaction.py"},
                            {"source_file": "src/transitive.py", "module_name": "transitive",
                             "unit_test": "tests/unit/mirror/src/test_transitive.py",
                             "interaction_test": "tests/interaction/mirror/src/test_transitive_interaction.py"}],
            }
        else:
            dependents = {}
        expected[source] = manifest_path
        owned(tmp_path, manifest_path, {
            "schema_version": SCHEMA_VERSION, "index_fingerprint": "FINGERPRINT",
            "source_file": source, "module_name": name, "mirrors": {
                "manifest": manifest_path,
                "unit_test": f"tests/unit/mirror/src/test_{name}.py",
                "interaction_test": f"tests/interaction/mirror/src/test_{name}_interaction.py",
            }, "dependents": dependents, "dynamic_references": [], "external_dependencies": [],
        })
    write(tmp_path, "tests/unit/mirror/src/test_pricing.py", "# authored\n")
    write(tmp_path, "tests/interaction/mirror/src/test_pricing_interaction.py", "# authored\n")
    write(tmp_path, "tests/unit/mirror/src/test_used.py", "# authored\n")
    write(tmp_path, "tests/interaction/mirror/src/test_unused_interaction.py", "# authored\n")
    write(tmp_path, "tests/unit/mirror/src/test_transitive.py", "# authored\n")
    registry = {
        "schema_version": 1, "registrations": {
            "src/pricing.py": {"business": ["tests/business/test_checkout.py"]},
            "used": {"business": ["tests/business/test_checkout.py"]},
            "src/unused.py": {"regression": ["tests/regression/test_bug_42.py"]},
        },
    }
    write(tmp_path, "tests/matma-verification.yaml", yaml.safe_dump(registry))
    write(tmp_path, "tests/business/test_checkout.py", "# authored business test\n")
    serialized = "".join(f"{x['source_file']}\0{x['sha256']}\n" for x in source_hashes) + "ROOTS\nsrc\n"
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    for path in expected.values():
        p = tmp_path / path
        p.write_text(p.read_text().replace("FINGERPRINT", fingerprint), encoding="utf-8")
    metadata = {
        "schema_version": SCHEMA_VERSION, "index_fingerprint": fingerprint,
        "source_roots": ["src"], "tests_root": "tests", "sources": source_hashes,
        "module_to_source": {name: source for source, name in names.items()},
        "symbol_to_source": {"pricing.price": "src/pricing.py"},
        "source_to_manifest": expected,
        "warnings_by_source": {
            "src/pricing.py": [{"code": "dynamic_import", "severity": "warning",
                                "message": "Dynamic import", "file": "src/pricing.py", "line": 1}],
        },
        "directories": [{"path": "src", "mtime_ns": (tmp_path / "src").stat().st_mtime_ns}],
    }
    owned(tmp_path, "tests/mirror/.index.auto.yaml", metadata)
    return names


def impact(root: Path, *, target: str = "pricing", level: int = 0, **kwargs):
    return select_impact(project_root=root, target=target, level=level, **kwargs)


def test_level_0_only_target_unit_and_registered_workflows(tmp_path: Path):
    fixture_project(tmp_path)
    selected = impact(tmp_path, level=0)
    assert selected["status"] == "impact_selected", selected
    assert selected["tests"]["unit"] == ["tests/unit/mirror/src/test_pricing.py"]
    assert selected["tests"]["interaction"] == []
    assert selected["tests"]["missing"] == []
    assert selected["affected_sources"] == [{"source_file": "src/pricing.py", "module_name": "pricing", "level": 0}]
    assert len(selected["verification"]["business"]) == 1
    assert selected["verification"]["regression"] == []
    assert selected["warnings"][0]["code"] == "dynamic_import"


def test_level_1_used_dependent_and_interaction_tier(tmp_path: Path):
    fixture_project(tmp_path)
    selected = impact(tmp_path, level=1)
    assert selected["status"] == "impact_selected"
    assert selected["tests"]["unit"] == ["tests/unit/mirror/src/test_pricing.py", "tests/unit/mirror/src/test_used.py"]
    assert selected["tests"]["interaction"] == ["tests/interaction/mirror/src/test_pricing_interaction.py"]
    assert selected["tests"]["missing"] == [{"source_file": "src/used.py", "level": 1, "tier": "interaction",
                                                "path": "tests/interaction/mirror/src/test_used_interaction.py"}]
    assert len(selected["verification"]["business"]) == 1  # dedup across two sources


def test_level_2_includes_import_only_and_transitive_with_missing_reports(tmp_path: Path):
    fixture_project(tmp_path)
    selected = impact(tmp_path, level=2)
    assert [x["source_file"] for x in selected["affected_sources"]] == [
        "src/pricing.py", "src/used.py", "src/transitive.py", "src/unused.py"
    ]  # alphabetical within same shortest graph level
    assert "tests/unit/mirror/src/test_transitive.py" in selected["tests"]["unit"]
    assert "tests/interaction/mirror/src/test_unused_interaction.py" in selected["tests"]["interaction"]
    assert {x["path"] for x in selected["tests"]["missing"]} == {
        "tests/interaction/mirror/src/test_used_interaction.py",
        "tests/unit/mirror/src/test_unused.py",
        "tests/interaction/mirror/src/test_transitive_interaction.py",
    }
    assert selected["verification"]["regression"] == []
    assert selected["verification"]["missing"] == [{
        "path": "tests/regression/test_bug_42.py", "source_file": "src/unused.py", "level": 2,
        "tier": "regression",
    }]
    assert selected["exit_code"] == 0  # Missing expected tests do NOT claim coverage or fail selection.


@pytest.mark.parametrize("target", ["src/pricing.py", "pricing", "pricing.price", r"src\pricing.py"])
def test_target_by_path_module_or_symbol(tmp_path: Path, target: str):
    fixture_project(tmp_path)
    assert impact(tmp_path, target=target)["target"] == {"source_file": "src/pricing.py", "module_name": "pricing"}


def test_impact_does_not_import_user_source_or_execute_tests(tmp_path: Path, monkeypatch):
    fixture_project(tmp_path)
    # Scope the guard carefully: pytest itself may call ast.parse to format
    # assertion tracebacks (notably on Windows/Python 3.13).
    import ast
    import subprocess
    original_parse = ast.parse
    calls: list[str] = []

    def track_ast(*args, **kwargs):
        calls.append(str(args[0])[:80] if args else "<no input>")
        return original_parse(*args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(ast, "parse", track_ast)
        guard.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Executed tests")))
        selected = impact(tmp_path, level=2)
    assert selected["status"] == "impact_selected"
    assert calls == [], f"Impact unexpectedly parsed AST: {calls}"


def test_only_companion_and_target_manifest_read(tmp_path: Path, monkeypatch):
    fixture_project(tmp_path)
    import matma.impact.reader as reader
    names = []
    original = reader._owned_yaml
    def capture(path):
        names.append(path.relative_to(tmp_path).as_posix())
        return original(path)
    monkeypatch.setattr(reader, "_owned_yaml", capture)
    selected = impact(tmp_path, level=2)
    assert selected["status"] == "impact_selected"
    assert names == ["tests/mirror/.index.auto.yaml", "tests/mirror/src/pricing.auto.yaml"]


def test_missing_and_modified_sources_invalidate_impact(tmp_path: Path):
    fixture_project(tmp_path)
    write(tmp_path, "src/pricing.py", "def price(): return 999\n")
    selected = impact(tmp_path)
    assert selected["status"] == "impact_failed"
    assert selected["error_code"] == "stale_index"


def test_added_python_source_invalidates_directory_freshness(tmp_path: Path):
    fixture_project(tmp_path)
    write(tmp_path, "src/new_module.py", "def hello(): pass\n")
    selected = impact(tmp_path)
    assert selected["error_code"] == "stale_index"


def test_deleted_source_invalidates_impact(tmp_path: Path):
    fixture_project(tmp_path)
    (tmp_path / "src/pricing.py").unlink()
    assert impact(tmp_path)["error_code"] == "stale_index"


def test_missing_metadata_or_target_manifest_is_error(tmp_path: Path):
    fixture_project(tmp_path)
    (tmp_path / "tests/mirror/.index.auto.yaml").unlink()
    assert impact(tmp_path)["error_code"] == "missing_index"
    fixture_project(tmp_path)
    (tmp_path / "tests/mirror/src/pricing.auto.yaml").unlink()
    assert impact(tmp_path)["error_code"] == "missing_index"


def test_user_yaml_with_no_ownership_header_is_rejected(tmp_path: Path):
    fixture_project(tmp_path)
    write(tmp_path, "tests/mirror/src/pricing.auto.yaml", "manually: authored\n")
    assert impact(tmp_path)["error_code"] == "unsafe_index"


def test_fingerprint_mismatch_is_rejected(tmp_path: Path):
    fixture_project(tmp_path)
    path = tmp_path / "tests/mirror/src/pricing.auto.yaml"
    path.write_text(path.read_text().replace("index_fingerprint:", "index_fingerprint: invalid #"))
    assert impact(tmp_path)["error_code"] == "invalid_index"


def test_missing_lookup_table_requires_reindex(tmp_path: Path):
    fixture_project(tmp_path)
    path = tmp_path / "tests/mirror/.index.auto.yaml"
    payload = yaml.safe_load(path.read_text())
    del payload["module_to_source"]
    owned(tmp_path, "tests/mirror/.index.auto.yaml", payload)
    assert impact(tmp_path)["error_code"] == "invalid_index"


def test_unknown_target_and_traversal_rejected(tmp_path: Path):
    fixture_project(tmp_path)
    for bad in ("does.not.exist", "../outside.py", "", "/etc/passwd"):
        selected = impact(tmp_path, target=bad)
        assert selected["error_code"] == "invalid_target"


def test_registry_is_optional(tmp_path: Path):
    fixture_project(tmp_path)
    (tmp_path / "tests/matma-verification.yaml").unlink()
    selected = impact(tmp_path, level=2)
    assert selected["verification"] == {"business": [], "regression": [], "missing": [], "registry": None}


@pytest.mark.parametrize("broken", [
    {"schema_version": 9, "registrations": {}},
    {"schema_version": 1, "registrations": {"missing.module": {"business": []}}},
    {"schema_version": 1, "registrations": {"pricing": {"business": ["../evil.py"]}}},
    {"schema_version": 1, "registrations": {"pricing": {"business": "not-a-list"}}},
    {"schema_version": 1, "registrations": {"pricing": {"unit": ["tests/unit/test_a.py"]}}},
])
def test_invalid_registry_errors_safely(tmp_path: Path, broken: dict):
    fixture_project(tmp_path)
    write(tmp_path, "tests/matma-verification.yaml", yaml.safe_dump(broken))
    result = impact(tmp_path)
    assert result["status"] == "impact_failed"
    assert result["error_code"] in ("invalid_registry", "unsafe_path")


def test_symlinked_test_path_is_refused(tmp_path: Path):
    fixture_project(tmp_path)
    target = tmp_path / "tests/unit/mirror/src/test_pricing.py"
    target.unlink()
    try:
        target.symlink_to(tmp_path / "src/pricing.py")
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    assert impact(tmp_path)["error_code"] == "unsafe_path"


def test_explicit_source_root_mismatch_refuses_old_index(tmp_path: Path):
    fixture_project(tmp_path)
    selected = impact(tmp_path, source_root="different", explicitly_selected=True)
    assert selected["error_code"] == "stale_index"


def test_custom_test_root_must_match_index(tmp_path: Path):
    fixture_project(tmp_path)
    assert impact(tmp_path, tests_root="qa")["error_code"] == "missing_index"


def test_index_directory_inventory_ignores_non_source_project_root(tmp_path: Path):
    from matma.indexing.manifests import _directory_inventory

    write(tmp_path, "src/pkg/worker.py", "def work(): pass\n")
    sources = [{"source_file": "src/pkg/worker.py", "sha256": "unused-in-directory-inventory"}]
    watched = _directory_inventory(tmp_path, sources, ["src"])
    assert {entry["path"] for entry in watched} == {"src", "src/pkg"}
    watched_flat = _directory_inventory(tmp_path, sources, ["."])
    assert "." in {entry["path"] for entry in watched_flat}
