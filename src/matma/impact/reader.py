"""Phase 5: use persisted YAML only; never parse Python or execute pytest.

The companion .index.auto.yaml is a bounded lookup table and freshness record.
A query reads the target's single manifest, source-file hashes and known source
folder mtimes, plus an optional user-owned verification registry. No source AST
or recursive source-tree traversal is performed here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from matma.indexing.manifests import HEADER, SCHEMA_VERSION, _path, _symlink_ancestor, ManifestError


class ImpactError(Exception):
    """Unavailable, stale, corrupt or unsafe index/registry (exit 1)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _safe_path(root: Path, relative: str, *, within: Path | None = None) -> Path:
    """Reject traversal and symlinks; never rely on resolve() to follow a link."""
    try:
        path = _path(root, relative)
    except (ManifestError, TypeError, ValueError) as exc:
        raise ImpactError("unsafe_path", f"Unsafe indexed path {relative!r}: {exc}") from exc
    if within is not None and (not path.is_relative_to(within) or path == within):
        raise ImpactError("unsafe_path", f"Path escapes its configured test root: {relative!r}")
    link = _symlink_ancestor(root, path)
    if link is not None:
        raise ImpactError("unsafe_path", f"Refusing symlinked indexed path: {relative!r}")
    return path


def _owned_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ImpactError("missing_index", f"Missing MATMA index {path}; run 'matma-indexer index' first")
    try:
        with path.open("rb") as handle:
            if handle.readline().rstrip(b"\r\n") != HEADER.encode().rstrip(b"\r\n"):
                raise ImpactError("unsafe_index", f"Not a MATMA-owned index: {path}")
            data = yaml.safe_load(handle)
    except (yaml.YAMLError, UnicodeError, OSError, ValueError) as exc:
        raise ImpactError("invalid_index", f"Cannot parse MATMA index {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ImpactError("invalid_index", f"Unsupported index schema at {path}; run 'matma-indexer index'")
    return data


def _fingerprint(sources: list[dict[str, str]], roots: list[str]) -> str:
    serialized = "".join(f"{entry['source_file']}\0{entry['sha256']}\n" for entry in sources)
    serialized += "ROOTS\n" + "\n".join(sorted(roots)) + "\n"
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_freshness(root: Path, metadata: dict[str, Any], tests_root: str) -> set[str]:
    """Hash known files and check known directory mtimes; no globs or AST."""
    roots = metadata.get("source_roots")
    sources = metadata.get("sources")
    directories = metadata.get("directories")
    fingerprint = metadata.get("index_fingerprint")
    if (not isinstance(roots, list) or not all(isinstance(x, str) for x in roots)
            or not isinstance(sources, list) or not isinstance(directories, list)
            or not isinstance(fingerprint, str) or len(fingerprint) != 64):
        raise ImpactError("invalid_index", "Incomplete index freshness metadata; run 'matma-indexer index'")
    if metadata.get("tests_root") != tests_root:
        raise ImpactError("stale_index", "Test root differs from indexed configuration; run 'matma-indexer index'")
    names: set[str] = set()
    hashes: list[dict[str, str]] = []
    for entry in sources:
        if not isinstance(entry, dict) or not isinstance(entry.get("source_file"), str) or not isinstance(entry.get("sha256"), str):
            raise ImpactError("invalid_index", "Invalid source entry in MATMA index")
        name = entry["source_file"]
        if name in names:
            raise ImpactError("invalid_index", f"Duplicated source file in index: {name}")
        names.add(name)
        file = _safe_path(root, name)
        try:
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
        except OSError as exc:
            raise ImpactError("stale_index", f"Source {name} is missing/unreadable; rerun index: {exc}") from exc
        if digest != entry["sha256"]:
            raise ImpactError("stale_index", f"Source {name} changed after indexing; run 'matma-indexer index'")
        hashes.append({"source_file": name, "sha256": digest})
    if not names or _fingerprint(hashes, roots) != fingerprint:
        raise ImpactError("invalid_index", "Inconsistent index fingerprint; run 'matma-indexer index'")
    for entry in directories:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("mtime_ns"), int):
            raise ImpactError("invalid_index", "Invalid directory freshness metadata")
        directory = _safe_path(root, entry["path"])
        try:
            current = directory.stat().st_mtime_ns
        except OSError as exc:
            raise ImpactError("stale_index", f"Indexed source directory {entry['path']} is missing: {exc}") from exc
        if current != entry["mtime_ns"]:
            raise ImpactError("stale_index", f"Source directory {entry['path']} changed (files may have been added/removed); run 'matma-indexer index'")
    return names


