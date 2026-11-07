"""Exercise the real Phase 2 AST resolver through the Phase 3 CLI indexer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def write(root: Path, filename: str, content: str) -> None:
    path = root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "matma", "index", *args],
                          cwd=root, text=True, capture_output=True, check=False)


def test_index_real_graph_used_vs_import_only_and_reexports(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/__init__.py", "from .base import Base\n")
    write(tmp_path, "src/pkg/base.py", "class Base:\n    pass\n")
    write(tmp_path, "src/pkg/used.py", "from . import Base\n\ndef run():\n    return Base()\n")
    write(tmp_path, "src/pkg/unused.py", "import pkg.base\n\ndef unrelated():\n    return 2\n")
    process = run(tmp_path, "--format", "json")
    assert process.returncode == 0, process.stdout + process.stderr
    payload = json.loads(process.stdout)
    assert payload["status"] == "indexed"
    assert payload["graph_summary"]["modules"] == 4
    assert payload["graph_summary"]["internal_edges"] >= 3
    target = tmp_path / "tests/mirror/src/pkg/base.auto.yaml"
    assert target.exists()
    manifest = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert any(x["source_file"] == "src/pkg/used.py" for x in manifest["dependents"]["level_1"])
    assert any(x["source_file"] == "src/pkg/unused.py" for x in manifest["dependents"]["level_2"])
    assert manifest["mirrors"]["unit_test"] == "tests/unit/mirror/src/pkg/test_base.py"
    assert manifest["symbols"][0]["qualname"] == "Base"
    assert manifest["schema_version"] == 1
    assert (tmp_path / "tests/mirror/.index.auto.yaml").exists()
    assert not (tmp_path / "tests/unit").exists()  # scaffolding belongs to Phase 4


def test_index_is_stable_and_target_does_not_drop_graph(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "def a(): ...\n")
    write(tmp_path, "src/b.py", "import a\n\nvalue = a.a()\n")
    first = run(tmp_path, "--target", "a", "-o", "json")
    second = run(tmp_path, "--target", "src/a.py", "-o", "json")
    assert first.returncode == second.returncode == 0
    one, two = json.loads(first.stdout), json.loads(second.stdout)
    assert one["index_fingerprint"] == two["index_fingerprint"]
    assert two["manifests"]["written"] == []
    assert len(two["manifests"]["unchanged"]) == 3
    assert (tmp_path / "tests/mirror/src/b.auto.yaml").is_file()


def test_index_refuses_parse_error_without_writing(tmp_path: Path) -> None:
    write(tmp_path, "src/valid.py", "def valid(): ...\n")
    write(tmp_path, "src/broken.py", "def broken(:\n")
    process = run(tmp_path, "-o", "json")
    assert process.returncode == 1
    data = json.loads(process.stdout)
    assert data["status"] == "index_failed"
    assert any(d["code"] == "syntax_error" for d in data["diagnostics"])
    assert not (tmp_path / "tests").exists()


def test_index_rejects_unknown_target_without_writes(tmp_path: Path) -> None:
    write(tmp_path, "src/valid.py", "def valid(): ...\n")
    process = run(tmp_path, "--target", "not.a.module", "-o", "json")
    assert process.returncode == 1
    assert any(d["code"] == "invalid_target" for d in json.loads(process.stdout)["diagnostics"])
    assert not (tmp_path / "tests").exists()


def test_index_scaffold_flag_creates_failing_starters(tmp_path: Path) -> None:
    write(tmp_path, "src/valid.py", "def valid(): ...\n")
    process = run(tmp_path, "--scaffold", "-o", "json")
    assert process.returncode == 0, process.stdout + process.stderr
    data = json.loads(process.stdout)
    assert data["status"] == "indexed"
    assert len(data["scaffolds"]["created"]) == 3
    assert (tmp_path / "tests/unit/mirror/src/test_valid.py").is_file()
    assert (tmp_path / "tests/mirror/src/valid.auto.yaml").is_file()


def test_index_supports_nondefault_test_root_and_multiple_source_roots(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "def a(): pass\n")
    write(tmp_path, "plugins/b.py", "def b(): pass\n")
    process = run(tmp_path, "-s", "src", "--extra-source-root", "plugins", "-t", "qa", "-o", "json")
    assert process.returncode == 0, process.stdout + process.stderr
    assert (tmp_path / "qa/mirror/src/a.auto.yaml").is_file()
    assert (tmp_path / "qa/mirror/plugins/b.auto.yaml").is_file()
    assert not (tmp_path / "tests").exists()


def test_index_respects_static_only_dynamic_import_warning(tmp_path: Path) -> None:
    write(tmp_path, "src/dynamic.py", "from importlib import import_module\n\ndef load(x):\n    return import_module(x)\n")
    process = run(tmp_path, "-o", "json")
    assert process.returncode == 0
    payload = json.loads(process.stdout)
    assert payload["summary"]["diagnostic_warnings"] >= 1
    entry = yaml.safe_load((tmp_path / "tests/mirror/src/dynamic.auto.yaml").read_text())
    assert entry["dynamic_references"]
    assert entry["dependencies"] == []


def test_index_reads_real_existing_consumer_project(tmp_path: Path) -> None:
    write(tmp_path, "src/app/__init__.py", "from .services import process\n")
    write(tmp_path, "src/app/services.py", "def process():\n    return 7\n")
    process = run(tmp_path, "-o", "yaml")
    assert process.returncode == 0
    result = yaml.safe_load(process.stdout)
    assert result["status"] == "indexed"
    assert result["summary"]["testable_modules"] == 1


def test_index_resolves_access_through_initializer_reexport(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/__init__.py", "from .impl import Service\n")
    write(tmp_path, "src/pkg/impl.py", "class Service:\n    pass\n")
    write(tmp_path, "src/pkg/client.py", "import pkg\n\ndef run():\n    return pkg.Service()\n")
    process = run(tmp_path, "-o", "json")
    assert process.returncode == 0, process.stdout + process.stderr
    manifest = yaml.safe_load((tmp_path / "tests/mirror/src/pkg/impl.auto.yaml").read_text())
    assert "src/pkg/client.py" in [dep["source_file"] for dep in manifest["dependents"]["level_1"]]
    client = yaml.safe_load((tmp_path / "tests/mirror/src/pkg/client.auto.yaml").read_text())
    assert any("reexport_usage" in edge["kinds"] for edge in client["dependencies"])


def test_index_persists_type_only_and_import_only_evidence(tmp_path: Path) -> None:
    write(tmp_path, "src/model.py", "class Model: pass\n")
    write(tmp_path, "src/consumer.py", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from model import Model\n")
    process = run(tmp_path, "-o", "json")
    assert process.returncode == 0, process.stdout + process.stderr
    contents = yaml.safe_load((tmp_path / "tests/mirror/src/consumer.auto.yaml").read_text())
    edge = contents["dependencies"][0]
    assert edge["kinds"] == ["type_only_import"]
    assert edge["weight"] == 2
    target = yaml.safe_load((tmp_path / "tests/mirror/src/model.auto.yaml").read_text())
    assert target["dependents"]["level_2"][0]["source_file"] == "src/consumer.py"
