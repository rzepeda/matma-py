# MATMA Python — Multi-Tiered Agentic Testing & Mock Architecture

MATMA Python is an agent-oriented testing tool designed to provide predictable,
module-mirrored tests and fast, persisted reverse-dependency impact selections.
It adapts to the **host project's existing Python layout** rather than requiring
one class per file or rewriting production source.

## Status: Phase 2 — read-only AST validation

The installable Python package now implements **`validate`**: structural
source inventory, Python AST symbol/import analysis and deterministic mirror
path resolution. It inspects existing code **without executing it** and
without generating or modifying project files. `index`, `scaffold` and `impact`
remain unimplemented and return exit `2`; the project has not published a
complete MATMA release.

[Accepted architecture](AIDocumentation/ARCHITECTURE_DECISIONS.md) ·
[Implementation checklist](AIDocumentation/TASKS.md) ·
[Phase 1 implementation](AIDocumentation/PHASE_1_IMPLEMENTATION.md) ·
[Phase 2 implementation](AIDocumentation/PHASE_2_IMPLEMENTATION.md)

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

`validate` now returns `validated` (exit `0`) or a strict failure (exit
`1`) for source errors. Without `--check`, structural errors are reported but
the audit returns `0`, except for unsafe/missing roots. The other engines
return exit `2` / `not_implemented`. Invalid flags or a missing impact target
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
reverse dependencies and Level 2 import-only impact are **Phase 3 work**.

## Test tiers (planned)

A source module such as `src/acme/pricing.py`, even with multiple functions or
classes, will map to exactly one unit test file and one interaction test file.
Both tiers will account for the module's testable symbols. Generated stubs will
explicitly fail until authored. Additional centralized mock helpers and
regenerable, untracked YAML manifests will follow the source layout.

Business and regression tests are separately authored and registered; dynamic
runtime behavior is outside the initial static-analysis scope. For import-only
dependencies, Level 2 must select the importing module's unit tests.

## Verification

`python -m pytest` checks CLI parsing, AST inventories, import resolution,
layout and mirror mapping, path safety, subprocess output, read-only behavior,
and an isolated installed consumer fixture. GitHub Actions validates Python
3.11–3.13 across Linux and Windows.
