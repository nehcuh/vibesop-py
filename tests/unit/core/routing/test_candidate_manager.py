"""Tests for CandidateManager — filtering, caching, usage recording."""

from __future__ import annotations

import json
from pathlib import Path

from vibesop.core.routing.candidate_manager import CandidateManager


def _source_file(tmp_path: Path, skill_id: str) -> str:
    """Create a real SKILL.md so the candidate passes the routability gate."""
    path = tmp_path / "sources" / skill_id / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nid: {skill_id}\n---\n# body\n", encoding="utf-8")
    return str(path)


class TestFilterRoutable:
    """Test candidate filtering by enablement, scope, and lifecycle."""

    def test_enabled_candidate_passes(self, tmp_path: Path) -> None:
        """Enabled candidates pass through filter."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "test",
                "enabled": True,
                "lifecycle": "active",
                "scope": "global",
                "source_file": _source_file(tmp_path, "test"),
            }
        ]
        filtered, warnings = mgr.filter_routable(candidates)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "test"
        assert len(warnings) == 0

    def test_disabled_candidate_filtered_out(self, tmp_path: Path) -> None:
        """Disabled candidates are filtered out."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "enabled",
                "enabled": True,
                "lifecycle": "active",
                "scope": "global",
                "source_file": _source_file(tmp_path, "enabled"),
            },
            {"id": "disabled", "enabled": False, "lifecycle": "active", "scope": "global"},
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "enabled"

    def test_enabled_defaults_to_true(self, tmp_path: Path) -> None:
        """Missing 'enabled' key defaults to True (passes filter)."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "test",
                "lifecycle": "active",
                "scope": "global",
                "source_file": _source_file(tmp_path, "test"),
            }
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1

    def test_archived_lifecycle_filtered_out(self, tmp_path: Path) -> None:
        """ARCHIVED lifecycle is not routable (source_file backed — dropped by
        the lifecycle gate, not by the no-content gate)."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "old",
                "enabled": True,
                "lifecycle": "archived",
                "scope": "global",
                "source_file": _source_file(tmp_path, "old"),
            }
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 0

    def test_draft_lifecycle_filtered_out(self, tmp_path: Path) -> None:
        """DRAFT lifecycle is not routable (source_file backed)."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "draft",
                "enabled": True,
                "lifecycle": "draft",
                "scope": "global",
                "source_file": _source_file(tmp_path, "draft"),
            }
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 0

    def test_deprecated_is_not_routable(self, tmp_path: Path) -> None:
        """DEPRECATED lifecycle is NOT routable (source_file backed)."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "dep-skill",
                "enabled": True,
                "lifecycle": "deprecated",
                "scope": "global",
                "source_file": _source_file(tmp_path, "dep-skill"),
            }
        ]
        filtered, _warnings = mgr.filter_routable(candidates)
        # DEPRECATED is not routable — filtered out entirely
        assert len(filtered) == 0

    def test_project_scoped_within_project_passes(self, tmp_path: Path) -> None:
        """Project-scoped skill whose source_file is within project root passes."""
        project = tmp_path / "project"
        project.mkdir()
        skill_file = project / "skill.md"
        skill_file.write_text("", encoding="utf-8")
        mgr = CandidateManager(project)
        candidates = [
            {
                "id": "proj",
                "enabled": True,
                "lifecycle": "active",
                "scope": "project",
                "source_file": str(skill_file),
            }
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1

    def test_project_scoped_outside_project_filtered(self, tmp_path: Path) -> None:
        """Project-scoped skill outside project root is filtered out."""
        project = tmp_path / "project"
        project.mkdir()
        mgr = CandidateManager(project)
        external_file = tmp_path / "external" / "skill.md"
        external_file.parent.mkdir()
        external_file.write_text("", encoding="utf-8")
        candidates = [
            {
                "id": "ext",
                "enabled": True,
                "lifecycle": "active",
                "scope": "project",
                "source_file": str(external_file),
            }
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 0

    def test_invalid_lifecycle_defaults_to_active(self, tmp_path: Path) -> None:
        """Invalid lifecycle string defaults to ACTIVE (passes filter)."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "bad",
                "enabled": True,
                "lifecycle": "nonexistent",
                "scope": "global",
                "source_file": _source_file(tmp_path, "bad"),
            }
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1

    def test_multiple_candidates_mixed_filtering(self, tmp_path: Path) -> None:
        """Mixed candidates: enabled+active pass, disabled/archived/deprecated filtered."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "good1",
                "enabled": True,
                "lifecycle": "active",
                "scope": "global",
                "source_file": _source_file(tmp_path, "good1"),
            },
            {"id": "disabled", "enabled": False, "lifecycle": "active", "scope": "global"},
            {"id": "deprecated", "enabled": True, "lifecycle": "deprecated", "scope": "global"},
            {"id": "archived", "enabled": True, "lifecycle": "archived", "scope": "global"},
        ]
        filtered, _ = mgr.filter_routable(candidates)
        # Only active+enabled passes; deprecated is not routable
        assert len(filtered) == 1
        assert filtered[0]["id"] == "good1"

    def test_global_scope_always_passes(self, tmp_path: Path) -> None:
        """Global-scoped skills pass regardless of project root."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "global",
                "enabled": True,
                "lifecycle": "active",
                "scope": "global",
                "source_file": _source_file(tmp_path, "global"),
            }
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1

    def test_missing_source_file_is_not_routable(self, tmp_path: Path) -> None:
        """A candidate whose SKILL.md is gone must not remain a match."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {
                "id": "ghost",
                "enabled": True,
                "lifecycle": "active",
                "scope": "global",
                "source_file": str(tmp_path / "missing" / "SKILL.md"),
            }
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert filtered == []

    def test_stub_without_source_file_is_not_routable(self, tmp_path: Path) -> None:
        """A registry stub (no source_file at all) must never be routable.

        Fail-closed match⇔injectable-content: an indexed-but-fileless entry
        would produce a "match" the injector can only serve a notice for.
        """
        mgr = CandidateManager(tmp_path)
        candidates = [
            {"id": "stub-none", "enabled": True, "lifecycle": "active", "scope": "global"},
            {
                "id": "stub-empty",
                "enabled": True,
                "lifecycle": "active",
                "scope": "global",
                "source_file": "",
            },
            {
                "id": "real",
                "enabled": True,
                "lifecycle": "active",
                "scope": "global",
                "source_file": _source_file(tmp_path, "real"),
            },
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert [c["id"] for c in filtered] == ["real"]

    def test_source_file_for_returns_indexed_path(self, tmp_path: Path) -> None:
        mgr = CandidateManager(tmp_path)
        skill = tmp_path / ".vibe" / "skills" / "demo-skill" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nid: demo-skill\nname: Demo\n---\n# demo\n", encoding="utf-8")
        mgr.get_candidates()
        found = mgr.source_file_for("demo-skill")
        assert found is not None
        assert Path(found).resolve() == skill.resolve()
        assert mgr.source_file_for("missing-id") is None


class TestGetSkillSource:
    """Test source determination from namespace."""

    def test_project_namespace(self, tmp_path: Path) -> None:
        mgr = CandidateManager(tmp_path)
        assert mgr._get_skill_source("test", "project") == "project"

    def test_builtin_namespace(self, tmp_path: Path) -> None:
        mgr = CandidateManager(tmp_path)
        assert mgr._get_skill_source("test", "builtin") == "builtin"

    def test_other_namespace_defaults_to_external(self, tmp_path: Path) -> None:
        mgr = CandidateManager(tmp_path)
        assert mgr._get_skill_source("test", "gstack") == "external"
        assert mgr._get_skill_source("test", "superpowers") == "external"


class TestExtractNameKeywords:
    """Test keyword extraction from skill names."""

    def test_hyphen_separated(self, tmp_path: Path) -> None:
        mgr = CandidateManager(tmp_path)
        keywords = mgr._extract_name_keywords("systematic-debugging")
        assert "systematic" in keywords
        assert "debugging" in keywords

    def test_underscore_separated(self, tmp_path: Path) -> None:
        mgr = CandidateManager(tmp_path)
        keywords = mgr._extract_name_keywords("code_review")
        assert "code" in keywords
        assert "review" in keywords

    def test_slash_separated(self, tmp_path: Path) -> None:
        mgr = CandidateManager(tmp_path)
        keywords = mgr._extract_name_keywords("gstack/review")
        assert "gstack" in keywords
        assert "review" in keywords

    def test_single_char_parts_filtered(self, tmp_path: Path) -> None:
        mgr = CandidateManager(tmp_path)
        keywords = mgr._extract_name_keywords("a-b-c-test")
        assert "test" in keywords
        assert "a" not in keywords
        assert "b" not in keywords


class TestRecordUsage:
    """Test usage recording and buffer flushing."""

    def test_record_usage_buffers(self, tmp_path: Path) -> None:
        """record_usage buffers stats, doesn't write immediately."""
        mgr = CandidateManager(tmp_path)
        assert len(mgr._usage_buffer) == 0
        mgr.record_usage("test-skill", was_successful=True)
        assert "test-skill" in mgr._usage_buffer
        assert mgr._usage_buffer["test-skill"]["call_count"] == 1
        assert mgr._usage_buffer["test-skill"]["success_count"] == 1

    def test_record_usage_accumulates(self, tmp_path: Path) -> None:
        """Multiple calls to same skill accumulate."""
        mgr = CandidateManager(tmp_path)
        mgr.record_usage("test-skill", was_successful=True)
        mgr.record_usage("test-skill", was_successful=False)
        mgr.record_usage("test-skill", was_successful=True)
        assert mgr._usage_buffer["test-skill"]["call_count"] == 3
        assert mgr._usage_buffer["test-skill"]["success_count"] == 2


class TestCacheInvalidation:
    """Regression tests for stale candidates cache when skills are added deep in the tree."""

    def test_deep_skill_changes_hash(self, tmp_path: Path) -> None:
        """Adding a SKILL.md at depth >= 2 must change _compute_paths_hash."""
        search_path = tmp_path / "skills"
        search_path.mkdir()
        deep_dir = search_path / "pack" / "sub"
        deep_dir.mkdir(parents=True)
        (deep_dir / "SKILL.md").write_text("id: old\n", encoding="utf-8")

        mgr = CandidateManager(tmp_path)
        hash_before = mgr._compute_paths_hash([search_path])

        # Add a new skill two levels deep
        new_dir = search_path / "pack" / "new"
        new_dir.mkdir(parents=True)
        (new_dir / "SKILL.md").write_text("id: new\n", encoding="utf-8")

        hash_after = mgr._compute_paths_hash([search_path])
        assert hash_before != hash_after

    def test_disk_cache_rejected_after_deep_change(self, tmp_path: Path) -> None:
        """Old disk cache must be rejected after a deep SKILL.md appears."""
        mgr = CandidateManager(tmp_path)
        search_path = tmp_path / "skills"
        search_path.mkdir()
        deep_dir = search_path / "pack" / "sub"
        deep_dir.mkdir(parents=True)
        (deep_dir / "SKILL.md").write_text("id: old\n", encoding="utf-8")

        # Write disk cache with the old hash
        paths_hash = mgr._compute_paths_hash([search_path])
        mgr._save_to_disk_cache([{"id": "old"}], paths_hash)

        # Cache should load successfully
        assert mgr._load_from_disk_cache([search_path]) is not None

        # Add a new deep skill
        new_dir = search_path / "pack" / "new"
        new_dir.mkdir(parents=True)
        (new_dir / "SKILL.md").write_text("id: new\n", encoding="utf-8")

        # Old cache is now stale
        assert mgr._load_from_disk_cache([search_path]) is None

    def test_disk_cache_with_foreign_schema_discarded(self, tmp_path: Path) -> None:
        """A cache file without the current schema_version (hand-written or
        from a future/old format) is discarded even when paths_hash matches."""
        mgr = CandidateManager(tmp_path)
        search_path = tmp_path / "skills"
        search_path.mkdir()
        (search_path / "SKILL.md").write_text("id: x\n", encoding="utf-8")
        paths_hash = mgr._compute_paths_hash([search_path])

        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        cache_path.parent.mkdir(parents=True)
        cache_path.write_text(
            json.dumps({"paths_hash": paths_hash, "candidates": [{"id": "foreign"}]}),
            encoding="utf-8",
        )
        assert mgr._load_from_disk_cache([search_path]) is None

        # Non-dict top level (hand-corrupted) must be discarded, not raise.
        cache_path.write_text(json.dumps([{"id": "array"}]), encoding="utf-8")
        assert mgr._load_from_disk_cache([search_path]) is None

        # Non-list candidates value is likewise discarded, not cached.
        cache_path.write_text(
            json.dumps({"schema_version": 2, "paths_hash": paths_hash, "candidates": "oops"}),
            encoding="utf-8",
        )
        assert mgr._load_from_disk_cache([search_path]) is None

        # v3 hashed mtime only. A matching paths_hash must still be discarded
        # so a pre-fix entry cannot be reread as if it were content-addressed.
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "paths_hash": paths_hash,
                    "candidates": [{"id": "stale-v3", "description": "old"}],
                }
            ),
            encoding="utf-8",
        )
        assert mgr._load_from_disk_cache([search_path]) is None

        # v4 hashed SKILL.md only and omitted project_hash / ordinary markdown.
        cache_path.write_text(
            json.dumps(
                {
                    "schema_version": 4,
                    "paths_hash": paths_hash,
                    "candidates": [{"id": "stale-v4", "description": "old"}],
                }
            ),
            encoding="utf-8",
        )
        assert mgr._load_from_disk_cache([search_path]) is None

        mgr._save_to_disk_cache([{"id": "current"}], paths_hash)
        loaded = mgr._load_from_disk_cache([search_path])
        assert loaded == [{"id": "current"}]

    def test_skill_mtimes_captures_deep_files(self, tmp_path: Path) -> None:
        """_compute_skill_mtimes must include files below depth 1."""
        search_path = tmp_path / "skills"
        search_path.mkdir()
        deep_dir = search_path / "pack" / "sub"
        deep_dir.mkdir(parents=True)
        skill_file = deep_dir / "SKILL.md"
        skill_file.write_text("id: x\n", encoding="utf-8")

        mtimes = CandidateManager._compute_skill_mtimes([search_path])
        assert str(skill_file) in mtimes
        assert isinstance(mtimes[str(skill_file)], float)

    def test_should_check_reload_triggers_on_deep_change(self, tmp_path: Path) -> None:
        """_should_check_reload returns True when a deep SKILL.md is added."""
        mgr = CandidateManager(tmp_path)
        search_path = tmp_path / "skills"
        search_path.mkdir()
        deep_dir = search_path / "pack" / "sub"
        deep_dir.mkdir(parents=True)
        (deep_dir / "SKILL.md").write_text("id: old\n", encoding="utf-8")

        mgr._search_paths = [search_path]
        mgr._path_mtimes = CandidateManager._compute_skill_mtimes([search_path])
        mgr._last_reload_check = 0.0  # Force the interval gate open

        # No change yet
        assert mgr._should_check_reload() is False

        # Open the interval gate again
        mgr._last_reload_check = 0.0

        # Add a new deep skill
        new_dir = search_path / "pack" / "new"
        new_dir.mkdir(parents=True)
        (new_dir / "SKILL.md").write_text("id: new\n", encoding="utf-8")

        assert mgr._should_check_reload() is True


