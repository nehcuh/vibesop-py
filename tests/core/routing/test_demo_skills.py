"""Block-2 demo skills: discovery, registry wiring, and keyless routing.

The four demo skills (systematic-debugging / test-generation / code-review /
commit-message) must be hittable by natural language on a fresh keyless
install — no LLM, and (per gate46 v2 A6) no embedding dependency either.
"""

from __future__ import annotations

import os
from pathlib import Path

# Must be set before any sentence_transformers/HF import: on machines without
# a cached MiniLM this makes the embedding layer fail fast (keyword layers
# still catch the demo queries) instead of stalling on a network download.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from typing import TYPE_CHECKING

import yaml

from vibesop.core.config.manager import ConfigManager

if TYPE_CHECKING:
    import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_SKILLS = ("systematic-debugging", "test-generation", "code-review", "commit-message")

# Verified routing floor: every pair hits its builtin skill with NO LLM and
# NO embedding model available (HF_HUB_OFFLINE=1, empty cache).
VERIFIED_DEMO_QUERIES: list[tuple[str, str]] = [
    ("why is this broken", "builtin/systematic-debugging"),
    ("这个函数出问题了，帮我排查根因", "builtin/systematic-debugging"),
    ("write unit tests for this module", "builtin/test-generation"),
    # ZH sentence deliberately avoids the substring "测试" — the qa_cycling
    # scenario owns that keyword (CJK substring match) and would hijack the
    # query to omx/ultraqa on pack-loaded machines (gate46 A7 / R7).
    ("给这个函数补一组单元用例", "builtin/test-generation"),
    ("look over my changes before I push", "builtin/code-review"),
    ("帮我看看这次改动有没有问题", "builtin/code-review"),
    ("help me write a commit message", "builtin/commit-message"),
    ("帮我写提交信息", "builtin/commit-message"),
]

# gate46 dual-review 误伤面档案 (pi P1-5): common queries that REAL pack
# skills own. "write tests" is superpowers/TDD's keyword; the bare phrase
# was moved from builtin/test-generation tags to triggers (explicit layer
# only) so keyless keyword routing cannot steal it on pack machines.
# What we pin: the KEYWORD layer must not fire for the builtin (pi measured
# a 1.00-confidence steal before the tag was moved). Below keyword, the
# 0.3-0.5 levenshtein fallback may pick any semantically-plausible candidate
# — that tier is pre-existing ownerless-query noise, not a steal.
PACK_OWNED_QUERIES: list[tuple[str, str]] = [
    ("write tests", "superpowers/test-driven-development"),
]


def _isolate_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_packs: bool
) -> Path:
    """Point HOME (env + Path.home + ExternalSkillLoader.EXTERNAL_PATHS —
    the class var binds to the real home at import) at a scratch dir,
    optionally seeded with realistic fake pack skills."""
    from vibesop.core.skills.external_loader import ExternalSkillLoader

    home = tmp_path / ("home-packs" if with_packs else "home-empty")
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(
        ExternalSkillLoader, "EXTERNAL_PATHS", [home / ".claude" / "skills"]
    )
    if with_packs:
        pack_skills = {
            ("superpowers", "systematic-debugging"): (
                "Systematic debugging with root cause focus",
                ["debugging", "root cause", "systematic debug", "排查", "根因"],
            ),
            ("superpowers", "debug"): (
                "Advanced debugging workflow for complex bugs",
                ["debug", "bug", "debugging workflow", "调试", "bug 排查"],
            ),
            ("superpowers", "test-driven-development"): (
                "TDD red-green-refactor workflow",
                ["tdd", "write tests", "test first", "red green refactor", "测试驱动"],
            ),
            ("omx", "ultraqa"): (
                "QA loop orchestration",
                ["qa loop", "测试", "qa 循环", "ultraqa"],
            ),
            ("omx", "build-fix"): (
                "Fix build errors and compile failures",
                ["build error", "fix error", "修复构建", "编译错误"],
            ),
            ("omx", "note"): (
                "Write release notes from commits",
                ["release note", "changelog", "发行说明", "版本说明"],
            ),
        }
        for (pack, name), (desc, tags) in pack_skills.items():
            skill_dir = home / ".claude" / "skills" / pack / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nid: {pack}/{name}\nname: {name}\ndescription: {desc}\n"
                f"tags: [{', '.join(tags)}]\n---\n\n# {name}\n{desc}\n",
                encoding="utf-8",
            )
    return home


