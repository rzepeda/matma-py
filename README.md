# MATMA Python — Multi-Tiered Agentic Testing & Mock Architecture

MATMA Python is an agent-oriented testing tool designed to provide predictable,
module-mirrored tests and fast, persisted reverse-dependency impact selections.
It adapts to the **host project's existing Python layout** rather than requiring
one class per file or rewriting production source.

## Status: Phase 3 — AST indexer and deterministic manifests

The installable Python package implements **`validate`** (read-only structural
analysis) and **`index`** (full AST dependency index and generated YAML
manifests). Neither command executes application code or tests or writes
production files. **`scaffold` and `impact` remain unimplemented** and return
exit `2`; the project has not published a complete MATMA release.

[Accepted architecture](AIDocumentation/ARCHITECTURE_DECISIONS.md) ·
[Implementation checklist](AIDocumentation/TASKS.md) ·
[Phase 1 implementation](AIDocumentation/PHASE_1_IMPLEMENTATION.md) ·
[Phase 2 implementation](AIDocumentation/PHASE_2_IMPLEMENTATION.md) ·
[Phase 3 implementation](AIDocumentation/PHASE_3_IMPLEMENTATION.md)

## Compatibility

- Python 3.11 or newer.
- Python projects with `src/`, flat, or custom source roots, including multiple roots.
- Pytest is the intended **test runner**; MATMA itself only selects tests.
- Dependency: PyYAML 6.x.

## Development installation

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

For a consumer project, the package can be installed from its Git repository
(as an editable checkout or package dependency) while it is in development.
No PyPI release has been published and no license grant is implied.

## Command-line interface

```bash
matma-indexer --help
matma-indexer validate --source-root src --check --format json
matma-indexer index --source-root src --tests-root tests --format yaml
matma-indexer scaffold --target src/example/service.py --format json
matma-indexer impact --target src/example/service.py --level 2 --format json

# Also available without relying on the console script:
python -m matma validate --check
```

`validate` returns `validated` (exit `0`) or a strict failure (exit
`1`) for source errors. Without `--check`, structural errors are reported but
the audit returns `0`, except for unsafe/missing roots. `index` returns
`indexed` (exit `0`) and writes only generated YAML. Invalid source graphs,
unsafe output or user-owned manifest conflicts return `1`. `index --scaffold`,
`scaffold`, and `impact` return `2` / `not_implemented` without writing files. Invalid flags or a missing impact target
return exit `64` / `invalid_options`; `--help` exits `0`.

Common options: `--source-root/-s` (default `src`), `--tests-root/-t`
(default `tests`), `--target/-f`, `--format/-o` (`text`, `json`, `yaml`).
`index` also accepts `--scaffold/-S`; `validate` accepts `--check/-c`;
`impact` accepts `--level/-l` (nonnegative integer, default `0`).
`--extra-source-root` can be repeated for additional source directories.

The shared response includes `command`, `status`, `message`, `exit_code`
and `options`. A completed `validate` adds `summary`, `target`, `files`,
`module_to_source`, `symbol_to_source` and `diagnostics`. Example:

```json
{
  "command": "validate",
  "status": "validated",
  "message": "Inspected 2 Python modules; 0 structural errors",
  "exit_code": 0,
  "options": {"source_root": "src", "tests_root": "tests", "extra_source_root": [], "format": "json", "target": null, "check": true},
  "summary": {"source_roots": ["src"], "source_files": 2, "parsed_files": 2, "testable_modules": 1, "symbols": 3, "imports": 2, "diagnostic_errors": 0, "diagnostic_warnings": 0},
  "target": null,
  "files": ["... per-module inventory ..."],
  "module_to_source": {"example_app": "src/example_app/__init__.py", "example_app.pricing": "src/example_app/pricing.py"},
  "symbol_to_source": {"example_app.pricing.PriceCalculator": "src/example_app/pricing.py"},
  "diagnostics": []
}
```

The example is abbreviated; real JSON output provides full module records.

Use JSON for coding-agent automation; YAML/text are available for developers.

## Source-root discovery and validation

```bash
# Discover roots from pyproject.toml or src/ / flat layout
matma-indexer validate --check --format json

# Explicit layout with multiple source directories
matma-indexer validate -s src --extra-source-root plugins --check -o json
```

`[tool.matma] source_roots = ["src", "plugins"]` in `pyproject.toml`
can configure more than one root; otherwise setuptools package discovery
metadata, `src`, then project root are considered in that order. Path
identities are project-relative (`src/example/pricing.py`) even when the
source root is `src`. Targets can be a source-file path, module name, or
qualified symbol. Python encoding declarations are honored. Invalid syntax,
module-name collisions, relative import errors, symlinked sources and unsafe
roots are diagnosed, with file/line context when available.

A Python `__init__.py` is analyzed for statically resolvable package exports
and re-exports, without treating every export as a direct use by every sibling
class. Static imports and actual references are inventoried separately;
the dependency indexer now records them in generated manifests. An import
with a proven symbol reference has edge weight 1; an import whose binding
is unused receives weight 2. Thus directly used imports appear in Level 1,
while import-only dependents enter at **Level 2**. Transitive paths use the
shortest sum of edge weights and cycles are deduplicated.

## Phase 3 index generation and persisted graph

```bash
matma-indexer index --source-root src --tests-root tests --format json
matma-indexer index --target pkg.services --format yaml
```

Indexing always scans and validates **all** source roots, even with `--target`,
so the reverse graph remains consistent. It builds file-owned dependency edges
from statically resolved imports and class/function usages. External imports,
dynamic imports, type-only imports and unresolved references are distinguished;
no application code is imported or executed to inspect them. For a source such
as `src/pkg/service.py`, index writes:

```text
tests/mirror/src/pkg/service.auto.yaml    # source symbols, typed dependencies, reverse dependents
tests/mirror/.index.auto.yaml             # shared fingerprint, source hashes, directory metadata
```

These generated `*.auto.yaml` files are excluded from version control. They
include an ownership header and schema version. Indexing refuses to overwrite
user-owned YAML, preserves byte-identical generated YAML without rewriting,
only deletes stale *MATMA-owned* YAML, and preflights paths against symlinks
and traversal. Missing/invalid sources, ambiguous collisions and unsafe output
produce a nonzero exit without claiming a complete index. Individual writes
are atomic; a multi-file rebuild is not a filesystem transaction.

`dependents.level_1` means established symbol usage, `level_2` adds unused
imports and depth-two usage chains, and `level_3+` expands weighted shortest
paths. This is persisted **selection information** only; the `impact` reader
remains Phase 5 work and tests are never executed by `index`. Fingerprint and
recorded directory timestamps support future freshness checking, but do not
make indexing incremental or guarantee complete detection of all external
filesystem changes.

## Test tiers (planned)

A source module such as `src/acme/pricing.py`, even with multiple functions or
classes, will map to exactly one unit test file and one interaction test file.
Both tiers will account for the module's testable symbols. Generated stubs will
explicitly fail until authored. Centralized mock helpers are planned for Phase 4. Regenerable, untracked YAML
manifests already follow the source layout.

Business and regression tests are separately authored and registered; dynamic
runtime behavior is outside the initial static-analysis scope. For import-only
dependencies, Level 2 must select the importing module's unit tests.

## Verification

`python -m pytest` checks CLI parsing, AST inventories, import resolution,
layout and mirror mapping, path safety, real YAML regeneration and
manual-file preservation, subprocess output, read-only validation, and an
isolated installed consumer fixture. GitHub Actions validates Python
3.11–3.13 across Linux and Windows.
