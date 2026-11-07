"""Cross-platform CLI and manifest portability/contract regression fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def put(root: Path, relative: str, data: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def run(root: Path, command: str, *args: str, fmt: str = "json"):
    proc = subprocess.run([sys.executable, "-m", "matma", command, *args, "-o", fmt],
                          cwd=root, capture_output=True, text=True, check=False)
    assert proc.stdout, proc.stderr
    return proc, (json.loads(proc.stdout) if fmt == "json" else yaml.safe_load(proc.stdout))


def test_crlf_source_byte_hash_and_explicit_reindex(tmp_path: Path):
    source = put(tmp_path, "src/service.py", b"def current():\r\n    return 1\r\n")
    assert run(tmp_path, "index")[0].returncode == 0
    first, selected = run(tmp_path, "impact", "-f", "service")
    assert first.returncode == 0, first.stdout + first.stderr
    assert selected["status"] == "impact_selected"
    source.write_bytes(b"def current():\n    return 1\n")
    stale, result = run(tmp_path, "impact", "-f", "service")
    assert stale.returncode == 1
    assert result["error_code"] == "stale_index"
    assert run(tmp_path, "index")[0].returncode == 0
    assert run(tmp_path, "impact", "-f", "service")[0].returncode == 0


def test_windows_separator_roots_and_targets_with_deterministic_yaml(tmp_path: Path):
    put(tmp_path, "source/pkg/pricing.py", b"def price(): return 3\n")
    command = ("-s", r"source\pkg", "-t", r"quality\tests")
    result, indexed = run(tmp_path, "index", *command)
    assert result.returncode == 0, result.stdout + result.stderr
    assert indexed["status"] == "indexed"
    assert (tmp_path / "quality/tests/mirror/source/pkg/pricing.auto.yaml").is_file()
    first, one = run(tmp_path, "impact", "-t", r"quality\tests", "-f", r"source\pkg\pricing.py")
    second, two = run(tmp_path, "impact", "-t", "quality/tests", "-f", "pricing", fmt="yaml")
    assert first.returncode == second.returncode == 0, first.stdout + second.stdout
    assert one["target"] == two["target"]
    assert one["affected_sources"] == two["affected_sources"]
    assert one["tests"] == two["tests"]
    assert first.stdout == run(tmp_path, "impact", "-t", r"quality\tests", "-f", r"source\pkg\pricing.py")[0].stdout


def test_symlinked_manifest_directory_is_never_followed(tmp_path: Path):
    put(tmp_path, "src/work.py", b"def work(): return 2\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "tests" / "mirror"
    target.parent.mkdir()
    try:
        target.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not available on this runner")
    result, payload = run(tmp_path, "index")
    assert result.returncode == 1
    assert payload["status"] == "unsafe_output"
    assert list(outside.iterdir()) == []


def test_casefold_source_collisions_are_reported_not_silently_mirrored(tmp_path: Path):
    put(tmp_path, "src/Foo.py", b"class A: ...\n")
    put(tmp_path, "src/foo.py", b"class B: ...\n")
    if len(list((tmp_path / "src").glob("*oo.py"))) < 2:
        pytest.skip("This filesystem does not support case-distinct paths")
    result, payload = run(tmp_path, "index")
    assert result.returncode == 1
    assert any(d["code"] == "case_collision" for d in payload["diagnostics"])
    assert not (tmp_path / "tests/mirror/.index.auto.yaml").exists()


def test_json_output_schema_and_stability_with_existing_missing_tests(tmp_path: Path):
    put(tmp_path, "src/worker.py", b"def work(): return 4\n")
    indexed, index_data = run(tmp_path, "index")
    assert indexed.returncode == 0
    assert {"command", "status", "message", "exit_code", "options", "index_fingerprint", "manifests"} <= set(index_data)
    left, a = run(tmp_path, "impact", "-f", "worker", "-l", "0")
    right, b = run(tmp_path, "impact", "-f", "worker", "-l", "0")
    assert left.returncode == right.returncode == 0
    assert left.stdout == right.stdout
    assert {"command", "status", "message", "exit_code", "options", "affected_sources", "tests", "verification", "warnings"} <= set(a)
    assert a["tests"]["unit"] == []
    assert len(a["tests"]["missing"]) == 1
    assert b == a


def test_missing_registry_path_reported_without_execution(tmp_path: Path):
    put(tmp_path, "src/task.py", b"def task(): return True\n")
    reg = {"schema_version": 1, "registrations": {"task": {
        "business": ["tests/business/test_missing.py"], "regression": []}}}
    put(tmp_path, "tests/matma-verification.yaml", yaml.safe_dump(reg).encode("utf-8"))
    assert run(tmp_path, "index")[0].returncode == 0
    response, selected = run(tmp_path, "impact", "-f", "task")
    assert response.returncode == 0
    assert selected["verification"]["business"] == []
    assert selected["verification"]["missing"][0]["path"] == "tests/business/test_missing.py"
