"""Phase 4 black-box fixture: real Python source -> indexed failing pytest tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run(root: Path, command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "matma", command, *arguments],
                          cwd=root, text=True, capture_output=True, check=False)


def test_scaffold_real_source_all_symbols_have_failing_placeholders(tmp_path: Path) -> None:
    write(tmp_path, "src/shop/__init__.py", "")
    write(tmp_path, "src/shop/pricing.py", '''
def calculate(amount, discount):
    return amount * (1 - discount)

async def fetch_price():
    return 42

class Prices:
    def __init__(self, name):
        self.name = name
    async def update(self):
        return self.name
''')
    process = run(tmp_path, "scaffold", "-o", "json")
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout)
    assert result["status"] == "scaffolded"
    assert result["graph_summary"]["modules"] == 2
    assert len(result["scaffolds"]["created"]) == 3
    unit = tmp_path / "tests/unit/mirror/src/shop/test_pricing.py"
    interaction = tmp_path / "tests/interaction/mirror/src/shop/test_pricing_interaction.py"
    assert unit.is_file() and interaction.is_file()
    assert (tmp_path / "tests/mocks/mirror/src/shop/mock_pricing.py").is_file()
    assert (tmp_path / "tests/mirror/src/shop/pricing.auto.yaml").is_file()
    for path in (unit, interaction):
        text = path.read_text(encoding="utf-8")
        assert text.count("pytest.fail(") == 5  # module functions, class, 2 methods
        assert "fetch_price (async_function)" in text
        assert "Prices.update (async_method)" in text
        assert "import shop.pricing" not in text

    pytest_run = subprocess.run([sys.executable, "-m", "pytest", "-q", str(unit), str(interaction)],
                                cwd=tmp_path, text=True, capture_output=True, check=False)
    assert pytest_run.returncode == 1, pytest_run.stdout + pytest_run.stderr
    assert "10 failed" in pytest_run.stdout
    assert "MATMA: implement" in pytest_run.stdout


def test_target_scaffold_creates_only_target_tests_and_direct_dependency_mocks(tmp_path: Path) -> None:
    write(tmp_path, "src/base.py", "class Dependency:\n    pass\n")
    write(tmp_path, "src/work.py", "from base import Dependency\n\ndef run():\n    return Dependency()\n")
    write(tmp_path, "src/unrelated.py", "def unrelated(): return 1\n")
    process = run(tmp_path, "scaffold", "-f", "work", "-o", "json")
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout)
    assert result["scaffolds"]["selected_sources"] == ["src/work.py"]
    assert result["scaffolds"]["mock_sources"] == ["src/base.py", "src/work.py"]
    assert len(result["scaffolds"]["created"]) == 4
    assert (tmp_path / "tests/unit/mirror/src/test_work.py").is_file()
    assert (tmp_path / "tests/interaction/mirror/src/test_work_interaction.py").is_file()
    assert not (tmp_path / "tests/unit/mirror/src/test_base.py").exists()
    assert not (tmp_path / "tests/unit/mirror/src/test_unrelated.py").exists()
    assert (tmp_path / "tests/mocks/mirror/src/mock_base.py").exists()
    # Entire graph is still indexed, including unrelated sources.
    assert (tmp_path / "tests/mirror/src/base.auto.yaml").exists()
    assert (tmp_path / "tests/mirror/src/unrelated.auto.yaml").exists()


def test_index_scaffold_uses_same_engine_and_target_filter(tmp_path: Path) -> None:
    write(tmp_path, "src/app/a.py", "def a(): return 1\n")
    write(tmp_path, "src/app/b.py", "def b(): return 2\n")
    result = run(tmp_path, "index", "--scaffold", "--target", "app.a", "-o", "json")
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["status"] == "indexed"
    assert parsed["graph_summary"]["modules"] == 2
    assert parsed["scaffolds"]["selected_sources"] == ["src/app/a.py"]
    assert not (tmp_path / "tests/unit/mirror/src/app/test_b.py").exists()
    assert (tmp_path / "tests/mirror/src/app/b.auto.yaml").exists()


def test_repeated_scaffold_does_not_overwrite_modified_file(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "def a(): return 1\n")
    first = run(tmp_path, "scaffold", "-o", "json")
    assert first.returncode == 0
    owned = tmp_path / "tests/unit/mirror/src/test_a.py"
    owned.write_bytes(b"# authored test\r\n")
    before = {p: p.stat().st_mtime_ns for p in (tmp_path / "tests").rglob("*.py")}
    rerun = run(tmp_path, "scaffold", "-o", "json")
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    result = json.loads(rerun.stdout)
    assert result["scaffolds"]["created"] == []
    assert len(result["scaffolds"]["existing"]) == 3
    assert owned.read_bytes() == b"# authored test\r\n"
    assert before == {p: p.stat().st_mtime_ns for p in (tmp_path / "tests").rglob("*.py")}
    assert result["manifests"]["written"] == []


def test_scaffold_preflight_failure_does_not_write_index_or_other_files(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "def a(): return 1\n")
    (tmp_path / "tests/unit/mirror/src/test_a.py").mkdir(parents=True)
    failed = run(tmp_path, "scaffold", "-o", "json")
    assert failed.returncode == 1
    data = json.loads(failed.stdout)
    assert data["status"] == "unsafe_output"
    assert not (tmp_path / "tests/mirror").exists()
    assert not (tmp_path / "tests/mocks").exists()


def test_manual_manifest_conflict_does_not_create_tests(tmp_path: Path) -> None:
    write(tmp_path, "src/a.py", "def a(): return 1\n")
    manual = write(tmp_path, "tests/mirror/src/a.auto.yaml", "mine: true\n")
    process = run(tmp_path, "index", "-S", "-o", "json")
    assert process.returncode == 1
    assert json.loads(process.stdout)["status"] == "unsafe_output"
    assert manual.read_text() == "mine: true\n"
    assert not (tmp_path / "tests/unit").exists()


def test_scaffold_bad_source_refuses_all_files(tmp_path: Path) -> None:
    write(tmp_path, "src/good.py", "def good(): return True\n")
    write(tmp_path, "src/broken.py", "def invalid(:\n")
    process = run(tmp_path, "scaffold", "-o", "json")
    assert process.returncode == 1
    assert json.loads(process.stdout)["status"] == "scaffold_failed"
    assert not (tmp_path / "tests").exists()


def test_source_is_never_modified_by_scaffold(tmp_path: Path) -> None:
    source = write(tmp_path, "src/demo.py", "async def work(): return 1\n")
    before = source.read_bytes(), source.stat().st_mtime_ns
    assert run(tmp_path, "scaffold", "-o", "json").returncode == 0
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_flat_and_custom_tests_root_support(tmp_path: Path) -> None:
    write(tmp_path, "mylib/__init__.py", "from .worker import work\n")
    write(tmp_path, "mylib/worker.py", "def work(): return 1\n")
    process = run(tmp_path, "scaffold", "-t", "qa", "-o", "json")
    assert process.returncode == 0, process.stdout + process.stderr
    assert (tmp_path / "qa/unit/mirror/mylib/test_worker.py").is_file()
    assert not (tmp_path / "qa/unit/mirror/mylib/test___init__.py").exists()
    assert (tmp_path / "qa/mirror/mylib/worker.auto.yaml").is_file()


def test_impact_still_intentionally_not_implemented(tmp_path: Path) -> None:
    write(tmp_path, "src/m.py", "def m(): ...\n")
    result = run(tmp_path, "impact", "--target", "m", "-o", "json")
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "not_implemented"
