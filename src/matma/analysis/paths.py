"""Project-root-relative, collision-safe file and mirror identities."""

from __future__ import annotations

from pathlib import Path


def relative_identity(project_root: Path, source: Path) -> str:
    """Store slash-separated relative paths; never embed machine-local paths."""
    return source.relative_to(project_root).as_posix()


def module_name(source: Path, source_root: Path) -> str:
    """Derive an import path from a configured source root and package layout."""
    relative = source.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    if (source_root / "__init__.py").is_file():
        parts.insert(0, source_root.name)
    # The source root itself may be the source package's only __init__.py.
    return ".".join(parts) or source_root.name


def mirror_paths(source_file: str, tests_root: str, *, testable: bool) -> dict[str, str | None]:
    """Exactly one pair of test files for a testable module, not per class."""
    source = Path(source_file)
    tests = Path(tests_root)
    parent = source.parent
    stem = source.stem
    return {
        "unit_test": (tests / "unit" / "mirror" / parent / f"test_{stem}.py").as_posix() if testable else None,
        "interaction_test": (tests / "interaction" / "mirror" / parent / f"test_{stem}_interaction.py").as_posix() if testable else None,
        "mock_file": (tests / "mocks" / "mirror" / parent / f"mock_{stem}.py").as_posix() if testable else None,
        "manifest": (tests / "mirror" / parent / f"{stem}.auto.yaml").as_posix(),
    }
