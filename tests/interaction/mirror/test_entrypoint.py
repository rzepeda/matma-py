"""Verify the CLI shell as a subprocess, including process exit status."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def invoke(*arguments: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "matma", *arguments],
        cwd=cwd or ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


@pytest.mark.parametrize("command", ["impact"])
def test_python_module_entrypoint_does_not_claim_completed_engine(command: str) -> None:
    args = [command, "-o", "json"]
    if command == "impact":
        args += ["--target", "src/acme/pricing.py"]
    result = invoke(*args)
    assert result.returncode == 2, result.stderr
    output = json.loads(result.stdout)
    assert output["command"] == command
    assert output["status"] == "not_implemented"


def test_python_module_entrypoint_invalid_options() -> None:
    result = invoke("impact", "--target", "pricing", "--level", "-2", "-o", "json")
    assert result.returncode == 64
    assert json.loads(result.stdout)["status"] == "invalid_options"


def test_python_module_entrypoint_help() -> None:
    result = invoke("--help")
    assert result.returncode == 0
    assert "validate" in result.stdout
    assert "impact" in result.stdout