def _isolated_manager(tmp_path: Path):
    """CandidateManager whose discovery is the tiny skills dir, not the machine."""
    from vibesop.core.skills.loader import SkillLoader

    search = tmp_path / "skills"
    search.mkdir(exist_ok=True)
    mgr = CandidateManager(tmp_path)
    mgr._search_paths = [search]
    mgr._skill_loader = SkillLoader(
        project_root=tmp_path,
        search_paths=[search],
        enable_external=False,
        strict_search_paths=True,
    )
    return mgr, search


def _write_skill(search: Path, skill_id: str, description: str) -> Path:
    skill = search / skill_id / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        f"---\nname: {skill_id}\ndescription: {description}\n---\n# {skill_id}\n",
        encoding="utf-8",
    )
    return skill


class TestFingerprintContract:
    """D04/D05 cache key: content, governance projection, registry, skill YAML."""

    def test_content_changes_hash_preserved_mtime_does_not(self, tmp_path: Path) -> None:
        mgr, search = _isolated_manager(tmp_path)
        skill = _write_skill(search, "alpha", "one")
        before = mgr._compute_paths_hash([search])

        stamp = skill.stat()
        skill.write_text(
            "---\nname: alpha\ndescription: two\n---\n# alpha\n",
            encoding="utf-8",
        )
        import os

        os.utime(skill, (stamp.st_atime, stamp.st_mtime))
        assert mgr._compute_paths_hash([search]) != before

        # A pure timestamp touch must not look like a new skill body.
        current = mgr._compute_paths_hash([search])
        os.utime(skill, (stamp.st_atime, stamp.st_mtime + 50))
        assert mgr._compute_paths_hash([search]) == current

    def test_yaml_skill_and_registry_are_in_the_fingerprint(self, tmp_path: Path) -> None:
        mgr, search = _isolated_manager(tmp_path)
        _write_skill(search, "alpha", "one")
        baseline = mgr._compute_paths_hash([search])

        yaml_skill = search / "beta.yaml"
        yaml_skill.write_text(
            "id: beta\nname: beta\ndescription: from yaml\n",
            encoding="utf-8",
        )
        with_yaml = mgr._compute_paths_hash([search])
        assert with_yaml != baseline

        yaml_skill.write_text(
            "id: beta\nname: beta\ndescription: yaml edited\n",
            encoding="utf-8",
        )
        assert mgr._compute_paths_hash([search]) != with_yaml

        registry = search / "registry.yaml"
        registry.write_text("skills: []\n", encoding="utf-8")
        with_registry = mgr._compute_paths_hash([search])
        registry.write_text("skills:\n  - id: added\n", encoding="utf-8")
        assert mgr._compute_paths_hash([search]) != with_registry

    def test_usage_stats_do_not_change_fingerprint_governance_does(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from vibesop.core.skills.config_manager import SkillConfigManager

        mgr, search = _isolated_manager(tmp_path)
        _write_skill(search, "alpha", "one")
        config_file = tmp_path / ".vibe" / "skills" / "auto-config.yaml"
        config_file.parent.mkdir(parents=True)
        monkeypatch.setattr(SkillConfigManager, "SKILL_CONFIG_FILE", config_file)

        SkillConfigManager.update_skill_config("alpha", {"enabled": True, "scope": "global"})
        baseline = mgr._compute_paths_hash([search])
        SkillConfigManager.update_skill_config("alpha", {"usage_stats": {"call_count": 4}})
        assert mgr._compute_paths_hash([search]) == baseline

        SkillConfigManager.update_skill_config("alpha", {"enabled": False})
        disabled = mgr._compute_paths_hash([search])
        assert disabled != baseline

        SkillConfigManager.update_skill_config("alpha", {"enabled": True, "lifecycle": "archived"})
        assert mgr._compute_paths_hash([search]) != disabled

    def test_same_mtime_edit_is_visible_to_auto_refresh(self, tmp_path: Path) -> None:
        import os

        mgr, search = _isolated_manager(tmp_path)
        skill = _write_skill(search, "alpha", "one")
        first = mgr.get_cached_candidates()
        assert next(c for c in first if c["id"] == "alpha")["description"] == "one"

        stamp = skill.stat()
        skill.write_text(
            "---\nname: alpha\ndescription: two\n---\n# alpha\n",
            encoding="utf-8",
        )
        os.utime(skill, (stamp.st_atime, stamp.st_mtime))
        # Open the rate-limit gate. This does not clear either cache.
        mgr._last_reload_check = 0.0
        second = mgr.get_cached_candidates()
        assert next(c for c in second if c["id"] == "alpha")["description"] == "two"

    def test_reload_persists_new_metadata_under_new_fingerprint(self, tmp_path: Path) -> None:
        mgr, search = _isolated_manager(tmp_path)
        skill = _write_skill(search, "alpha", "one")
        assert (
            next(c for c in mgr.get_cached_candidates() if c["id"] == "alpha")["description"]
            == "one"
        )

        skill.write_text(
            "---\nname: alpha\ndescription: two\n---\n# alpha\n",
            encoding="utf-8",
        )
        mgr.reload()
        refreshed = next(c for c in mgr.get_cached_candidates() if c["id"] == "alpha")
        assert refreshed["description"] == "two"

        payload = json.loads((tmp_path / ".vibe" / "cache" / "candidates_v2.json").read_text())
        assert payload["paths_hash"] == mgr._compute_paths_hash(mgr._search_paths)
        cached = next(c for c in payload["candidates"] if c["id"] == "alpha")
        assert cached["description"] == "two"

        # A second manager must hit that file, not rebuild a different body.
        payload["candidates"].append({"id": "disk-cache-sentinel", "description": "hit"})
        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        stamped = cache_path.stat().st_mtime_ns

        fresh, _fresh_search = _isolated_manager(tmp_path)
        # Same roots the writer hashed. pin_search_paths would bypass the disk.
        fresh._search_paths = [search]
        fresh._skill_loader = mgr._skill_loader
        # The shared loader was cleared by reload; a hit must not need it.
        ids = {c["id"] for c in fresh.get_cached_candidates()}
        assert "disk-cache-sentinel" in ids
        assert (
            next(c for c in fresh.get_cached_candidates() if c["id"] == "alpha")["description"]
            == "two"
        )
        assert cache_path.stat().st_mtime_ns == stamped

    def test_add_and_delete_via_auto_refresh_and_reload(self, tmp_path: Path) -> None:
        mgr, search = _isolated_manager(tmp_path)
        _write_skill(search, "alpha", "one")
        assert {c["id"] for c in mgr.get_cached_candidates()} == {"alpha"}

        _write_skill(search, "beta", "two")
        mgr._last_reload_check = 0.0
        assert {c["id"] for c in mgr.get_cached_candidates()} == {"alpha", "beta"}

        (search / "beta" / "SKILL.md").unlink()
        mgr.reload()
        assert {c["id"] for c in mgr.get_cached_candidates()} == {"alpha"}
        payload = json.loads((tmp_path / ".vibe" / "cache" / "candidates_v2.json").read_text())
        assert all(c.get("id") != "beta" for c in payload["candidates"])

    def test_reload_invalidates_index_layer_cache(self, tmp_path: Path) -> None:
        from types import SimpleNamespace

        from vibesop.core.routing._layers import try_index_layer
        from vibesop.core.routing.candidate_manager import index_cache_epoch

        mgr, _search = _isolated_manager(tmp_path)
        router = SimpleNamespace(
            project_root=tmp_path,
            _config=SimpleNamespace(
                index_match_threshold=0.35,
                index_external_match_threshold=0.5,
            ),
            _index_layer_cache={"stale-skill": object()},
            _index_profile_tokens={"stale-skill": {"stale"}},
            _index_layer_epoch=index_cache_epoch(tmp_path),
            _get_skill_source=lambda _sid, _ns: "builtin",
        )
        mgr.reload()
        _match, detail = try_index_layer(router, "review code", [])
        assert detail.matched is False
        assert "stale-skill" not in router._index_layer_cache


class _Clock:
    """Controllable monotonic clock for the declared 5s auto-refresh interval."""

    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _write_named_markdown(search: Path, skill_id: str, filename: str, description: str) -> Path:
    skill = search / skill_id / filename
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        f"---\nname: {skill_id}\ndescription: {description}\n---\n# {skill_id}\n",
        encoding="utf-8",
    )
    return skill


