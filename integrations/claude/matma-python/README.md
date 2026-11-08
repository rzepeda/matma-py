# Claude Code / Claude.ai installation

This folder is self-contained: keep `SKILL.md` together with `references/`.

- **Claude Code repository installation:** copy this entire `matma-python`
  directory into `<PYTHON_PROJECT>/.claude/skills/matma-python/`.
- **Claude Code personal installation:** `~/.claude/skills/matma-python/`.
- **Claude.ai custom skills:** ZIP this `matma-python/` directory and upload
  it in `Customize > Skills` when your plan/settings allow custom skills.

Ask Claude Code: `Use /matma-python to validate the project, index its
imports and find tests affected by src/pkg/service.py at level 2.`

This is an **instruction skill**, not the MATMA Python CLI itself. Install
MATMA in your development environment as described in
`references/MATMA_CLI.md`.
