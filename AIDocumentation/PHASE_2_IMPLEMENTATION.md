# MATMA Python — Phase 2: Read-only AST Discovery and Validation

**Status:** Implemented and CI-verified: **68 local pytest tests passed** (Python 3.13); **6/6 GitHub Actions jobs passed** on Python 3.11–3.13 across Linux/Windows ([run 42393367584](https://github.com/rzepeda/matma-py/actions/runs/42393367584)).  
**Architecture:** [ADR-001](ARCHITECTURE_DECISIONS.md).  
**Scope:** Inventory, symbol collection, deterministic mirror mapping and `validate`. This phase does **not** build the dependency graph, write YAML, scaffold tests/mocks, select impacted tests or execute pytest.

## Implementation components

- `src/matma/analysis/project.py`: root discovery, filesystem safety, sorted source inventory, Python-encoding-aware reading, AST syntax diagnostics, target lookup, and read-only inspection result.
- `src/matma/analysis/syntax.py`: `ast` inventory of classes, nested classes, methods, async functions/methods, nested functions, imports, type-only imports, aliases, static references, decorator/inheritance/annotation contexts, `__all__` and common dynamic-import warnings.
- `src/matma/analysis/resolver.py`: package-relative import resolution, module and symbol identities, package `__init__.py` re-exports, duplicate module diagnostics and explicit external/unresolved resolution without importing application code.
- `src/matma/analysis/paths.py`: predictable project-relative module, test, mock and manifest paths. One source **file** maps to one pair of mirrored test **files** (when testable), not one pair per class/function.
- `src/matma/cli.py`: completed `validate` engine, including `--check`, `--target`, `--extra-source-root`, and stable text/JSON/YAML output. Other three commands continue returning `not_implemented` / exit `2`.

## Source layouts and scope

Default source root selection: a valid `[tool.matma] source_roots` array from `pyproject.toml`, else setuptools package-find `where` when configured, else `src` if it exists, else project root (`.`). Explicit `--source-root` overrides inferred roots; repeatable `--extra-source-root` adds more. Source roots must remain within the current project. Overlapping roots are deduplicated and the deepest root determines the module's import identity. **Source-file paths retain the full project-relative path** (e.g. `src/acme/pricing.py`) to avoid collisions between different source roots.

Unwanted directories such as `tests`, `.venv`, `build`, `vendor`, caches and VCS directories are skipped; configured test roots are excluded from recursive discovery. Symlinked Python source files and source subdirectories are rejected with diagnostics and never traversed. Tests-root overlap and path traversal are rejected. Case-only path collisions are flagged for cross-platform safety. Projects are not renamed or rewritten.

Normal Python modules can define any number of classes and functions. An import-only/empty `__init__.py` is indexed as a package node but has no independent unit/interaction test path. A normal Python source module has one unit and one interaction mirror file; explicit test scaffolds arrive in Phase 4. Nested functions and methods remain individual symbols in the inventory for later coverage policy.

## Import and reference semantics

`ast.Import`, `ast.ImportFrom`, aliases, absolute/relative package imports, known internal source modules and statically identifiable re-exports are resolved without executing consumer modules. Internal imports carry `resolved_module`, `resolved_symbol` when known, and `resolved_source`; external/dynamic imports are not invented as internal edges. `TYPE_CHECKING` conditionals are marked type-only; syntactic references distinguish ordinary uses, annotations, decorators and inheritance. A warning identifies common runtime dynamic import patterns; this is **not** a complete dynamic analysis.

**Important boundary:** Recording resolved imports is **not** equivalent to computing or selecting transitive dependency impact. Phase 3 will distinguish actual symbol uses from import-only edges and ensure that an importer depending solely on a module import is selected by **Level 2** when that module changes.

## CLI examples

```bash
matma-indexer validate --check --format json
matma-indexer validate --source-root . --tests-root tests --format yaml
matma-indexer validate --source-root src --extra-source-root plugins --target acme.pricing --check
python -m matma validate -f src/acme/pricing.py -o text
```

Stable top-level fields: `command`, `status`, `message`, `exit_code`, `options`, `summary`, `target`, `files`, `module_to_source`, `symbol_to_source`, `diagnostics`. Module entries provide `source_file`, `source_root`, `module_name`, `is_package`, `testable`, `symbols`, `imports`, `references`, `dynamic_imports`, `explicit_exports`, `reexports` and `mirrors`. All lists and maps have deterministic ordering for identical source.

- Exit `0`: valid invocation; `validate` without `--check` may return reportable structural errors without failing.
- Exit `1`: invalid source-root/test-root conditions, or any structural error with `--check`.
- Exit `2`: unimplemented `index`, `scaffold` or `impact` engines.
- Exit `64`: invalid CLI syntax, flag value or missing required impact target.

Diagnostic entries have `code`, `severity`, `message`, `file`, `line`, `column`. Errors include syntax failures, unsafe roots/symlinks, source-case/module-identity collisions, invalid relative imports and invalid targets. External/unresolved imports are not silently converted into internal graph edges; common dynamic imports generate warnings.

## Tests and acceptance evidence

New unit fixtures cover: multiple classes/functions per module, nested and async definitions, `__init__` re-exports, `TYPE_CHECKING`, alias/relative imports, flat/custom/multi-root layouts, namespace packages, duplicate module identities, file/mirror naming, invalid source encodings/syntax, symlink safety, case collisions, path traversal, exclusions, stable repeated reads and unresolved references. Integration tests use **real subprocesses** for JSON/YAML/text, strict/non-strict exit behavior, unimplemented-command safety and zero generated files. The Phase 1 installed consumer test now proves `validate --check` succeeds and correctly resolves real consumer code.

P2-01 through P2-06 are marked complete after passing the exact Linux/Windows matrix above. Phase 3 dependency graph generation, Phase 4 scaffold generation and Phase 5 impact selection remain unimplemented.
