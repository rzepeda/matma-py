# MATMA Python — Multi-Tiered Agentic Testing & Mock Architecture

MATMA Python is an agent-oriented testing tool designed to provide predictable,
module-mirrored tests and fast, persisted reverse-dependency impact selections.
It adapts to the **host project's existing Python layout** rather than requiring
one class per file or rewriting production source.

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
matma-indexer index --scaffold --target src/example/service.py --format json
matma-indexer impact --target src/example/service.py --level 2 --format json

# Also available without relying on the console script:
python -m matma validate --check
```

`validate` returns `validated` (exit `0`) or a strict failure (exit
`1`) for source errors. Without `--check`, structural errors are reported but
the audit returns `0`, except for unsafe/missing roots. `index` returns
`indexed` (exit `0`) and writes only generated YAML unless `--scaffold`
is supplied. `scaffold` returns `scaffolded` (exit `0`) on success and generates
only **missing** authored-file starters; it also rebuilds the full index.
`index --scaffold` returns `indexed` with a `scaffolds` report. Invalid source
graphs, unsafe destinations or user-owned manifest conflicts return `1`.
`impact` returns `impact_selected` (exit `0`) with existing unit/interaction
test paths and separate missing-test diagnostics. Missing, stale, invalid or
unsafe generated metadata fails (`impact_failed`, exit `1`) and requires an
explicit `index` refresh. `impact` never runs tests or reparses Python AST.
Invalid flags or a missing impact target return exit `64` / `invalid_options`;
`--help` exits `0`.

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
paths. This is persisted **selection information** only; the `impact` reader selects already existing test files from those manifests.
Fingerprint and recorded directory timestamps support freshness checking,
but do not make indexing incremental or guarantee detection of every external
filesystem change (e.g. metadata-preserving modifications).

## Phase 4: module-mirrored test and mock starters

```bash
# Scaffold every eligible source module (full graph is indexed first):
matma-indexer scaffold -o json

# Only create tests for a selected source; also add its direct internal mocks:
matma-indexer scaffold -f pkg.service -o json

# Equivalent scoped scaffolding through the index operation:
matma-indexer index --scaffold -f pkg.service -o json

# Test execution is ALWAYS explicit. Generated placeholders intentionally fail:
python -m pytest tests/unit/mirror/src/pkg/test_service.py
```

Every testable source module maps to **one** unit and **one** interaction file,
plus a centralized mock helper. A module may contain any number of functions,
classes and methods. Both tiers emit distinct, **failing `pytest.fail` tests**
for each statically addressable function, async function, class and method.
An addressable nested class is included; a function-local declaration is
reported as omitted and must be covered through the enclosing callable's tests.
A module with no addressable callable still generates a failing module-behavior
test. These placeholders are not passing coverage or a substitute for assertions.

The mock file exposes `unittest.mock.create_autospec` factories for local classes,
functions and async functions. `patch_at_lookup(consumer_module, bound_name)`
encourages patching **where an imported name is looked up**. Generated mock
helpers only import the application module when a developer calls a factory;
MATMA itself does not execute it. External, unresolved, non-testable and dynamic
mocking limits are surfaced as warnings, not invented mocks.

For `--target`, only that module's unit/interaction tests are created, along
with a mock helper for the target and for direct **testable internal** dependencies.
Unrelated tests are untouched, but the complete dependency index is rebuilt.
All output destinations are checked before writing manifests. Test/mock files
are opened exclusively, **never rewritten or deleted**. Even altered generated
files immediately become developer-owned. Re-running reports `existing` paths
and preserves bytes and timestamps; only MATMA-owned YAML is regenerated.

Example paths for `src/pkg/service.py`:

```text
tests/unit/mirror/src/pkg/test_service.py
tests/interaction/mirror/src/pkg/test_service_interaction.py
tests/mocks/mirror/src/pkg/mock_service.py
tests/mirror/src/pkg/service.auto.yaml
```

MATMA never runs pytest for you; developers and agents run selected tests
explicitly. Only `validate` is read-only; `index` and `scaffold` write the
generated artifacts they document.

## Phase 5: read-only impact selection

```bash
matma-indexer index -o json
matma-indexer impact -f pkg.service --level 2 --format json
```

Level `0` selects the target's unit tests; Level `1` adds target interaction
and direct proven usage dependents; Level `2` includes importing modules whose
binding was imported but never used, and two-edge usage chains. Greater levels
select more transitive dependents using the precomputed shortest weighted
reverse graph. **Only existing files** appear in `tests.unit` and
`tests.interaction`; expected absent tests appear in `tests.missing` with their
tier, source and level. Missing tests do not cause a false claim of coverage.

`impact` reads the generated companion `.index.auto.yaml` and **one target
manifest**, never reindexes automatically, never parses source AST and never
runs pytest. SHA-256 freshness checks read only already indexed source-file
bytes, and recorded source directory timestamps signal added or removed files.
If stale, run `matma-indexer index` again.

Business and regression tests are optional, explicitly registered in the
user-owned `tests/matma-verification.yaml`:

```yaml
schema_version: 1
registrations:
  src/pkg/service.py:
    business:
      - tests/business/test_user_workflow.py
    regression:
      - tests/regression/test_issue_123.py
