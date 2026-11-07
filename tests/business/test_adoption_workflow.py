"""Installed MATMA consumer workflow, including real authored verification.

The generated application tests are *expected to fail* until developers author
assertions. This is not a MATMA test-suite failure: the subprocess assertion
checks that those templates fail and business/regression tests independently pass.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def write(project: Path, relative: str, contents: str) -> Path:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents.encode("utf-8"))
    return path


def invoke(project: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = subprocess.run([sys.executable, "-m", "matma", *args, "-o", "json"],
                            cwd=project, capture_output=True, text=True, check=False)
    assert result.stdout, result.stderr
    return result, json.loads(result.stdout)


def test_full_consumer_lifecycle_with_real_business_and_regression_evidence(tmp_path: Path):
    project = tmp_path / "consumer"
    source = write(project, "src/pricing.py", '''
def total(quantity: int, unit_price: int) -> int:
    return quantity * unit_price

class Quote:
    def subtotal(self, quantity: int, unit_price: int) -> int:
        return total(quantity, unit_price)

    async def subtotal_async(self, quantity: int, unit_price: int) -> int:
        return total(quantity, unit_price)
''')
    write(project, "src/checkout.py", '''
from pricing import total

def order_cost(quantity: int, unit_price: int) -> int:
    return total(quantity, unit_price)
''')
    write(project, "src/unused.py", '''
import pricing

def unrelated() -> bool:
    return True
''')
    write(project, "tests/business/test_order_cost.py", '''
from checkout import order_cost

def test_checkout_total() -> None:
    assert order_cost(3, 12) == 36
''')
    write(project, "tests/regression/test_zero_amount.py", '''
from pricing import Quote

def test_zero_quantity_is_free() -> None:
    assert Quote().subtotal(0, 100) == 0
''')
    registry = project / "tests/matma-verification.yaml"
    registry.write_text(yaml.safe_dump({"schema_version": 1,
        "registrations": {"pricing": {
            "business": ["tests/business/test_order_cost.py"],
            "regression": ["tests/regression/test_zero_amount.py"],
        }}}), encoding="utf-8")

    before = hashlib.sha256(source.read_bytes()).hexdigest()
    index, indexed = invoke(project, "index")
    assert index.returncode == 0, index.stdout + index.stderr
    assert indexed["status"] == "indexed"

    scaffold, generated = invoke(project, "scaffold")
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    assert generated["status"] == "scaffolded"
    assert len(generated["scaffolds"]["created"]) == 9  # 3 modules × unit, interaction, mock
    assert (project / "tests/unit/mirror/src/test_pricing.py").is_file()
    assert (project / "tests/interaction/mirror/src/test_pricing_interaction.py").is_file()

    validation, checked = invoke(project, "validate", "--check")
    assert validation.returncode == 0, validation.stdout + validation.stderr
    assert checked["status"] == "validated"

    level_one, one = invoke(project, "impact", "--target", "pricing", "--level", "1")
    assert level_one.returncode == 0
    names_one = {item["source_file"] for item in one["affected_sources"]}
    assert "src/pricing.py" in names_one
    assert "src/checkout.py" in names_one
    assert "src/unused.py" not in names_one

    before_query = {
        path.relative_to(project).as_posix(): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in project.rglob("*") if path.is_file()
    }
    level_two, two = invoke(project, "impact", "--target", "pricing.total", "--level", "2")
    assert level_two.returncode == 0, level_two.stdout + level_two.stderr
    assert two["status"] == "impact_selected"
    selected = {item["source_file"] for item in two["affected_sources"]}
    assert selected == {"src/pricing.py", "src/checkout.py", "src/unused.py"}
    assert "tests/unit/mirror/src/test_unused.py" in two["tests"]["unit"]
    assert "tests/interaction/mirror/src/test_pricing_interaction.py" in two["tests"]["interaction"]
    assert two["tests"]["missing"] == []
    assert [item["path"] for item in two["verification"]["business"]] == ["tests/business/test_order_cost.py"]
    assert [item["path"] for item in two["verification"]["regression"]] == ["tests/regression/test_zero_amount.py"]
    assert two["verification"]["missing"] == []
    assert len(two["affected_sources"]) == len(selected)  # deduplication
    after_query = {
        path.relative_to(project).as_posix(): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in project.rglob("*") if path.is_file()
    }
    assert before_query == after_query  # impact does not write anywhere
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before

    # Genuine authored business/regression suites are independent evidence.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project / "src") + os.pathsep + env.get("PYTHONPATH", "")
    authored = subprocess.run([sys.executable, "-m", "pytest", "-q",
        "tests/business", "tests/regression"], cwd=project, env=env,
        capture_output=True, text=True, check=False)
    assert authored.returncode == 0, authored.stdout + authored.stderr
    assert "2 passed" in authored.stdout

    # Generated templates are never mistaken for passing coverage.
    placeholder = subprocess.run([sys.executable, "-m", "pytest", "-q",
        "tests/unit/mirror/src/test_pricing.py"], cwd=project, env=env,
        capture_output=True, text=True, check=False)
    assert placeholder.returncode == 1, placeholder.stdout + placeholder.stderr
    assert "MATMA: implement" in placeholder.stdout

    # An unchanged reindex does not rewrite developer-owned test files.
    authored_unit = project / "tests/unit/mirror/src/test_pricing.py"
    previous = authored_unit.read_bytes()
    second, output = invoke(project, "index", "--scaffold")
    assert second.returncode == 0, second.stdout + second.stderr
    assert output["scaffolds"]["created"] == []
    assert authored_unit.read_bytes() == previous

    # A changed source must explicitly invalidate impact until reindexing.
    source.write_bytes(source.read_bytes() + b"\n# intentional change\n")
    stale, stale_data = invoke(project, "impact", "-f", "pricing")
    assert stale.returncode == 1
    assert stale_data["error_code"] == "stale_index"
    rebuilt, _ = invoke(project, "index")
    assert rebuilt.returncode == 0
    assert invoke(project, "impact", "-f", "pricing")[0].returncode == 0


def test_business_registration_is_never_inferred(tmp_path: Path):
    project = tmp_path
    write(project, "src/worker.py", "def work(): return 8\n")
    write(project, "tests/business/test_unregistered.py", "def test_unrelated(): assert True\n")
    assert invoke(project, "index")[0].returncode == 0
    proc, selected = invoke(project, "impact", "--target", "worker", "--level", "2")
    assert proc.returncode == 0
    assert selected["verification"]["business"] == []
    assert selected["verification"]["regression"] == []
    assert selected["verification"]["missing"] == []
    assert "tests/business/test_unregistered.py" not in json.dumps(selected)
