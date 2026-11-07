"""Read-only source inventory and structural audit for arbitrary Python layouts."""

from __future__ import annotations

import ast
import os
import posixpath
import tokenize
import tomllib
from pathlib import Path
from typing import Any

from .paths import mirror_paths, module_name, relative_identity
from .resolver import resolve_imports
from .syntax import SyntaxVisitor

# Skip known non-production artifacts, without making the source tree conform
# to MATMA's own directory structure.
EXCLUDED_DIRS = frozenset({
    ".git", ".hg", ".svn", ".tox", ".nox", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tools", "build", "dist",
    "site-packages", "node_modules", "vendor", "tests", "test", "docs", "documentation",
})


def _diagnostic(code: str, severity: str, message: str, file: str | None = None,
                line: int | None = None, column: int | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message,
            "file": file, "line": line, "column": column}


def _is_relative_to(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _project_path(root: Path, value: str) -> Path:
    """Normalize path separators while preserving real filesystem path checks."""
    path = Path(value.replace("\\", "/"))
    return (path if path.is_absolute() else root / path).resolve(strict=False)


def _traverses_symlink(root: Path, value: str) -> bool:
    path = Path(value.replace("\\", "/"))
    raw = Path(os.path.normpath(str(path if path.is_absolute() else root / path)))
    return any(part.is_symlink() for part in [raw, *raw.parents] if _is_relative_to(part, root))


def _configured_roots(project_root: Path) -> list[str]:
    config = project_root / "pyproject.toml"
    if not config.is_file():
        return []
    try:
        with config.open("rb") as handle:
            doc = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    matma = doc.get("tool", {}).get("matma", {})
    source_roots = matma.get("source_roots")
    if isinstance(source_roots, list) and source_roots and all(isinstance(s, str) for s in source_roots):
        return source_roots
    setuptools = doc.get("tool", {}).get("setuptools", {}).get("packages", {})
    where = setuptools.get("find", {}).get("where", []) if isinstance(setuptools, dict) else []
    return where if isinstance(where, list) and all(isinstance(s, str) for s in where) else []


def _source_roots(project_root: Path, source_root: str, extra_roots: tuple[str, ...],
                  explicitly_selected: bool) -> list[str]:
    if explicitly_selected:
        return [source_root, *extra_roots]
    return [*(_configured_roots(project_root) or (["src"] if (project_root / "src").is_dir() else ["."])), *extra_roots]


def _testable(tree: ast.Module, visitor: SyntaxVisitor, is_package: bool) -> bool:
    if not tree.body:
        return False
    if not is_package:
        return True
    if visitor.symbols:
        return True
    # Import/re-export-only __init__.py files provide dependency context without
    # requiring a unit test of their own. Executable top-level effects count.
    return any(not isinstance(stmt, (ast.Import, ast.ImportFrom, ast.Pass)) and not (
        isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    ) and not (
        isinstance(stmt, ast.Assign)
        and all(isinstance(t, ast.Name) and t.id == "__all__" for t in stmt.targets)
    ) for stmt in tree.body)


def _inventory(root: Path, roots: list[Path], excluded_test_root: Path,
               diagnostics: list[dict]) -> list[tuple[Path, Path]]:
    """Collect candidates without following symlinks or visiting generated tiers."""
    candidates: dict[Path, Path] = {}
    for source_root in roots:
        for dirname, directories, filenames in os.walk(source_root, topdown=True, followlinks=False):
            directory = Path(dirname)
            keep_dirs = []
            for name in sorted(directories):
                candidate = directory / name
                if name in EXCLUDED_DIRS or _is_relative_to(candidate, excluded_test_root):
                    continue
                if candidate.is_symlink():
                    diagnostics.append(_diagnostic(
                        "unsafe_symlink", "error", "Symlinked source directories are not followed",
                        relative_identity(root, candidate)))
                else:
                    keep_dirs.append(name)
            directories[:] = keep_dirs
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                path = directory / name
                if path.is_symlink():
                    diagnostics.append(_diagnostic(
                        "unsafe_symlink", "error", "Symlinked Python source files are not followed",
                        relative_identity(root, path)))
                    continue
                # Prefer deepest source root in an overlapping-root configuration.
                selected = candidates.get(path)
                if selected is None or len(source_root.parts) > len(selected.parts):
                    candidates[path] = source_root
    return sorted(candidates.items(), key=lambda item: relative_identity(root, item[0]))


def inspect_project(
    *, source_root: str = "src", tests_root: str = "tests", target: str | None = None,
    extra_source_roots: tuple[str, ...] = (), explicitly_selected: bool = False,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Inspect an entire project without mutating its filesystem or imports.

    The returned files and maps are sorted, serializable, and suitable for the
    Phase 3 dependency graph. Neither manifests nor tests are written here.
    """
    root = (project_root or Path.cwd()).resolve()
    diagnostics: list[dict] = []
    raw_roots = _source_roots(root, source_root, extra_source_roots, explicitly_selected)
    configured: list[Path] = []
    for text in raw_roots:
        item = _project_path(root, text)
        if not _is_relative_to(item, root):
            diagnostics.append(_diagnostic("unsafe_source_root", "error", "Source root must remain inside the project", text))
        elif _traverses_symlink(root, text):
            diagnostics.append(_diagnostic("unsafe_symlink", "error", "Source root must not traverse symlinks", text))
        elif not item.is_dir():
            diagnostics.append(_diagnostic("missing_source_root", "error", "Source root does not exist", text))
        elif item not in configured:
            configured.append(item)

    test_path = _project_path(root, tests_root)
    if not _is_relative_to(test_path, root) or _traverses_symlink(root, tests_root):
        diagnostics.append(_diagnostic("unsafe_tests_root", "error", "Test root is outside the project or symlinked", tests_root))
    elif any(test_path == source or _is_relative_to(source, test_path) or (
        source != root and _is_relative_to(test_path, source)
    ) for source in configured):
        diagnostics.append(_diagnostic("unsafe_tests_root", "error", "Test root overlaps a production source root", tests_root))

    safe = not any(d["severity"] == "error" for d in diagnostics)
    candidates = _inventory(root, configured, test_path, diagnostics) if safe else []
    files: list[dict] = []
    by_case: dict[str, str] = {}
    for path, selected_root in candidates:
        relative = relative_identity(root, path)
        fold = relative.casefold()
        if fold in by_case and by_case[fold] != relative:
            diagnostics.append(_diagnostic(
                "case_collision", "error", f"Source path collides with {by_case[fold]} on case-insensitive filesystems", relative))
        by_case[fold] = relative
        try:
            with tokenize.open(path) as handle:
                source = handle.read()
            tree = ast.parse(source, filename=relative, type_comments=True)
        except (SyntaxError, UnicodeError, OSError) as error:
            diagnostics.append(_diagnostic(
                "syntax_error" if isinstance(error, SyntaxError) else "unreadable_source",
                "error", str(error), relative,
                getattr(error, "lineno", None), getattr(error, "offset", None)))
            continue
        visitor = SyntaxVisitor(tree)
        for call in visitor.dynamic_imports:
            diagnostics.append(_diagnostic(
                "dynamic_import", "warning", f"Cannot statically verify dynamic import through {call['name']}",
                relative, call["line"], call["column"]))
        is_package = path.name == "__init__.py"
        testable = _testable(tree, visitor, is_package)
        entry = {
            "source_file": relative,
            "source_root": relative_identity(root, selected_root) if selected_root != root else ".",
            "module_name": module_name(path, selected_root),
            "is_package": is_package,
            "testable": testable,
            "symbols": visitor.symbols,
            "imports": visitor.imports,
            "references": visitor.references,
            "dynamic_imports": visitor.dynamic_imports,
            "explicit_exports": visitor.explicit_exports,
            "mirrors": mirror_paths(relative, relative_identity(root, test_path), testable=testable),
        }
        files.append(entry)
    module_to_source, symbol_to_source = resolve_imports(files, diagnostics)

    selected = None
    if target:
        normalized = posixpath.normpath(target.replace("\\", "/")).removeprefix("./")
        hits = [f for f in files if normalized in (f["source_file"], f["module_name"]) or (
            normalized in symbol_to_source and symbol_to_source[normalized] == f["source_file"]
        )]
        if len(hits) == 1:
            selected = hits[0]["source_file"]
        else:
            diagnostics.append(_diagnostic(
                "invalid_target", "error", f"Target {target!r} could not be resolved unambiguously"))

    diagnostics.sort(key=lambda d: (d["file"] or "", d["line"] or 0, d["column"] or 0, d["code"], d["message"]))
    errors = sum(d["severity"] == "error" for d in diagnostics)
    return {
        "summary": {
            "source_roots": sorted(relative_identity(root, path) if path != root else "." for path in configured),
            "source_files": len(candidates), "parsed_files": len(files),
            "testable_modules": sum(f["testable"] for f in files),
            "symbols": sum(len(f["symbols"]) for f in files),
            "imports": sum(len(f["imports"]) for f in files),
            "diagnostic_errors": errors,
            "diagnostic_warnings": len(diagnostics) - errors,
        },
        "target": selected,
        "files": files,
        "module_to_source": module_to_source,
        "symbol_to_source": symbol_to_source,
        "diagnostics": diagnostics,
    }
