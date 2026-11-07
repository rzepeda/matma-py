# MATMA Python — Phase 5: Persisted Impact Selection and Verification Registry

**Status:** Implemented on Phase 5 feature branch; do not mark complete until the full GitHub Actions Python 3.11–3.13 / Linux+Windows matrix passes.

**Design reference:** [accepted ADR-001](ARCHITECTURE_DECISIONS.md) and [implementation checklist](TASKS.md). This phase is **read-only**: it does not run pytest, import application modules, parse source AST, regenerate stale manifests, or crawl source trees.

## Implemented components

| File | Purpose |
| --- | --- |
| `src/matma/impact/reader.py` | Safe target lookup, persisted-index validation/freshness, level filtering, test-file existence checks and explicit registration lookup |
| `src/matma/impact/__init__.py` | Stable `select_impact(...)` API |
| `src/matma/indexing/manifests.py` | Extend `.index.auto.yaml` with precomputed module/symbol/manifest lookup, test root and per-source diagnostic warnings |
| `src/matma/cli.py` | Implement `impact`, retaining JSON/YAML/text results and strict exit codes |
| `tests/unit/mirror/test_impact.py` | Deterministic unit fixtures without AST analysis; safety and read-only assertions |
| `tests/interaction/mirror/test_impact_cli.py` | Real index/scaffold → impact with used and unused imports, aliases and registry |

## Impact level contract

- **Level 0:** select the target module's **existing** unit-test file. A missing test file appears under `tests.missing`, not among selected runnable files. A non-testable package initializer may not have its own test file.
- **Level 1:** include Level 0 plus target interaction tests, direct **proven usage** dependent modules' unit and interaction test files.
- **Level 2:** include all lower levels plus unused/import-only dependents' unit tests (and their existing interaction files), plus two-edge usage chains at shortest weighted distance 2.
- **Level N:** include all dependent modules at precomputed shortest weighted graph distance ≤ N. Cycles remain deduplicated. This is the established Phase 3 graph; no source traversal occurs in `impact`.
- Always sort and deduplicate paths. `tests.unit` and `tests.interaction` contain **existing files only**; `tests.missing` lists expected but absent paths with source, tier and level. Missing test files do not make the selection itself fail and must not be reported as proof of coverage.

`--target` may be a source path (`src/pkg/service.py`), module (`pkg.service`) or qualified class/function (`pkg.service.Service`), resolved through persisted metadata. Backslash separators in source paths are normalized to slashes. Unknown targets return a nonzero error.

## Read-only persisted index and freshness

`impact` opens only **two MATMA-owned YAML files** for a query: `tests/mirror/.index.auto.yaml` and the requested module's `tests/mirror/<source>.auto.yaml` (along with the optional user-owned registry). It validates ownership headers, schema and matching content fingerprints, checks SHA-256 hashes of the already indexed source files, and checks recorded source-directory modification times. It opens source files only to hash bytes; it never reads or parses their AST, and never imports them. The metadata now includes `module_to_source`, `symbol_to_source`, `source_to_manifest`, `tests_root`, and `warnings_by_source` so no other manifest needs opening.

Freshness checks require **O(number of indexed source files + recorded source directories)** filesystem reads/stat operations, not O(1) end-to-end. Directory mtimes provide an inexpensive signal for newly added/deleted files, but metadata-preserving external file operations can evade this heuristic. A malformed, missing, stale or unsafe index fails with `impact_failed` and exit code `1` plus an error code (`missing_index`, `stale_index`, `invalid_index`, `unsafe_index`, `unsafe_path`, `invalid_target`). The user must explicitly rerun `matma-indexer index`. **Impact never automatically reindexes**.

Generated index files may be removed and regenerated; they remain excluded from version control and user-authored test files remain untouched. An index written by an older version without the lookup fields must be regenerated once with the Phase 5 indexer.

## Explicit user-owned business/regression registration

Optional file: **`tests/matma-verification.yaml`** (or `<tests-root>/matma-verification.yaml`). MATMA never generates, replaces or mutates this file.

```yaml
schema_version: 1
registrations:
  src/pkg/pricing.py:
    business:
      - tests/business/test_checkout.py
    regression:
      - tests/regression/test_discount_rounding.py
  pkg.consumer:
    business:
      - tests/business/test_checkout.py
```

Registry keys must identify an indexed source module by its file path, module name or qualified symbol. Business and regression files must be explicit project-relative `.py` paths **inside the configured tests root**; MATMA does not glob directories or infer these tests by naming convention. The registry is safe-loaded, validates all entries and forbids traversal/symlink destinations. The output groups **existing registered files** in `verification.business` and `verification.regression`; missing registered files are separately reported in `verification.missing`. Registrations attached to unaffected modules are not included. Duplicate registered paths are selected once, even if they belong to several affected sources.

The output *reports* suggested verification paths; MATMA does **not** run registered or mirrored tests. These workflows are user-authored evidence for business behavior and regression prevention, not proof inferred from static import analysis.

## Command and example

```bash
matma-indexer index -o json                      # required before impact
matma-indexer scaffold -f pkg.pricing -o json   # optional, creates failing templates
matma-indexer impact -f pkg.pricing -l 2 -o json # read-only
# Then choose paths explicitly, e.g.
python -m pytest tests/unit/mirror/src/pkg/test_pricing.py
```

Successful output has the stable common keys `command`, `status`, `message`, `exit_code`, `options` and the new `target`, `level`, `index_fingerprint`, `affected_sources`, `tests.unit`, `tests.interaction`, `tests.missing`, `verification`, `warnings`, `analysis_limits`. Status is `impact_selected`, exit `0`; wrong arguments still return exit `64`. Missing, invalid or stale metadata returns `impact_failed`, exit `1` with `error_code`. Never state a test has passed solely because MATMA selected its path.

## Tests and acceptance

- Unit: target lookup by all supported spellings; weighted Levels 0–2; deterministic deduplication; missing test paths; explicit registration (including missing files), malformed paths, YAML ownership and schema, source hash and directory freshness, symlinks, absent manifests; monkeypatch guards against AST parsing or automatic test execution.
- Integration: real source → `index` → persisted graph → `impact`; used import at L1, unused import at L2, flat/package layouts, custom test roots; registered business/regression files are never inferred when unregistered.
- Installed consumer: run `impact` after `scaffold`; confirm selected existing templates without modifying or executing the generated app's tests.
- Linux/Windows CI matrix on Python 3.11–3.13 must pass before tasks are marked verified.

## Out of scope

Phase 6 includes end-to-end adoption documentation and release preparation, more complete portability/benchmark evidence and performance claims. Dynamic Python runtime dependencies are not guessed; users should supplement static selections with registered business/regression workflows.


### CI-discovered freshness correction

The initial Phase 5 CI run found that Phase 3 was also watching the project root
for `src/`-layout projects. Running pytest in a consumer created
`.pytest_cache/` next to `src/` and incorrectly invalidated the source index.
The directory inventory now watches only the explicitly configured source roots
and their nested indexed folders (including `.` only for a flat source-root `.`).
An actual change to a known source file or tracked source folder still requires reindexing.
Regression fixtures cover both the inventory policy and the real CLI workflow.