def _resolve_target(value: str, metadata: dict[str, Any], names: set[str]) -> str:
    candidate = value.strip().replace("\\", "/")
    if not candidate or candidate.startswith("/") or ".." in PurePosixPath(candidate).parts:
        raise ImpactError("invalid_target", f"Unsafe or empty target: {value!r}")
    candidate = candidate.removeprefix("./")
    module_map = metadata.get("module_to_source")
    symbol_map = metadata.get("symbol_to_source")
    if not isinstance(module_map, dict) or not isinstance(symbol_map, dict):
        raise ImpactError("invalid_index", "Missing module/symbol lookup in index; rerun 'matma-indexer index'")
    source = candidate if candidate in names else module_map.get(candidate, symbol_map.get(candidate))
    if not isinstance(source, str) or source not in names:
        raise ImpactError("invalid_target", f"Target {value!r} is not present in the index; run 'matma-indexer index' if new")
    return source


def _validate_test_path(root: Path, tests_dir: Path, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.endswith(".py"):
        raise ImpactError("invalid_index", f"Invalid generated pytest path: {value!r}")
    _safe_path(root, value, within=tests_dir)
    return value


def _selection(manifest: dict[str, Any], source: str, level: int,
               source_names: set[str], root: Path, tests_dir: Path) -> list[dict[str, Any]]:
    rows = [{"source_file": source, "level": 0, "module_name": manifest["module_name"],
             "unit_test": manifest["mirrors"].get("unit_test"),
             "interaction_test": manifest["mirrors"].get("interaction_test")}]
    dependents = manifest.get("dependents")
    if not isinstance(dependents, dict):
        raise ImpactError("invalid_index", "Missing indexed reverse dependents; rerun index")
    seen = {source}
    for key, bucket in dependents.items():
        if not isinstance(key, str) or not key.startswith("level_") or not key[6:].isdigit() or not isinstance(bucket, list):
            raise ImpactError("invalid_index", f"Invalid reverse-dependent level {key!r}")
        depth = int(key[6:])
        if depth <= 0:
            raise ImpactError("invalid_index", f"Invalid reverse-dependent depth {key!r}")
        if depth > level:
            continue
        for row in bucket:
            if (not isinstance(row, dict) or not isinstance(row.get("source_file"), str)
                    or row["source_file"] not in source_names or not isinstance(row.get("module_name"), str)):
                raise ImpactError("invalid_index", f"Corrupt reverse dependent in level {depth}")
            dep = row["source_file"]
            if dep in seen:
                raise ImpactError("invalid_index", f"Duplicate reverse dependent {dep} in index")
            seen.add(dep)
            rows.append({"source_file": dep, "level": depth, "module_name": row["module_name"],
                         "unit_test": row.get("unit_test"), "interaction_test": row.get("interaction_test")})
    rows.sort(key=lambda row: (row["level"], row["source_file"]))
    for row in rows:
        for key in ("unit_test", "interaction_test"):
            row[key] = _validate_test_path(root, tests_dir, row[key])
    return rows


def _registered(root: Path, tests_root: str, metadata: dict[str, Any],
                selected: list[dict[str, Any]], names: set[str]) -> dict[str, Any]:
    """Only user-declared business/regression paths; never glob test directories."""
    tests_dir = _safe_path(root, tests_root)
    registry_file = _safe_path(root, f"{tests_root}/matma-verification.yaml", within=tests_dir)
    result: dict[str, Any] = {"business": [], "regression": [], "missing": [], "registry": None}
    if not registry_file.exists():
        return result
    if not registry_file.is_file():
        raise ImpactError("invalid_registry", "Verification registry is not a regular file")
    try:
        with registry_file.open("r", encoding="utf-8") as handle:
            registry = yaml.safe_load(handle)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ImpactError("invalid_registry", f"Invalid verification registry: {exc}") from exc
    if not isinstance(registry, dict) or registry.get("schema_version") != 1 or not isinstance(registry.get("registrations"), dict):
        raise ImpactError("invalid_registry", "Expected schema_version: 1 and registrations mapping in verification registry")
    module_map = metadata["module_to_source"]
    source_map = metadata["symbol_to_source"]
    canonical: dict[str, dict[str, list[str]]] = {}
    for key, groups in registry["registrations"].items():
        if not isinstance(key, str) or not isinstance(groups, dict):
            raise ImpactError("invalid_registry", f"Invalid registration source {key!r}")
        source = key if key in names else module_map.get(key, source_map.get(key))
        if not isinstance(source, str) or source not in names or source in canonical:
            raise ImpactError("invalid_registry", f"Unknown or duplicated registration source {key!r}")
        unknown = set(groups) - {"business", "regression"}
        if unknown:
            raise ImpactError("invalid_registry", f"Unknown verification tier(s): {sorted(map(str, unknown))}")
        groups_checked = {"business": [], "regression": []}
        for tier in ("business", "regression"):
            paths = groups.get(tier, [])
            if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
                raise ImpactError("invalid_registry", f"{tier} registration for {key!r} must be a list of paths")
            for p in paths:
                if not p.endswith(".py"):
                    raise ImpactError("invalid_registry", f"Registered test is not a .py path: {p!r}")
                _safe_path(root, p, within=tests_dir)
                groups_checked[tier].append(p)
        canonical[source] = groups_checked
    dedup: dict[str, dict[str, dict[str, Any]]] = {"business": {}, "regression": {}}
    missing: list[dict[str, Any]] = []
    for item in selected:
        source = item["source_file"]
        for tier in ("business", "regression"):
            for path in canonical.get(source, {}).get(tier, []):
                if path not in dedup[tier]:
                    record = {"path": path, "source_file": source, "level": item["level"]}
                    if (root / path).is_file():
                        dedup[tier][path] = record
                    else:
                        missing.append({**record, "tier": tier})
    result["business"] = [dedup["business"][p] for p in sorted(dedup["business"])]
    result["regression"] = [dedup["regression"][p] for p in sorted(dedup["regression"])]
    result["missing"] = sorted(missing, key=lambda x: (x["tier"], x["path"], x["source_file"]))
    result["registry"] = f"{tests_root}/matma-verification.yaml"
    return result


def select_impact(*, target: str, level: int = 0, tests_root: str = "tests",
                  source_root: str = "src", extra_source_roots: tuple[str, ...] = (),
                  explicitly_selected: bool = False, project_root: Path | None = None) -> dict[str, Any]:
    """Return deterministic paths to already existing tests, without running any.

    Source-root flags are validated against index metadata only when explicitly
    supplied. A fully indexed flat/pyproject layout therefore needs no flags.
    """
    root = (project_root or Path.cwd()).resolve()
    try:
        tests_dir = _safe_path(root, tests_root)
        metadata_file = _safe_path(root, f"{tests_root}/mirror/.index.auto.yaml", within=tests_dir)
        metadata = _owned_yaml(metadata_file)
        if explicitly_selected:
            requested = {str(PurePosixPath(source_root)), *(str(PurePosixPath(r)) for r in extra_source_roots)}
            if requested != set(metadata.get("source_roots", [])):
                raise ImpactError("stale_index", "Indexed source-root configuration differs; run 'matma-indexer index'")
        elif extra_source_roots and not set(extra_source_roots).issubset(set(metadata.get("source_roots", []))):
            raise ImpactError("stale_index", "Indexed source roots differ; run 'matma-indexer index'")
        names = _validate_freshness(root, metadata, tests_root)
        source = _resolve_target(target, metadata, names)
        manifest_by_source = metadata.get("source_to_manifest")
        if not isinstance(manifest_by_source, dict) or source not in manifest_by_source:
            raise ImpactError("invalid_index", "Missing manifest locator in index; run 'matma-indexer index'")
        path = manifest_by_source[source]
        if not isinstance(path, str):
            raise ImpactError("invalid_index", "Corrupt indexed manifest locator")
        manifest_file = _safe_path(root, path, within=tests_dir / "mirror")
        manifest = _owned_yaml(manifest_file)
        if (manifest.get("source_file") != source or manifest.get("index_fingerprint") != metadata.get("index_fingerprint")
                or not isinstance(manifest.get("module_name"), str) or not isinstance(manifest.get("mirrors"), dict)
                or manifest["mirrors"].get("manifest") != path):
            raise ImpactError("invalid_index", "Target manifest does not match companion index; rerun index")
        selected = _selection(manifest, source, level, names, root, tests_dir)
        unit: set[str] = set()
        interaction: set[str] = set()
        missing: list[dict[str, Any]] = []
        for row in selected:
            for tier, key in (("unit", "unit_test"), ("interaction", "interaction_test")):
                # The target's integration/interaction tests join at Level 1;
                # its unit tests are available immediately at Level 0.
                if row["level"] == 0 and tier == "interaction" and level == 0:
                    continue
                file = row[key]
                if file is None:
                    continue
                if (root / file).is_file():
                    (unit if tier == "unit" else interaction).add(file)
                else:
                    missing.append({"source_file": row["source_file"], "level": row["level"],
                                    "tier": tier, "path": file})
        registry = _registered(root, tests_root, metadata, selected, names)
        warnings = []
        warnings_by_source = metadata.get("warnings_by_source", {})
        if not isinstance(warnings_by_source, dict):
            raise ImpactError("invalid_index", "Corrupt persisted analysis warning metadata")
        for row in selected:
            recorded = warnings_by_source.get(row["source_file"], [])
            if not isinstance(recorded, list) or any(not isinstance(item, dict) for item in recorded):
                raise ImpactError("invalid_index", "Corrupt persisted source diagnostics")
            warnings.extend(recorded)
        warnings = sorted(warnings, key=lambda d: (d.get("file") or "", d.get("line") or 0, d.get("code") or ""))
        return {
            "status": "impact_selected", "exit_code": 0,
            "message": (f"Selected {len(unit)} unit and {len(interaction)} interaction tests "
                        f"for {len(selected)} affected source modules at Level {level}; "
                        f"{len(missing)} expected test files missing"),
            "target": {"source_file": source, "module_name": manifest["module_name"]},
            "level": level, "index_fingerprint": metadata["index_fingerprint"],
            "affected_sources": [{"source_file": row["source_file"], "module_name": row["module_name"],
                                  "level": row["level"]} for row in selected],
            "tests": {"unit": sorted(unit), "interaction": sorted(interaction),
                      "missing": sorted(missing, key=lambda x: (x["level"], x["tier"], x["path"]))},
            "verification": registry,
            "warnings": warnings,
            "analysis_limits": {"dynamic_references": manifest.get("dynamic_references", []),
                                "external_dependencies": manifest.get("external_dependencies", [])},
        }
    except ImpactError as exc:
        return {"status": "impact_failed", "exit_code": 1, "error_code": exc.code,
                "message": str(exc), "target": {"requested": target}, "level": level}
