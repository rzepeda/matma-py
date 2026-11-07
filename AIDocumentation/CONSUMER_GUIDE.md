# MATMA Python — Consumer Adoption Guide

**Scope:** Use the development package in an existing Python repository. MATMA
adapts to the project's files and uses **pytest** as the test runner. It does
not modify production modules or require a pytest plugin.

## 1. Install in the development environment

Python **3.11+** and pytest are needed. The repository currently identifies its
package as **`matma-py==0.1.0.dev0`**. This is a development version, **not** a
published PyPI release.

```bash
# Clone and check out the MATMA implementation branch or an approved release.
# From the MATMA Python checkout:
python -m pip install -e ".[dev]"
python -m pytest -q
matma-indexer --help
```

For a separate consumer project, install MATMA as a **development-only** tool
from a local MATMA checkout or approved Git revision. Do not add a production
runtime dependency solely to run the indexer. PyYAML is required at runtime by
the developer tool; pytest is the normal test runner.

## 2. Select the production source roots

By default MATMA uses `src/` when it exists and otherwise the flat project
root. It also recognizes setuptools package-discovery configuration. For
multiple or nonstandard source roots, set:

```toml
[tool.matma]
source_roots = ["src", "plugins"]
```

Or specify roots explicitly with `--source-root` and repeated
`--extra-source-root` flags. A path identity always includes the project-root
relative path; multiple source files can share the same basename without
sharing their mirrored test destination.

An ordinary module can declare many functions, classes, and methods: the
module **file** is the atomic MATMA unit. One source file gets at most one unit
test, one interaction test, and one centralized mock helper. A normal
`__init__.py` is read for imports/re-exports and is not forced to have its own
test unless it contains independently testable behavior.

## 3. Inspect and index

```bash
matma-indexer validate --check --format json
matma-indexer index --format json
```

`validate` reads ASTs without creating files. `index` builds a **full** static
dependency graph and persists safe, deterministic, MATMA-owned YAML:

```text
tests/mirror/.index.auto.yaml
tests/mirror/src/pkg/pricing.auto.yaml
```

These generated manifests are ignored by Git; user-authored test files should
remain tracked. Changing any known source file or its graph requires an explicit
`index` rerun before `impact` can select tests. `index -f pkg.pricing` still
indexes the **whole** project for correct reverse dependency information.

## 4. Scaffold missing pytest tests and mocks

```bash
matma-indexer scaffold --target pkg.pricing --format json
# Alternative: matma-indexer index --scaffold --target pkg.pricing
```

For example, `src/pkg/pricing.py` maps to:

```text
tests/unit/mirror/src/pkg/test_pricing.py
tests/interaction/mirror/src/pkg/test_pricing_interaction.py
tests/mocks/mirror/src/pkg/mock_pricing.py
```

Both mirrored test tiers contain separate, intentionally failing pytest
placeholders for addressable functions, async functions, classes and methods.
**Replace them with assertions**. Their failure is deliberate; an empty or
passing template would be dishonest evidence of coverage. Function-local
nested definitions are inventoried but must generally be exercised through an
enclosing callable. MATMA never overwrites or deletes an existing test/mock
file, even when its developer has modified the original generated starter.

Mock helpers rely on `unittest.mock` autospec and lazy spec resolution, and
`patch_at_lookup` encourages patching the name in the *consumer* module where
it is used. MATMA does not execute application code when indexing or
scaffolding. Calling a mock factory during an actual test may import its spec;
the developer owns that runtime behavior.

## 5. Register human-owned business and regression workflows (optional)

Create and track **`tests/matma-verification.yaml`**:

```yaml
schema_version: 1
registrations:
  pkg.pricing:
    business:
      - tests/business/test_checkout.py
    regression:
      - tests/regression/test_discount_rounding.py
```

MATMA neither creates nor infers these workflows. Paths must be explicit
project-relative `.py` files inside the configured test root. Missing
registered files are shown separately. This registry is important for dynamic
loading, runtime injection, monkey-patching, workflows, and correctness
obligations the static dependency graph cannot establish.

## 6. Select affected tests, then run pytest explicitly

```bash
matma-indexer impact -f pkg.pricing -l 2 -o json
python -m pytest tests/unit/mirror/src/pkg/test_pricing.py
```

**Inclusive impact levels:**

| Level | Meaning |
| --- | --- |
| 0 | Target module's unit test if it exists |
| 1 | Adds interaction tests and direct established-use dependents |
| 2 | Adds import-only dependents' unit and interaction tests and two-step usage chains |
| N | Includes all shorter weighted reverse-dependency paths |

`impact` reports `tests.unit`, `tests.interaction` (existing, runnable paths),
`tests.missing` (expected paths not present), `verification.business`,
`verification.regression`, `verification.missing`, `affected_sources`, and
`warnings`/`analysis_limits`. **Selection is not test execution.** Run
`python -m pytest <selected file paths>` yourself or from an explicit CI
workflow. Do not turn a list of selected tests into a claim that they passed.

`impact` uses only the generated companion YAML, requested module YAML, and
optional registry for graph selection. To check freshness it **hashes known
source files** and stats recorded source directories. It does not reparse AST,
scan the full source tree, automatically reindex, or execute tests. Freshness
work is O(indexed source files + tracked directories), not O(1) total.

## 7. Troubleshooting and safety

| Symptom | Expected response |
| --- | --- |
| `missing_index` / `stale_index` | Run `matma-indexer index` after validating roots |
| `invalid_target` | Use a project-relative `.py` path, module name, or qualified symbol from the index |
| `invalid_registry` | Validate the user-authored YAML schema and explicit test paths |
| `unsafe_output` / `unsafe_path` | Remove path traversal, output collisions, or symlinked destinations; MATMA refuses unsafe writes |
| Generated pytest tests fail | Implement actual assertions; this is intentional scaffold behavior |
| Business/regression tests not selected | Explicitly register them in `matma-verification.yaml` |
| Dynamic import not represented | Review diagnostic, manually include relevant business/regression tests |
| Source file changed only in CRLF/LF bytes | Content hash changes: run `index` to refresh |

Use `--format json` for coding-agent orchestration and stable machine-readable
exit statuses: 0 success, 1 semantic/unsafe/stale error, 64 invalid options.
The reserved exit 2 remains for unfinished commands; all four core commands
are implemented in Phase 5 and later.

## 8. Continuous integration adoption

A safe minimal workflow is: install MATMA in development, run `validate
--check`, build `index`, select a target with `impact -l 2`, review missing
files, then run the selected pytest paths and the explicitly registered
business/regression tests. Keep full business/regression suites in your CI
policy independently of MATMA's static-only selection; MATMA does not provide
a complete proof of arbitrary Python runtime behavior.

For a measured reproducible fixture, see
[`../benchmarks/benchmark_matma.py`](../benchmarks/benchmark_matma.py) and
[Phase 6 report](PHASE_6_IMPLEMENTATION.md).
