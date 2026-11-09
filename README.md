# MATMA Python — Multi-Tiered Agentic Testing & Mock Architecture

MATMA Python is an agent-oriented testing tool designed to provide predictable,
module-mirrored tests and fast, persisted reverse-dependency impact selections.
It adapts to the **host project's existing Python layout** rather than requiring
one class per file or rewriting production source.

## The MATMA Methodology

### 1. What is MATMA?

**MATMA (Multi-Tiered Agentic Testing & Mock Architecture)** is a software testing methodology and architectural framework designed to optimize Test-Driven Development (TDD), refactoring, and verification workflows performed by autonomous AI coding agents.

MATMA establishes **seven architectural rules** governing source organization, test isolation, mock management, dependency relationships, and verification boundaries. It addresses constraints specific to LLM-based coding agents: finite context windows, token consumption, repeated filesystem exploration, and the need for focused, deterministic feedback when modifying software.

An agent working on a single class may need to find its tests, inspect dependencies, locate appropriate mocks, and determine which consumers could be affected by a change. MATMA combines two mechanisms to make that work predictable:

- **A rule-based testing and mocking methodology:** precise definitions of which classes are real and which are mocked at each testing tier.
- **A deterministic indexing and discovery architecture:** mirrored tests and mock helpers, precomputed reverse dependencies, and persisted manifests for selecting affected verification.

MATMA complements existing frameworks such as pytest and PHPUnit; **it does not replace the host project's test runner**.

### 2. Five optimization objectives

#### 2.1 Context-window and token efficiency

Autonomous coding agents repeatedly load source files, tests, mocks, and dependency information into their working context. Centralized mocks, predictable test paths, and disk-persisted manifests help agents retrieve only the files and metadata relevant to the current task, reducing redundant inspection and token consumption.

#### 2.2 Deterministic file and symbol discovery

MATMA defines source-to-test, source-to-mock, and source-to-manifest mappings that can be derived from the source identity. This is intended to avoid repeated repository-wide `find`, `grep`, and `glob` searches merely to locate verification artifacts.

#### 2.3 Disk-materialized reverse dependencies

A change to a class or module can affect its consumers. MATMA analyzes source dependencies ahead of time, computes the reverse relationships, and persists them in generated `.auto.yaml` manifests. Impact queries then use persisted information instead of reconstructing the source dependency graph on every request.

#### 2.4 Signal-to-noise isolation

Tests with too many real collaborators can fail for unrelated reasons. MATMA's testing rules prescribe which participants are real and which are mocked, giving each tier a bounded diagnostic purpose.

#### 2.5 Tiered verification scaling

MATMA separates isolated unit tests, pairwise interactions, business workflows, and real-system regressions. Class-centric tests can be selected using a reverse-dependency impact radius (`--level`); business and regression tests remain distinct verification tiers.

### 3. The seven architectural rules

These are MATMA's **accepted normative testing rules**. Language-specific Architecture Decision Records (ADRs) define the implementation conventions, including the explicitly accepted Python adaptation to Rule 1.

#### Rule 1 — One Class Per File with Coinciding Names

The original structural rule requires each source, test, and mock file to encapsulate one class whose identifier deterministically corresponds to its filename under the target language's naming convention.

**Why:** Aligning file and class identities makes source and verification artifacts predictable. Agents can derive paths instead of discovering them through repeated searches.

**Accepted Python adaptation — PY-ADR-01: Atomic identity is the source module, not the class.** Python conventionally allows multiple classes, functions, asynchronous functions, and methods in one source module. Enforcing a class-per-file constraint would impose an artificial organization on existing Python projects. MATMA Python therefore treats the **source module/file** as the atomic mirror and impact target:

- A Python module can contain multiple classes and functions.
- One testable module maps to one unit test file, one interaction test file, one centralized mock helper, and one generated manifest.
- Tests must address the module's testable functions and classes.
- The existing source layout is preserved; MATMA does not rename or split production modules.

For example:

~~~text
src/acme/pricing.py
tests/unit/mirror/src/acme/test_pricing.py
tests/interaction/mirror/src/acme/test_pricing_interaction.py
tests/mocks/mirror/src/acme/mock_pricing.py
tests/mirror/src/acme/pricing.auto.yaml
~~~

This changes the **granularity of structural mirroring**, not the intent of deterministic discovery or the real-versus-mock testing boundaries. MATMA PHP retains native PascalCase class filenames and PSR-4 mapping.

#### Rule 2 — Isolated Unit Testing with Mocks

When performing TDD on `ClassA`, instantiate **`ClassA` as real** and replace **every external interaction and collaborator** with a mock.

