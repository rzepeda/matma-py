"""Phase 4: full index + narrowly scoped, truthful pytest/mock scaffolding."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from matma.analysis import inspect_project
from matma.indexing.graph import build_graph
from matma.indexing.manifests import ManifestError, write_manifests

from .writer import ScaffoldError, make_plan, preflight_scaffolds, write_scaffolds


def scaffold_project(
    *, source_root: str = "src", tests_root: str = "tests", target: str | None = None,
    extra_source_roots: tuple[str, ...] = (), explicitly_selected: bool = False,
    project_root: Path | None = None, from_index: bool = False,
) -> dict[str, Any]:
    """Build the *complete* graph, then generate only missing scoped test files.

    Tests and mocks are preflighted before any index writes. Manifest writing
    retains its own ownership preflight; a manifest conflict never generates
    any tests. A filesystem race or I/O failure after preflight may produce
    partial creations, but never overwrites a developer-authored file.
    """
    root = (project_root or Path.cwd()).resolve()
    inspected = inspect_project(
        source_root=source_root, tests_root=tests_root, target=target,
        extra_source_roots=extra_source_roots,
        explicitly_selected=explicitly_selected, project_root=root,
    )
    empty = {"created": [], "existing": [], "selected_sources": [],
             "mock_sources": [], "omitted_symbols": [], "warnings": []}
    if inspected["summary"]["diagnostic_errors"]:
        return {
            "status": "scaffold_failed", "exit_code": 1,
            "message": "Source validation failed; no generated files were modified",
            **inspected,
            "manifests": {"written": [], "unchanged": [], "removed": []},
            "scaffolds": empty,
        }

    graph = build_graph(inspected["files"])
    indexed: dict[str, Any] | None = None
    try:
        plan = make_plan(inspected, graph, target=target)
        preflight_scaffolds(root, tests_root, plan)
        indexed = write_manifests(root, tests_root, inspected, graph)
        result = write_scaffolds(root, tests_root, plan)
    except (ScaffoldError, ManifestError) as exc:
        # A late filesystem race can leave new files and/or already written
        # owned manifests. Report what is known; never claim atomic rollback.
        return {
            "status": "unsafe_output", "exit_code": 1,
            "message": str(exc), **inspected,
            "graph_summary": graph["summary"],
            **({"index_fingerprint": indexed["index_fingerprint"]} if indexed else {}),
            "manifests": indexed["manifests"] if indexed else {"written": [], "unchanged": [], "removed": []},
            "scaffolds": {**empty, "created": exc.created} if isinstance(exc, ScaffoldError) else empty,
        }
    count = len(result["created"])
    cmd = "index" if from_index else "scaffold"
    return {
        "status": "indexed" if from_index else "scaffolded", "exit_code": 0,
        "message": f"Indexed {len(inspected['files'])} modules; created {count} missing pytest/mock files",
        **inspected,
        "graph_summary": graph["summary"], **indexed,
        "scaffolds": result,
    }
