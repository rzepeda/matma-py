"""Black-box CLI validation, preserving the project's unmodified sources."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def run(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "matma", "validate", *args],
                          cwd=project, check=False, capture_output=True, text=True)


def write(project: Path, name: str, content: str) -> None:
    p = project / name
    p.parent.mkdir(exist_ok=True, parents=True)
    p.write_text(content, encoding="utf8")


def test_validate_reads_source_and_exports_json_without_creating_mirrors(tmp_path: Path) -> None:
    write(tmp_path, "src/app/__init__.py", "from .worker import run\n")
    write(tmp_path, "src/app/worker.py", "def run(): return 1\nclass Service: pass\n")
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    result = run(tmp_path, "--check", "-o", "json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "validated"
    assert payload["summary"]["source_files"] == 2
    assert payload["summary"]["testable_modules"] == 1
    assert payload["symbol_to_source"]["app.worker.Service"] == "src/app/worker.py"
    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert after == before


def test_strict_validation_is_nonzero_on_syntax_errors(tmp_path: Path) -> None:
    write(tmp_path, "src/valid.py", "class Z: pass\n")
    write(tmp_path, "src/invalid.py", "def invalid(:\n")
    strict = run(tmp_path, "--check", "-o", "json")
    loose = run(tmp_path, "-o", "json")
    assert strict.returncode == 1
    assert loose.returncode == 0
    assert json.loads(strict.stdout)["status"] == "validation_failed"
    assert any(d["code"] == "syntax_error" for d in json.loads(loose.stdout)["diagnostics"])


def test_unknown_explicit_source_root_returns_nonzero_even_without_check(tmp_path: Path) -> None:
    result = run(tmp_path, "-s", "missing", "-o", "json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["diagnostics"][0]["code"] == "missing_source_root"


def test_text_yaml_outputs_are_real_and_deterministic(tmp_path: Path) -> None:
    write(tmp_path, "src/mod.py", "def go(): return 1\n")
    first = run(tmp_path, "-o", "yaml")
    second = run(tmp_path, "-o", "yaml")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert yaml.safe_load(first.stdout)["summary"]["source_files"] == 1
    text = run(tmp_path, "-o", "text")
    assert "matma:validate [validated]" in text.stdout
    assert "1 modules" in text.stdout


def test_unimplemented_engines_still_fail(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "def f(): ...\n")
    for command in ("scaffold", "impact"):
        args = [sys.executable, "-m", "matma", command, "-o", "json"]
        if command == "impact":
            args.extend(["--target", "src/a.py"])
        result = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True, check=False)
        assert result.returncode == 2
        assert json.loads(result.stdout)["status"] == "not_implemented"


def test_multiple_source_roots_from_cli(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "def a(): ...\n")
    write(tmp_path, "addons/b.py", "def b(): ...\n")
    result = run(tmp_path, "-s", "src", "--extra-source-root", "addons", "--check", "-o", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["source_roots"] == ["addons", "src"]
    assert payload["module_to_source"] == {"a": "src/a.py", "b": "addons/b.py"}


def test_dynamic_import_warning_is_machine_readable(tmp_path: Path) -> None:
    write(tmp_path, "src/mod.py", "import importlib\n\ndef load(name):\n    return importlib.import_module(name)\n")
    result = run(tmp_path, "--check", "-o", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["diagnostic_warnings"] == 1
    assert payload["diagnostics"][0]["code"] == "dynamic_import"
    assert payload["files"][0]["dynamic_imports"][0]["scope"] == "load"