~~~text
Unit test: ClassA
ClassA  REAL
  ├── ClassB  MOCK
  └── ClassC  MOCK
~~~

**Why:** The unit test checks the target class independently of its collaborators. If a failure occurs, the testing boundary limits the possible causes to the target's behavior and its test configuration, rather than an unrestricted dependency graph.

For MATMA Python, module-level mirroring determines the **test file's location**; individual tests inside it still isolate the class or function being verified.

#### Rule 3 — Centralized Mirrored Mock Registries

Reusable mock classes/helpers live under `tests/mocks/mirror/`, following the production source structure. Tests import them from that registry instead of defining equivalent inline mocks.

**Why:** A central registry provides a single source of truth for test doubles, reduces duplicate mock implementations, and helps agents load the relevant dependency substitute directly. Public interface changes require corresponding updates to mirrored mocks and associated interaction tests.

Mocks must use the host language's supported mocking mechanisms; an unsafe or unmockable dependency must not be represented as a working fake without evidence.

#### Rule 4 — Strict Pairwise Interaction Isolation

An interaction test checks a selected call from `ClassA` into `ClassB`. **Both `ClassA` and `ClassB` are real**; **every other downstream collaborator** needed by either class is mocked.

~~~text
Interaction test: ClassA + ClassB
ClassA  REAL
  ├── ClassB  REAL
  │    └── ClassC  MOCK
  └── ClassD  MOCK
~~~

**Why:** Two classes may pass independent unit tests yet fail to exchange parameters, results, or errors correctly. Pairwise verification checks their real contract without accidentally involving a third real dependency and expanding the diagnostic scope into a broader integration graph.

#### Rule 5 — Service-Level Boundary Mocking for Workflows

Business tests under `tests/business/` exercise **real internal domain models, business classes, and workflow logic**. Only **external or infrastructure services** are mocked at their service boundaries—such as databases, LLM providers, vector stores, and HTTP clients.

**Why:** Mocking internal business logic would stop the test from validating the actual workflow. Mocking its infrastructure boundary keeps the process testable while exercising the real internal sequence. These tests are **process-oriented**, not mirrored to a single source class.

#### Rule 6 — Integrated Regression Gateways

MATMA's regression tier, `tests/regression/`, must verify **end-to-end application behavior with real datasets and real, live, or containerized participating services**. Participating services are **not replaced with mocks**. The methodology requires this regression suite as a gateway before merge or deployment.

**Why:** Unit, pairwise, and business tests deliberately isolate parts of the system. They cannot alone establish that all participating components and services work together with real data. The regression tier provides that separate full-system evidence.

**Implementation boundary:** The current MATMA Python and PHP tools select and report verification paths but **do not themselves run tests or enforce the regression gateway**. The application's runner and CI/deployment workflow must carry out that requirement.

#### Rule 7 — Bifurcated Directory Topology (Mirrored vs. Process-Oriented)

MATMA divides test organization into two categories.

**Source-mirrored, class-centric artifacts:**

~~~text
tests/unit/mirror/
tests/interaction/mirror/
tests/mocks/mirror/
tests/mirror/**/*.auto.yaml
~~~

**Process-oriented, non-mirrored tests:**

~~~text
tests/business/
tests/regression/
~~~

**Why:** Unit, interaction, mock, and manifest artifacts have a deterministic relationship with source targets. Business workflows and end-to-end regressions span multiple components and should instead be organized by capability, process, feature, or user journey.

### 4. Four verification tiers and their boundaries

The central distinction is **which components are real and where mocking is permitted**.

| Tier | Real components | Mocked components | Purpose |
| --- | --- | --- | --- |
| **Unit** | One class under test | Every collaborator and external interaction | Isolate class behavior |
| **Interaction** | Exactly two selected collaborating classes | All other downstream collaborators | Verify the contract between the real pair |
| **Business** | Internal domain and workflow classes | External/infrastructure services at the boundary | Verify real internal business processes |
| **Regression** | Full application and participating services | None | Verify real-system behavior and integrity |

Unit testing supplies the narrowest diagnostic boundary. Pairwise interaction testing checks the contract between two real collaborators. Business testing verifies multi-step internal behavior while controlling infrastructure. Regression testing verifies complete behavior with real data and participating services. **These tiers provide complementary evidence, not interchangeable forms of testing.**

### 5. Deterministic structural mirroring

The original class-based blueprint illustrates the relationship between source files and testing artifacts:

~~~text
<source_root>/
└── core/
    └── document_parser.<ext>

