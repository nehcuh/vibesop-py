"""Load, parse, and scan the bundled builtin/verify-result skill."""

from __future__ import annotations

from pathlib import Path

from vibesop.core.skills.loader import SkillLoader
from vibesop.core.skills.parser import extract_frontmatter, parse_skill_md
from vibesop.security.runtime_scan import is_skill_content_safe
from vibesop.utils.bundled import resolve_builtin_skills_dir

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_ID = "builtin/verify-result"


def _builtin_skills_dir() -> Path:
    return resolve_builtin_skills_dir(REPO_ROOT)


def _skill_dir() -> Path:
    return _builtin_skills_dir() / "verify-result"


def _skill_file() -> Path:
    return _skill_dir() / "SKILL.md"


def test_skill_file_ships_with_bundled_core_skills() -> None:
    path = _skill_file()
    assert path.is_file(), f"missing bundled skill at {path}"


def test_parser_reads_id_and_manual_invocation_limits() -> None:
    spec = parse_skill_md(_skill_dir())
    assert spec is not None
    assert spec.id == SKILL_ID
    assert spec.name == "verify-result"
    assert spec.namespace == "builtin"
    assert spec.disable_model_invocation is True
    assert spec.user_invocable is False
    assert spec.triggers == []
    assert spec.trigger_when == ""
    assert spec.routing_patterns == []
    assert spec.commands == []
    assert spec.tags == []


def test_loader_discovers_skill_from_bundled_skills_dir() -> None:
    skills_dir = _builtin_skills_dir()
    loader = SkillLoader(
        project_root=REPO_ROOT,
        search_paths=[skills_dir],
        strict_search_paths=True,
        enable_external=False,
    )
    loaded = loader.discover_all()
    assert SKILL_ID in loaded

    skill = loader.get_skill(SKILL_ID)
    assert skill is not None
    assert skill.metadata.id == SKILL_ID
    assert skill.metadata.disable_model_invocation is True
    assert skill.metadata.triggers == []
    assert skill.source_file is not None
    assert skill.source_file.resolve() == _skill_file().resolve()

    content = loader.read_skill_content(SKILL_ID)
    assert "只做验收" in content
    assert "disable-model-invocation: true" in content


def test_skill_body_and_full_file_pass_runtime_scan() -> None:
    content = _skill_file().read_text(encoding="utf-8")
    assert is_skill_content_safe(content) is True

    _frontmatter, body = extract_frontmatter(content)
    assert body
    assert is_skill_content_safe(body) is True
    assert "blocked" in body
    assert "failed" in body
    assert "passed" in body
