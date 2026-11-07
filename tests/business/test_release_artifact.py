"""Build the actual package wheel and inspect its installable contents."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]


def test_wheel_build_contains_cli_and_all_four_engines(tmp_path: Path):
    result = subprocess.run([sys.executable, "-m", "build", "--wheel", "--no-isolation",
                             "--outdir", str(tmp_path)], cwd=ROOT,
                            check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    wheels = sorted(tmp_path.glob("matma_py-*.whl"))
    assert len(wheels) == 1
    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        assert {
            "matma/__init__.py", "matma/__main__.py", "matma/cli.py",
            "matma/analysis/project.py", "matma/indexing/graph.py",
            "matma/scaffolding/engine.py", "matma/impact/reader.py",
        } <= names
        assert not any(name.startswith("tests/") or name.startswith("benchmarks/")
                       for name in names)
        entries = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        assert len(entries) == 1
        assert "matma-indexer = matma.cli:main" in wheel.read(entries[0]).decode("utf-8")