tests/
├── unit/mirror/core/
│   └── test_document_parser.<ext>
├── interaction/mirror/core/
│   └── test_document_parser_interaction.<ext>
├── mocks/mirror/core/
│   └── mock_document_parser.<ext>
├── mirror/core/
│   └── document_parser.auto.yaml
├── business/
│   └── test_document_ingestion_workflow.<ext>
└── regression/
    └── test_end_to_end_pipeline.<ext>
~~~

The first four verification artifacts are resolved from source identity. Business and regression tests are deliberately independent of source mirroring. **Actual filenames follow each implementation's accepted naming convention:** the Python module example in Rule 1 and the PHP PSR-4 example in Section 9 illustrate the native forms.

### 6. Persisted dependency and reverse-dependency analysis

MATMA provides an ahead-of-time static indexer. It inspects source Abstract Syntax Trees (ASTs), identifies supported outbound dependencies, builds a dependency graph, reverses those relationships, and writes generated YAML manifests under `tests/mirror/`.

Consider this dependency chain:

~~~text
RagController
     |
     v
SemanticChunker
     |
     v
DocumentParser
~~~

If `DocumentParser` changes, `SemanticChunker` is a direct dependent and `RagController` is an indirect dependent. The source target's manifest records references to its unit, interaction, and mock artifacts, as well as dependencies and precomputed reverse dependents grouped by impact depth.

**Why persist the graph?** Coding agents frequently revisit impact questions while implementing and debugging changes. Indexing once and reading the stored relationships avoids reparsing source ASTs and reconstructing the graph for every impact query.

The optimization concerns **dependency selection**, not a guarantee that the entire command is constant-time. Current implementations read a target manifest and shared index metadata and also hash/stat indexed source files to validate freshness. A missing or stale index requires explicit regeneration.

Generated manifests must not be hand-edited. The existing implementations protect MATMA-owned generated YAML, preserve user-authored files, and report unsafe or stale metadata rather than silently returning misleading selections. Static analysis cannot fully capture dynamic imports, reflection, runtime injection, or other unresolved relationships; these limits need diagnostics and additional workflow verification.

### 7. Progressive verification through impact levels

The `--level` option selects an **inclusive reverse-dependency radius** for class-centric verification.

| Level | Intended scope |
| --- | --- |
| `0` | Unit verification for the target |
| `1` | Level 0 plus relevant interaction tests and directly dependent targets |
| `2+` | Previous levels plus additional transitive dependents within the requested radius |

Selections are deterministic, sorted, and deduplicated. The meaning of dependency edges follows each implementation's accepted ADR: Python distinguishes proven symbol usage from import-only relationships, conservatively including import-only dependents at Level 2; PHP uses its accepted actual-reference rules.

**Business and regression tests are separate tiers**, not class-mirrored tests inferred from a higher `--level`. In the current implementations, developers can register relevant business and regression workflows explicitly in `tests/matma-verification.yaml`. Impact analysis reports these registrations separately without silently executing them.

### 8. MATMA development operations

The architecture defines four CLI operations:

| Operation | Responsibility |
| --- | --- |
| `validate` | Analyze source structure and the applicable language-specific mapping conventions |
| `index` | Parse ASTs, build the dependency graph, calculate reverse dependencies, and persist manifests |
| `scaffold` | Generate missing mirrored unit/interaction test and mock starters, plus metadata |
| `impact` | Read persisted impact metadata to select affected class-centric tests |

**Validation** checks the rules applicable to the implementation. Python uses module-based source identity and does not reject valid multi-class modules; PHP validates its own native class-file and PSR-4 conventions.

**Indexing** refreshes the graph after relevant source or structural changes. The initial implementations rebuild the full indexed graph to keep reverse dependents consistent.

**Scaffolding** creates only missing testing artifacts. The current Python and PHP implementations deliberately generate **failing test placeholders** until developers or agents author meaningful assertions; existing test and mock files are not overwritten.

**Impact analysis** selects existing test paths and reports missing tests and stale index errors. It does not reparse ASTs or execute the tests. The project's native runner—such as `python -m pytest` or `php artisan test`—performs execution.

### 9. Language-specific architecture decisions

MATMA defines the shared testing methodology and verification boundaries. Its language implementations preserve their accepted source naming and testing-framework conventions rather than imposing the same file structure on every ecosystem.

#### MATMA Python — module-based identity

**Accepted PY-ADR-01: the source module is the atomic target, not the class.** A Python file may declare multiple classes, synchronous and asynchronous functions, and methods. MATMA Python maps each testable module to one unit file, one interaction file, one centralized mock helper, and one manifest. It retains the existing `src/`, flat, or configured multi-root layout.

