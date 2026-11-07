"""Real AST index/scaffold -> manifest-only impact selections through the CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def write(root: Path, filename: str, content: str) -> Path:
    path = root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run(root: Path, command: str, *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    process = subprocess.run([sys.executable, "-m", "matma", command, *args, "-o", "json"],
                             cwd=root, capture_output=True, text=True, check=False)
    assert process.stdout, process.stderr
    return process, json.loads(process.stdout)


def test_real_index_to_level_2_usage_import_only_and_missing_tests(tmp_path: Path):
    write(tmp_path, "src/pkg/__init__.py", "")
    write(tmp_path, "src/pkg/base.py", "class Base:\n    pass\n")
    write(tmp_path, "src/pkg/used.py", "from .base import Base\n\ndef run(): return Base()\n")
    write(tmp_path, "src/pkg/import_only.py", "import pkg.base\n\ndef unrelated(): return 1\n")
    write(tmp_path, "src/pkg/extra.py", "def outside(): return 1\n")
    initial, indexed = run(tmp_path, "index")
    assert initial.returncode == 0, initial.stdout + initial.stderr
    meta = yaml.safe_load((tmp_path / "tests/mirror/.index.auto.yaml").read_text())
    assert meta["module_to_source"]["pkg.base"] == "src/pkg/base.py"
    assert meta["source_to_manifest"]["src/pkg/base.py"] == "tests/mirror/src/pkg/base.auto.yaml"
    assert meta["symbol_to_source"]["pkg.base.Base"] == "src/pkg/base.py"

    level0, zero = run(tmp_path, "impact", "-f", "pkg.base.Base", "-l", "0")
    assert level0.returncode == 0, level0.stdout + level0.stderr
    assert zero["status"] == "impact_selected"
    assert zero["affected_sources"] == [{"source_file": "src/pkg/base.py", "module_name": "pkg.base", "level": 0}]
    assert zero["tests"]["unit"] == []
    assert zero["tests"]["missing"] == [{
        "source_file": "src/pkg/base.py", "level": 0, "tier": "unit",
        "path": "tests/unit/mirror/src/pkg/test_base.py"}]

    level1, one = run(tmp_path, "impact", "-f", "src/pkg/base.py", "-l", "1")
    assert level1.returncode == 0
    assert "src/pkg/used.py" in [x["source_file"] for x in one["affected_sources"]]
    assert "src/pkg/import_only.py" not in [x["source_file"] for x in one["affected_sources"]]

    level2, two = run(tmp_path, "impact", "-f", "pkg.base", "-l", "2")
    assert level2.returncode == 0
    assert "src/pkg/import_only.py" in [x["source_file"] for x in two["affected_sources"]]
    assert "tests/unit/mirror/src/pkg/test_import_only.py" in {x["path"] for x in two["tests"]["missing"]}
    assert "src/pkg/extra.py" not in [x["source_file"] for x in two["affected_sources"]]


def test_real_scaffold_preserves_authored_tests_and_impact_selects_existing(tmp_path: Path):
    source = write(tmp_path, "src/acme/pricing.py", "def calc(): return 4\n")
    scaffold, generated = run(tmp_path, "scaffold", "--target", "acme.pricing")
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    assert generated["status"] == "scaffolded"
    path = tmp_path / "tests/unit/mirror/src/acme/test_pricing.py"
    expected_bytes = path.read_bytes()
    selected, payload = run(tmp_path, "impact", "--target", "acme.pricing", "--level", "1")
    assert selected.returncode == 0, selected.stdout + selected.stderr
    assert payload["tests"]["unit"] == ["tests/unit/mirror/src/acme/test_pricing.py"]
    assert payload["tests"]["interaction"] == ["tests/interaction/mirror/src/acme/test_pricing_interaction.py"]
    assert payload["tests"]["missing"] == []
    assert path.read_bytes() == expected_bytes
    assert source.read_text() == "def calc(): return 4\n"


def test_registration_is_opt_in_and_not_silently_discovered(tmp_path: Path):
    write(tmp_path, "src/service.py", "def run(): return True\n")
    write(tmp_path, "tests/business/test_flow.py", "assert 1\n")
    write(tmp_path, "tests/regression/test_issue.py", "assert 1\n")
    assert run(tmp_path, "index")[0].returncode == 0
    before = run(tmp_path, "impact", "--target", "service", "--level", "2")[1]
    assert before["verification"]["business"] == []
    assert before["verification"]["regression"] == []

    write(tmp_path, "tests/matma-verification.yaml", yaml.safe_dump({
        "schema_version": 1,
        "registrations": {"service": {
            "business": ["tests/business/test_flow.py"],
            "regression": ["tests/regression/test_issue.py"],
        }},
    }))
    selected, after = run(tmp_path, "impact", "--target", "service", "--level", "0")
    assert selected.returncode == 0, selected.stdout + selected.stderr
    assert [item["path"] for item in after["verification"]["business"]] == ["tests/business/test_flow.py"]
    assert [item["path"] for item in after["verification"]["regression"]] == ["tests/regression/test_issue.py"]


def test_cli_freshness_and_invalid_data_never_auto_reindexes(tmp_path: Path):
    source = write(tmp_path, "src/service.py", "def run(): return True\n")
    assert run(tmp_path, "index")[0].returncode == 0
    manifest = tmp_path / "tests/mirror/src/service.auto.yaml"
    initial = manifest.read_bytes()
    source.write_text("def run(): return False\n")
    failed, result = run(tmp_path, "impact", "-f", "service", "-l", "2")
    assert failed.returncode == 1
    assert result["error_code"] == "stale_index"
    assert manifest.read_bytes() == initial  # no silent reindex
    fresh, _ = run(tmp_path, "index")
    assert fresh.returncode == 0
    assert run(tmp_path, "impact", "-f", "service")[0].returncode == 0


def test_flat_src_layout_and_custom_test_root(tmp_path: Path):
    write(tmp_path, "apkg/__init__.py", "")
    write(tmp_path, "apkg/worker.py", "def work(): return 1\n")
    indexed, _ = run(tmp_path, "index", "-t", "qa")
    assert indexed.returncode == 0, indexed.stdout + indexed.stderr
    selected, payload = run(tmp_path, "impact", "-t", "qa", "-f", "apkg.worker")
    assert selected.returncode == 0, selected.stdout + selected.stderr
    assert payload["target"]["source_file"] == "apkg/worker.py"
    assert payload["tests"]["missing"][0]["path"] == "qa/unit/mirror/apkg/test_worker.py"


def test_indexing_failure_does_not_create_invalid_impact_metadata(tmp_path: Path):
    write(tmp_path, "src/bad.py", "def broken(:\n")
    failed, _ = run(tmp_path, "index")
    assert failed.returncode == 1
    result, data = run(tmp_path, "impact", "-f", "bad")
    assert result.returncode == 1
    assert data["error_code"] == "missing_index"
    assert not (tmp_path / "tests").exists()


def test_pytest_cache_outside_source_root_does_not_make_index_stale(tmp_path: Path):
    write(tmp_path, "src/service.py", "def compute(): return 4\n")
    assert run(tmp_path, "index")[0].returncode == 0
    # Normal pytest execution creates a project-root cache after indexing.
    # This must not invalidate a source-root `src/` dependency index.
    write(tmp_path, ".pytest_cache/CACHEDIR.TAG", "pytest cache\n")
    selected, impact = run(tmp_path, "impact", "-f", "service")
    assert selected.returncode == 0, selected.stdout + selected.stderr
    assert impact["status"] == "impact_selected"
