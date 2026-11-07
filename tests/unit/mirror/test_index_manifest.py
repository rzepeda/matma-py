"""Real filesystem evidence for ownership-aware index persistence."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from matma.indexing.engine import index_project
from matma.indexing.graph import build_graph
from matma.indexing.manifests import HEADER, ManifestError, write_manifests
from test_index_graph import binding, make_module, reference


def setup_project(root: Path) -> tuple[list[dict], dict]:
    (root / "src").mkdir()
    (root / "src" / "base.py").write_text("class Base: ...\n", encoding="utf8")
    (root / "src" / "consumer.py").write_text("from base import Base\nx = Base()\n", encoding="utf8")
    a, b = make_module("base"), make_module("consumer", [binding("base")], [reference("Base")])
    examined = {
        "summary": {"source_roots": ["src"], "diagnostic_errors": 0, "parsed_files": 2},
        "files": [a, b], "target": None, "diagnostics": [],
    }
    return [a, b], examined


def test_persist_idempotent_and_fingerprint_matches_all_manifests(tmp_path: Path):
    modules, inspected = setup_project(tmp_path)
    graph = build_graph(modules)
    first = write_manifests(tmp_path, "tests", inspected, graph)
    assert len(first["manifests"]["written"]) == 3
    metadata = tmp_path / "tests/mirror/.index.auto.yaml"
    one = tmp_path / "tests/mirror/src/base.auto.yaml"
    assert one.read_text().startswith(HEADER)
    loaded = yaml.safe_load(one.read_text())
    assert loaded["index_fingerprint"] == first["index_fingerprint"]
    assert loaded["dependents"]["level_1"][0]["source_file"] == "src/consumer.py"
    assert yaml.safe_load(metadata.read_text())["sources"][0]["source_file"] == "src/base.py"
    before = {p: p.stat().st_mtime_ns for p in [one, metadata]}
    second = write_manifests(tmp_path, "tests", inspected, graph)
    assert first["index_fingerprint"] == second["index_fingerprint"]
    assert second["manifests"]["written"] == []
    assert len(second["manifests"]["unchanged"]) == 3
    assert {p: p.stat().st_mtime_ns for p in before} == before


def test_changed_source_changes_fingerprint(tmp_path: Path):
    modules, inspected = setup_project(tmp_path)
    first = write_manifests(tmp_path, "tests", inspected, build_graph(modules))
    (tmp_path / "src/base.py").write_text("class Base: pass\n", encoding="utf8")
    second = write_manifests(tmp_path, "tests", inspected, build_graph(modules))
    assert second["index_fingerprint"] != first["index_fingerprint"]
    assert len(second["manifests"]["written"]) == 3


def test_manual_existing_manifest_blocks_all_index_writes(tmp_path: Path):
    modules, inspected = setup_project(tmp_path)
    manual = tmp_path / "tests/mirror/src/base.auto.yaml"
    manual.parent.mkdir(parents=True)
    manual.write_text("user: 1\n")
    with pytest.raises(ManifestError, match="user-owned"):
        write_manifests(tmp_path, "tests", inspected, build_graph(modules))
    assert manual.read_text() == "user: 1\n"
    assert not (tmp_path / "tests/mirror/src/consumer.auto.yaml").exists()
    assert not (tmp_path / "tests/mirror/.index.auto.yaml").exists()


def test_stale_owned_yaml_is_removed_but_manual_yaml_preserved(tmp_path: Path):
    modules, inspected = setup_project(tmp_path)
    graph = build_graph(modules)
    write_manifests(tmp_path, "tests", inspected, graph)
    stale = tmp_path / "tests/mirror/src/stale.auto.yaml"
    manual = tmp_path / "tests/mirror/src/user.auto.yaml"
    # Simulate CRLF writes on Windows: safely recognize the MATMA header.
    stale.write_bytes((HEADER + "schema_version: 1\n").replace("\n", "\r\n").encode())
    manual.write_text("my_own: true\n")
    outcome = write_manifests(tmp_path, "tests", inspected, graph)
    assert not stale.exists()
    assert manual.exists()
    assert outcome["manifests"]["removed"] == ["tests/mirror/src/stale.auto.yaml"]


def test_symlinked_tier_is_rejected_without_writing_outside(tmp_path: Path):
    modules, inspected = setup_project(tmp_path)
    target = tmp_path / "outside"
    target.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    try:
        (tests / "mirror").symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported")
    with pytest.raises(ManifestError, match="symlink"):
        write_manifests(tmp_path, "tests", inspected, build_graph(modules))
    assert list(target.iterdir()) == []


def test_index_reports_structural_error_and_performs_no_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    modules, inspected = setup_project(tmp_path)
    inspected["summary"]["diagnostic_errors"] = 1
    inspected["diagnostics"] = [{"code": "syntax_error", "severity": "error", "file": "src/base.py"}]
    monkeypatch.setattr("matma.indexing.engine.inspect_project", lambda **kwargs: inspected)
    outcome = index_project(project_root=tmp_path)
    assert outcome["status"] == "index_failed"
    assert outcome["exit_code"] == 1
    assert not (tmp_path / "tests").exists()


def test_target_only_affects_response_not_global_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    modules, inspected = setup_project(tmp_path)
    inspected["target"] = "src/base.py"
    monkeypatch.setattr("matma.indexing.engine.inspect_project", lambda **kwargs: inspected)
    outcome = index_project(project_root=tmp_path, target="base")
    assert outcome["status"] == "indexed"
    assert outcome["target"] == "src/base.py"
    assert outcome["graph_summary"]["modules"] == 2
    assert (tmp_path / "tests/mirror/src/consumer.auto.yaml").exists()


def test_unsafe_manual_manifest_is_reported_without_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    modules, inspected = setup_project(tmp_path)
    manual = tmp_path / "tests/mirror/src/base.auto.yaml"
    manual.parent.mkdir(parents=True)
    manual.write_text("user: 1\n")
    monkeypatch.setattr("matma.indexing.engine.inspect_project", lambda **kwargs: inspected)
    outcome = index_project(project_root=tmp_path)
    assert outcome["status"] == "unsafe_output"
    assert outcome["exit_code"] == 1
    assert manual.read_text() == "user: 1\n"


def test_metadata_handles_flat_source_root_without_mtime_churn(tmp_path: Path):
    modules, inspected = setup_project(tmp_path)
    inspected["summary"]["source_roots"] = ["."]
    graph = build_graph(modules)
    first = write_manifests(tmp_path, "tests", inspected, graph)
    second = write_manifests(tmp_path, "tests", inspected, graph)
    assert second["manifests"]["written"] == []
    metadata = yaml.safe_load((tmp_path / "tests/mirror/.index.auto.yaml").read_text())
    assert any(x["path"] == "." for x in metadata["directories"])

def test_existing_crlf_owned_manifest_can_be_regenerated(tmp_path: Path):
    modules, inspected = setup_project(tmp_path)
    write_manifests(tmp_path, "tests", inspected, build_graph(modules))
    owned = tmp_path / "tests/mirror/src/base.auto.yaml"
    owned.write_bytes(owned.read_bytes().replace(b"\n", b"\r\n"))
    second = write_manifests(tmp_path, "tests", inspected, build_graph(modules))
    assert "tests/mirror/src/base.auto.yaml" in second["manifests"]["written"]
    assert owned.read_bytes().startswith(HEADER.encode())
