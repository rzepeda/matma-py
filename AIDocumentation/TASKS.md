# MATMA Python — Implementation Checklist

**Status:** All six MATMA Python implementation phases are complete and CI-verified. The Phase 6 implementation passed **163 tests on Linux** and **161 passed, 2 skipped on Windows** across Python 3.11–3.13 ([six-job CI run 42407788706](https://github.com/rzepeda/matma-py/actions/runs/42407788706)). Package remains version `0.1.0.dev0`; no tag, license grant or publication is implied.  
**Authoritative decisions:** [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)  
**Reference implementation:** `rzepeda/matma-php` (behavioral contracts, not a source-code port).

This checklist uses **unchecked** items until code and corresponding tests are verified. Never count a generated failing test scaffold as passing coverage.

## Phase 0 — Accepted contracts

- [x] **P0-01** Source **module** is the mirror/test unit; permit multiple classes/functions per file, keep individual symbols in the index, no one-class-per-file validation.
- [x] **P0-02** Exactly one unit and one interaction *test file* per testable source file; account for module functions/classes in each.
- [x] **P0-03** Preserve arbitrary host source layouts and deterministic mirrored paths; no production changes.
- [x] **P0-04** Imports are graph relationships; unused imports affect importing-module unit selection at Level 2.
- [x] **P0-05** Parse `__init__.py` for package resolution, aliases, re-exports and actual symbol usage; don't blindly mark all initializer imports as used by sibling classes.
- [x] **P0-06** Use Python `ast`, `PyYAML`, `pyproject.toml`, `pytest`, `unittest.mock`, Python 3.11+, Linux/Windows CI.
- [x] **P0-07** Static-first indexing; dynamic/unresolved reference diagnostics. Business/regression suites provide separately registered workflow evidence; no full dynamic analysis.
- [x] **P0-08** Engineering design fixtures for collision-safe multi-root module identity, module-owned testable symbol policy (e.g. nested functions, methods, `__init__.py`), and exact impact ordering for mixed usage/import edges. These are **implementation details** that must be tested without contradicting the accepted architecture.

## Phase 1 — Installable Python package and CLI

- [x] **P1-01** Add `pyproject.toml` with package identity `matma-py`, Python >=3.11, dependencies, build backend and `[project.scripts]` `matma-indexer = "matma.cli:main"`.
- [x] **P1-02** Introduce `src/matma/` package and command entrypoints: `index`, `validate`, `scaffold`, `impact`.
- [x] **P1-03** Parse and validate shared flags, source-root overrides and output formats; provide stable JSON result/diagnostics and exit codes.
- [x] **P1-04** Create pytest suite and isolated consumer fixture that installs the package and verifies CLI discovery/help/errors.
- [x] **P1-05** Added the initial Linux/Windows and Python 3.11–3.13 GitHub Actions matrix. **Verified:** all six Linux/Windows Python 3.11–3.13 jobs passed in [CI run 42390809898](https://github.com/rzepeda/matma-py/actions/runs/42390809898).
- **Exit criterion:** install + CLI help/options work in a real consumer; unimplemented commands never report success.

## Phase 2 — Module and symbol discovery

**Status:** 6/6 tasks implemented and CI-verified. [Phase 2 implementation](PHASE_2_IMPLEMENTATION.md); [passing Linux/Windows CI](https://github.com/rzepeda/matma-py/actions/runs/42393367584). `validate` is read-only; `index`, `scaffold`, and `impact` remain unimplemented.


- [x] **P2-01** Inventory Python files across configured project source roots; document exclusions, namespace packages, project-root identity and path safety.
- [x] **P2-02** Parse files with standard `ast`; record each module, top-level function, async function, class, method, and references, including line diagnostics.
- [x] **P2-03** Resolve static package/module identities, alias and relative imports, `__init__.py` exports/re-exports, `TYPE_CHECKING` contexts and collision diagnostics without executing source code.
- [x] **P2-04** Deterministically map **one source file to one unit and one interaction file**, plus a mock helper file and manifest. Never enforce a single class or class-name filename.
- [x] **P2-05** Implement read-only `validate`; strict `--check` rejects actual invalid/unsafe structures, not normal Python multi-class modules.
- [x] **P2-06** Test mixed classes/functions, async definitions, methods, nested functions, `__init__.py`, flat and `src/` projects, multiple source roots, Windows paths, and unsafe symlinks.
- **Exit criterion:** byte-stable inventories, correct symbol/file identity, no application code executed or modified.

## Phase 3 — Typed dependency graph and persisted index

**Status:** 6/6 tasks implemented and CI-verified ([Phase 3 report](PHASE_3_IMPLEMENTATION.md); [successful six-job CI run](https://github.com/rzepeda/matma-py/actions/runs/42402164370)). `index` persists deterministic reverse-dependency YAML; `scaffold` and `impact` remain explicit not-implemented shells.


- [x] **P3-01** Define typed static dependency edges: actual symbol use, runtime import/import-only, inheritance, decorator, annotation/type-only and unresolved/dynamic diagnostics.
- [x] **P3-02** Resolve references through aliases/re-exports where supported; distinguish package initialization side effects from symbols actually used by sibling modules.
- [x] **P3-03** Compute reverse dependency impact with stable deduplication, cycles, shortest-path semantics and explicit Level 2 import-only acceptance fixtures.
- [x] **P3-04** Serialize source module manifests `tests/mirror/**/*.auto.yaml` containing symbols, typed dependency edges, mirrors, reverse dependents, warnings, schema version and index fingerprint; include generated companion freshness metadata.
- [x] **P3-05** Implement full deterministic `index`, atomic and ownership-safe writes, byte-identical regeneration, MATMA-owned stale cleanup, and non-destructive source-validation failure.
- [x] **P3-06** Test chain/diamond/cycle, used vs unused import, imports through `__init__.py`, external imports, `TYPE_CHECKING`, unresolved dynamic references, re-exports and multi-root identity.
- **Exit criterion:** full deterministic graph and reliable import-only Level 2 impact information, with no false internal edges.

## Phase 4 — pytest and unittest.mock scaffolding

**Status:** Complete and CI-verified on Linux/Windows, Python 3.11–3.13. [Phase 4 implementation report](PHASE_4_IMPLEMENTATION.md) and [six-job passing run](https://github.com/rzepeda/matma-py/actions/runs/42403853787).


- [x] **P4-01** Create only missing mirrored unit/interaction test files, one pair **per eligible module**, preserving existing authored files.
- [x] **P4-02** Generate distinct intentionally failing pytest placeholders for module functions, async functions, classes and their applicable methods in **both** tiers; preserve paths/names for actionable test selection.
- [x] **P4-03** Create centralized mock helper/factory files using `unittest.mock`, `AsyncMock` and autospec where safe; support patch-at-lookup-site conventions and warn on impossible/ambiguous cases.
- [x] **P4-04** Ensure `scaffold` and `index --scaffold` follow the same engine and reindex full reverse dependencies while generating tests only for selected targets.
- [x] **P4-05** Preflight all destinations, enforce exclusive creation and symlink safety, and prove repeated scaffold calls never overwrite edited tests.
- [x] **P4-06** Run generated scaffold via pytest in a consumer fixture and **verify intentional failures**, not passing fake tests.
- **Exit criterion:** both tiers account for all supported callable symbols; safe no-clobber generation and honest placeholder failure verified.

## Phase 5 — Read-only impact selection and registered workflows

**Status:** Complete and CI-verified. [Phase 5 report](PHASE_5_IMPLEMENTATION.md) and [successful 6-job Linux/Windows CI run](https://github.com/rzepeda/matma-py/actions/runs/42405857265).


- [x] **P5-01** Implement `impact` using generated YAML/index metadata, with **no AST reparse and no automatic pytest invocation**.
- [x] **P5-02** Verify Level 0 target unit, Level 1 direct established-use dependents/interaction, **Level 2 import-only importing modules' unit tests**, and deeper transitive dependents; preserve inclusive selection.
- [x] **P5-03** Emit stable sorted paths for affected source modules, unit/interaction tests, missing test paths, and unresolved/dynamic warnings.
- [x] **P5-04** Reject missing, invalid or stale indexes with actionable reindex instructions; report missing *tests* without treating them as successfully covered.
- [x] **P5-05** Implement explicit user-owned registration for business and regression workflows; report separately but do not automatically run them.
- [x] **P5-06** Test no parsing at query time, selection levels, import-only use cases, cycles, stale hash/new-file signals and registry safety.
- **Exit criterion:** selected tests are reproducible, graph-based and truthful about freshness and analysis limitations.

## Phase 6 — Consumer validation, portability and release preparation

**Status:** Implemented, tested and CI-verified: [Phase 6 report](PHASE_6_IMPLEMENTATION.md) and [six passing Python 3.11–3.13 Linux/Windows jobs](https://github.com/rzepeda/matma-py/actions/runs/42407788706). Wheel inspection and the measured 96-module benchmark also passed. **Release approval remains separate.**


- [x] **P6-01** End-to-end installed consumer walkthrough: `index → scaffold → validate → impact → python -m pytest`; last step fails until generated placeholders are authored.
- [x] **P6-02** Linux/Windows CI matrix, Python versions, path/separator/case/CRLF normalization, symlink safety and CLI snapshot tests.
- [x] **P6-03** Unit, interaction and business tests for MATMA itself, with meaningful assertions, plus explicit registry/regression behavior tests.
- [x] **P6-04** Benchmark full AST indexing/YAML writes **separately** from persisted impact selection/freshness checks; report workload, timings and I/O caveats instead of guaranteeing O(1) total runtime.
- [x] **P6-05** README, adoption guide, troubleshooting and documented package/manifest formats; audit real pytest project compatibility.
- [x] **P6-06** Prepare semver release checklist without tagging or publishing until separately authorized.
- **Exit criterion:** cross-platform CI and real consumer pass their intended acceptance tests; failing generated templates are verified to fail by design; release status is accurately documented.

## Rules for implementing the checklist

- Work in phased, testable increments; update checkboxes **only after evidence** exists.
- Use one coherent commit for a logically complete batch of related edits whenever possible.
- Never present passing MATMA-engine tests as evidence that generated application tests have been implemented.
- Preserve native Python project organization; avoid requiring a MATMA runtime dependency in production code.
- Tests are run by normal `python -m pytest` invocation, not automatically by MATMA.
- Before changing accepted architecture, record the discrepancy and obtain an explicit decision.
