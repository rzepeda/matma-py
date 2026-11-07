"""Install the real package and consumer into an isolated target directory.

Uses the already-installed build backend, no network, and tests the installed
entrypoint metadata and pytest consumer workflow rather than a mocked setup.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONSUMER = ROOT / "tests" / "fixtures" / "consumer"


def _run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def test_installed_package_in_real_consumer(tmp_path: Path) -> None:
    target = tmp_path / "packages"
    target.mkdir()
    # Install both projects from local sources, with no dependency download.
    for project in (ROOT, CONSUMER):
        install = _run(
            "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation",
            "--target", str(target), str(project), cwd=CONSUMER,
        )
        assert install.returncode == 0, install.stdout + install.stderr

    env = os.environ.copy()
    env["PYTHONPATH"] = str(target)

    metadata = _run(
        "-c",
        "import importlib.metadata as md; "
        "ep = next(x for x in md.distribution('matma-py').entry_points "
        "if x.name == 'matma-indexer'); "
        "assert ep.value == 'matma.cli:main'; "
        "assert callable(ep.load()); "
        "import example_app; assert example_app.PriceCalculator",
        cwd=CONSUMER, env=env,
    )
    assert metadata.returncode == 0, metadata.stdout + metadata.stderr

    result = _run("-m", "matma", "validate", "--check", "-o", "json", cwd=CONSUMER, env=env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "not_implemented"

    # A genuine installed consumer runs its existing tests independently.
    consumer_tests = _run("-m", "pytest", "-q", "tests", cwd=CONSUMER, env=env)
    assert consumer_tests.returncode == 0, consumer_tests.stdout + consumer_tests.stderr
    assert "2 passed" in consumer_tests.stdout
