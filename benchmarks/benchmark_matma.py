"""Reproducible synthetic index-versus-impact benchmark (not a speed guarantee).

Runs against a temporary real Python source tree. Includes filesystem reads,
YAML serialization and actual index freshness verification. It deliberately
uses the installed MATMA APIs and requires no application imports or pytest.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

from matma.impact import select_impact
from matma.indexing import index_project


def make_fixture(root: Path, modules: int) -> None:
    source = root / "src"
    source.mkdir(parents=True)
    for number in range(modules):
        predecessor = f"module_{number - 1:04d}"
        if number == 0:
            body = "def evaluate(value: int = 1) -> int:\n    return value + 1\n"
        else:
            body = (
                f"import {predecessor}\n\n"
                "def evaluate(value: int = 1) -> int:\n"
                f"    return {predecessor}.evaluate(value)\n"
            )
            # An import-only edge exercises the additional Level 2 policy.
            if number > 5 and number % 7 == 0:
                body = f"import module_{number - 5:04d}\n" + body
        (source / f"module_{number:04d}.py").write_bytes(body.encode("utf-8"))


def _run_timed(callable_):
    started = time.perf_counter_ns()
    result = callable_()
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    if result["exit_code"] != 0:
        raise RuntimeError(f"Benchmark failed: {result.get('message', result)}")
    return elapsed, result


def measure(modules: int = 96, iterations: int = 3) -> dict:
    if modules < 8 or iterations < 1:
        raise ValueError("modules must be >= 8 and iterations >= 1")
    with tempfile.TemporaryDirectory(prefix="matma-benchmark-") as directory:
        project = Path(directory)
        make_fixture(project, modules)
        cold_ms, cold = _run_timed(lambda: index_project(project_root=project))
        indexing = []
        for _ in range(iterations):
            milliseconds, response = _run_timed(lambda: index_project(project_root=project))
            assert response["manifests"]["written"] == [], "Expected byte-identical warm reindex"
            indexing.append(milliseconds)
        queries = []
        last = None
        for _ in range(iterations):
            milliseconds, last = _run_timed(lambda: select_impact(
                target="module_0000", level=2, project_root=project
            ))
            queries.append(milliseconds)
        assert last is not None
        assert last["target"]["source_file"] == "src/module_0000.py"
        # The first two modules are direct usage dependents, but the others
        # are too far away for Level 2. This is an intentional narrow query.
        assert len(last["affected_sources"]) >= 2
        index_median = statistics.median(indexing)
        query_median = statistics.median(queries)
        return {
            "status": "measured",
            "environment": {"python": platform.python_version(), "system": platform.system()},
            "fixture": {"modules": modules, "iterations": iterations, "layout": "src/",
                        "graph": "linear imports plus periodic import-only edges",
                        "target": "module_0000", "impact_level": 2},
            "cold_index_ms": round(cold_ms, 3),
            "warm_index": {"samples_ms": [round(x, 3) for x in indexing],
                           "median_ms": round(index_median, 3)},
            "impact_with_freshness": {"samples_ms": [round(x, 3) for x in queries],
                                      "median_ms": round(query_median, 3)},
            "warm_index_over_impact_ratio": round(index_median / max(query_median, 0.000001), 3),
            "selection": {"affected_source_files": len(last["affected_sources"]),
                          "missing_test_paths": len(last["tests"]["missing"])},
            "limitations": (
                "Synthetic workload; environment-specific measurements, not an SLA. "
                "Impact does not parse AST, but it hashes all known source files and "
                "stats recorded source directories (O(N) filesystem checks)."
            ),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules", type=int, default=96)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output", type=Path, help="optional JSON output file")
    args = parser.parse_args(argv)
    try:
        data = measure(args.modules, args.iterations)
    except (ValueError, RuntimeError, AssertionError) as error:
        print(json.dumps({"status": "benchmark_failed", "message": str(error)}), file=sys.stderr)
        return 1
    serialized = json.dumps(data, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