class TestDiscoveryFingerprintParity:
    """R1–R3: fingerprint, config reader, and loader discovery stay one source."""

    def test_same_mtime_config_edit_hides_skill_on_hot_and_fresh_disk(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import os

        from vibesop.core.skills.config_manager import (
            _CONFIG_FILE_CACHE,
            SkillConfigManager,
        )

        mgr, search = _isolated_manager(tmp_path)
        _write_skill(search, "alpha", "before")
        config = tmp_path / "auto-config.yaml"
        monkeypatch.setattr(SkillConfigManager, "SKILL_CONFIG_FILE", config)
        _CONFIG_FILE_CACHE.clear()
        config.write_text("skills:\n  alpha:\n    enabled: true\n", encoding="utf-8")

        first = mgr.get_cached_candidates()
        assert [c["enabled"] for c in first if c["id"] == "alpha"] == [True]
        before = mgr._content_fingerprint
        stamp = config.stat()
        config.write_text("skills:\n  alpha:\n    enabled: false\n", encoding="utf-8")
        os.utime(config, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

        hot = mgr.get_cached_candidates()
        after = mgr._content_fingerprint
        assert before != after
        assert [c["id"] for c in hot] == []
        assert SkillConfigManager.get_skill_config("alpha").enabled is False

        _CONFIG_FILE_CACHE.clear()
        fresh, _ = _isolated_manager(tmp_path)
        fresh_ids = [c["id"] for c in fresh.get_cached_candidates()]
        assert fresh_ids == []
        assert SkillConfigManager.get_skill_config("alpha").enabled is False

        cache_path = tmp_path / ".vibe" / "cache" / "candidates_v2.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        assert all(c.get("id") != "alpha" for c in payload["candidates"])

    def test_ordinary_markdown_edit_is_visible_after_declared_interval(
        self, tmp_path: Path
    ) -> None:
        mgr, search = _isolated_manager(tmp_path)
        skill = _write_named_markdown(search, "alpha", "alpha.md", "before")
        clock = _Clock(100.0)
        mgr._clock = clock
        first = mgr.get_cached_candidates()
        assert next(c for c in first if c["id"] == "alpha")["description"] == "before"
        before = mgr._content_fingerprint
        mgr._last_reload_check = clock.now

        skill.write_text(
            "---\nname: alpha\ndescription: after\n---\n# alpha\n",
            encoding="utf-8",
        )
        clock.now += 1.0
        held = mgr.get_cached_candidates()
        assert next(c for c in held if c["id"] == "alpha")["description"] == "before"
        assert mgr._compute_paths_hash([search]) != before

        clock.now += 5.0
        hot = mgr.get_cached_candidates()
        fresh, _ = _isolated_manager(tmp_path)
        assert next(c for c in hot if c["id"] == "alpha")["description"] == "after"
        assert (
            next(c for c in fresh.get_cached_candidates() if c["id"] == "alpha")["description"]
            == "after"
        )

    def test_default_project_skills_root_is_fingerprinted(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from vibesop.core.skills.config_manager import _CONFIG_FILE_CACHE, SkillConfigManager
        from vibesop.core.skills.external_loader import ExternalSkillLoader
        from vibesop.core.skills.loader import SkillLoader

        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.setattr(ExternalSkillLoader, "EXTERNAL_PATHS", [home / "none"])
        config = tmp_path / "auto-config.yaml"
        config.write_text("skills: {}\n", encoding="utf-8")
        monkeypatch.setattr(SkillConfigManager, "SKILL_CONFIG_FILE", config)
        _CONFIG_FILE_CACHE.clear()

        project = tmp_path / "default-root"
        search = project / "skills"
        skill = _write_skill(search, "alpha", "before")
        mgr = CandidateManager(project)
        mgr._search_paths = mgr._build_search_paths()
        mgr._skill_loader = SkillLoader(
            project,
            search_paths=mgr._search_paths,
            enable_external=False,
            strict_search_paths=False,
        )
        clock = _Clock(100.0)
        mgr._clock = clock
        mgr.get_cached_candidates()
        before = mgr._content_fingerprint
        assert search in mgr._search_paths
        assert search in mgr._skill_loader._search_paths

        skill.write_text(
            "---\nname: alpha\ndescription: after\n---\n# alpha\n",
            encoding="utf-8",
        )
        clock.now += 5.0
        mgr._last_reload_check = 0.0
        hot = mgr.get_cached_candidates()
        fresh = CandidateManager(project)
        fresh._search_paths = fresh._build_search_paths()
        fresh._skill_loader = SkillLoader(
            project,
            search_paths=fresh._search_paths,
            enable_external=False,
            strict_search_paths=False,
        )
        assert before != mgr._compute_paths_hash(mgr._search_paths)
        assert [c["description"] for c in hot if c["id"] == "alpha"] == ["after"]
        assert [c["description"] for c in fresh.get_cached_candidates() if c["id"] == "alpha"] == [
            "after"
        ]

    def test_public_owner_hash_update_hides_skill_on_hot_and_fresh(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from vibesop.core.skills.config_manager import _CONFIG_FILE_CACHE, SkillConfigManager
        from vibesop.core.skills.loader import SkillLoader

        mgr, search = _isolated_manager(tmp_path)
        _write_skill(search, "alpha", "before")
        config = tmp_path / ".vibe" / "skills" / "auto-config.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(SkillConfigManager, "SKILL_CONFIG_FILE", config)
        _CONFIG_FILE_CACHE.clear()

        SkillConfigManager.update_skill_config(
            "alpha",
            {
                "scope": "project",
                "evaluation_context": {"project_hash": mgr._skill_loader.project_hash},
            },
        )
        first = mgr.get_cached_candidates()
        assert [c["id"] for c in first] == ["alpha"]
        before = mgr._content_fingerprint

        SkillConfigManager.update_skill_config(
            "alpha",
            {"evaluation_context": {"project_hash": "another-project"}},
        )
        mgr._last_reload_check = 0.0
        hot = mgr.get_cached_candidates()
        fresh, _ = _isolated_manager(tmp_path)
        raw = SkillLoader(
            tmp_path,
            search_paths=[search],
            enable_external=False,
            strict_search_paths=True,
        ).discover_all()
        assert before != mgr._compute_paths_hash([search])
        assert [c["id"] for c in hot] == []
        assert [c["id"] for c in fresh.get_cached_candidates()] == []
        assert list(raw) == []
        payload = json.loads((tmp_path / ".vibe" / "cache" / "candidates_v2.json").read_text())
        assert all(c.get("id") != "alpha" for c in payload["candidates"])

    def test_metadata_project_hash_fallback_matches_loader(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from vibesop.core.skills.config_manager import _CONFIG_FILE_CACHE, SkillConfigManager
        from vibesop.core.skills.loader import SkillLoader

        mgr, search = _isolated_manager(tmp_path)
        _write_skill(search, "alpha", "before")
        config = tmp_path / ".vibe" / "skills" / "auto-config.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(SkillConfigManager, "SKILL_CONFIG_FILE", config)
        _CONFIG_FILE_CACHE.clear()

        SkillConfigManager.update_skill_config(
            "alpha",
            {"scope": "project", "metadata": {"project_hash": "another-project"}},
        )
        assert mgr.get_cached_candidates() == []
        raw = SkillLoader(
            tmp_path,
            search_paths=[search],
            enable_external=False,
            strict_search_paths=True,
        ).discover_all()
        assert list(raw) == []
        config_obj = SkillConfigManager.get_skill_config("alpha")
        assert config_obj.evaluation_context.get("project_hash") == "another-project"

    def test_unmodified_config_does_not_reparse_yaml(self, tmp_path: Path, monkeypatch) -> None:
        from unittest.mock import patch

        import yaml

        from vibesop.core.skills.config_manager import _CONFIG_FILE_CACHE, SkillConfigManager

        mgr, search = _isolated_manager(tmp_path)
        _write_skill(search, "alpha", "one")
        config = tmp_path / ".vibe" / "skills" / "auto-config.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(SkillConfigManager, "SKILL_CONFIG_FILE", config)
        _CONFIG_FILE_CACHE.clear()
        SkillConfigManager.update_skill_config("alpha", {"enabled": True, "scope": "global"})
        mgr.get_cached_candidates()
        mgr._last_reload_check = mgr._clock()

        with patch(
            "vibesop.core.skills.config_manager.yaml.safe_load", wraps=yaml.safe_load
        ) as spy:
            mgr.get_cached_candidates()
            mgr.get_cached_candidates()
            assert spy.call_count == 0

        version = SkillConfigManager.config_content_version()
        SkillConfigManager.invalidate_config_cache()
        with patch(
            "vibesop.core.skills.config_manager.yaml.safe_load", wraps=yaml.safe_load
        ) as spy:
            assert SkillConfigManager.get_skill_config("alpha").enabled is True
            assert spy.call_count == 1
        assert SkillConfigManager.config_content_version() == version
