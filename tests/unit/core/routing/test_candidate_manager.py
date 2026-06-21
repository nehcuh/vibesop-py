"""Tests for CandidateManager — filtering, caching, usage recording."""

from __future__ import annotations

from pathlib import Path

from vibesop.core.routing.candidate_manager import CandidateManager


class TestFilterRoutable:
    """Test candidate filtering by enablement, scope, and lifecycle."""

    def test_enabled_candidate_passes(self, tmp_path: Path) -> None:
        """Enabled candidates pass through filter."""
        mgr = CandidateManager(tmp_path)
        candidates = [{"id": "test", "enabled": True, "lifecycle": "active", "scope": "global"}]
        filtered, warnings = mgr.filter_routable(candidates)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "test"
        assert len(warnings) == 0

    def test_disabled_candidate_filtered_out(self, tmp_path: Path) -> None:
        """Disabled candidates are filtered out."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {"id": "enabled", "enabled": True, "lifecycle": "active", "scope": "global"},
            {"id": "disabled", "enabled": False, "lifecycle": "active", "scope": "global"},
        ]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "enabled"

    def test_enabled_defaults_to_true(self, tmp_path: Path) -> None:
        """Missing 'enabled' key defaults to True (passes filter)."""
        mgr = CandidateManager(tmp_path)
        candidates = [{"id": "test", "lifecycle": "active", "scope": "global"}]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1

    def test_archived_lifecycle_filtered_out(self, tmp_path: Path) -> None:
        """ARCHIVED lifecycle is not routable."""
        mgr = CandidateManager(tmp_path)
        candidates = [{"id": "old", "enabled": True, "lifecycle": "archived", "scope": "global"}]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 0

    def test_draft_lifecycle_filtered_out(self, tmp_path: Path) -> None:
        """DRAFT lifecycle is not routable."""
        mgr = CandidateManager(tmp_path)
        candidates = [{"id": "draft", "enabled": True, "lifecycle": "draft", "scope": "global"}]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 0

    def test_deprecated_is_not_routable(self, tmp_path: Path) -> None:
        """DEPRECATED lifecycle is NOT routable (filtered out)."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {"id": "dep-skill", "enabled": True, "lifecycle": "deprecated", "scope": "global"}
        ]
        filtered, _warnings = mgr.filter_routable(candidates)
        # DEPRECATED is not routable — filtered out entirely
        assert len(filtered) == 0

    def test_project_scoped_within_project_passes(self, tmp_path: Path) -> None:
        """Project-scoped skill whose source_file is within project root passes."""
        project = tmp_path / "project"
        project.mkdir()
        skill_file = project / "skill.md"
        skill_file.write_text("")
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
        external_file.write_text("")
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
        candidates = [{"id": "bad", "enabled": True, "lifecycle": "nonexistent", "scope": "global"}]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1

    def test_multiple_candidates_mixed_filtering(self, tmp_path: Path) -> None:
        """Mixed candidates: enabled+active pass, disabled/archived/deprecated filtered."""
        mgr = CandidateManager(tmp_path)
        candidates = [
            {"id": "good1", "enabled": True, "lifecycle": "active", "scope": "global"},
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
        candidates = [{"id": "global", "enabled": True, "lifecycle": "active", "scope": "global"}]
        filtered, _ = mgr.filter_routable(candidates)
        assert len(filtered) == 1


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
        (deep_dir / "SKILL.md").write_text("id: old\n")

        mgr = CandidateManager(tmp_path)
        hash_before = mgr._compute_paths_hash([search_path])

        # Add a new skill two levels deep
        new_dir = search_path / "pack" / "new"
        new_dir.mkdir(parents=True)
        (new_dir / "SKILL.md").write_text("id: new\n")

        hash_after = mgr._compute_paths_hash([search_path])
        assert hash_before != hash_after

    def test_disk_cache_rejected_after_deep_change(self, tmp_path: Path) -> None:
        """Old disk cache must be rejected after a deep SKILL.md appears."""
        mgr = CandidateManager(tmp_path)
        search_path = tmp_path / "skills"
        search_path.mkdir()
        deep_dir = search_path / "pack" / "sub"
        deep_dir.mkdir(parents=True)
        (deep_dir / "SKILL.md").write_text("id: old\n")

        # Write disk cache with the old hash
        paths_hash = mgr._compute_paths_hash([search_path])
        mgr._save_to_disk_cache([{"id": "old"}], paths_hash)

        # Cache should load successfully
        assert mgr._load_from_disk_cache([search_path]) is not None

        # Add a new deep skill
        new_dir = search_path / "pack" / "new"
        new_dir.mkdir(parents=True)
        (new_dir / "SKILL.md").write_text("id: new\n")

        # Old cache is now stale
        assert mgr._load_from_disk_cache([search_path]) is None

    def test_skill_mtimes_captures_deep_files(self, tmp_path: Path) -> None:
        """_compute_skill_mtimes must include files below depth 1."""
        search_path = tmp_path / "skills"
        search_path.mkdir()
        deep_dir = search_path / "pack" / "sub"
        deep_dir.mkdir(parents=True)
        skill_file = deep_dir / "SKILL.md"
        skill_file.write_text("id: x\n")

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
        (deep_dir / "SKILL.md").write_text("id: old\n")

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
        (new_dir / "SKILL.md").write_text("id: new\n")

        assert mgr._should_check_reload() is True
