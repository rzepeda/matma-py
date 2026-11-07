# MATMA Python — Architecture Decision Record (ADR-001)

**Status:** Accepted project decisions, recorded 2026-11-07. Implementation not yet started.  
**Source:** MATMA architecture blueprint, accepted MATMA PHP ADR-001, and owner decisions for Python.  
**Repository:** `rzepeda/matma-py`

## Purpose and governing rule

MATMA is an agent-oriented test architecture and development tool. It must adapt to the **existing Python project**, without renaming, restructuring, rewriting, or executing its production source merely to discover dependencies. Preserve the language-independent MATMA contracts learned from MATMA PHP: deterministic mirrored tests, centralized test doubles, indexed reverse dependencies, non-destructive failing scaffolds, explicit test selection, and actionable diagnostics.

## Accepted Python-specific decisions

### PY-ADR-01 — Atomic identity is the source module, not the class

- **A source Python file is the atomic mirror and impact target.** Multiple classes, top-level functions, async functions, and methods may appear in one file. There is **no one-class-per-file or filename-equals-class validation**.
- Keep class and function symbols in the AST inventory and dependency metadata, including their file ownership and source location.
- **Exactly one unit test file and one interaction test file map to each testable production module** (not one test file for each class/function).
- Both unit and interaction test files must account for the testable functions and classes declared in that module. Generate individually identifiable **explicitly failing placeholders** for unimplemented unit/interaction coverage; do not claim coverage from an empty test, a skip, or a passing placeholder.
- Class methods, synchronous/async functions and decorators require explicit test inventory/fixture coverage. Definitions that are not independently testable (for example nested implementation functions or magic methods) should be represented in the AST; concrete scaffold selection rules are specified and tested during Phase 4 rather than quietly inventing tests.
- `__init__.py` and other helper modules are indexed for dependency meaning; an empty package initializer is not automatically treated as a useful independent test target.

### PY-ADR-02 — Follow the host project's source layout

- Discover Python source in the project's configured source roots, whether `src/` layout, flat packages, or another structure. Do not require a project reorganization or a fixed package directory name.
- Mirror the source file's relative directory hierarchy deterministically under:
  - `tests/unit/mirror/`
  - `tests/interaction/mirror/`
  - `tests/mocks/mirror/`
  - `tests/mirror/` for generated `.auto.yaml` files
- Preserve enough source-root identity to avoid collisions when multiple source roots contain the same relative file path. Canonical path representation, root-prefix rules and exclusions must be explicit and cross-platform tested.
- Discover source files at **index/validate time**; the `impact` query must not crawl the project tree.
- Exclude environment/vendor/cache/generated/testing directories by documented rules while respecting explicit source-root overrides. Prevent path traversal, unsafe symlink handling and source-tree overwrites.

### PY-ADR-03 — Imports are meaningful, including import-only relationships

- Index **actual symbol usage** and **module imports** as separately typed static dependency edges. A Python import may execute top-level module code, so unused imports cannot automatically be discarded like PHP `use` aliases.
- Direct class/function usage, inheritance, decorators, annotations, alias use, and module import effects are distinguished in manifests.
- **An imported module creates a conservative impact relationship even when no imported symbol is later referenced. Its importing module's unit tests must be included by Level 2** when the imported module changes.
- Preserve MATMA's inclusive `--level` behavior: Level 0 selects the target module's unit tests; Level 1 selects direct established usage dependents and relevant interaction tests; Level 2 also includes import-only dependents' unit tests and expanded transitive impact, preserving lower levels. Higher levels progressively expand transitive impact. Use deterministic deduplication, shortest-path semantics appropriate to the edge tiers, and cycle safety.
- The precise edge-weight/level implementation is an engineering detail to validate against explicit fixtures; it must **not** weaken the accepted L2 import-only requirement or silently reclassify unused imports as no impact.
- Imported *external* modules must be identified without pretending they are internal source files. Unresolved/dynamic edges are diagnostics, not fabricated internal edges.

### PY-ADR-04 — Parse `__init__.py` to resolve actual symbol dependencies

- Analyze `__init__.py` modules as part of the project's dependency context, including package aliases and re-exports.
- Resolve what a sibling module/class actually uses from the package's exported/imported dependencies; do **not** blindly assign every initializer import as a used dependency of every class in the directory.
- Also record explicit runtime import relationships independently where they may affect impact at L2.
- Resolve static absolute and relative imports, `from ... import ...`, aliases, and statically identifiable package re-exports. Respect `TYPE_CHECKING` distinctions where detectable.
- Do **not** import or execute project code to inspect runtime definitions.

### PY-ADR-05 — Python-native mocks

- Use Python `unittest.mock` (`Mock`, `MagicMock`, `AsyncMock`, and `create_autospec` where appropriate) through centralized mirrored mock factories/helpers.
- Respect patch-at-lookup-site semantics, dependency injection, sync/async behavior and the project's test fixtures.
- Do not invent a fake successful behavior or silently manufacture a mock for a runtime-unsafe/unresolvable dependency. Report diagnostic limits, including dynamically bound references.
- Do not modify production code to make mocking possible. Only generate missing owned test helpers; preserve all developer-authored files.

