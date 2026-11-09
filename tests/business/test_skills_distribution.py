"""Test installable Claude, ChatGPT/Codex and Antigravity skill distributions."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / 'integrations' / 'install_skills.py'


def get_installer():
    spec = importlib.util.spec_from_file_location('matma_skill_installer', INSTALLER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('platform,expected', [
    ('claude', 'matma-python'),
    ('chatgpt', 'matma-python-chatgpt'),
    ('antigravity', 'matma-python-antigravity'),
])
def test_valid_independent_skill_structure(platform: str, expected: str) -> None:
    folder = ROOT / 'integrations' / platform / expected
    skill = (folder / 'SKILL.md').read_text(encoding='utf-8')
    assert skill.startswith('---\n')
    manifest = yaml.safe_load(skill.split('---', 2)[1])
    assert manifest['name'] == expected
    assert 0 < len(manifest['description']) <= 200
    assert (folder / 'references' / 'MATMA_CLI.md').is_file()
    assert (folder / 'README.md').is_file()
    assert 'pytest.fail' in (folder / 'references' / 'MATMA_CLI.md').read_text()


def test_install_all_then_skip_existing_files(tmp_path: Path) -> None:
    script = get_installer()
    created = script.install(tmp_path, list(script.SKILLS))
    assert len([s for s in created if s.startswith('created:')]) == 10
    assert (tmp_path / '.claude/skills/matma-python/SKILL.md').is_file()
    assert (tmp_path / '.agents/skills/matma-python-chatgpt/SKILL.md').is_file()
    assert (tmp_path / '.agents/skills/matma-python-antigravity/SKILL.md').is_file()
    assert (tmp_path / '.agents/skills/matma-python-chatgpt/agents/openai.yaml').is_file()
    again = script.install(tmp_path, list(script.SKILLS))
    assert len(again) == len(created)
    assert all(s.startswith('unchanged:') for s in again)


def test_dry_run_has_zero_side_effects(tmp_path: Path) -> None:
    script = get_installer()
    result = script.install(tmp_path, ['claude'], dry_run=True)
    assert all(s.startswith('would create:') for s in result)
    assert list(tmp_path.iterdir()) == []


def test_existing_user_file_is_never_overwritten_and_aborts_all(tmp_path: Path) -> None:
    script = get_installer()
    content = tmp_path / '.agents/skills/matma-python-chatgpt/SKILL.md'
    content.parent.mkdir(parents=True)
    content.write_text('user owned file\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Different file already exists'):
        script.install(tmp_path, ['claude','chatgpt','antigravity'])
    assert content.read_text(encoding='utf-8') == 'user owned file\n'
    assert not (tmp_path / '.claude').exists()


def test_symlink_destination_refused(tmp_path: Path) -> None:
    script = get_installer()
    exterior = tmp_path / 'external'
    exterior.mkdir()
    symlink = tmp_path / '.agents'
    try:
        symlink.symlink_to(exterior, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('Symlink creation unavailable in this test environment')
    with pytest.raises(ValueError, match='symlinked'):
        script.install(tmp_path, ['chatgpt'])
    assert list(exterior.iterdir()) == []


def test_missing_project_refused(tmp_path: Path) -> None:
    script = get_installer()
    with pytest.raises(ValueError, match='does not exist'):
        script.install(tmp_path / 'absent', ['claude'])