```

They are **reported separately**, never automatically selected or executed as
unit/interaction tests. Dynamic Python behavior remains outside the static
index's guarantees; use genuine business and regression assertions for additional
evidence. See [Phase 5 implementation](AIDocumentation/PHASE_5_IMPLEMENTATION.md).

## Verification

`python -m pytest` checks CLI parsing, AST inventories, import resolution,
layout and mirror mapping, path safety, real YAML regeneration and
manual-file preservation, subprocess output, read-only validation, non-clobber
pytest/mock templates, scoped dependency mocks, and a consumer fixture that
confirms generated pytest tests fail until authored. GitHub Actions validates Python
3.11–3.13 across Linux and Windows.


## Phase 6: consumer validation and release preparation

Phase 6 includes a full consumer lifecycle, authored business/regression
evidence, wheel-build checks, portable CLI fixtures and a reproducible
**full index versus persisted impact-with-freshness** benchmark.

[Consumer adoption guide](AIDocumentation/CONSUMER_GUIDE.md) ·
[Phase 6 evidence](AIDocumentation/PHASE_6_IMPLEMENTATION.md) ·
[Release readiness checklist](AIDocumentation/RELEASE_CHECKLIST.md)

```bash
python -m pytest -q
python benchmarks/benchmark_matma.py --modules 96 --iterations 3
python -m build --wheel --no-isolation
```

This phase does **not** tag, license, publish to PyPI, or merge into `main`.
The package remains version `0.1.0.dev0` until a separately authorized release.

**CI evidence:** Six Linux/Windows Python 3.11–3.13 jobs passed in
[run 42407788706](https://github.com/rzepeda/matma-py/actions/runs/42407788706).
On the synthetic 96-module Linux/Python 3.13 benchmark, the median full warm
index was **1,173.3 ms**, versus **84.5 ms** for impact with freshness checks
(**13.9×** in that fixture; not a performance guarantee).

## Coding-agent skills: Claude, ChatGPT/Codex, Antigravity

MATMA includes three independently installable agent skills with
platform-specific instructions and a shared exact CLI contract:
[skill distribution and setup](integrations/README.md),
[Python project setup](integrations/PYTHON_PROJECT_SETUP.md).

```bash
python integrations/install_skills.py --project /path/to/python-project --platform all
```

The installer only copies skill instructions. Install the MATMA developer CLI
separately in the consumer project's Python 3.11+ environment; it does not
install or run application code. Claude Code uses `.claude/skills/matma-python`,
while ChatGPT desktop/Codex and Antigravity use separately named directories
under `.agents/skills`. A normal ChatGPT browser chat does not automatically
load local Codex skills.
