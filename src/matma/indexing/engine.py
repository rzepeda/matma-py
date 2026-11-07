"""Full AST index orchestrator; no user tests, mocks, or production writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from matma.analysis import inspect_project

from .graph import build_graph
from .manifests import ManifestError, write_manifests


def index_project(
    *, source_root: str = "src", tests_root: str = "tests", target: str | None = None,
    extra_source_roots: tuple[str, ...] = (), explicitly_selected: bool = False,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build all reverse relationships and persist manifests on explicit index.

    A target is a response filter, *not* a partial index operation; partial
    rebuilds would produce invalid downstream reverse-dependency levels.
    """
    root = (project_root or Path.cwd()).resolve()
    examined = inspect_project(
        source_root=source_root, tests_root=tests_root, target=target,
        extra_source_roots=extra_source_roots,
        explicitly_selected=explicitly_selected, project_root=root,
    )
    if examined["summary"]["diagnostic_errors"]:
        return {
            "status": "index_failed", "exit_code": 1,
            "message": "Source validation failed; no manifests were modified",
            **examined,
            "manifests": {"written": [], "unchanged": [], "removed": []},
        }
    graph = build_graph(examined["files"])
    try:
        result = write_manifests(root, tests_root, examined, graph)
    except ManifestError as exc:
        return {
            "status": "unsafe_output", "exit_code": 1,
            "message": str(exc), **examined,
            "graph_summary": graph["summary"],
            "manifests": {"written": [], "unchanged": [], "removed": []},
        }
    return {
        "status": "indexed", "exit_code": 0,
        "message": (f"Indexed {len(examined['files'])} Python modules, "
                    f"{graph['summary']['internal_edges']} internal dependencies"),
        **examined,
        "graph_summary": graph["summary"],
        **result,
    }
