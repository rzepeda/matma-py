"""Stable MATMA command-line surface for coding agents and human developers.

The command implementations are deliberately unavailable during Phase 1.
They return exit code 2 instead of pretending an index/scaffold exists.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
from collections.abc import Sequence
from typing import Any

import yaml

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_NOT_IMPLEMENTED = 2
EXIT_USAGE = 64

COMMAND_PHASES = {
    "validate": (2, "AST validation"),
    "index": (3, "dependency indexing"),
    "scaffold": (4, "test and mock scaffolding"),
    "impact": (5, "impact selection"),
}


class UsageError(Exception):
    """A CLI usage problem, distinct from unfinished engines."""


class ArgumentParser(argparse.ArgumentParser):
    """Preserve machine-readable errors rather than exiting inside argparse."""

    def error(self, message: str) -> None:
        raise UsageError(message)


def _non_empty(value: str) -> str:
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("must not be empty")
    return value


def _non_negative(value: str) -> int:
    try:
        integer = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from exc
    if integer < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return integer


def _root(value: str) -> str:
    """Normalize path spelling only; never resolve paths or touch the host FS."""
    text = _non_empty(value).replace("\\", "/")
    return posixpath.normpath(text)


def make_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="matma-indexer",
        description="MATMA Python: deterministic testing mirrors and impact selection",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=ArgumentParser)

    for command, (phase, description) in COMMAND_PHASES.items():
        p = subparsers.add_parser(
            command,
            help=f"{description} (engine planned for Phase {phase})",
            description=f"{description}: not implemented until Phase {phase}",
        )
        p.add_argument("-s", "--source-root", type=_root, default="src", help="production source root (default: src)")
        p.add_argument("-t", "--tests-root", type=_root, default="tests", help="test root (default: tests)")
        p.add_argument("-o", "--format", choices=("text", "json", "yaml"), default="text", help="result format")

        if command in ("index", "scaffold", "validate", "impact"):
            p.add_argument("-f", "--target", type=_non_empty, help="source module path or qualified target")
        if command == "index":
            p.add_argument("-S", "--scaffold", action="store_true", help="also generate missing tests (Phase 4)")
        if command == "validate":
            p.add_argument("-c", "--check", action="store_true", help="strict structural audit (Phase 2)")
        if command == "impact":
            p.add_argument("-l", "--level", type=_non_negative, default=0, help="inclusive impact level (default: 0)")
    return parser


def _format_requested(argv: Sequence[str]) -> str:
    """Honor explicitly requested JSON/YAML even if another flag is invalid."""
    for index, arg in enumerate(argv):
        if arg in ("--format", "-o") and index + 1 < len(argv):
            candidate = argv[index + 1]
        elif arg.startswith("--format="):
            candidate = arg.partition("=")[2]
        elif arg.startswith("-o="):
            candidate = arg.partition("=")[2]
        else:
            continue
        if candidate in ("json", "yaml"):
            return candidate
    return "text"


def _result(command: str | None, status: str, message: str, exit_code: int, options: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": command,
        "status": status,
        "message": message,
        "exit_code": exit_code,
        "options": options,
    }


def _display(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=False))
    elif output_format == "yaml":
        print(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), end="")
    else:
        cmd = payload["command"] or "cli"
        print(f"matma:{cmd} [{payload['status']}] {payload['message']} (exit {payload['exit_code']})")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and return a meaningful process exit status.

    Phase 1 never writes files, executes pytest, parses a project AST or builds
    graph manifests. Later phases replace the respective command handlers.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    parser = make_parser()
    try:
        namespace = parser.parse_args(args)
    except UsageError as exc:
        command = next((arg for arg in args if arg in COMMAND_PHASES), None)
        payload = _result(command, "invalid_options", str(exc), EXIT_USAGE, {})
        _display(payload, _format_requested(args))
        return EXIT_USAGE

    options = {key: value for key, value in vars(namespace).items() if key != "command"}
    if namespace.command == "impact" and not namespace.target:
        payload = _result("impact", "invalid_options", "--target/-f is required for impact", EXIT_USAGE, options)
        _display(payload, namespace.format)
        return EXIT_USAGE

    phase, description = COMMAND_PHASES[namespace.command]
    payload = _result(
        namespace.command,
        "not_implemented",
        f"{description} is not available yet (planned for Phase {phase}); no work performed",
        EXIT_NOT_IMPLEMENTED,
        options,
    )
    _display(payload, namespace.format)
    return EXIT_NOT_IMPLEMENTED
