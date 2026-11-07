"""Stable MATMA Python CLI: validation, indexing and safe pytest scaffolding.

Phase 5 impact remains unavailable; no command executes consumer tests.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
from collections.abc import Sequence
from typing import Any

import yaml

from matma.analysis import inspect_project
from matma.indexing import index_project
from matma.scaffolding import scaffold_project

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
    """Invalid CLI arguments (exit 64)."""


class ArgumentParser(argparse.ArgumentParser):
    """Return machine-readable usage errors rather than exiting from argparse."""

    def error(self, message: str) -> None:
        raise UsageError(message)


def _non_empty(value: str) -> str:
    value = value.strip()
    if not value:
        raise argparse.ArgumentTypeError("must not be empty")
    return value


def _non_negative(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return parsed


def _root(value: str) -> str:
    return posixpath.normpath(_non_empty(value).replace("\\", "/"))


def make_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="matma-indexer", description="MATMA Python: deterministic testing mirrors and impact selection",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=ArgumentParser)
    for command, (phase, description) in COMMAND_PHASES.items():
        available = command in ("validate", "index", "scaffold")
        p = subparsers.add_parser(
            command,
            help=f"{description} ({'available' if available else f'planned for Phase {phase}'})",
            description=f"{description}: {'AST validation, index generation or scaffolding' if available else f'not implemented until Phase {phase}'}",
        )
        p.add_argument("-s", "--source-root", type=_root, default="src", help="production source root (default: src)")
        p.add_argument("-t", "--tests-root", type=_root, default="tests", help="test root (default: tests)")
        p.add_argument("--extra-source-root", type=_root, action="append", default=[],
                       help="additional production source root; may be repeated")
        p.add_argument("-o", "--format", choices=("text", "json", "yaml"), default="text", help="result format")
        p.add_argument("-f", "--target", type=_non_empty, help="source module path or qualified target")
        if command == "index":
            p.add_argument("-S", "--scaffold", action="store_true", help="also generate missing pytest and mock files")
        if command == "validate":
            p.add_argument("-c", "--check", action="store_true", help="strict structural audit (Phase 2)")
        if command == "impact":
            p.add_argument("-l", "--level", type=_non_negative, default=0,
                           help="inclusive impact level (default: 0)")
    return parser


def _format_requested(argv: Sequence[str]) -> str:
    for index, arg in enumerate(argv):
        if arg in ("--format", "-o") and index + 1 < len(argv):
            candidate = argv[index + 1]
        elif arg.startswith("--format=") or arg.startswith("-o="):
            candidate = arg.partition("=")[2]
        else:
            continue
        if candidate in ("json", "yaml"):
            return candidate
    return "text"


def _result(command: str | None, status: str, message: str, exit_code: int,
            options: dict[str, Any]) -> dict[str, Any]:
    return {"command": command, "status": status, "message": message,
            "exit_code": exit_code, "options": options}


def _display(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=False))
    elif output_format == "yaml":
        print(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), end="")
    else:
        cmd = payload["command"] or "cli"
        print(f"matma:{cmd} [{payload['status']}] {payload['message']} (exit {payload['exit_code']})")
        if cmd in ("validate", "index", "scaffold") and "summary" in payload:
            summary = payload["summary"]
            print(f"  {summary['parsed_files']} modules, {summary['symbols']} symbols, "
                  f"{summary['diagnostic_errors']} errors, {summary['diagnostic_warnings']} warnings")
            if cmd in ("index", "scaffold") and "graph_summary" in payload:
                graph = payload["graph_summary"]
                print(f"  {graph['internal_edges']} internal graph edges, "
                      f"{graph['import_only_edges']} import-only edges")
            if "scaffolds" in payload and payload["exit_code"] == 0:
                print(f"  {len(payload['scaffolds']['created'])} scaffold files created, "
                      f"{len(payload['scaffolds']['existing'])} existing files retained")
            for diagnostic in payload["diagnostics"]:
                location = (f"{diagnostic['file']}:{diagnostic['line'] or 1}"
                            if diagnostic["file"] else "project")
                print(f"  {location}: {diagnostic['severity']} "
                      f"{diagnostic['code']}: {diagnostic['message']}")


def _source_root_selected(args: Sequence[str]) -> bool:
    return any(arg in ("-s", "--source-root") or arg.startswith("--source-root=")
               or arg.startswith("-s=") for arg in args)


def main(argv: Sequence[str] | None = None) -> int:
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

    if namespace.command == "validate":
        examined = inspect_project(
            source_root=namespace.source_root, tests_root=namespace.tests_root,
            target=namespace.target, extra_source_roots=tuple(namespace.extra_source_root),
            explicitly_selected=_source_root_selected(args),
        )
        error_count = examined["summary"]["diagnostic_errors"]
        fatal = any(d["code"] in {"missing_source_root", "unsafe_source_root", "unsafe_tests_root"}
                    for d in examined["diagnostics"])
        failed = fatal or (namespace.check and error_count > 0)
        payload = {
            **_result("validate", "validation_failed" if failed else "validated",
                      f"Inspected {examined['summary']['parsed_files']} Python modules; "
                      f"{error_count} structural errors", EXIT_FAILURE if failed else EXIT_SUCCESS, options),
            **examined,
        }
        _display(payload, namespace.format)
        return payload["exit_code"]

    if namespace.command in ("index", "scaffold"):
        common = dict(
            source_root=namespace.source_root, tests_root=namespace.tests_root,
            target=namespace.target, extra_source_roots=tuple(namespace.extra_source_root),
            explicitly_selected=_source_root_selected(args),
        )
        do_scaffold = namespace.command == "scaffold" or bool(getattr(namespace, "scaffold", False))
        indexed = (scaffold_project(**common, from_index=(namespace.command == "index"))
                   if do_scaffold else index_project(**common))
        command = namespace.command
        payload = {**_result(command, indexed["status"], indexed["message"], indexed["exit_code"], options),
                   **{key: value for key, value in indexed.items()
                      if key not in ("status", "message", "exit_code")}}
        _display(payload, namespace.format)
        return payload["exit_code"]

    phase, description = COMMAND_PHASES[namespace.command]
    payload = _result(namespace.command, "not_implemented",
                      f"{description} is not available yet (planned for Phase {phase}); no work performed",
                      EXIT_NOT_IMPLEMENTED, options)
    _display(payload, namespace.format)
    return EXIT_NOT_IMPLEMENTED
