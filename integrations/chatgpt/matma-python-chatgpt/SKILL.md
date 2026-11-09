---
name: matma-python-chatgpt
description: Use MATMA in ChatGPT desktop or Codex on Python projects to generate pytest/mock starters and identify impacted tests from its dependency index.
---

# MATMA Python — ChatGPT desktop / Codex skill

Use when an engineering user asks to integrate MATMA with a Python
repository, create unit/interaction test scaffolds, inspect dependencies,
or find tests affected by source changes. Requires terminal or an equivalent
code-execution environment **with access to the consumer repository**.
Merely referencing this skill in an ordinary ChatGPT web chat does not
install a local CLI or grant filesystem access.

Read `references/MATMA_CLI.md` before preparing commands or editing tests.

## Task workflow

1. Find the consumer project root and inspect its current Python environment,
   source layout, test roots and `pyproject.toml`. Prefer working inside the
   project's virtual environment, Python >=3.11.
2. Confirm MATMA exists via `python -m matma --help`. If it is absent,
   explain the Git/local-checkout development installation and obtain
   authorization for any network installation; do not claim a PyPI release.
3. **Discovery:** `python -m matma validate --check -o json`. Review errors
   and any dynamic import warnings. MATMA supports flat, src and multi-root
   layouts; never enforce one class per source module.
4. **Fresh index:** `python -m matma index -o json`; ensure `status == indexed`
   before relying on the graph. No pytest tests are created by `index` alone.
5. **Scaffold only when requested:**
   `python -m matma scaffold -f pkg.module -o json`. Preserve any existing
   test/mock files. Inspect the generated tests in both tiers and replace
   `pytest.fail` with meaningful assertions before declaring coverage.
6. **Find affected tests:**
   `python -m matma impact -f pkg.module -l 2 -o json`. Read existing test
   paths and report missing ones. Respect the import-only **Level 2** rule,
   inclusive levels, explicit business/regression registry and limitations.
   If `stale_index`, rerun `index` and retry once; never report a stale result
   as current.
7. **Execute when authorized:** choose the existing selected file paths and
   registered paths, then call `python -m pytest` explicitly. Record the
   actual exit code, failing test IDs and what was fixed; do not claim
   success just because a selection JSON contains paths.
8. Summarize scope, new files, authored work, result paths, missing tests,
   unresolved dynamics and executed test outcomes.

## Safety rules

- MATMA doesn't run tests, and `impact` doesn't reparse Python AST.
- Full reverse graph is always rebuilt by `index` and `scaffold`, even when
  scaffolding is restricted to a target module.
- Existing tests belong to the developer. Never overwrite, delete or hide
  failing placeholders to obtain a green CI.
- Patch dependencies using `unittest.mock` at the consuming lookup site;
  autospec helpers are available in the generated mock file.
- Treat static analysis as conservative, not proof of all runtime behavior.

For output JSON schema and errors, see `references/MATMA_CLI.md`.
