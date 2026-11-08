#!/usr/bin/env python3
"""Install MATMA Agent Skills into a Python project without clobbering files.

Uses only Python's standard library. All destinations are preflighted before
anything is copied; existing identical files are preserved byte-for-byte.
There is no --force flag: edit or remove conflicting files explicitly.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parent
SKILLS = {
    "claude": ("claude/matma-python", ".claude/skills/matma-python"),
    "chatgpt": ("chatgpt/matma-python-chatgpt", ".agents/skills/matma-python-chatgpt"),
    "antigravity": ("antigravity/matma-python-antigravity", ".agents/skills/matma-python-antigravity"),
}


def _unsafe_link(project: Path, destination: Path) -> Path | None:
    candidate = destination
    while candidate != project:
        if candidate.is_symlink():
            return candidate
        if project not in candidate.parents:
            return candidate
        candidate = candidate.parent
    return None


def install(project: Path, platforms: list[str], *, dry_run: bool = False) -> list[str]:
    project = project.resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")

    actions: list[tuple[str, Path, Path]] = []
    report: list[str] = []
    for platform in platforms:
        source_rel, destination_rel = SKILLS[platform]
        source = ROOT / source_rel
        destination = project / destination_rel
        if not (source / "SKILL.md").is_file():
            raise ValueError(f"Missing source SKILL.md for {platform}: {source}")
        link = _unsafe_link(project, destination)
        if link:
            raise ValueError(f"Refusing symlinked or unsafe destination: {link}")
        if destination.exists() and not destination.is_dir():
            raise ValueError(f"Destination is not a directory: {destination}")

        for original in sorted(p for p in source.rglob("*") if p.is_file()):
            relative = original.relative_to(source)
            target = destination / relative
            link = _unsafe_link(project, target)
            if link:
                raise ValueError(f"Refusing symlinked destination: {link}")
            if target.exists():
                if not target.is_file():
                    raise ValueError(f"Destination is not a file: {target}")
                if target.read_bytes() != original.read_bytes():
                    raise ValueError(
                        f"Different file already exists at {target}; edit/remove it explicitly"
                    )
                report.append(f"unchanged: {target}")
            else:
                actions.append((platform, original, target))
                report.append(f"{'would create' if dry_run else 'created'}: {target}")
    if not dry_run:
        for _, original, target in actions:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Never replace existing content created concurrently: fail instead.
            with target.open("xb") as output:
                output.write(original.read_bytes())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install non-clobbering MATMA coding-agent skills")
    parser.add_argument("--project", required=True, type=Path, help="existing consumer project root")
    parser.add_argument("--platform", choices=["all", *SKILLS], default="all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    platforms = list(SKILLS) if args.platform == "all" else [args.platform]
    try:
        for line in install(args.project, platforms, dry_run=args.dry_run):
            print(line)
    except (OSError, ValueError) as exc:
        print(f"MATMA skills installation refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