~~~text
src/acme/pricing.py
tests/unit/mirror/src/acme/test_pricing.py
tests/interaction/mirror/src/acme/test_pricing_interaction.py
tests/mocks/mirror/src/acme/mock_pricing.py
tests/mirror/src/acme/pricing.auto.yaml
~~~

The implementation uses Python's `ast`, PyYAML, pytest, and `unittest.mock`. The exception to Rule 1 concerns **structural mapping granularity**, not an exception to unit, pairwise, business, or regression isolation requirements.

#### MATMA PHP — native class-file and PSR-4 mapping

MATMA PHP follows Laravel's PascalCase filenames, PSR-4 namespaces, and existing source structure.

~~~text
app/Services/DocumentParser.php
tests/unit/mirror/Services/DocumentParserTest.php
tests/interaction/mirror/Services/DocumentParserInteractionTest.php
tests/mocks/mirror/Services/MockDocumentParser.php
tests/mirror/Services/DocumentParser.auto.yaml
~~~

The implementation uses `nikic/php-parser`, Symfony YAML, Laravel Artisan commands, and PHPUnit-compatible scaffolding. It does not rename or reorganize application source to follow the blueprint's illustrative snake_case filenames.

| Property | MATMA Python | MATMA PHP |
| --- | --- | --- |
| Atomic mirror identity | Source module/file | Class/file |
| Multiple classes in one source file | Permitted | Restricted by accepted PHP structural rules |
| Mirroring convention | Native Python module paths | Native PascalCase / PSR-4 |
| AST analysis | Python `ast` | `nikic/php-parser` |
| Mock helpers | `unittest.mock` | PHPUnit-compatible mocks |
| Native test runner | pytest | Laravel / PHPUnit |
| Dependency metadata | Generated YAML | Generated YAML |

See the [Python architecture decisions](https://github.com/rzepeda/matma-py/blob/main/AIDocumentation/ARCHITECTURE_DECISIONS.md) and [PHP architecture decisions](https://github.com/rzepeda/matma-php/blob/main/AIDocumentation/ARCHITECTURE_DECISIONS.md) for the language-specific contracts.

### 10. Benefits for autonomous coding agents

The architectural decisions are intended to provide:

- **Lower context consumption:** load relevant source, mock, test, and dependency artifacts rather than repeatedly exploring the repository.
- **Reduced discovery overhead:** derive mirrored artifact paths from source identity instead of searching for companions.
- **Efficient impact queries:** reuse precomputed reverse dependencies rather than rebuilding the source dependency graph during each selection.
- **Precise failure diagnosis:** keep unit and pairwise tests bounded by the exact real-versus-mock rules; distinguish those failures from workflow and full-system failures.
- **Verification proportional to a change:** grow class-centric test selection according to dependency impact while preserving distinct business and regression responsibilities.

These are optimization objectives and expected benefits, **not guaranteed token savings, fixed performance ratios, or proof that selected tests passed**. Actual results depend on the project, dependency graph, test quality, and execution environment.

### 11. Responsibilities and limitations

Adopting MATMA requires maintaining the accepted source/test mappings and test-isolation boundaries:

- **Mock synchronization:** public-interface changes require corresponding updates to centralized mocks and relevant pairwise tests.
- **Tier integrity:** unit tests isolate every collaborator; pairwise tests keep exactly two selected real collaborators; business tests retain real internal logic with mocked service boundaries; regression tests use real participating services.
- **Index freshness:** regenerate manifests after relevant source or dependency changes; do not manually edit generated YAML.
- **Honest diagnostics:** static analysis has limits, and missing tests, unresolved dependencies, and stale data must not be concealed.
- **Real verification:** scaffolding is not test coverage; selecting paths is not executing tests. The native runner executes assertions.
- **Regression gateway:** the methodology requires real-data, real-service verification before merge or deployment; enforcement belongs to the application's CI/deployment process, not the present index/impact commands.

### 12. Conclusion

MATMA's seven rules define a controlled progression of verification: **one real class in unit testing, two selected real collaborators in interaction testing, real internal business classes with mocked infrastructure in workflow testing, and complete real-service, real-data verification in regression testing**.

Deterministic mirroring makes class-centric test and mock artifacts discoverable. Centralized mock registries reduce duplication and context overhead. Persisted reverse dependencies support focused, change-aware selection without repeated AST graph construction.

Together, these decisions aim to make software testing and change verification **deterministic, context-efficient, and diagnostically precise** for autonomous coding agents while preserving the system-level evidence required before release.

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

Phase 6 did **not** tag, license, or publish the package to PyPI.
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
