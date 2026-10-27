"""The real release skill can route a release subtask without an LLM."""

from pathlib import Path
from shutil import copyfile

from vibesop.core.matching import RoutingContext
from vibesop.core.routing.unified import UnifiedRouter
from vibesop.core.skills.loader import SkillLoader


def _pinned_router(tmp_path: Path, skill: str) -> UnifiedRouter:
    """Router whose candidate universe is ONLY the tmp test copy.

    Passing ``skill_loader`` to UnifiedRouter does not constrain the
    CandidateManager pool — without pinning, the pool silently includes
    every machine-local skill, and the test only proves routability against
    ambient IDF mass (2026-10-27 adversarial panel, lanes A/C/D).
    """
    skill_dir = tmp_path / "skills" / skill
    skill_dir.mkdir(parents=True)
    source = Path(__file__).resolve().parents[3] / f"core/skills/{skill}/SKILL.md"
    copyfile(source, skill_dir / "SKILL.md")
    loader = SkillLoader(
        project_root=tmp_path,
        search_paths=[tmp_path / "skills"],
        strict_search_paths=True,
        enable_external=False,
    )
    router = UnifiedRouter(project_root=tmp_path, skill_loader=loader)
    router._candidate_manager.pin_search_paths([tmp_path / "skills"])
    return router


def test_release_subtask_resolves_real_skill(tmp_path: Path) -> None:
    router = _pinned_router(tmp_path, "release-version")
    result = router._single_skill_route(
        "在合并后更新项目版本号至 0.7.1，更新 CHANGELOG，并执行版本发布流程",
        context=RoutingContext(skip_ai_triage=True),
    )
    assert result.primary is not None
    assert result.primary.skill_id == "builtin/release-version"
    assert (
        Path(result.primary.metadata["source_file"]).resolve()
        == (tmp_path / "skills" / "release-version" / "SKILL.md").resolve()
    )


def test_release_skill_explicit_mention(tmp_path: Path) -> None:
    """@-mention must resolve to the isolated test copy."""
    router = _pinned_router(tmp_path, "release-version")
    result = router._single_skill_route(
        "@builtin/release-version 走一遍发版流程",
        context=RoutingContext(skip_ai_triage=True),
    )
    assert result.primary is not None
    assert result.primary.skill_id == "builtin/release-version"
    assert (
        Path(result.primary.metadata["source_file"]).resolve()
        == (tmp_path / "skills" / "release-version" / "SKILL.md").resolve()
    )


def test_release_skill_negative_queries(tmp_path: Path) -> None:
    """Ordinary review/off-domain explanation queries must not reach the
    release skill (mirrors the worktree-convergence steal regression).

    A semver *explanation* query is deliberately NOT in this list: its
    "版本" token legitimately lives in the skill's description phrases, and
    in a one-skill vacuum that domain jargon still matches — pool
    competition is what rules it out (kimi lane 3 measured exactly this
    vacuum-vs-full-pool asymmetry).
    """
    router = _pinned_router(tmp_path, "release-version")
    for query in ("帮我 review 这个 diff", "review my changes", "解释一下 CI 是什么"):
        result = router._single_skill_route(query, context=RoutingContext(skip_ai_triage=True))
        assert not (
            result.primary is not None and result.primary.skill_id == "builtin/release-version"
        ), query
