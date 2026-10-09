"""Tests for Skill Governance (Phase 3): enable/disable and scope enforcement."""

import json
from pathlib import Path

import pytest

from vibesop.core.routing.unified import UnifiedRouter
from vibesop.core.skills.config_manager import SkillConfigManager


def _isolate_config_and_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point auto-config and external skill roots at ``tmp_path``.

    ``SkillConfigManager`` writes a CWD-relative file. Leaving that pointed
    at the repo would persist test disables into the worktree and would make
    the candidate fingerprint depend on unrelated files.
    """
    from vibesop.core.skills.external_loader import ExternalSkillLoader

    config_file = tmp_path / ".vibe" / "skills" / "auto-config.yaml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(SkillConfigManager, "SKILL_CONFIG_FILE", config_file)

    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(ExternalSkillLoader, "EXTERNAL_PATHS", [home / ".claude" / "skills"])
    return config_file


def _router(tmp_path: Path) -> UnifiedRouter:
    router = UnifiedRouter(project_root=tmp_path)
    router._config.enable_ai_triage = False
    router._config.enable_embedding = False
    return router


def _open_deep_watch(router: UnifiedRouter) -> None:
    """Let the next route run the deep SKILL.md walk.

    One ``route()`` calls ``get_cached_candidates`` more than once. The later
    call sees no change and arms the 5s interval, so a follow-up route skips
    the body scan. This only rewinds that interval. The candidate list and
    ``SkillLoader._skill_cache`` stay populated; a refresh that forgets to
    drop them still returns the old description.
    """
    router._candidate_manager._last_reload_check = 0.0


@pytest.fixture
def router_with_skills(tmp_path, monkeypatch):
    """Router with a local project skill and a builtin skill."""
    _isolate_config_and_home(tmp_path, monkeypatch)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "vibesop"\n', encoding="utf-8")
    (tmp_path / ".vibe").mkdir(exist_ok=True)
    (tmp_path / ".vibe" / "skills").mkdir(exist_ok=True)

    # Create a local project skill
    local_skill_dir = tmp_path / ".vibe" / "skills" / "my-local-skill"
    local_skill_dir.mkdir(parents=True)
    (local_skill_dir / "SKILL.md").write_text(
        "---\nname: my-local-skill\ndescription: Run local task\n"
        "intent: Run local task\ntags: [run, local, task]\n---\n# My Local Skill\n",
        encoding="utf-8",
    )

    # Create a builtin skill in the temp project tree (simulating builtin)
    builtin_skill_dir = tmp_path / "core" / "skills" / "systematic-debugging"
    builtin_skill_dir.mkdir(parents=True)
    (builtin_skill_dir / "SKILL.md").write_text(
        "---\nname: systematic-debugging\nintent: Debug systematically\n---\n# Systematic Debugging\n",
        encoding="utf-8",
    )

    from vibesop.core.config.manager import ConfigManager

    manager = ConfigManager(project_root=tmp_path)
    router = UnifiedRouter(project_root=tmp_path, config=manager)
    router._config.enable_ai_triage = False
    return router


class TestSkillEnablement:
    """Test enable/disable filtering in routing."""

    def test_disabled_skill_excluded_from_routing(self, router_with_skills):
        """Skills with enabled=False stay unroutable, including explicit !id.

        The pool is whatever the public route path loaded. Nothing clears
        ``_candidates_cache`` or ``SkillLoader._skill_cache`` from the test.
        """
        SkillConfigManager.update_skill_config("my-local-skill", {"enabled": False})
        try:
            result = router_with_skills.route(
                "!my-local-skill run local task",
                record_telemetry=False,
            )
            assert result.primary is None or result.primary.skill_id != "my-local-skill"
        finally:
            SkillConfigManager.update_skill_config("my-local-skill", {"enabled": True})

    def test_disable_hides_skill_on_hot_route_and_disk_cache_hit(
        self, router_with_skills, tmp_path
    ):
        """D04: update_skill_config(enabled=False) then route().

        The same process must drop the skill on the next route, and a new
        process must not revive it from ``candidates_v2.json``. A third
        router proves the rebuilt file is a disk-cache hit, not another rescan
        that happens to agree.
        """
        hot = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert hot.primary is not None
        assert hot.primary.skill_id == "my-local-skill"

        # Arm the 5s filesystem watch, then disable. Governance must still
        # win on the next route; the interval must not keep the old enabled bit.
        router_with_skills.route("!my-local-skill run local task", record_telemetry=False)
        SkillConfigManager.update_skill_config("my-local-skill", {"enabled": False})
        try:
            again = router_with_skills.route(
                "!my-local-skill run local task",
                record_telemetry=False,
            )
            assert again.primary is None or again.primary.skill_id != "my-local-skill"
            hot_ids = {
                c["id"] for c in router_with_skills._candidate_manager.get_cached_candidates()
            }
            assert "my-local-skill" not in hot_ids

            cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            manager = router_with_skills._candidate_manager
            assert payload["paths_hash"] == manager._compute_paths_hash(manager._search_paths)
            assert all(c.get("id") != "my-local-skill" for c in payload["candidates"])

            payload["candidates"].append(
                {
                    "id": "disk-cache-sentinel",
                    "enabled": True,
                    "description": "hit",
                    "lifecycle": "active",
                    "scope": "global",
                    "source_file": str(
                        tmp_path / ".vibe" / "skills" / "my-local-skill" / "SKILL.md"
                    ),
                }
            )
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            stamped = cache_path.stat().st_mtime_ns

            fresh = _router(tmp_path)
            fresh_ids = {c["id"] for c in fresh._candidate_manager.get_cached_candidates()}
            assert "my-local-skill" not in fresh_ids
            assert "disk-cache-sentinel" in fresh_ids
            assert cache_path.stat().st_mtime_ns == stamped

            cold = fresh.route("!my-local-skill run local task", record_telemetry=False)
            assert cold.primary is None or cold.primary.skill_id != "my-local-skill"
        finally:
            SkillConfigManager.update_skill_config("my-local-skill", {"enabled": True})

    def test_enabled_skill_included_in_routing(self, router_with_skills):
        """Skills with enabled=True (default) should be available."""
        # Use explicit syntax to bypass prefilter/levenshtein complexities in test
        result = router_with_skills.orchestrate("!my-local-skill run local task")
        assert result.primary is not None
        assert result.primary.skill_id == "my-local-skill"


class TestSkillScope:
    """Test project vs global scope filtering."""

    def test_project_scoped_skill_available_in_project(self, router_with_skills):
        """Project-scoped skills from the current project should be routable."""
        # Set local skill to project scope
        SkillConfigManager.update_skill_config("my-local-skill", {"scope": "project"})

        # Use explicit syntax to bypass prefilter/levenshtein complexities in test
        result = router_with_skills.orchestrate("!my-local-skill run local task")
        assert result.primary is not None
        assert result.primary.skill_id == "my-local-skill"

        SkillConfigManager.update_skill_config("my-local-skill", {"scope": "global"})

    def test_scope_and_archive_refresh_hot_and_fresh_routes(self, router_with_skills, tmp_path):
        """Scope and lifecycle edits follow the same path as enabled=False."""
        first = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert first.primary is not None
        assert first.primary.skill_id == "my-local-skill"

        SkillConfigManager.update_skill_config("my-local-skill", {"scope": "project"})
        try:
            scoped = router_with_skills.route(
                "!my-local-skill run local task",
                record_telemetry=False,
            )
            assert scoped.primary is not None
            assert scoped.primary.skill_id == "my-local-skill"
            hot_scope = next(
                c
                for c in router_with_skills._candidate_manager.get_cached_candidates()
                if c["id"] == "my-local-skill"
            )
            assert hot_scope["scope"] == "project"

            fresh = _router(tmp_path)
            fresh_scope = next(
                c
                for c in fresh._candidate_manager.get_cached_candidates()
                if c["id"] == "my-local-skill"
            )
            assert fresh_scope["scope"] == "project"
            fresh_hit = fresh.route("!my-local-skill run local task", record_telemetry=False)
            assert fresh_hit.primary is not None
            assert fresh_hit.primary.skill_id == "my-local-skill"
        finally:
            SkillConfigManager.update_skill_config("my-local-skill", {"scope": "global"})

        SkillConfigManager.update_skill_config("my-local-skill", {"lifecycle": "archived"})
        try:
            archived = router_with_skills.route(
                "!my-local-skill run local task",
                record_telemetry=False,
            )
            assert archived.primary is None or archived.primary.skill_id != "my-local-skill"
            cold = _router(tmp_path)
            cold_ids = {c["id"] for c in cold._candidate_manager.get_cached_candidates()}
            assert "my-local-skill" not in cold_ids
            cold_route = cold.route("!my-local-skill run local task", record_telemetry=False)
            assert cold_route.primary is None or cold_route.primary.skill_id != "my-local-skill"
        finally:
            SkillConfigManager.update_skill_config("my-local-skill", {"lifecycle": "active"})

    def test_same_mtime_yaml_disable_hides_skill_hot_and_fresh(self, router_with_skills, tmp_path):
        """R1: same-mtime auto-config edit is visible to reader, hot, and disk."""
        import os

        from vibesop.core.skills.config_manager import _CONFIG_FILE_CACHE

        config = SkillConfigManager.SKILL_CONFIG_FILE
        config.write_text(
            "skills:\n  my-local-skill:\n    enabled: true\n",
            encoding="utf-8",
        )
        first = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert first.primary is not None
        assert first.primary.skill_id == "my-local-skill"

        stamp = config.stat()
        config.write_text(
            "skills:\n  my-local-skill:\n    enabled: false\n",
            encoding="utf-8",
        )
        os.utime(config, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

        hot = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert hot.primary is None or hot.primary.skill_id != "my-local-skill"
        hot_ids = {c["id"] for c in router_with_skills._candidate_manager.get_cached_candidates()}
        assert "my-local-skill" not in hot_ids
        assert SkillConfigManager.get_skill_config("my-local-skill").enabled is False

        _CONFIG_FILE_CACHE.clear()
        fresh = _router(tmp_path)
        fresh_ids = {c["id"] for c in fresh._candidate_manager.get_cached_candidates()}
        assert "my-local-skill" not in fresh_ids
        assert SkillConfigManager.get_skill_config("my-local-skill").enabled is False
        cold = fresh.route("!my-local-skill run local task", record_telemetry=False)
        assert cold.primary is None or cold.primary.skill_id != "my-local-skill"

        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        assert all(c.get("id") != "my-local-skill" for c in payload["candidates"])

    def test_public_owner_hash_update_hides_skill_hot_and_fresh(self, router_with_skills, tmp_path):
        """R3: update_skill_config owner hash is honored by hot, fresh, and loader."""
        from vibesop.core.skills.loader import SkillLoader

        first = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert first.primary is not None
        assert first.primary.skill_id == "my-local-skill"

        loader = router_with_skills._candidate_manager._skill_loader
        own_hash = loader.project_hash
        SkillConfigManager.update_skill_config(
            "my-local-skill",
            {"scope": "project", "evaluation_context": {"project_hash": own_hash}},
        )
        owned = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert owned.primary is not None
        assert owned.primary.skill_id == "my-local-skill"

        SkillConfigManager.update_skill_config(
            "my-local-skill",
            {"evaluation_context": {"project_hash": "another-project"}},
        )
        hot = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert hot.primary is None or hot.primary.skill_id != "my-local-skill"
        hot_ids = {c["id"] for c in router_with_skills._candidate_manager.get_cached_candidates()}
        assert "my-local-skill" not in hot_ids

        fresh = _router(tmp_path)
        fresh_ids = {c["id"] for c in fresh._candidate_manager.get_cached_candidates()}
        assert "my-local-skill" not in fresh_ids
        cold = fresh.route("!my-local-skill run local task", record_telemetry=False)
        assert cold.primary is None or cold.primary.skill_id != "my-local-skill"

        raw = SkillLoader(
            tmp_path,
            search_paths=[tmp_path / ".vibe" / "skills"],
            enable_external=False,
            strict_search_paths=True,
        ).discover_all()
        assert "my-local-skill" not in raw
        disk = SkillConfigManager.get_skill_config("my-local-skill")
        assert disk.evaluation_context.get("project_hash") == "another-project"
        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        assert all(c.get("id") != "my-local-skill" for c in payload["candidates"])

    def test_project_scoped_skill_filtered_outside_project(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ):
        """Project-scoped skills should be excluded when routing from a different project."""
        _isolate_config_and_home(tmp_path, monkeypatch)
        # Create two project roots
        project_a = tmp_path / "project_a"
        project_b = tmp_path / "project_b"
        (project_a / ".vibe" / "skills").mkdir(parents=True)
        (project_b / ".vibe").mkdir(parents=True)

        # Create a skill in project A
        skill_dir = project_a / ".vibe" / "skills" / "project-a-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: project-a-skill\nintent: Do project A thing\n---\n# Project A Skill\n",
            encoding="utf-8",
        )

        SkillConfigManager.update_skill_config("project-a-skill", {"scope": "project"})

        # Create router for project B - should not see project-a-skill
        from vibesop.core.config.manager import ConfigManager

        manager = ConfigManager(project_root=project_b)
        router_b = UnifiedRouter(project_root=project_b, config=manager)

        raw_candidates = router_b._get_candidates()
        {c["id"] for c in raw_candidates}

        # The skill may be discovered (if SkillLoader searches broadly),
        # but should be filtered at route time
        result = router_b.orchestrate("do project A thing")
        if result.primary:
            assert result.primary.skill_id != "project-a-skill"

        SkillConfigManager.update_skill_config("project-a-skill", {"scope": "global"})

    def test_global_skill_always_available(self, router_with_skills):
        """Global-scoped skills should be available regardless of project."""
        # Builtin skills are global by default
        result = router_with_skills.orchestrate("!systematic-debugging debug systematically")
        assert result.primary is not None
        assert result.primary.skill_id == "systematic-debugging"


class TestSkillBodyRefresh:
    """D05: SKILL.md edits show up through auto-refresh and explicit reload."""

    def test_description_edit_auto_refresh_and_explicit_reload(self, router_with_skills, tmp_path):
        skill = tmp_path / ".vibe" / "skills" / "my-local-skill" / "SKILL.md"
        first = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert first.primary is not None
        assert first.primary.description == "Run local task"

        skill.write_text(
            "---\nname: my-local-skill\ndescription: Edited description\n"
            "intent: Run local task\ntags: [run, local, task]\n---\n# edited\n",
            encoding="utf-8",
        )
        # The first route already armed the 5s deep walk. While that gate is
        # shut the previous body is served; opening it is what auto-refresh is.
        held = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert held.primary is not None
        assert held.primary.description == "Run local task"
        _open_deep_watch(router_with_skills)
        refreshed = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert refreshed.primary is not None
        assert refreshed.primary.skill_id == "my-local-skill"
        assert refreshed.primary.description == "Edited description"

        skill.write_text(
            "---\nname: my-local-skill\ndescription: Reloaded description\n"
            "intent: Run local task\ntags: [run, local, task]\n---\n# reloaded\n",
            encoding="utf-8",
        )
        # Auto-refresh just re-armed the interval. Explicit reload must not
        # wait it out, and must not store the previous body under the new hash.
        assert router_with_skills._candidate_manager._last_reload_check != 0.0
        router_with_skills.reload_candidates()
        reloaded = router_with_skills.route(
            "!my-local-skill run local task",
            record_telemetry=False,
        )
        assert reloaded.primary is not None
        assert reloaded.primary.description == "Reloaded description"

        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        manager = router_with_skills._candidate_manager
        assert payload["paths_hash"] == manager._compute_paths_hash(manager._search_paths)
        cached = next(c for c in payload["candidates"] if c["id"] == "my-local-skill")
        assert cached["description"] == "Reloaded description"
        assert all(c.get("description") != "Edited description" for c in payload["candidates"])
        assert all(c.get("description") != "Run local task" for c in payload["candidates"])

    def test_add_and_delete_refresh_the_pool(self, router_with_skills, tmp_path):
        router_with_skills.route("!my-local-skill run local task", record_telemetry=False)
        added = tmp_path / ".vibe" / "skills" / "added-skill"
        added.mkdir()
        (added / "SKILL.md").write_text(
            "---\nname: added-skill\ndescription: Newly added\n---\n# added\n",
            encoding="utf-8",
        )
        _open_deep_watch(router_with_skills)
        seen = router_with_skills.route("!added-skill use it", record_telemetry=False)
        assert seen.primary is not None
        assert seen.primary.skill_id == "added-skill"
        assert seen.primary.description == "Newly added"

        (added / "SKILL.md").unlink()
        # Delete goes through explicit reload while the deep-walk interval is
        # still armed by the route that discovered the new skill.
        assert router_with_skills._candidate_manager._last_reload_check != 0.0
        router_with_skills.reload_candidates()
        gone = router_with_skills.route("!added-skill use it", record_telemetry=False)
        assert gone.primary is None or gone.primary.skill_id != "added-skill"
        ids = {c["id"] for c in router_with_skills._candidate_manager.get_cached_candidates()}
        assert "added-skill" not in ids

        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        assert all(c.get("id") != "added-skill" for c in payload["candidates"])


class TestDisableModelInvocation:
    """Fail-closed A-5: explicit-only skills stay reachable by name only."""

    def test_explicit_reaches_invocation_disabled_skill(self, tmp_path, monkeypatch):
        _isolate_config_and_home(tmp_path, monkeypatch)
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "vibesop"\n', encoding="utf-8")
        skill_dir = tmp_path / "core" / "skills" / "explicit-only-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: explicit-only-skill\n"
            "description: Probe spec gaps for the xyzzy-plugh ritual\n"
            "disable-model-invocation: true\n---\n# explicit only\n",
            encoding="utf-8",
        )
        router = _router(tmp_path)
        from vibesop.core.routing.matcher_pipeline import (
            filter_invocation_disabled_candidates,
            invocation_disabled_skill_ids,
        )

        explicit = router.route("!explicit-only-skill do it", record_telemetry=False)
        assert explicit.primary is not None
        assert explicit.primary.skill_id == "explicit-only-skill"

        auto = router.route(
            "please handle the xyzzy-plugh ritual now",
            record_telemetry=False,
        )
        assert auto.primary is None or auto.primary.skill_id != "explicit-only-skill"

        pool = router._candidate_manager.get_cached_candidates()
        assert any(c["id"] == "explicit-only-skill" and c["disable_model_invocation"] for c in pool)
        assert all(
            c["id"] != "explicit-only-skill" for c in filter_invocation_disabled_candidates(pool)
        )
        assert "explicit-only-skill" in invocation_disabled_skill_ids(router)


class TestSkillConfigDefaults:
    """Test SkillConfig default values."""

    def test_default_scope_is_global(self):
        """Default scope should be global so skills are universally available."""
        from vibesop.core.skills.config_manager import SkillConfig

        config = SkillConfig(skill_id="test-skill")
        assert config.scope == "global"
        assert config.enabled is True

    def test_default_enabled_is_true(self):
        """Default enabled should be True."""
        from vibesop.core.skills.config_manager import SkillConfig

        config = SkillConfig(skill_id="test-skill")
        assert config.enabled is True
