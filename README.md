# MATMA Python — Multi-Tiered Agentic Testing & Mock Architecture

MATMA Python is an agent-oriented testing tool designed to provide predictable,
module-mirrored tests and fast, persisted reverse-dependency impact selections.
It adapts to the **host project's existing Python layout** rather than requiring
one class per file or rewriting production source.

## Status: Phase 1 — package and CLI foundation

The package is installable and exposes all four **command shells**. **The AST,
indexing, scaffolding, and impact engines are not implemented yet.** Running a
shell returns `not_implemented` and exit code `2`; it does not write files,
run tests, or claim success. The validated Phase 1 package and CLI foundation
is **not** a release of the complete MATMA system.

[Accepted architecture](AIDocumentation/ARCHITECTURE_DECISIONS.md) ·
[Implementation checklist](AIDocumentation/TASKS.md) ·
[Phase 1 implementation](AIDocumentation/PHASE_1_IMPLEMENTATION.md)

## Compatibility

- Python 3.11 or newer.
- Python projects with `src/`, flat, or custom source layouts (later phases).
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

In Phase 1, *valid* command invocations return `2` with an honest
`not_implemented` response. Invalid flags or a missing impact target return
`64` with `invalid_options`. `--help` exits `0`.

Common options: `--source-root/-s` (default `src`), `--tests-root/-t`
(default `tests`), `--target/-f`, `--format/-o` (`text`, `json`, `yaml`).
`index` also accepts `--scaffold/-S`; `validate` accepts `--check/-c`;
`impact` accepts `--level/-l` (nonnegative integer, default `0`).

The response contract is stable for all four commands:

```json
{
  "command": "validate",
  "status": "not_implemented",
  "message": "AST validation is not available yet (planned for Phase 2); no work performed",
  "exit_code": 2,
  "options": {
    "source_root": "src",
    "tests_root": "tests",
    "format": "json",
    "target": null,
    "check": true
  }
}
```

Use JSON for coding-agent automation; YAML/text are available for developers.

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

`python -m pytest` checks CLI parsing, formats, errors, no-side-effects,
subprocess entry points, and an isolated installed consumer fixture. CI runs
on Linux and Windows with supported Python versions.
