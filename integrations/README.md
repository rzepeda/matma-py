# MATMA Python — ready-to-install coding-agent skills

Three **independent**, self-contained skill directories accompany the MATMA
Python CLI. Each has its own `SKILL.md`, `README.md` and copy of the same
verified MATMA CLI reference, so it still works when installed alone.

```text
integrations/
├── install_skills.py
├── claude/matma-python/
│   ├── SKILL.md
│   ├── README.md
│   └── references/MATMA_CLI.md
├── chatgpt/matma-python-chatgpt/
│   ├── SKILL.md
│   ├── README.md
│   ├── agents/openai.yaml
│   └── references/MATMA_CLI.md
└── antigravity/matma-python-antigravity/
    ├── SKILL.md
    ├── README.md
    └── references/MATMA_CLI.md
```

## Install the MATMA tool in a Python project

MATMA is an installable developer tool, **not** included in these skills.
It requires Python 3.11+. In an activated project virtual environment:

```bash
python -m pip install "git+https://github.com/rzepeda/matma-py.git@main"
python -m pip install pytest
python -m matma --help
```

For an offline/local MATMA checkout, use
`python -m pip install -e /path/to/matma-py` instead. MATMA is at development
version `0.1.0.dev0` and is not published to PyPI. Review the repository's
license status before redistributing the package; no license grant is assumed.

## Install the three skills into your Python project

With a checkout of this repository, run from any directory:

```bash
python /path/to/matma-py/integrations/install_skills.py --project /path/to/consumer --platform all
```

`--platform` also accepts `claude`, `chatgpt` or `antigravity` to install a
single skill. `--dry-run` displays destinations without copying. The
installer refuses to replace different existing content or follow symlinks;
repeat installation is safe and unchanged files are skipped. **The installer
never installs MATMA or invokes pip.**

| Platform | Project-relative install path | How to invoke |
| --- | --- | --- |
| Claude Code | `.claude/skills/matma-python/` | `/matma-python` |
| ChatGPT desktop / Codex | `.agents/skills/matma-python-chatgpt/` | `$matma-python-chatgpt` in Codex |
| Google Antigravity | `.agents/skills/matma-python-antigravity/` | Ask the Antigravity agent to use the skill |

ChatGPT and Antigravity share the **modern `.agents/skills` parent** but use
distinct skill folder names, allowing installation side-by-side. Agent
availability/discovery depends on the host product and workspace. A local
Codex skill does not automatically activate in an ordinary ChatGPT web chat.

## MATMA daily workflow

From the root of your *consumer Python project*, not from this skill folder:

```bash
python -m matma validate --check -o json
python -m matma index -o json
python -m matma scaffold --target pkg.service -o json
python -m matma impact --target pkg.service --level 2 -o json
# Only run pytest explicitly on existing paths reported by MATMA, after
# replacing generated pytest.fail placeholders with real assertions.
python -m pytest tests/unit/mirror/src/pkg/test_service.py
```

- `validate`: analyzes modules without writing files.
- `index`: writes owned YAML manifests for the **full** dependency graph.
- `scaffold`: creates missing test/mock starters for a selected source
  module. Existing files are never overwritten. Starters deliberately fail.
- `impact`: reads manifests, checks index freshness, and selects *existing*
  unit/interaction tests and explicit business/regression registrations.
  It does not run any tests. Actual usage is Level 1; an unused import is
  Level 2. Missing tests are separately reported.

See each skill's own `references/MATMA_CLI.md` for exact flags, optional
`tests/matma-verification.yaml` registry, and error recovery.

## Distribution notes

- **Claude.ai:** upload the standalone Claude skill ZIP when supported.
- **ChatGPT web:** for automatic product-wide discovery, a plugin/skill
  integration is required; standalone folders are directly usable by
  ChatGPT desktop/Codex. Simply attaching a file in chat is a manual
  reference, not a persistent local installation.
- **Antigravity:** the modern workspace path is `.agents/skills/` and
  user-wide is `~/.gemini/config/skills/`.

Official documentation: [Claude Code skills](https://claude.com/resources/articles/steering-claude-code-skills-hooks-rules-subagents-and-more), [OpenAI skills](https://learn.chatgpt.com/docs/build-skills), [Antigravity skills](https://antigravity.google/docs/skills).
