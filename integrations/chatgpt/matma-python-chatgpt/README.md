# ChatGPT desktop / Codex installation

This folder is a self-contained OpenAI skill for **ChatGPT desktop/Codex**.

- **Repository-local:** copy `matma-python-chatgpt/` to
  `<PYTHON_PROJECT>/.agents/skills/matma-python-chatgpt/`.
- **Personal:** `~/.agents/skills/matma-python-chatgpt/`.
- Use it in Codex as `$matma-python-chatgpt` or select it in a skills UI
  where supported. Optional `agents/openai.yaml` provides UI metadata.

A repository skill is **not automatically loaded by an ordinary ChatGPT web
conversation**. Web/mobile ChatGPT distribution requires an appropriate
plugin or supported skills integration, or the skill content can be
provided as reference instructions in the conversation. A skill cannot
run `python -m matma` without access to your project and execution tools.

The MATMA CLI must be installed separately; see `references/MATMA_CLI.md`.
