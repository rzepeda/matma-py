"""Install the real package and consumer into an isolated target directory.

Uses the already-installed build backend, no network, and tests the installed
entrypoint metadata and pytest consumer workflow rather than a mocked setup.
"""

from __future__ import annotations

import json
import os
import shutil
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
    assert result.returncode == 0, result.stdout + result.stderr
    validate = json.loads(result.stdout)
    assert validate["status"] == "validated"
    assert validate["summary"]["parsed_files"] == 2
    assert validate["module_to_source"]["example_app.pricing"] == "src/example_app/pricing.py"

    # A genuine installed consumer runs its existing tests independently.
    consumer_tests = _run("-m", "pytest", "-q", "tests", cwd=CONSUMER, env=env)
    assert consumer_tests.returncode == 0, consumer_tests.stdout + consumer_tests.stderr
    assert "2 passed" in consumer_tests.stdout

    # Use a copy of the installed consumer's source to verify the Phase 4
    # scaffold workflow without modifying tracked fixture files.
    consumer_work = tmp_path / "scaffold-consumer"
    shutil.copytree(CONSUMER / "src", consumer_work / "src")
    scaffold = _run("-m", "matma", "scaffold", "--format", "json", cwd=consumer_work, env=env)
    assert scaffold.returncode == 0, scaffold.stdout + scaffold.stderr
    output = json.loads(scaffold.stdout)
    assert output["status"] == "scaffolded"
    assert len(output["scaffolds"]["created"]) == 3
    assert (consumer_work / "tests/mirror/src/example_app/pricing.auto.yaml").is_file()

    generated = consumer_work / "tests/unit/mirror/src/example_app/test_pricing.py"
    assert generated.is_file()
    failing = _run("-m", "pytest", "-q", str(generated), cwd=consumer_work, env=env)
    assert failing.returncode == 1, failing.stdout + failing.stderr
    assert "MATMA: implement" in failing.stdout
    assert "failed" in failing.stdout

    # Phase 5: the installed consumer reads persisted impact metadata without
    # running generated pytest placeholders or changing source files.
    selected = _run("-m", "matma", "impact", "--target", "example_app.pricing",
                    "--level", "1", "-o", "json", cwd=consumer_work, env=env)
    assert selected.returncode == 0, selected.stdout + selected.stderr
    impact = json.loads(selected.stdout)
    assert impact["status"] == "impact_selected"
    assert impact["tests"]["unit"] == ["tests/unit/mirror/src/example_app/test_pricing.py"]
    assert impact["tests"]["interaction"] == ["tests/interaction/mirror/src/example_app/test_pricing_interaction.py"]
    assert impact["tests"]["missing"] == []
