# Set up MATMA Python and agent skills in an existing Python project

MATMA Python is a Python >=3.11 development tool. Its `matma-indexer` CLI is
fully implemented on the `main` branch of
[`rzepeda/matma-py`](https://github.com/rzepeda/matma-py). The package is still
version `0.1.0.dev0` and has **not** been published to PyPI.

## 1. Open the existing Python project and create a venv

Open a terminal at the **consumer project's root**, not the MATMA source root:

```bash
python -m venv .venv
```

Activate on Linux/macOS:

```bash
source .venv/bin/activate
```

Activate on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

If PowerShell activation is restricted, run `.venv\Scripts\python.exe` in place
of `python` in the commands below. Check that `python --version` is 3.11+.

## 2. Install MATMA and pytest in the development venv

```bash
python -m pip install "git+https://github.com/rzepeda/matma-py.git@main"
python -m pip install pytest
python -m matma --help
```

If the Git repository is private, authenticate your normal GitHub Git
credentials. If you already have a local MATMA checkout, you can instead use
`python -m pip install -e "/absolute/path/to/matma-py"` to avoid remote Git.
Pin a commit SHA rather than `main` for repeatable team builds. Do not add
MATMA to production runtime requirements solely for this workflow.

## 3. Validate the host project's layout

```bash
python -m matma validate --check --format json
```

The default is a `src/` project when present, otherwise a flat layout;
set nondefault roots in `pyproject.toml` or CLI flags:

```toml
[tool.matma]
source_roots = ["src", "plugins"]
```

```bash
python -m matma validate --check --source-root src --extra-source-root plugins -o json
```

## 4. Index dependencies, scaffold only requested tests

```bash
python -m matma index -o json
python -m matma scaffold --target pkg.service -o json
```

MATMA generates the full dependency index but creates unit/interaction test
starters only for the selected module. For `src/pkg/service.py`, expect:

```text
tests/mirror/.index.auto.yaml
tests/mirror/src/pkg/service.auto.yaml
tests/unit/mirror/src/pkg/test_service.py
tests/interaction/mirror/src/pkg/test_service_interaction.py
tests/mocks/mirror/src/pkg/mock_service.py
```

Replace each starter's deliberate `pytest.fail(...)` with meaningful
assertions. MATMA never overwrites an existing user-owned test or mock file.
**Running pytest immediately after scaffolding is expected to fail** until
you implement the test cases. MATMA does not run pytest automatically.

## 5. Find which tests are affected by a source change

After source files change, rerun `index` explicitly to ensure freshness:

```bash
python -m matma index -o json
python -m matma impact --target pkg.service --level 2 -o json
```

Impact is inclusive. Level 0 picks the target's unit tests, Level 1 adds
interaction/direct-use dependents, Level 2 includes import-only dependents and
transitive usage. The JSON `tests.unit` and `tests.interaction` lists contain
**existing** paths; `tests.missing` identifies absent tests.

When appropriate, run the selected existing test files yourself, e.g.:

```bash
python -m pytest -q tests/unit/mirror/src/pkg/test_service.py
```

Do not copy that illustrative filename if your module uses a different
path: rely on MATMA's JSON output. Dynamic imports and reflection may require
additional tests.

## 6. Register business and regression tests explicitly (optional)

Create `tests/matma-verification.yaml`:

```yaml
schema_version: 1
registrations:
  pkg.service:
    business:
      - tests/business/test_checkout.py
    regression:
      - tests/regression/test_issue_123.py
```

Only explicit, valid test-root `.py` paths are selected; MATMA doesn't infer or
run business tests.

## 7. Install platform skills in this Python project

With MATMA checked out, from any terminal directory:

```bash
python /path/to/matma-py/integrations/install_skills.py --project /path/to/your-python-project --platform all
```

This installs **three independent skills**, safe to use together:

```text
your-python-project/
├── .claude/skills/matma-python/
│   └── SKILL.md
└── .agents/skills/
    ├── matma-python-chatgpt/
    │   └── SKILL.md
    └── matma-python-antigravity/
        └── SKILL.md
```

Each directory also has its README and `references/MATMA_CLI.md`; the ChatGPT
skill adds `agents/openai.yaml` UI metadata. These install paths match
Claude Code, ChatGPT desktop/Codex and Google's Antigravity current formats.

You can install one platform with `--platform claude`, `--platform chatgpt`,
or `--platform antigravity`. The installer refuses to overwrite different
existing files, and supports `--dry-run`.

Ask your assistant to use the corresponding MATMA skill. In Claude Code,
`/matma-python` is an explicit invocation; in Codex use
`$matma-python-chatgpt`; in Antigravity refer to
`matma-python-antigravity` in your task.

**ChatGPT web note:** local workspace skills are directly usable with
ChatGPT desktop/Codex; an ordinary ChatGPT web chat does not discover your
local `.agents/skills` directory. For browser-wide use, package the workflow
as a supported plugin/skill integration, or provide the instructions manually.

## 8. Diagnostics

`missing_index`/`stale_index` → reindex. `invalid_target` → use a module,
qualified symbol or project-relative `.py` path present in the index.
`unsafe_output` → check symlinks, traversals and user-owned manifest conflicts
instead of force-overwriting. Exit 64 means invalid CLI arguments. Read JSON
`status` and diagnostics rather than guessing success from a file's presence.

**Security / distribution:** skill instructions are not an executable MATMA
installation. Review and commit them like any repository instructions.
No licensing or public package publication was authorized for MATMA; do not
assume otherwise.
