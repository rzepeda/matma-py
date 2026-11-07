"""Bounded reproducible benchmark should measure, not assume, elapsed time."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "benchmarks" / "benchmark_matma.py"


def load_benchmark():
    spec = importlib.util.spec_from_file_location("matma_benchmark", BENCHMARK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_measures_index_and_fresh_impact_on_real_synthetic_project():
    result = load_benchmark().measure(modules=9, iterations=2)
    assert result["status"] == "measured"
    assert result["fixture"]["modules"] == 9
    assert len(result["warm_index"]["samples_ms"]) == 2
    assert len(result["impact_with_freshness"]["samples_ms"]) == 2
    assert result["cold_index_ms"] > 0
    assert result["warm_index"]["median_ms"] > 0
    assert result["impact_with_freshness"]["median_ms"] > 0
    assert result["selection"]["affected_source_files"] >= 2
    assert "O(N)" in result["limitations"]
