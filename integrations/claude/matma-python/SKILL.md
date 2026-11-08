---
name: matma-python
description: Use MATMA in a Python repository to index dependencies, scaffold pytest tests and mocks, or select impacted tests after code changes.
---

# MATMA Python — Claude Code skill

Use this skill when asked to assess Python test impact, add module-mirrored
unit/interaction tests, create safe unittest.mock starters, or plan pytest
runs for a code change. MATMA is a local CLI tool, **not** a Claude native
analysis engine. Follow `references/MATMA_CLI.md` for exact commands,
output fields and errors.

## Procedure

1. Work from the **consumer Python repository root**. Inspect its
   `pyproject.toml`, source roots, existing pytest layout and developer
   environment. Do not reorganize production code or assume one class per file.
2. Check whether `python -m matma --help` works in the active Python 3.11+
   environment. If absent, explain how to install the tool from the MATMA
   repo; do not silently install from the network or into production.
3. Run `python -m matma validate --check --format json`. Correct unsafe
   layouts/syntax issues before indexing. If source roots are custom, use
   the existing `[tool.matma] source_roots` config or explicit consistent flags.
4. Run `python -m matma index --format json` when a fresh dependency graph is
   needed. Check `status == "indexed"` and review warnings. The generated
   manifests are **not** authored tests.
5. If asked to **write tests**, generate narrowly for the requested source:
   `python -m matma scaffold --target pkg.module --format json`. Inspect
   generated and pre-existing files, implement real assertions for the
   relevant callable symbols in **both** tiers, and preserve authored files.
   Never disguise the generated `pytest.fail` placeholders as passing tests.
6. If asked to **assess impact**, run
   `python -m matma impact --target pkg.module --level 2 --format json`.
   Use `tests.unit`, `tests.interaction` and explicitly registered workflows.
   Report `tests.missing`, dynamic limitations and unresolved references.
   Reindex if the reader reports a missing/stale index; don't try to
   reconstruct affected tests manually as if MATMA returned them.
7. Only if asked to execute tests, or if the development work requires
   validation, run `python -m pytest` on existing selected paths and
   registered business/regression files. Do not invoke a full test suite
   containing untouched failing scaffolds and present the failures as bugs.
8. Report exact commands, changes, affected test paths, missing paths,
   warnings and **observed** test results. Do not claim tests ran when
   only `impact` was used. Keep git changes small and reviewable.

## Nonnegotiable checks

- **Module** is the atomic unit: one unit file and one interaction file for a
  testable `.py` source module, however many classes/functions it contains.
- A referenced import contributes **Level 1**; an unused import still
  contributes **Level 2** (inclusive selection).
- MATMA indexing and impact do not execute consumer code or pytest.
- `scaffold` creates missing files only; no overwrites, no auto-fixing
  user-owned manifests, no deleting handwritten tests.
- Dynamic imports and reflection need explicit additional verification.

For command details and examples, open `references/MATMA_CLI.md`.