### PY-ADR-06 — pytest is the runner, MATMA is the selector

- Default to `pytest` test discovery and assertion conventions without requiring a MATMA pytest plugin, replacing pytest, or creating a separate runner.
- Generate one pytest-compatible unit and interaction test module per eligible source module; both tiers must expose work needed for the module's functions and classes.
- Tests remain **explicitly failing** until a developer authors real assertions (e.g. `pytest.fail("MATMA: implement ...")`).
- MATMA does **not** run selected tests. Coding agents/developers use `python -m pytest <selected paths>`; retain existing `pyproject.toml`, `pytest.ini`, `conftest.py`, and installed plugins.
- Ensure fixture-based testing and asynchronous tests can be authored without requiring new MATMA runtime hooks.

### PY-ADR-07 — Static-first, diagnostics for dynamic behavior

- Perform static AST analysis only for dependency discovery in the first implementation; exhaustive dynamic/runtime analysis is intentionally out of scope for performance.
- Explicitly report unresolved, dynamic, ambiguous or otherwise incomplete analysis in persisted metadata and CLI diagnostics. Do not claim that the static graph proves complete runtime behavior.
- Business and regression suites are responsible for additional workflow/end-to-end evidence; they are non-mirrored and selected via **explicit user-owned registration**, not filename inference.
- Manual dynamic dependency annotations are not required for v0.1.0; consider them a future extension only with a separate accepted decision.

## Retained MATMA contracts from PHP

1. **Full deterministic index rebuild** initially: parse `ast`, resolve known dependencies, compute internal graph and reverse dependents, and write sorted YAML manifests. Incremental indexing is not required for v0.1.0.
2. **Index-only AST work:** `impact` reads persisted target manifest and freshness metadata, selects tests without parsing AST, and never executes tests. Source-hash checks mean the *whole* impact operation is not strictly O(1).
3. **Safety and ownership:** generated `tests/mirror/**/*.auto.yaml` are ignored by Git; use ownership headers, schema version, fingerprints, atomic writes, safe cleanup of MATMA-owned stale files, and byte-stable regeneration. Missing/stale indexes fail loudly and require explicit reindexing.
4. **Non-destructive scaffolding:** create missing test/mock files exclusively; never overwrite existing source or test content. Failing generated tests are not proof of coverage.
5. **Tier isolation:** unit and interaction mirror source modules. Business and regression tests are separate user-authored suites and require explicit registration; `impact` reports registrations but never executes them automatically.
6. **CLI behavior:** `index`, `scaffold`, `impact`, `validate`; options `--source-root/-s`, `--tests-root/-t`, `--scaffold/-S`, `--level/-l`, `--target/-f`, `--check/-c`, `--format/-o`; stable text/json/yaml output and documented nonzero failures. Python exposes these via `matma-indexer`. Prefer machine-readable JSON for coding agents.
7. **No false certainty:** distinguish implementation completed, tests passed, benchmarks measured, and release prepared. A proposed package version does not imply a published release.

## Accepted technical baseline

- Python **3.11+**; native package/installable development tool named **`matma-py`**.
- AST: Python standard-library `ast`; YAML: `PyYAML` with safe loading.
- Package configuration: `pyproject.toml`; `[project.scripts]` entry `matma-indexer = "matma.cli:main"`.
- Tests: `pytest`; mock helpers: `unittest.mock`.
- Cross-platform CI: Linux and Windows, including normalization, path aliases, line endings, symlink safety, CLI snapshots and a real installed consumer fixture.
- Generated manifest storage: `tests/mirror/**/*.auto.yaml`; per-source unit/interaction/mock mirrors follow the host layout.

## Required example and behavior fixture

```text
production: src/acme/pricing.py                 # multiple classes and functions allowed
unit:       tests/unit/mirror/src/acme/test_pricing.py
interaction:tests/interaction/mirror/src/acme/test_pricing_interaction.py
mock:       tests/mocks/mirror/src/acme/mock_pricing.py
manifest:   tests/mirror/src/acme/pricing.auto.yaml
```

This example preserves the `src/` segment. For a flat package, preserve its corresponding relative path. If chosen source roots permit an unambiguous shorter relative mapping, it must be documented and collision-safe; do not silently change identity between runs.

**L2 acceptance example:** `consumer.py` contains `import acme.pricing` but never accesses its attributes. A change to `pricing.py` must include `consumer.py`'s unit-test path by `impact --level 2`. A used `pricing` symbol provides stronger direct usage evidence. Tests must also cover import aliases and `__init__.py` re-exports.

## Implementation phases

Phase 1 package/CLI foundation; Phase 2 AST source and symbol inventory/path mapping; Phase 3 dependency graph/manifests; Phase 4 pytest/mock scaffolding; Phase 5 read-only impact selection/registries; Phase 6 consumer tests, cross-platform CI, benchmarks, adoption documentation and release preparation.

No production engine has been implemented or verified by the existence of this ADR.