class TestDemoSkillFiles:
    def test_all_demo_skill_dirs_exist(self) -> None:
        for name in DEMO_SKILLS:
            skill_file = REPO_ROOT / "core" / "skills" / name / "SKILL.md"
            assert skill_file.exists(), f"missing {skill_file}"

    def test_frontmatter_wellformed(self) -> None:
        for name in DEMO_SKILLS:
            text = (REPO_ROOT / "core" / "skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            )
            assert text.startswith("---"), f"{name}: missing frontmatter"
            fm = yaml.safe_load(text.split("---", 2)[1])
            assert fm["id"] == f"builtin/{name}"
            # R2': multi-word bilingual tags are the keyless hit path.
            tags = fm["tags"]
            assert len(tags) >= 8, f"{name}: tags too thin for keyword routing"
            has_cjk = any(any("一" <= ch <= "鿿" for ch in t) for t in tags)
            assert has_cjk, f"{name}: no Chinese tags (zh queries would miss)"


class TestDemoSkillRegistry:
    def test_registry_entries_load(self) -> None:
        skills = {s["id"]: s for s in ConfigManager().get_all_skills(force_reload=True)}
        for name in DEMO_SKILLS:
            entry = skills.get(name)
            assert entry is not None, f"{name} missing from registry"
            assert entry["namespace"] == "builtin"
            assert entry["entrypoint"] == f"skills/{name}/SKILL.md"
            # A10: demo skills must deploy to grok-build too.
            targets = entry.get("supported_targets", {})
            assert "grok-build" in targets, f"{name}: grok-build missing from targets"


class TestDemoSkillKeylessRouting:
    def test_verified_demo_queries_hit(self, tmp_path, monkeypatch) -> None:
        """The documented demo queries must hit their builtin skill with
        skip_ai_triage and no embedding model — the fresh-install floor.

        project_root is a scratch dir (not this repo) and HOME is isolated
        (no packs) so the floor holds on any developer machine, not just a
        clean CI runner.
        """
        from vibesop.core.routing.lightweight_api import LightweightRouter

        _isolate_home(tmp_path, monkeypatch, with_packs=False)
        router = LightweightRouter(project_root=tmp_path / "project")
        misses: list[str] = []
        for query, expected in VERIFIED_DEMO_QUERIES:
            result = router.route(query)
            got = result.get("skill_id") or ""
            if got != expected:
                misses.append(f"{query!r} -> {got} (want {expected})")
        assert not misses, "demo query misses:\n  " + "\n  ".join(misses)


class TestDemoSkillDualStateRouting:
    """R7 (gate46 exit criterion 1): demo queries keep hitting their builtin
    skill even when the user has community packs installed — the adoption GIF
    must not break on existing superpowers/omx users."""

    def _router_with_packs(self, tmp_path, monkeypatch):
        from vibesop.core.routing.lightweight_api import LightweightRouter

        _isolate_home(tmp_path, monkeypatch, with_packs=True)
        router = LightweightRouter(project_root=tmp_path / "project")
        router._get_router()
        pool_ids = [c.get("id") for c in router._router._candidate_manager.get_candidates()]
        # Non-vacuous guard: the fixture packs must actually be in the pool —
        # isolation bugs (e.g. EXTERNAL_PATHS binding at import) silently turn
        # this whole class into a no-pack rerun.
        for ns in ("superpowers/", "omx/"):
            assert any(i.startswith(ns) for i in pool_ids), (
                f"fixture {ns}* not discovered — dual-state test is vacuous (pool: {pool_ids})"
            )
        return router

    def test_demo_queries_hit_with_packs_installed(self, tmp_path, monkeypatch) -> None:
        router = self._router_with_packs(tmp_path, monkeypatch)
        misses: list[str] = []
        for query, expected in VERIFIED_DEMO_QUERIES:
            got = router.route(query).get("skill_id") or ""
            if got != expected:
                misses.append(f"{query!r} -> {got} (want {expected})")
        assert not misses, "demo query hijacked by installed packs:\n  " + "\n  ".join(misses)

    def test_pack_owned_queries_not_stolen_by_builtin(
        self, tmp_path, monkeypatch
    ) -> None:
        """误伤面档案 (pi P1-5): builtin demo skills must not keyword-own
        queries that installed pack skills own. Before the tag fix,
        `write tests` hit builtin/test-generation at 1.00 (keyword layer)
        because the bare phrase was a tag."""
        router = self._router_with_packs(tmp_path, monkeypatch)
        for query, owner in PACK_OWNED_QUERIES:
            result = router.route(query)
            got = result.get("skill_id") or ""
            layer = result.get("layer") or ""
            assert not (
                got.startswith("builtin/") and layer == "keyword"
            ), f"{query!r} keyword-stolen by {got} (owner: {owner})"
