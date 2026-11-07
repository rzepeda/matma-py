"""Safe, non-destructive planner and exclusive-create test/mock writer."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from matma.indexing.manifests import _path, _symlink_ancestor, ManifestError

from .templates import render_mock_module, render_test_module


class ScaffoldError(Exception):
    """Unsafe scaffold destination or an unscaffoldable requested target.

    ``created`` reports newly created files on a post-preflight I/O failure,
    never files that already belonged to a developer.
    """

    def __init__(self, message: str, *, created: list[str] | None = None) -> None:
        super().__init__(message)
        self.created = sorted(created or [])


@dataclass(frozen=True)
class ScaffoldPlan:
    files: dict[str, str]
    selected_sources: list[str]
    mock_sources: list[str]
    omitted_symbols: list[dict[str, str]]
    warnings: list[str]


def make_plan(examined: dict[str, Any], graph: dict[str, Any], *, target: str | None) -> ScaffoldPlan:
    """Choose testable modules and direct-dependency mocks, not tests for dependents."""
    modules = {item["source_file"]: item for item in examined["files"]}
    if target:
        item = modules.get(examined.get("target"))
        if item is None:
            raise ScaffoldError(f"Unresolvable scaffold target: {target!r}")
        if not item["testable"]:
            raise ScaffoldError(f"Source module has no independent testable behavior: {item['source_file']}")
        selected = [item["source_file"]]
    else:
        selected = sorted(name for name, mod in modules.items() if mod["testable"])

    mock_sources: set[str] = set(selected)
    warnings: list[str] = []
    for source in selected:
        source_mod = modules[source]
        for import_entry in source_mod.get("imports", []):
            if import_entry.get("resolution") not in ("internal", None):
                module_name = import_entry.get("absolute_module") or import_entry.get("module")
                warnings.append(
                    f"External/unresolved import {module_name!r} in {source} at line "
                    f"{import_entry.get('line', '?')} is not auto-mocked; configure a patch explicitly"
                )
        for call in source_mod.get("dynamic_imports", []):
            warnings.append(
                f"Dynamic import {call.get('name', '<unknown>')} in {source} at line "
                f"{call.get('line', '?')} cannot be safely auto-mocked by static analysis"
            )
        for edge in graph["dependencies"].get(source, []):
            dependency = edge["source_file"]
            item = modules.get(dependency)
            if item is None:
                continue
            if not item["testable"]:
                warnings.append(f"No mock file for non-testable dependency {dependency} (of {source})")
            else:
                mock_sources.add(dependency)

    proposed: dict[str, str] = {}
    omissions: list[dict[str, str]] = []
    case_names: dict[str, str] = {}

    def add(filename: str | None, content: str) -> None:
        if not filename:
            raise ScaffoldError("Missing mirror path for a testable source module")
        folded = filename.casefold()
        if filename in proposed or (folded in case_names and case_names[folded] != filename):
            raise ScaffoldError(f"Scaffold output collision: {filename!r} and {case_names.get(folded)!r}")
        case_names[folded] = filename
        proposed[filename] = content

    for source in selected:
        module = modules[source]
        for tier, key in (("unit", "unit_test"), ("interaction", "interaction_test")):
            content, omitted = render_test_module(module, tier)
            add(module["mirrors"][key], content)
            if tier == "unit":
                omissions.extend({"source_file": source, "kind": sym["kind"], "qualname": sym["qualname"]}
                                 for sym in omitted)

    for source in sorted(mock_sources):
        module = modules[source]
        content, _ = render_mock_module(module)
        add(module["mirrors"]["mock_file"], content)

    return ScaffoldPlan(
        files=dict(sorted(proposed.items())), selected_sources=selected,
        mock_sources=sorted(mock_sources),
        omitted_symbols=sorted(omissions, key=lambda s: (s["source_file"], s["qualname"])),
        warnings=sorted(set(warnings)),
    )


def preflight_scaffolds(root: Path, tests_root: str, plan: ScaffoldPlan) -> tuple[list[str], list[str]]:
    """Verify EVERY requested path before touching the filesystem."""
    project_root = root.resolve()
    try:
        base = _path(project_root, tests_root)
    except ManifestError as exc:
        raise ScaffoldError(str(exc)) from exc
    parents = [base / tier / "mirror" for tier in ("unit", "interaction", "mocks")]
    new, existing = [], []
    for relative in plan.files:
        try:
            path = _path(project_root, relative)
        except ManifestError as exc:
            raise ScaffoldError(str(exc)) from exc
        if not any(path.is_relative_to(parent) and path != parent for parent in parents):
            raise ScaffoldError(f"Scaffold output escapes its managed test tiers: {relative}")
        unsafe = _symlink_ancestor(project_root, path)
        if unsafe is not None:
            raise ScaffoldError(f"Refusing symlinked scaffold destination: {unsafe}")
        if path.exists():
            if not path.is_file():
                raise ScaffoldError(f"Scaffold destination is not a regular file: {relative}")
            existing.append(relative)
        else:
            parent = path.parent
            while parent != project_root:
                if parent.exists() and not parent.is_dir():
                    raise ScaffoldError(f"Scaffold parent is not a directory: {parent}")
                parent = parent.parent
            new.append(relative)
    return new, existing


def write_scaffolds(root: Path, tests_root: str, plan: ScaffoldPlan) -> dict[str, Any]:
    """Never overwrite: create new files with OS-level exclusive creation."""
    planned_new, existing = preflight_scaffolds(root, tests_root, plan)
    created: list[str] = []
    project_root = root.resolve()
    for relative in planned_new:
        path = _path(project_root, relative)
        # Revalidate just before opening; O_EXCL also handles concurrent writes.
        if _symlink_ancestor(project_root, path) is not None:
            raise ScaffoldError("Scaffold path became a symlink", created=created)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(path, flags, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(plan.files[relative])
            created.append(relative)
        except OSError as exc:
            raise ScaffoldError(f"Failed to exclusively create {relative}: {exc}", created=created) from exc
    return {
        "created": sorted(created),
        "existing": sorted(existing),
        "selected_sources": plan.selected_sources,
        "mock_sources": plan.mock_sources,
        "omitted_symbols": plan.omitted_symbols,
        "warnings": plan.warnings,
    }
