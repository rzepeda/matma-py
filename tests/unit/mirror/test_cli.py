"""Unit verification of the Phase 1 CLI argument/output contract."""

from __future__ import annotations

import json

import pytest
import yaml

from matma.cli import COMMAND_PHASES, EXIT_NOT_IMPLEMENTED, EXIT_USAGE, main, make_parser


@pytest.mark.parametrize("command", ["index", "scaffold", "impact"])
def test_every_command_shell_reports_unimplemented(command: str, capsys: pytest.CaptureFixture[str]) -> None:
    argv = [command, "--format", "json"]
    if command == "impact":
        argv += ["--target", "src/acme/pricing.py"]

    exit_code = main(argv)
    output = json.loads(capsys.readouterr().out)
    assert exit_code == EXIT_NOT_IMPLEMENTED
    assert output["command"] == command
    assert output["status"] == "not_implemented"
    assert output["exit_code"] == EXIT_NOT_IMPLEMENTED
    assert "no work performed" in output["message"]
    assert output["options"]["format"] == "json"


@pytest.mark.parametrize("command", COMMAND_PHASES)
def test_all_commands_have_source_and_tests_roots(command: str) -> None:
    args = [command]
    if command == "impact":
        args += ["--target", "src/acme/pricing.py"]
    parsed = make_parser().parse_args(args)
    assert parsed.source_root == "src"
    assert parsed.tests_root == "tests"
    assert parsed.format == "text"


def test_index_scaffold_flag_is_retained(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["index", "-S", "-s", r"src\acme", "-t", "tests", "-o", "json"]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data["options"]["scaffold"] is True
    assert data["options"]["source_root"] == "src/acme"


def test_validate_strict_flag_and_target(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "-c", "-f", "acme.pricing", "-o", "json"]) == 1
    opts = json.loads(capsys.readouterr().out)["options"]
    assert opts["check"] is True
    assert opts["target"] == "acme.pricing"


def test_impact_level_and_target(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["impact", "-l", "2", "-f", "src/acme/pricing.py", "-o", "json"]) == 2
    opts = json.loads(capsys.readouterr().out)["options"]
    assert opts["level"] == 2
    assert opts["target"] == "src/acme/pricing.py"


def test_yaml_result_is_valid_yaml(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scaffold", "-f", "acme.pricing", "-o", "yaml"]) == 2
    output = yaml.safe_load(capsys.readouterr().out)
    assert output["command"] == "scaffold"
    assert output["status"] == "not_implemented"
    assert output["options"]["target"] == "acme.pricing"


def test_text_result_includes_nonzero_status(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["index"]) == 2
    text = capsys.readouterr().out
    assert "matma:index [not_implemented]" in text
    assert "(exit 2)" in text


@pytest.mark.parametrize(
    "argv",
    [
        ["impact", "-o", "json"],
        ["impact", "-l", "-1", "--target", "mod", "-o", "json"],
        ["impact", "-l", "not-a-number", "--target", "mod", "-o", "json"],
        ["index", "--scaffold", "--unknown", "-o", "json"],
        ["validate", "--source-root", "", "-o", "json"],
        ["validate", "--target", " ", "-o", "json"],
        ["index", "--format", "xml", "--target", "mod", "-o", "json"],
    ],
)
def test_invalid_cli_arguments_report_exit_64(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(argv) == EXIT_USAGE
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "invalid_options"
    assert data["exit_code"] == EXIT_USAGE
    assert data["message"]


def test_without_command_is_an_explicit_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--format", "json"]) == EXIT_USAGE
    data = json.loads(capsys.readouterr().out)
    assert data["command"] is None
    assert data["status"] == "invalid_options"


@pytest.mark.parametrize("argv", [["--help"], ["index", "--help"], ["impact", "--help"]])
def test_help_is_successful(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as outcome:
        main(argv)
    assert outcome.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_no_command_mutates_the_consumer_project(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pricing.py").write_text("def a(): return 1\n", encoding="utf-8")
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    for cmd in COMMAND_PHASES:
        args = [cmd, "--source-root", "src", "--tests-root", "tests"]
        if cmd == "impact":
            args += ["--target", "src/pricing.py"]
        assert main(args) == (0 if cmd == "validate" else EXIT_NOT_IMPLEMENTED)
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert after == before
