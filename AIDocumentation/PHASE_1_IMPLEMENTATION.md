# MATMA Python — Phase 1 Package and CLI Foundation

**Status:** Phase 1 implemented; 32 local pytest checks passed on Python 3.13.5 and **6/6 GitHub CI jobs passed** on Python 3.11–3.13 across Linux and Windows ([verified CI run](https://github.com/rzepeda/matma-py/actions/runs/42390809898)). Follow [TASKS.md](TASKS.md) for acceptance status.

## Deliverables

- `pyproject.toml`: `matma-py` installable package (`0.1.0.dev0`, not a release), Python >=3.11, PyYAML, setuptools build, development extras, and `matma-indexer = "matma.cli:main"`.
- `src/matma/__init__.py`, `src/matma/__main__.py`, `src/matma/cli.py`: Python module and installed CLI entry points with four commands.
- CLI option parsing with stable text, JSON, YAML output; `--source-root/-s`, `--tests-root/-t`, `--target/-f`, `--format/-o`, plus command-specific `--scaffold/-S`, `--check/-c`, `--level/-l`.
- `tests/unit/mirror/test_cli.py`: command/flag/format/validation and no-work checks.
- `tests/interaction/mirror/test_entrypoint.py`: real subprocess Python module command exit/format behavior.
- `tests/business/test_consumer_install.py`: isolated no-network `pip --target` installations of the MATMA package and a real sample consumer, entry-point discovery, command behavior, and two legitimate pytest consumer tests.
- `.github/workflows/ci.yml`: initial Ubuntu/Windows matrix with Python 3.11, 3.12 and 3.13; install, entry point, pytest and pip dependency checks.
- `README.md` and `.gitignore`: accurate Phase 1 readiness, developer usage, and selective future generated-manifest exclusion.

## Phase 1 command contract

Commands exist but **none of the AST, graph, scaffold or impact engines exists yet**. All currently return `not_implemented` / exit `2` on valid command invocation:

```bash
matma-indexer validate --check --format json
matma-indexer index --format json
matma-indexer scaffold --target src/example/pricing.py --format json
matma-indexer impact --target src/example/pricing.py --level 2 --format json
```

All commands share `command`, `status`, `message`, `exit_code`, `options`. Invalid options and missing `impact --target` return `invalid_options` / exit `64`. Help returns `0`. The output contract is intended for agents as well as human developers. No command modifies a project or executes pytest yet. Correct Phase 1 behavior is a clear nonzero unimplemented result, **not a fake green test**.

## Local verification

```bash
python -m pip install -e . --no-build-isolation --no-deps
python -m pytest -q
matma-indexer --help
python -m matma validate --check --format json  # expected exit 2
python -m compileall -q src tests
```

Local recorded result: **32 passed**; the isolated consumer fixture performed package/consumer installations and ran **2 consumer tests**. The local environment's unrelated package requirements can cause `pip check` to report global-environment conflicts; the CI check runs in a clean setup-python environment.

## Boundaries and follow-up

- The current package is intentionally **not** an AST analyzer, indexer, generator or test selector.
- Phase 2 implements Python module inventory, symbol discovery, naming/mirror mapping and structural validation without one-class-per-file enforcement.
- Phase 3 implements typed dependency edges and Level 2 import-only acceptance.
- Phase 4 implements honest failing mirrored test scaffolds and mock factories.
- Phase 5 implements manifest-only impact selection and explicit business/regression registration.
- Phase 6 verifies cross-platform robustness, benchmark and release readiness.
- The six-job matrix is CI-verified. Feature branches are verified through pull requests; the push event targets `main` only to avoid duplicate CI runs per feature commit.

## Cross-platform CI fix

The first GitHub matrix exposed a real Python 3.12+ packaging nuance: those runner environments did not provide `setuptools` in the execution environment. The consumer smoke test deliberately uses `pip --no-build-isolation --no-index`, so `setuptools>=69` is an explicit **development dependency** to make the package wheel build reproducible without fetching packages during the test. The package still uses normal isolated PEP 517 builds for users.
