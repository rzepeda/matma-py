# MATMA Python — Phase 6: Consumer Validation, Portability, Benchmarks and Release Preparation

**Status:** Implemented and CI-verified on 2026-11-07. **All six GitHub Actions jobs passed** across Python 3.11, 3.12 and 3.13 on Linux/Windows ([run 42407788706](https://github.com/rzepeda/matma-py/actions/runs/42407788706)). **163 pytest tests passed on Linux**, and **161 passed with two platform-specific skips on Windows**. No tag, publication, license grant or merge into `main` is performed by this phase. Prior accepted architecture is [ADR-001](ARCHITECTURE_DECISIONS.md); milestones are in [TASKS.md](TASKS.md).

## What Phase 6 adds

| File | Acceptance evidence |
| --- | --- |
| `tests/business/test_adoption_workflow.py` | Real source → index → scaffold → validate → impact → explicit pytest execution. Authored business/regression tests pass; generated placeholders **fail by design**, without modifying production source. Stale-index handling and safe regeneration. |
| `tests/business/test_release_artifact.py` | Real wheel build under `python -m build --wheel --no-isolation`, inspect entry point, included engines and absence of developer tests in the wheel. |
| `tests/interaction/mirror/test_portability_contract.py` | CRLF byte hashes, Windows path separators, deterministic JSON/YAML, symlinked manifest-output rejection, case collisions, missing registrations. |
| `tests/unit/mirror/test_benchmark_contract.py` | Benchmark smoke run checks actual measured timing samples and non-O(1) caveats, without asserting guaranteed speed ratios. |
| `benchmarks/benchmark_matma.py` | Reproducible temporary source graph measuring first index, repeated full warm AST index/YAML process, and read-only impact **including source freshness hash/stat I/O**. No built-in simulated time or fixed speed claim. |
| `AIDocumentation/CONSUMER_GUIDE.md` | End-to-end adoption, pytest/manual registries, diagnostics and recovery, unsupported dynamic behavior. |
| `AIDocumentation/RELEASE_CHECKLIST.md` | Explicit owner approval, licensing, CI/release gates; no tagging or PyPI upload. |

## Benchmark method and limits

Invoke against the **installed development package**:

```bash
python benchmarks/benchmark_matma.py --modules 96 --iterations 3
python benchmarks/benchmark_matma.py --modules 96 --iterations 3 --output benchmark-results.json
```

The script creates a temporary 96-module `src/` project with a chain of
statically known imports and periodic unused imports; the graph includes
real Level 2 import-only evidence. It measures one cold full index, three
warm **full AST graph rebuild + YAML** runs, then three persisted
`select_impact` queries at Level 2 including known-source SHA-256 checks.
It reports individual samples and medians in milliseconds and the runtime
Python version and OS. No production project is mutated. Warm indexes are
asserted not to rewrite byte-identical manifests; queries are verified to
select a valid target. **The measured ratio is workload-specific and not a
performance guarantee.**

Impact does not parse Python AST but is not O(1) end-to-end: it hashes every
indexed source and stats recorded source directories, O(N) source I/O. Index
also has AST parsing, dependency resolution, shortest-path computation and
YAML writes. Results are not comparable to real application projects without
matching dependency density, disk speed, OS and file counts.

### Measurements

**Measured in [CI run 42407788706](https://github.com/rzepeda/matma-py/actions/runs/42407788706) (Linux, Python 3.13.18), 96-module synthetic workload, 3 repetitions:**

| Work | Samples (ms) | Median / measured value |
| --- | --- | --- |
| First cold full index | one run | **1,218.487 ms** |
| Warm full AST + graph + YAML index | 1,173.326; 1,169.743; 1,173.470 | **1,173.326 ms** |
| Persisted impact with SHA-256 + directory freshness | 84.073; 84.653; 84.543 | **84.543 ms** |
| Warm index / impact median | — | **13.878×** in this fixture |

The Level 2 impact selection affected **3 source modules** and correctly reported **6 expected but missing test-file paths**, not passing test coverage. See the [full CI job and benchmark artifact](https://github.com/rzepeda/matma-py/actions/runs/42407788706) (`matma-benchmark-linux-py313`). This synthetic result is not an SLA or proof of a universal speedup; timings vary by graph density, disk, interpreter and filesystem. Impact still reads/hashes all indexed source bytes and stats tracked source directories (O(N) freshness work).

## Portability, release readiness and acceptance

The existing CI matrix runs **Python 3.11, 3.12 and 3.13** on Linux/Windows.
The Phase 6 fixtures additionally exercise CRLF/LF byte changes, backslash
paths, case-sensitive versus case-insensitive filesystems, rejected symlinks,
real `pytest.fail` placeholders and source-index freshness after test activity.
The wheel build confirms all four engines and the CLI entry point are included.

The implementation commit passed **six CI jobs** and the reproducible benchmark; the P6 checklist is marked complete. The final documentation-only commit must also pass the matrix. Phase 6 remains *development validation*, not a tagged, licensed or published release. Publication is governed by
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) and requires separate authorization.
