# MATMA Python — Release Readiness and SemVer Checklist

**Status: PREPARATION ONLY.** No Git tag, PyPI upload, GitHub Release, or
publication of a distributable is authorized by Phase 6. The repository uses
**`0.1.0.dev0`** (PEP 440 pre-release/development version) in `pyproject.toml`.
All checks below must be revalidated on the exact approved release commit.

## Scope and compatibility gates

- [ ] Confirm project owner approves the target version and release scope.
- [ ] Choose and commit a license and complete package metadata, including
  any applicable legal notices and author/maintainer fields. **Currently no
  license grant is asserted.** Do not assume the repository is open source.
- [ ] Adopt the final compatibility policy (Python 3.11+ presently tested).
- [ ] Confirm the exact CLI and persisted YAML schema compatibility contract.
- [ ] Decide whether a change to `SCHEMA_VERSION` or required reindex is needed.
- [ ] Decide whether optional pytest/mock integration packages need bounds.

## Evidence gates

- [ ] All stacked PRs #1–#6 merged/reviewed in dependency order and CI green on
  the **actual target branch**, not only on each feature branch.
- [ ] Verify all Linux/Windows Python 3.11–3.13 CI jobs and reproducible
  installed-consumer `index → scaffold → validate → impact → pytest` checks.
- [ ] Confirm unit/integration/business/regression tests have meaningful
  assertions; generated placeholders **must** fail until authored.
- [ ] Review static analysis limitations and the human-owned verification
  registry, including import-only L2 behavior and dynamic diagnostics.
- [ ] Run benchmark on the release commit and record Python/OS/workload and
  both indexing and impact-with-freshness timings; no O(1) end-to-end claim.
- [ ] Re-run safety fixtures: symlinks, collisions, traversal, malformed
  manifests, CRLF, and explicit stale-index failures.

## Artifact and security gates

- [ ] On the approved commit, build wheel and sdist locally with
  `python -m build --no-isolation` and inspect the archive contents.
- [ ] Inspect wheel entry points: `matma-indexer = matma.cli:main`, and ensure
  no secret, developer cache, tests, or sensitive generated YAML is packaged.
- [ ] Check dependency metadata, reproducible clean installation, and
  `python -m pip check` in an isolated environment.
- [ ] Run a distribution-metadata check (e.g. `twine check dist/*`) once that
  release tooling has been explicitly installed and authorized.
- [ ] Confirm documentation and example commands reflect the release branch.
- [ ] Inspect vulnerabilities and supply-chain provenance for release assets.

## Publication gate (requires separate approval)

- [ ] Owner explicitly authorizes publishing and chooses destination (TestPyPI,
  PyPI, GitHub Release, or internal index) and credentials/permissions.
- [ ] Change `0.1.0.dev0` to the approved release version in source metadata;
  build/test the exact version, following SemVer for interface changes.
- [ ] Tag only the approved source commit and publish only approved artifacts.
- [ ] Verify the uploaded distribution, document migration/reindexing guidance,
  and record artifact checksums and release URL.

**Do not mark these approval gates complete merely because development CI
passes.** Phase 6 produces validation evidence and a candidate package build,
not a licensed, tagged, or published release.
