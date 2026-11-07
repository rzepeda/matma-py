# MATMA Python — Phase 4: Pytest and unittest.mock Scaffolding

**Status:** Implemented locally; GitHub Actions verification pending. This document will be updated with a passing run before marking Phase 4 complete.

**Architecture:** [ADR-001](ARCHITECTURE_DECISIONS.md) and [implementation checklist](TASKS.md). This implementation builds on Phase 3's typed, full-project graph. It creates only missing, user-owned pytest and mock helper files; the source module remains the atomic unit.

## Components

| File | Purpose |
| --- | --- |
| `src/matma/scaffolding/templates.py` | Pure, deterministic pytest placeholders and lazy `unittest.mock` factories |
| `src/matma/scaffolding/writer.py` | Scope selection, direct-dependency mock planning, path preflight, exclusive file creation |
| `src/matma/scaffolding/engine.py` | Single full-AST-index + scoped scaffold orchestration, with explicit partial-error diagnostics |
| `src/matma/scaffolding/__init__.py` | Public `scaffold_project()` entry point |
| `src/matma/cli.py` | Enables `scaffold` and `index --scaffold`; `impact` stays an unimplemented Phase 5 command |

## Module-first test template contract

- Every eligible Python source file maps to **one** pytest unit module and **one** pytest interaction module. Multiple classes, functions, async functions and methods per source file are supported without requiring a class-per-file rule.
- Each addressable top-level function, async function, class, nested class accessible through class qualification, ordinary method and async method receives its **own** deterministic failing test function in **both** tiers. Identifiers are human-readable, collision-resistant and stable under repeated generation.
- Function-local definitions that cannot be addressed by import path remain in the AST inventory and are **explicitly listed as omitted** in the generated test file and scaffold result; their behavior must be covered through the owning callable's assertions. Empty/side-effect-only source modules get a single failing module-behavior placeholder in each tier.
- Generated tests call `pytest.fail("MATMA: implement ...")` until a developer adds real assertions; they are **not** skipped, xfailed, marked passing or auto-executed. Async callable placeholders are ordinary pytest functions so no mandatory async-test plugin is imposed.
- Existing authored tests are left intact even if they don't follow scaffold naming; MATMA never rewrites them to add new symbols or claims they are complete. Changes to production symbols should be reviewed by the developer/agent through the indexed AST inventory.

Example for `src/acme/pricing.py`:

```text
tests/unit/mirror/src/acme/test_pricing.py
tests/interaction/mirror/src/acme/test_pricing_interaction.py
tests/mocks/mirror/src/acme/mock_pricing.py
tests/mirror/src/acme/pricing.auto.yaml
tests/mirror/.index.auto.yaml
```

The generated tests have no runtime imports of the application module; they fail honestly before any application behavior is executed. The developer decides how to import, inject, call and assert the real module in each tier.

## Mock factories

- One centralized mock helper file per eligible source module, containing `create_autospec()` factories for statically addressable classes, top-level functions and async functions, and a reusable `patch_at_lookup(consumer_module, bound_name, autospec=True)` patch helper.
- Class factories use `create_autospec(original_class, instance=True)`; function factories use `create_autospec(original_function)` and naturally provide async-aware mocks for async functions.
- A mock helper imports the application module **only if a test calls a factory**, not when MATMA analyzes or generates files. Such a call can execute consumer import side effects or inspect descriptors; that limitation is documented and developer-controlled.
- Patching takes a consumer module and its bound name rather than assuming the original definition module is the patch target. A test must explicitly configure return values/side effects and assertions. No fabricated behavior is considered verified.
- Only statically identified *internal* direct dependency modules get additional helper files for a targeted scaffold. Non-testable package initializers are not treated as mockable test units. External/unresolved or dynamic imports are reported for explicit handling rather than automatically mocked.

## Target scope and index semantics

```bash
matma-indexer scaffold --format json             # all eligible source modules
matma-indexer scaffold --target pkg.pricing -o json  # just this module's tests + direct dependency mocks
matma-indexer index --scaffold --target pkg.pricing -o json
```

- All three workflows parse the **full project** and build its complete reverse graph. When a target is specified, it limits test and mock generation only—not graph indexing.
- `scaffold` returns `scaffolded` on success, with `scaffolds.created|existing|selected_sources|mock_sources|omitted_symbols|warnings`. `index --scaffold` uses the **same engine**, retaining the `indexed` success status and index metadata plus the scaffold report.
- `scaffold --target` creates the target module's unit/interaction files and mock helper, plus **mock helpers only** for its immediate testable internal dependencies. It does not generate unrelated dependency or dependent tests.
- The pure `index` command continues to write only the generated YAML index. The `validate` command stays read-only; `impact` remains exit code `2` (not implemented) until Phase 5.

## Safe, non-destructive writing

1. The AST and path validation must pass before any index/test writes. An invalid target or source syntax fails explicitly.
2. Test/mock plans are generated in memory and **all** test/mock destinations are preflighted *before* the manifest indexer writes anything. A directory occupying a test filename, path outside its tier, case-colliding output or symlinked destination fails without overwriting or creating tests.
3. The Phase 3 manifest writer independently preflights **all** `.auto.yaml` destinations and rejects user-owned YAML/symlinks before its writes.
4. Test and mock files are created through OS-level exclusive creation (`O_CREAT | O_EXCL`; `O_NOFOLLOW` where supported). Any existing authored file is preserved byte-for-byte, including modified generated stubs and CRLF files.
5. Repeated generation is idempotent for existing pytest/mock files, does not change their modification times, and reports them under `scaffolds.existing`.
6. A late filesystem error can result in partial newly created files and/or manifests; the result reports known output and **does not claim transaction/rollback guarantees**. No automatic cleanup deletes user-owned files.

Test/mock starters become user-owned as soon as created. The `tests/mirror/**/*.auto.yaml` manifests alone remain generated and Git-ignored.

## Verification and limitations

Acceptance tests cover:
- Class/function/async/method fixtures in both tiers, including uniquely named failing placeholders and omitted function-local definitions.
- Real subprocess consumer: `index -> scaffold -> python -m pytest` explicitly fails for generated test placeholders; existing consumer-authored pytest tests remain independently executable.
- Direct dependency-only mock files with full index persistence, plus lazy runtime spec loading and actual `unittest.mock` semantics.
- Repeated generation, manual test changes/CRLF preservation, directory and symlink conflicts, unsafe path/casefold collision, preflight before manifests and read-only validation.
- Full package and consumer suite on Python 3.11, 3.12 and 3.13 across Linux and Windows (CI matrix; pending verification).

**Not in scope:** Phase 5 impact query and selected test execution, comprehensive Python dynamic import analysis, generating passing business/regression tests, adding a pytest plugin, publishing a release. Generated failing tests demonstrate missing work, not verified application correctness.
