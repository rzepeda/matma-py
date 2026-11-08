# Google Antigravity installation

This folder is an Antigravity workspace **Agent Skill**.

- **Current native workspace path:** copy `matma-python-antigravity/` into
  `<PYTHON_PROJECT>/.agents/skills/matma-python-antigravity/`.
- **Global Antigravity path:** `~/.gemini/config/skills/matma-python-antigravity/`.
- The older `.agent/skills/` layout may still work, but prefer `.agents/skills/`.
- Open the Python workspace in Antigravity and ask:
  `Use matma-python-antigravity to index the repository and identify pytest
  tests impacted by a change in src/pkg/service.py at level 2.`

This is a skill manifest, not an Antigravity-specific executable plugin.
MATMA CLI installation and usage are in `references/MATMA_CLI.md`.
