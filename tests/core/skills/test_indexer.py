"""Tests for the tiered skill indexer (global / project layers).

Covers:
- ``_classify_skill_source`` partitioning rules (project vs global, edge cases)
- ``_save_index`` schema (v1.1.0, ``indexed_at``, ``scope``)
- ``_load_single_index`` graceful failure on malformed input
- ``load_index`` global + project merge with project-overrides-global semantics
- ``has_index`` reporting either layer
- ``build_index`` partitioning across scopes
- ``update_global_index_for_pack`` incremental update behaviour
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from vibesop.core.skills.indexer import (
    IndexResult,
    SkillIndexer,
    SkillProfile,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_loaded_skill(
    skill_id: str,
    source_file: Path | None,
    *,
    name: str | None = None,
) -> SimpleNamespace:
    """Build a duck-typed LoadedSkill stub for indexer logic.

    The indexer only touches ``loaded_skill.source_file`` and (via
    ``_analyze_skill``) ``loaded_skill.metadata`` + ``loaded_skill.content``.
    We mock the LLM path, so metadata fields can be minimal.
    """
    metadata = SimpleNamespace(
        id=skill_id,
        name=name or skill_id,
        description="Test skill",
        intent="test",
        tags=[],
        triggers=[],
        capabilities=[],
    )
    return SimpleNamespace(
        metadata=metadata,
        content="# Test\nSome content",
        source_file=source_file,
        external_metadata=None,
    )


def _make_profile(skill_id: str, **overrides: object) -> SkillProfile:
    return SkillProfile(
        skill_id=skill_id,
        scenarios=overrides.get("scenarios", [f"scenario for {skill_id}"]),
        query_patterns=overrides.get("query_patterns", [f"use {skill_id}"]),
        differentiation=overrides.get("differentiation", f"unique {skill_id}"),
        confidence_boosters=overrides.get("confidence_boosters", [skill_id]),
    )


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Isolated project root with .vibe directory."""
    root = tmp_path / "project"
    (root / ".vibe").mkdir(parents=True)
    (root / "skills").mkdir()
    return root


@pytest.fixture
def global_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated home with .vibe directory; redirects ``Path.home()``."""
    home = tmp_path / "home"
    (home / ".vibe").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def indexer(project_root: Path, global_home: Path) -> SkillIndexer:
    return SkillIndexer(project_root=project_root)


# ---------------------------------------------------------------------------
# _classify_skill_source
# ---------------------------------------------------------------------------


class TestClassifySkillSource:
    def test_project_skills_directory(self, indexer: SkillIndexer) -> None:
        ls = _fake_loaded_skill(
            "foo",
            indexer.project_root / "skills" / "foo" / "SKILL.md",
        )
        assert indexer._classify_skill_source(ls) == "project"

    def test_project_vibe_skills_directory(self, indexer: SkillIndexer) -> None:
        ls = _fake_loaded_skill(
            "bar",
            indexer.project_root / ".vibe" / "skills" / "bar" / "SKILL.md",
        )
        assert indexer._classify_skill_source(ls) == "project"

    def test_external_pack_under_home_is_global(
        self, indexer: SkillIndexer, global_home: Path
    ) -> None:
        ls = _fake_loaded_skill(
            "gstack/review",
            global_home / ".config" / "skills" / "gstack" / "review" / "SKILL.md",
        )
        assert indexer._classify_skill_source(ls) == "global"

    def test_builtin_outside_project_is_global(self, indexer: SkillIndexer, tmp_path: Path) -> None:
        ls = _fake_loaded_skill(
            "builtin/research",
            tmp_path / "site-packages" / "vibesop" / "core" / "skills" / "research.md",
        )
        assert indexer._classify_skill_source(ls) == "global"

    def test_no_source_file_is_global(self, indexer: SkillIndexer) -> None:
        ls = _fake_loaded_skill("phantom", None)
        assert indexer._classify_skill_source(ls) == "global"

    def test_path_outside_project_is_global(self, indexer: SkillIndexer, tmp_path: Path) -> None:
        # Sibling dir to project, not under it
        ls = _fake_loaded_skill(
            "external",
            tmp_path / "elsewhere" / "skills" / "ext" / "SKILL.md",
        )
        assert indexer._classify_skill_source(ls) == "global"

    def test_project_root_dotted_dir_other_than_vibe_is_global(self, indexer: SkillIndexer) -> None:
        # File under project_root but not in skills/ or .vibe/
        ls = _fake_loaded_skill(
            "weird",
            indexer.project_root / "tools" / "weird" / "SKILL.md",
        )
        assert indexer._classify_skill_source(ls) == "global"


# ---------------------------------------------------------------------------
# _save_index / _load_single_index
# ---------------------------------------------------------------------------


class TestSaveIndexSchema:
    def test_save_writes_v1_4_0_schema(self, indexer: SkillIndexer) -> None:
        profiles = {"a/b": _make_profile("a/b")}
        indexer._save_index(profiles, scope="global")

        data = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert data["version"] == "1.4.0"
        assert data["scope"] == "global"
        assert data["indexed_count"] == 1
        assert "indexed_at" in data
        # ISO 8601 timestamp
        assert "T" in data["indexed_at"]
        assert "a/b" in data["skills"]
        # v1.2 adds pack_owner to every profile (default "")
        assert "pack_owner" in data["skills"]["a/b"]

    def test_save_global_writes_to_global_path(self, indexer: SkillIndexer) -> None:
        indexer._save_index({"x": _make_profile("x")}, scope="global")
        assert indexer.global_index_path.exists()
        assert not indexer.project_index_path.exists()

    def test_save_project_writes_to_project_path(self, indexer: SkillIndexer) -> None:
        indexer._save_index({"y": _make_profile("y")}, scope="project")
        assert indexer.project_index_path.exists()
        assert not indexer.global_index_path.exists()

    def test_save_uses_atomic_temp_rename(self, indexer: SkillIndexer) -> None:
        indexer._save_index({"z": _make_profile("z")}, scope="global")
        # Final file exists; no leftover .tmp staging files in the directory
        assert indexer.global_index_path.exists()
        leftovers = list(indexer.global_index_path.parent.glob("*.tmp"))
        assert leftovers == [], f"Atomic write left tempfile: {leftovers}"

    def test_save_uses_unique_temp_names(self, indexer: SkillIndexer) -> None:
        """Two saves must not collide on the same staging filename — that
        was the race condition with the old ``.tmp``-suffix scheme. We
        verify by intercepting NamedTemporaryFile and checking each call
        gets a distinct path (the OS already guarantees this; this test
        documents the contract)."""
        import tempfile as tempfile_module

        captured: list[str] = []
        original = tempfile_module.NamedTemporaryFile

        def _spy(*args: object, **kwargs: object) -> object:
            tf = original(*args, **kwargs)  # type: ignore[arg-type]
            captured.append(tf.name)
            return tf

        with patch(
            "vibesop.core.skills.indexer.tempfile.NamedTemporaryFile",
            side_effect=_spy,
        ):
            indexer._save_index({"a": _make_profile("a")}, scope="global")
            indexer._save_index({"b": _make_profile("b")}, scope="global")

        assert len(captured) == 2
        assert captured[0] != captured[1], (
            "Concurrent saves would clobber each other if temp names were equal"
        )


class TestLoadSingleIndex:
    def test_loads_valid_index(self, indexer: SkillIndexer) -> None:
        indexer._save_index(
            {"foo": _make_profile("foo")},
            scope="global",
        )
        loaded = indexer._load_single_index(indexer.global_index_path)
        assert "foo" in loaded
        assert loaded["foo"].skill_id == "foo"

    def test_prunes_non_skill_state_file_profiles(self, indexer: SkillIndexer) -> None:
        """Pre-1.4 indexers treated any YAML under .vibe/skills as a skill, so
        auto-config.yaml / registry.yaml were indexed under synthesized ids like
        ``project/auto-config.yaml/auto-config``. Those phantom profiles are
        pruned at load time so stale on-disk indexes self-heal."""
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text(
            json.dumps(
                {
                    "version": "1.3.0",
                    "scope": "project",
                    "skills": {
                        "project/auto-config.yaml/auto-config": _make_profile(
                            "project/auto-config.yaml/auto-config"
                        ).to_dict(),
                        "project/registry.yaml/registry": _make_profile(
                            "project/registry.yaml/registry"
                        ).to_dict(),
                        "real-skill": _make_profile("real-skill").to_dict(),
                    },
                }
            ),
            encoding="utf-8",
        )
        loaded = indexer._load_single_index(indexer.global_index_path)
        assert set(loaded) == {"real-skill"}

    def test_prune_matches_whole_id_segments_only(self, indexer: SkillIndexer) -> None:
        """The prune matches "/" separated id segments exactly (mirroring the
        loader's exact-filename exclusion): a real skill whose id merely
        CONTAINS a state filename as a non-final component is kept."""
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text(
            json.dumps(
                {
                    "version": "1.3.0",
                    "scope": "project",
                    "skills": {
                        "project/registry.yaml-tools/main": _make_profile(
                            "project/registry.yaml-tools/main"
                        ).to_dict(),
                        "project/auto-config.yaml/auto-config": _make_profile(
                            "project/auto-config.yaml/auto-config"
                        ).to_dict(),
                    },
                }
            ),
            encoding="utf-8",
        )
        loaded = indexer._load_single_index(indexer.global_index_path)
        assert set(loaded) == {"project/registry.yaml-tools/main"}

    def test_missing_file_returns_empty(self, indexer: SkillIndexer) -> None:
        # Path that doesn't exist
        result = indexer._load_single_index(indexer.global_index_path)
        assert result == {}

    def test_malformed_json_returns_empty(self, indexer: SkillIndexer) -> None:
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text("not json {", encoding="utf-8")
        result = indexer._load_single_index(indexer.global_index_path)
        assert result == {}

    def test_missing_skills_key_returns_empty(self, indexer: SkillIndexer) -> None:
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text(
            json.dumps({"version": "1.1.0"}),
            encoding="utf-8",
        )
        result = indexer._load_single_index(indexer.global_index_path)
        assert result == {}

    def test_loads_legacy_v1_0_0_index(self, indexer: SkillIndexer) -> None:
        """Indexes written by older versions (no scope, no indexed_at) must
        still load — backward compat for users who haven't run quickstart
        since the schema bump."""
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "skills": {
                        "legacy/skill": {
                            "skill_id": "legacy/skill",
                            "scenarios": ["old"],
                            "query_patterns": ["old"],
                            "differentiation": "legacy",
                            "confidence_boosters": ["old"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        result = indexer._load_single_index(indexer.global_index_path)
        assert "legacy/skill" in result
        assert result["legacy/skill"].differentiation == "legacy"


# ---------------------------------------------------------------------------
# load_index (merge semantics)
# ---------------------------------------------------------------------------


class TestLoadIndexMerge:
    def test_global_only(self, indexer: SkillIndexer) -> None:
        indexer._save_index(
            {"g/a": _make_profile("g/a"), "g/b": _make_profile("g/b")},
            scope="global",
        )
        merged = indexer.load_index()
        assert set(merged.keys()) == {"g/a", "g/b"}

    def test_project_only(self, indexer: SkillIndexer) -> None:
        indexer._save_index(
            {"p/a": _make_profile("p/a")},
            scope="project",
        )
        merged = indexer.load_index()
        assert set(merged.keys()) == {"p/a"}

    def test_both_layers_combine(self, indexer: SkillIndexer) -> None:
        indexer._save_index(
            {"g/a": _make_profile("g/a")},
            scope="global",
        )
        indexer._save_index(
            {"p/a": _make_profile("p/a")},
            scope="project",
        )
        merged = indexer.load_index()
        assert set(merged.keys()) == {"g/a", "p/a"}

    def test_project_overrides_global_for_same_skill_id(self, indexer: SkillIndexer) -> None:
        # Same skill_id in both, project should win
        global_profile = _make_profile(
            "shared",
            differentiation="GLOBAL_VERSION",
        )
        project_profile = _make_profile(
            "shared",
            differentiation="PROJECT_VERSION",
        )
        indexer._save_index({"shared": global_profile}, scope="global")
        indexer._save_index({"shared": project_profile}, scope="project")

        merged = indexer.load_index()
        assert merged["shared"].differentiation == "PROJECT_VERSION"

    def test_no_index_returns_empty(self, indexer: SkillIndexer) -> None:
        assert indexer.load_index() == {}


# ---------------------------------------------------------------------------
# has_index
# ---------------------------------------------------------------------------


class TestHasIndex:
    def test_no_index(self, indexer: SkillIndexer) -> None:
        assert not indexer.has_index()

    def test_global_index_only(self, indexer: SkillIndexer) -> None:
        indexer._save_index({"g/a": _make_profile("g/a")}, scope="global")
        assert indexer.has_index()

    def test_project_index_only(self, indexer: SkillIndexer) -> None:
        indexer._save_index({"p/a": _make_profile("p/a")}, scope="project")
        assert indexer.has_index()

    def test_both_layers(self, indexer: SkillIndexer) -> None:
        indexer._save_index({"g/a": _make_profile("g/a")}, scope="global")
        indexer._save_index({"p/a": _make_profile("p/a")}, scope="project")
        assert indexer.has_index()

    def test_corrupt_global_returns_false(self, indexer: SkillIndexer) -> None:
        """A corrupt or empty index file shouldn't fool the router into
        thinking the index is healthy — has_index must validate content."""
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text("not json {", encoding="utf-8")
        assert not indexer.has_index()

    def test_empty_skills_returns_false(self, indexer: SkillIndexer) -> None:
        """Index file with valid JSON but empty skills dict → not usable."""
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text(
            json.dumps({"version": "1.1.0", "scope": "global", "skills": {}}),
            encoding="utf-8",
        )
        assert not indexer.has_index()

    def test_corrupt_global_falls_back_to_valid_project(self, indexer: SkillIndexer) -> None:
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text("garbage", encoding="utf-8")
        indexer._save_index({"p/a": _make_profile("p/a")}, scope="project")
        assert indexer.has_index()


# ---------------------------------------------------------------------------
# build_index (scope partitioning)
# ---------------------------------------------------------------------------


class TestBuildIndexScope:
    def _patch_loader_and_llm(
        self,
        indexer: SkillIndexer,
        skills: dict[str, object],
    ) -> tuple[object, object]:
        """Return (loader_patcher, llm_patcher) — caller responsible for stop."""
        # Patch SkillLoader.discover_all to return our fake skills
        loader_patcher = patch(
            "vibesop.core.skills.loader.SkillLoader.discover_all",
            return_value=skills,
        )
        # Patch _get_llm to return a non-None marker
        llm_marker = SimpleNamespace(name="fake-llm")
        llm_patcher = patch.object(indexer, "_get_llm", return_value=llm_marker)
        return loader_patcher, llm_patcher

    def test_scope_global_only_writes_global_index(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        skills = {
            "g/a": _fake_loaded_skill(
                "g/a", global_home / ".config" / "skills" / "g" / "a" / "SKILL.md"
            ),
            "p/a": _fake_loaded_skill(
                "p/a", indexer.project_root / "skills" / "p" / "a" / "SKILL.md"
            ),
        }
        loader_p, llm_p = self._patch_loader_and_llm(indexer, skills)

        with (
            loader_p,
            llm_p,
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            result = indexer.build_index(scope="global", show_progress=False)

        assert result.success is True
        assert result.indexed_count == 1  # only g/a
        assert indexer.global_index_path.exists()
        assert not indexer.project_index_path.exists()

        data = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert data["scope"] == "global"
        assert "g/a" in data["skills"]
        assert "p/a" not in data["skills"]

    def test_scope_project_only_writes_project_index(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        skills = {
            "g/a": _fake_loaded_skill(
                "g/a", global_home / ".config" / "skills" / "g" / "a" / "SKILL.md"
            ),
            "p/a": _fake_loaded_skill(
                "p/a", indexer.project_root / "skills" / "p" / "a" / "SKILL.md"
            ),
        }
        loader_p, llm_p = self._patch_loader_and_llm(indexer, skills)

        with (
            loader_p,
            llm_p,
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            result = indexer.build_index(scope="project", show_progress=False)

        assert result.success is True
        assert result.indexed_count == 1  # only p/a
        assert indexer.project_index_path.exists()
        assert not indexer.global_index_path.exists()

        data = json.loads(indexer.project_index_path.read_text(encoding="utf-8"))
        assert data["scope"] == "project"
        assert "p/a" in data["skills"]
        assert "g/a" not in data["skills"]

    def test_scope_all_writes_both_indexes_partitioned(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        skills = {
            "g/a": _fake_loaded_skill(
                "g/a", global_home / ".config" / "skills" / "g" / "a" / "SKILL.md"
            ),
            "p/a": _fake_loaded_skill(
                "p/a", indexer.project_root / "skills" / "p" / "a" / "SKILL.md"
            ),
        }
        loader_p, llm_p = self._patch_loader_and_llm(indexer, skills)

        with (
            loader_p,
            llm_p,
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            result = indexer.build_index(scope="all", show_progress=False)

        assert result.success is True
        assert result.indexed_count == 2
        assert indexer.global_index_path.exists()
        assert indexer.project_index_path.exists()

        global_data = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        project_data = json.loads(indexer.project_index_path.read_text(encoding="utf-8"))
        assert "g/a" in global_data["skills"]
        assert "g/a" not in project_data["skills"]
        assert "p/a" in project_data["skills"]
        assert "p/a" not in global_data["skills"]

    def test_no_skills_returns_failure_result(self, indexer: SkillIndexer) -> None:
        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value={},
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
        ):
            result = indexer.build_index(scope="all", show_progress=False)
        assert result.success is False
        assert any("No skills" in e for e in result.errors)

    def test_no_llm_returns_failure_result(self, indexer: SkillIndexer) -> None:
        with patch.object(indexer, "_get_llm", return_value=None):
            result = indexer.build_index(scope="all", show_progress=False)
        assert result.success is False
        assert any("LLM" in e for e in result.errors)

    def test_pack_owner_inferred_from_central_storage_path(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """``build_index`` must stamp ``pack_owner`` on global profiles by
        inferring from the central-storage layout, so a full rebuild produces
        the same ownership info that incremental updates write."""
        skills = {
            "g/a": _fake_loaded_skill(
                "g/a",
                global_home / ".config" / "skills" / "gpack" / "a" / "SKILL.md",
            ),
            "loose": _fake_loaded_skill(
                "loose",
                global_home / ".config" / "skills" / "looseapp" / "SKILL.md",
            ),
            # Project-local skill — pack_owner should remain empty.
            "p/a": _fake_loaded_skill(
                "p/a", indexer.project_root / "skills" / "p" / "a" / "SKILL.md"
            ),
        }
        # Materialize the source files so .resolve() works (symlinks/realpath).
        for ls in skills.values():
            if ls.source_file is not None:
                ls.source_file.parent.mkdir(parents=True, exist_ok=True)
                ls.source_file.write_text("# stub", encoding="utf-8")

        loader_p = patch(
            "vibesop.core.skills.loader.SkillLoader.discover_all",
            return_value=skills,
        )
        llm_p = patch.object(indexer, "_get_llm", return_value=SimpleNamespace())

        with (
            loader_p,
            llm_p,
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            result = indexer.build_index(scope="all", show_progress=False)

        assert result.success is True

        global_data = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert global_data["skills"]["g/a"]["pack_owner"] == "gpack"
        assert global_data["skills"]["loose"]["pack_owner"] == "looseapp"

        project_data = json.loads(indexer.project_index_path.read_text(encoding="utf-8"))
        assert project_data["skills"]["p/a"]["pack_owner"] == "", (
            "Project-local profiles aren't owned by any pack"
        )


# ---------------------------------------------------------------------------
# update_global_index_for_pack
# ---------------------------------------------------------------------------


class TestUpdateGlobalIndexForPack:
    def test_indexes_only_pack_skills(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        central = global_home / ".config" / "skills"
        # Pack "newpack" with two skills
        pack_a = central / "newpack" / "a" / "SKILL.md"
        pack_b = central / "newpack" / "b" / "SKILL.md"
        pack_a.parent.mkdir(parents=True)
        pack_b.parent.mkdir(parents=True)
        pack_a.write_text("# A", encoding="utf-8")
        pack_b.write_text("# B", encoding="utf-8")

        # Existing pack "old" already in index
        old_skill_path = central / "old" / "x" / "SKILL.md"
        old_skill_path.parent.mkdir(parents=True)
        old_skill_path.write_text("# X", encoding="utf-8")

        # Discover returns all of them
        discovered = {
            "newpack/a": _fake_loaded_skill("newpack/a", pack_a),
            "newpack/b": _fake_loaded_skill("newpack/b", pack_b),
            "old/x": _fake_loaded_skill("old/x", old_skill_path),
        }

        # Pre-existing global index has old/x but not newpack
        indexer._save_index({"old/x": _make_profile("old/x")}, scope="global")

        analyzed: list[str] = []

        def _fake_analyze(ls: object, _llm: object) -> SkillProfile:
            sid = ls.metadata.id  # type: ignore[attr-defined]
            analyzed.append(sid)
            return _make_profile(sid)

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(indexer, "_analyze_skill", side_effect=_fake_analyze),
        ):
            result = indexer.update_global_index_for_pack(
                pack_name="newpack",
                pack_storage=central,
                show_progress=False,
            )

        assert result.success is True
        assert result.indexed_count == 2
        # LLM was called only for the new pack's skills
        assert sorted(analyzed) == ["newpack/a", "newpack/b"]

        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert set(merged["skills"].keys()) == {"newpack/a", "newpack/b", "old/x"}

    def test_preserves_existing_other_pack_profiles(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        central = global_home / ".config" / "skills"
        pack_path = central / "newpack" / "a" / "SKILL.md"
        pack_path.parent.mkdir(parents=True)
        pack_path.write_text("# A", encoding="utf-8")
        old_path = central / "old" / "x" / "SKILL.md"
        old_path.parent.mkdir(parents=True)
        old_path.write_text("# X", encoding="utf-8")

        # Pre-existing has old/x with custom differentiation
        old_profile = _make_profile("old/x", differentiation="OLD_VALUE")
        indexer._save_index({"old/x": old_profile}, scope="global")

        discovered = {
            "newpack/a": _fake_loaded_skill("newpack/a", pack_path),
            "old/x": _fake_loaded_skill("old/x", old_path),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            indexer.update_global_index_for_pack(
                pack_name="newpack",
                pack_storage=central,
                show_progress=False,
            )

        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert merged["skills"]["old/x"]["differentiation"] == "OLD_VALUE", (
            "Old pack profile must be preserved"
        )
        assert "newpack/a" in merged["skills"]

    def test_replaces_renamed_skill_in_same_pack(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """Renamed-or-removed skill within a pack must NOT leak into the
        merged index. The cleanup keys off the ``<pack_name>/`` namespace —
        any existing entry that matches the namespace but is no longer in
        the fresh discovery is dropped."""
        central = global_home / ".config" / "skills"
        new_path = central / "newpack" / "new_name" / "SKILL.md"
        new_path.parent.mkdir(parents=True)
        new_path.write_text("# new", encoding="utf-8")

        # Pre-existing index has the OLD skill_id (since renamed/removed).
        # No corresponding file on disk.
        indexer._save_index(
            {
                "newpack/old_name": _make_profile("newpack/old_name"),
                # Non-namespaced and other-pack entries must survive.
                "other/x": _make_profile("other/x"),
            },
            scope="global",
        )

        # discover_all only returns the new skill (old one was removed)
        discovered = {
            "newpack/new_name": _fake_loaded_skill("newpack/new_name", new_path),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            indexer.update_global_index_for_pack(
                pack_name="newpack",
                pack_storage=central,
                show_progress=False,
            )

        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert "newpack/new_name" in merged["skills"]
        assert "newpack/old_name" not in merged["skills"], (
            "Stale namespace entry must be cleaned up when its file is gone"
        )
        # Foreign packs are untouched
        assert "other/x" in merged["skills"]

    def test_empty_pack_name_rejected(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        central = global_home / ".config" / "skills"
        result = indexer.update_global_index_for_pack(
            pack_name="",
            pack_storage=central,
            show_progress=False,
        )
        assert result.success is False
        assert any("non-empty" in e for e in result.errors)

    def test_whitespace_pack_name_rejected(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        central = global_home / ".config" / "skills"
        result = indexer.update_global_index_for_pack(
            pack_name="   ",
            pack_storage=central,
            show_progress=False,
        )
        assert result.success is False
        assert any("non-empty" in e for e in result.errors)

    def test_llm_returning_none_increments_failed_count(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """An LLM that returns None for analysis must bump failed_count and
        record a useful error so the user can see what went wrong."""
        central = global_home / ".config" / "skills"
        skill_path = central / "pack" / "a" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("# A", encoding="utf-8")

        discovered = {
            "pack/a": _fake_loaded_skill("pack/a", skill_path),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                return_value=None,  # Simulate LLM parse failure
            ),
        ):
            result = indexer.update_global_index_for_pack(
                pack_name="pack",
                pack_storage=central,
                show_progress=False,
            )

        assert result.failed_count == 1
        assert result.indexed_count == 0
        assert any("pack/a" in e and "no profile" in e for e in result.errors)

    def test_empty_pack_preserves_existing_index(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        central = global_home / ".config" / "skills"
        # Pre-existing global index
        indexer._save_index({"old/x": _make_profile("old/x")}, scope="global")

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value={},
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
        ):
            result = indexer.update_global_index_for_pack(
                pack_name="ghost",
                pack_storage=central,
                show_progress=False,
            )

        # No skills found → result reports the issue but existing index untouched
        assert any("No skills discovered" in e for e in result.errors)
        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert "old/x" in merged["skills"]

    def test_handles_symlinked_source_file(
        self,
        indexer: SkillIndexer,
        global_home: Path,
        tmp_path: Path,
        symlink_supported: bool,
    ) -> None:
        """Platform symlinks (e.g., ~/.kimi-code/skills/<flat>/SKILL.md) must
        resolve back to the central storage so the source classifier can
        correctly attribute them to the pack."""
        if not symlink_supported:
            pytest.skip("directory symlinks not supported on this host")
        central = global_home / ".config" / "skills"
        real_skill = central / "newpack" / "a" / "SKILL.md"
        real_skill.parent.mkdir(parents=True)
        real_skill.write_text("# real", encoding="utf-8")

        # Create a symlinked copy as a platform would
        platform_dir = global_home / ".kimi-code" / "skills" / "newpack-a"
        platform_dir.parent.mkdir(parents=True, exist_ok=True)
        platform_dir.symlink_to(real_skill.parent, target_is_directory=True)
        symlinked_skill = platform_dir / "SKILL.md"

        # discover_all reports the symlink path
        discovered = {
            "newpack/a": _fake_loaded_skill("newpack/a", symlinked_skill),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            result = indexer.update_global_index_for_pack(
                pack_name="newpack",
                pack_storage=central,
                show_progress=False,
            )

        assert result.success is True
        assert result.indexed_count == 1
        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert "newpack/a" in merged["skills"]

    def test_drops_renamed_non_namespaced_skill_via_pack_owner(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """The P1 fix in action: packs whose skill IDs DON'T follow
        ``<pack>/<skill>`` (e.g. ``superpowers``'s flat ``brainstorming``)
        couldn't be cleaned by the prefix-only scheme. Now ownership is
        carried in ``pack_owner``, so renames are detectable for any ID
        convention."""
        central = global_home / ".config" / "skills"
        new_path = central / "superpowers" / "ideation" / "SKILL.md"
        new_path.parent.mkdir(parents=True)
        new_path.write_text("# new", encoding="utf-8")

        # Existing v1.2 profile: pack_owner="superpowers", flat ID.
        old_profile = _make_profile("brainstorming")
        old_profile.pack_owner = "superpowers"
        indexer._save_index({"brainstorming": old_profile}, scope="global")

        # Pack now ships only "ideation" — "brainstorming" was renamed/removed.
        discovered = {
            "ideation": _fake_loaded_skill("ideation", new_path),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            indexer.update_global_index_for_pack(
                pack_name="superpowers",
                pack_storage=central,
                show_progress=False,
            )

        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert "ideation" in merged["skills"]
        assert "brainstorming" not in merged["skills"], (
            "Non-namespaced stale entry must be dropped via pack_owner match"
        )

    def test_legacy_profile_namespace_fallback_still_works(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """v1.0/v1.1 profiles (no ``pack_owner`` field) for namespaced packs
        must still get cleaned up via the prefix-match fallback. Ensures
        existing user indexes self-heal on first re-index after upgrade."""
        central = global_home / ".config" / "skills"
        new_path = central / "gstack" / "review" / "SKILL.md"
        new_path.parent.mkdir(parents=True)
        new_path.write_text("# review", encoding="utf-8")

        # Pre-existing legacy profile, pack_owner defaults to "".
        legacy_profile = _make_profile("gstack/old")
        assert legacy_profile.pack_owner == "", "Legacy profiles have empty pack_owner"
        indexer._save_index({"gstack/old": legacy_profile}, scope="global")

        discovered = {
            "gstack/review": _fake_loaded_skill("gstack/review", new_path),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            indexer.update_global_index_for_pack(
                pack_name="gstack",
                pack_storage=central,
                show_progress=False,
            )

        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert "gstack/review" in merged["skills"]
        assert "gstack/old" not in merged["skills"], (
            "Legacy namespaced entries must still be cleaned via prefix fallback"
        )

    def test_pack_owner_stamped_on_new_profiles(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """Every profile written by ``update_global_index_for_pack`` must
        carry ``pack_owner = pack_name`` so future re-indexing can identify
        ownership independent of skill_id naming."""
        central = global_home / ".config" / "skills"
        skill = central / "mypack" / "thing" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("# t", encoding="utf-8")

        discovered = {
            "mypack/thing": _fake_loaded_skill("mypack/thing", skill),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            indexer.update_global_index_for_pack(
                pack_name="mypack",
                pack_storage=central,
                show_progress=False,
            )

        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert merged["skills"]["mypack/thing"]["pack_owner"] == "mypack"

    def test_foreign_pack_with_explicit_pack_owner_preserved(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """When indexing pack X, profiles owned by pack Y must remain
        untouched even if their skill_ids don't carry a namespace prefix
        — without ``pack_owner`` the indexer couldn't distinguish them."""
        central = global_home / ".config" / "skills"
        new_path = central / "newpack" / "a" / "SKILL.md"
        new_path.parent.mkdir(parents=True)
        new_path.write_text("# a", encoding="utf-8")

        # Foreign pack profile with non-namespaced ID. Without pack_owner,
        # the old prefix-based logic couldn't tell this apart from a stranger.
        foreign_profile = _make_profile("flat-id", differentiation="FOREIGN")
        foreign_profile.pack_owner = "other"
        indexer._save_index({"flat-id": foreign_profile}, scope="global")

        discovered = {
            "newpack/a": _fake_loaded_skill("newpack/a", new_path),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=discovered,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            indexer.update_global_index_for_pack(
                pack_name="newpack",
                pack_storage=central,
                show_progress=False,
            )

        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert "flat-id" in merged["skills"], "Foreign-pack profile must survive"
        assert merged["skills"]["flat-id"]["pack_owner"] == "other"
        assert merged["skills"]["flat-id"]["differentiation"] == "FOREIGN"
        assert "newpack/a" in merged["skills"]


# ---------------------------------------------------------------------------
# Index path properties
# ---------------------------------------------------------------------------


class TestIndexPaths:
    def test_project_index_path_uses_project_root(
        self, project_root: Path, global_home: Path
    ) -> None:
        indexer = SkillIndexer(project_root=project_root)
        assert indexer.project_index_path == project_root / ".vibe" / "skill-index.json"

    def test_global_index_path_uses_home(self, project_root: Path, global_home: Path) -> None:
        indexer = SkillIndexer(project_root=project_root)
        assert indexer.global_index_path == global_home / ".vibe" / "skill-index.json"

    def test_custom_index_dir_overrides_project_path(
        self, project_root: Path, global_home: Path, tmp_path: Path
    ) -> None:
        custom = tmp_path / "custom_index"
        indexer = SkillIndexer(project_root=project_root, index_dir=custom)
        assert indexer.project_index_path == custom / "skill-index.json"
        # Global path is unaffected by index_dir
        assert indexer.global_index_path == global_home / ".vibe" / "skill-index.json"


def test_index_result_defaults() -> None:
    result = IndexResult()
    assert result.success is False
    assert result.indexed_count == 0
    assert result.failed_count == 0
    assert result.index_path is None
    assert result.errors == []


# ---------------------------------------------------------------------------
# Content-hash cache + parallelism (P2 indexer perf work)
# ---------------------------------------------------------------------------


class TestContentHashCache:
    """Verify the SHA256 prompt-hash cache short-circuits LLM calls when
    a skill's prompt is byte-identical to the existing index.

    The cache is what turns a 5-minute global re-index into a few seconds.
    Without it, every ``vibe quickstart`` re-pays the full LLM cost.
    """

    def test_hash_prompt_is_deterministic(self, indexer: SkillIndexer) -> None:
        """Same input → same hash. If this breaks, the entire cache breaks."""
        h1 = indexer._hash_prompt("hello world")
        h2 = indexer._hash_prompt("hello world")
        assert h1 == h2
        assert len(h1) == 16  # truncated sha256 — see _hash_prompt docstring

    def test_hash_prompt_changes_with_content(self, indexer: SkillIndexer) -> None:
        assert indexer._hash_prompt("a") != indexer._hash_prompt("b")

    def test_analyze_skill_stamps_content_hash(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """``_analyze_skill`` must populate ``content_hash`` so the next run
        can decide whether to skip the LLM call."""
        ls = _fake_loaded_skill("g/a", global_home / ".config" / "skills" / "g" / "a" / "SKILL.md")

        class _StubLLM:
            def call(self, prompt: str, max_tokens: int, temperature: float) -> object:
                return SimpleNamespace(
                    content=json.dumps(
                        {
                            "scenarios": ["s"],
                            "query_patterns": ["q"],
                            "differentiation": "d",
                            "confidence_boosters": ["c"],
                        }
                    )
                )

        profile = indexer._analyze_skill(ls, _StubLLM())
        assert profile is not None
        assert profile.content_hash, "content_hash must be stamped after success"
        # Idempotent: rebuilding the prompt and rehashing matches the stamp.
        expected = indexer._hash_prompt(indexer._build_prompt(ls))
        assert profile.content_hash == expected

    def test_save_and_load_round_trip_preserves_content_hash(self, indexer: SkillIndexer) -> None:
        profile = _make_profile("a/b")
        profile.content_hash = "deadbeefcafe1234"
        indexer._save_index({"a/b": profile}, scope="global")

        loaded = indexer._load_single_index(indexer.global_index_path)
        assert loaded["a/b"].content_hash == "deadbeefcafe1234"

    def test_load_legacy_index_without_content_hash_defaults_empty(
        self, indexer: SkillIndexer
    ) -> None:
        """v1.0 / v1.1 profiles have no content_hash field — they must load
        with an empty hash, which forces a re-analysis on next build."""
        indexer.global_index_path.parent.mkdir(parents=True, exist_ok=True)
        indexer.global_index_path.write_text(
            json.dumps(
                {
                    "version": "1.1.0",
                    "skills": {
                        "old/x": {
                            "skill_id": "old/x",
                            "scenarios": [],
                            "query_patterns": [],
                            "differentiation": "",
                            "confidence_boosters": [],
                            "pack_owner": "old",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        loaded = indexer._load_single_index(indexer.global_index_path)
        assert loaded["old/x"].content_hash == ""

    def test_build_index_skips_llm_for_cached_skills(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """If an existing profile's content_hash matches the freshly-computed
        prompt hash, build_index reuses the cached profile and never calls
        the LLM. Saves both wall-clock and API spend."""
        ls = _fake_loaded_skill("g/a", global_home / ".config" / "skills" / "g" / "a" / "SKILL.md")

        # Materialize source so .resolve() works inside _infer_pack_owner.
        if ls.source_file is not None:
            ls.source_file.parent.mkdir(parents=True, exist_ok=True)
            ls.source_file.write_text("# stub", encoding="utf-8")

        # Pre-seed the global index with a profile whose content_hash matches
        # what the indexer would compute for this skill.
        cached_hash = indexer._hash_prompt(indexer._build_prompt(ls))
        cached_profile = _make_profile("g/a", differentiation="CACHED")
        cached_profile.content_hash = cached_hash
        cached_profile.pack_owner = "g"
        indexer._save_index({"g/a": cached_profile}, scope="global")

        analyze_calls: list[str] = []

        def _spy_analyze(loaded: object, _llm: object) -> SkillProfile:
            analyze_calls.append(loaded.metadata.id)  # type: ignore[attr-defined]
            return _make_profile(loaded.metadata.id)  # type: ignore[attr-defined]

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value={"g/a": ls},
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(indexer, "_analyze_skill", side_effect=_spy_analyze),
        ):
            result = indexer.build_index(scope="global", show_progress=False)

        assert result.success is True
        assert result.indexed_count == 1
        assert analyze_calls == [], "Cache hit must skip the LLM call entirely"

        # Cached profile content survives — proves the cache hit was used,
        # not just silently overwritten.
        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert merged["skills"]["g/a"]["differentiation"] == "CACHED"

    def test_force_bypasses_cache(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """``force=True`` must re-analyze every skill, even cached ones.
        Use case: the prompt template changed, every profile needs rebuilding."""
        ls = _fake_loaded_skill("g/a", global_home / ".config" / "skills" / "g" / "a" / "SKILL.md")
        if ls.source_file is not None:
            ls.source_file.parent.mkdir(parents=True, exist_ok=True)
            ls.source_file.write_text("# stub", encoding="utf-8")

        cached_hash = indexer._hash_prompt(indexer._build_prompt(ls))
        cached_profile = _make_profile("g/a", differentiation="CACHED")
        cached_profile.content_hash = cached_hash
        indexer._save_index({"g/a": cached_profile}, scope="global")

        analyze_calls: list[str] = []

        def _spy_analyze(loaded: object, _llm: object) -> SkillProfile:
            analyze_calls.append(loaded.metadata.id)  # type: ignore[attr-defined]
            return _make_profile(loaded.metadata.id, differentiation="FRESH")  # type: ignore[attr-defined]

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value={"g/a": ls},
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(indexer, "_analyze_skill", side_effect=_spy_analyze),
        ):
            indexer.build_index(scope="global", show_progress=False, force=True)

        assert analyze_calls == ["g/a"], "force=True must re-run analysis even when hash matches"
        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert merged["skills"]["g/a"]["differentiation"] == "FRESH"

    def test_cache_invalidated_when_skill_content_changes(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """Changing skill content changes the prompt → hash mismatch →
        cache miss → LLM re-analyzes. This is the bug the cache MUST NOT have:
        stale results for genuinely-changed skills."""
        ls = _fake_loaded_skill("g/a", global_home / ".config" / "skills" / "g" / "a" / "SKILL.md")

        # Stash a profile with a stale hash (computed from a different prompt).
        stale_profile = _make_profile("g/a")
        stale_profile.content_hash = "0" * 16  # Doesn't match anything real
        indexer._save_index({"g/a": stale_profile}, scope="global")

        analyze_calls: list[str] = []

        def _spy_analyze(loaded: object, _llm: object) -> SkillProfile:
            analyze_calls.append(loaded.metadata.id)  # type: ignore[attr-defined]
            return _make_profile(loaded.metadata.id)  # type: ignore[attr-defined]

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value={"g/a": ls},
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(indexer, "_analyze_skill", side_effect=_spy_analyze),
        ):
            indexer.build_index(scope="global", show_progress=False)

        assert analyze_calls == ["g/a"], "Hash mismatch must trigger fresh LLM analysis"

    def test_update_global_index_for_pack_uses_cache(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """Same cache logic must apply to incremental pack updates — that's
        the hot path during ``vibe pack add`` re-runs."""
        central = global_home / ".config" / "skills"
        skill_path = central / "newpack" / "a" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text("# A", encoding="utf-8")

        ls = _fake_loaded_skill("newpack/a", skill_path)
        cached_hash = indexer._hash_prompt(indexer._build_prompt(ls))
        cached_profile = _make_profile("newpack/a", differentiation="CACHED")
        cached_profile.content_hash = cached_hash
        cached_profile.pack_owner = "newpack"
        indexer._save_index({"newpack/a": cached_profile}, scope="global")

        analyze_calls: list[str] = []

        def _spy_analyze(loaded: object, _llm: object) -> SkillProfile:
            analyze_calls.append(loaded.metadata.id)  # type: ignore[attr-defined]
            return _make_profile(loaded.metadata.id)  # type: ignore[attr-defined]

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value={"newpack/a": ls},
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(indexer, "_analyze_skill", side_effect=_spy_analyze),
        ):
            result = indexer.update_global_index_for_pack(
                pack_name="newpack",
                pack_storage=central,
                show_progress=False,
            )

        assert result.success is True
        assert result.indexed_count == 1
        assert analyze_calls == [], "Pack-level cache hit must skip LLM"
        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        # Cache hit preserves cached profile, refreshes pack_owner.
        assert merged["skills"]["newpack/a"]["differentiation"] == "CACHED"
        assert merged["skills"]["newpack/a"]["pack_owner"] == "newpack"


class TestParallelism:
    """The ThreadPoolExecutor path is what makes the indexer's wall-clock
    time scale with provider response time, not skill count."""

    def test_build_index_parallelizes_independent_skills(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """Many skills, slow analyze → wall time should be << serial. We
        verify by introducing a small artificial delay in `_analyze_skill`
        and checking the total elapsed is consistent with concurrency."""
        import threading
        import time

        # 8 skills × 50ms each. Serial ≥ 400ms, parallel (8 workers) ≈ 50–100ms.
        # We assert against a generous bound (250ms) to stay deflakey on slow CI.
        skills = {}
        for i in range(8):
            sid = f"g/{i}"
            skills[sid] = _fake_loaded_skill(
                sid, global_home / ".config" / "skills" / "g" / str(i) / "SKILL.md"
            )

        max_concurrent = 0
        active = 0
        lock = threading.Lock()

        def _slow_analyze(loaded: object, _llm: object) -> SkillProfile:
            nonlocal active, max_concurrent
            with lock:
                active += 1
                max_concurrent = max(max_concurrent, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return _make_profile(loaded.metadata.id)  # type: ignore[attr-defined]

        start = time.perf_counter()
        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=skills,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(indexer, "_analyze_skill", side_effect=_slow_analyze),
            # Embedding computation is out of scope for this test; with the
            # semantic extra installed it would load a real model (~10s) and
            # drown the parallelism timing assertion.
            patch.object(indexer, "_compute_embeddings"),
        ):
            result = indexer.build_index(scope="global", show_progress=False, max_workers=8)
        elapsed = time.perf_counter() - start

        assert result.success is True
        assert result.indexed_count == 8
        # Serial would be ~400ms; parallel with 8 workers ≈ 50ms.
        # Generous bound to absorb scheduling + GIL noise.
        assert elapsed < 0.25, f"Indexer not parallelizing: 8×50ms slept took {elapsed:.3f}s"
        assert max_concurrent > 1, "Expected concurrent _analyze_skill executions"

    def test_analyze_failure_in_one_thread_doesnt_kill_others(
        self,
        indexer: SkillIndexer,
        global_home: Path,
    ) -> None:
        """A single skill raising must increment failed_count without
        aborting the whole batch — the indexer is best-effort by design."""
        skills = {
            "g/ok": _fake_loaded_skill(
                "g/ok", global_home / ".config" / "skills" / "g" / "ok" / "SKILL.md"
            ),
            "g/boom": _fake_loaded_skill(
                "g/boom",
                global_home / ".config" / "skills" / "g" / "boom" / "SKILL.md",
            ),
        }

        def _maybe_explode(loaded: object, _llm: object) -> SkillProfile:
            sid = loaded.metadata.id  # type: ignore[attr-defined]
            if sid == "g/boom":
                raise RuntimeError("provider down")
            return _make_profile(sid)

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=skills,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(indexer, "_analyze_skill", side_effect=_maybe_explode),
        ):
            result = indexer.build_index(scope="global", show_progress=False)

        assert result.indexed_count == 1
        assert result.failed_count == 1
        assert any("g/boom" in e for e in result.errors)
        # Surviving skill still in the saved index.
        merged = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert "g/ok" in merged["skills"]
        assert "g/boom" not in merged["skills"]


class TestProgressSuppression:
    """Tests run with show_progress=False to keep CI logs clean. This is a
    contract — if a future Rich update auto-attaches to stderr unconditionally,
    this test catches it."""

    def test_show_progress_false_emits_nothing_to_console(
        self,
        indexer: SkillIndexer,
        global_home: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        skills = {
            "g/a": _fake_loaded_skill(
                "g/a", global_home / ".config" / "skills" / "g" / "a" / "SKILL.md"
            ),
        }

        with (
            patch(
                "vibesop.core.skills.loader.SkillLoader.discover_all",
                return_value=skills,
            ),
            patch.object(indexer, "_get_llm", return_value=SimpleNamespace()),
            patch.object(
                indexer,
                "_analyze_skill",
                side_effect=lambda ls, _llm: _make_profile(ls.metadata.id),
            ),
        ):
            indexer.build_index(scope="global", show_progress=False)

        captured = capsys.readouterr()
        # Only Rich console output should be silent; logger output is fine.
        assert "Indexing" not in captured.out
        assert "✅ Index built" not in captured.out
        assert "skills indexed" not in captured.out


class TestEmbeddingSupport:
    """Route B: sentence-transformers embedding integration in SkillProfile."""

    def test_profile_to_dict_includes_embedding_when_set(self) -> None:
        prof = _make_profile("a/b")
        prof.embedding = [0.1, 0.2, 0.3]
        d = prof.to_dict()
        assert d["embedding"] == [0.1, 0.2, 0.3]

    def test_profile_to_dict_omits_embedding_when_none(self) -> None:
        prof = _make_profile("a/b")
        prof.embedding = None
        d = prof.to_dict()
        assert "embedding" not in d

    def test_profile_from_dict_parses_embedding(self) -> None:
        d = {
            "skill_id": "a/b",
            "scenarios": ["s"],
            "query_patterns": ["q"],
            "differentiation": "d",
            "confidence_boosters": ["c"],
            "pack_owner": "",
            "content_hash": "",
            "embedding": [0.4, 0.5],
        }
        prof = SkillProfile.from_dict(d)
        assert prof.embedding == [0.4, 0.5]

    def test_profile_from_dict_missing_embedding_defaults_none(self) -> None:
        d = {
            "skill_id": "a/b",
            "scenarios": ["s"],
            "query_patterns": ["q"],
            "differentiation": "d",
            "confidence_boosters": ["c"],
            "pack_owner": "",
            "content_hash": "",
        }
        prof = SkillProfile.from_dict(d)
        assert prof.embedding is None

    def test_save_index_writes_v1_4_0_schema(self, indexer: SkillIndexer) -> None:
        prof = _make_profile("a/b")
        prof.embedding = [0.1, 0.2]
        indexer._save_index({"a/b": prof}, scope="global")

        data = json.loads(indexer.global_index_path.read_text(encoding="utf-8"))
        assert data["version"] == "1.4.0"
        assert data["skills"]["a/b"]["embedding"] == [0.1, 0.2]

    def test_load_single_index_restores_embedding(self, indexer: SkillIndexer) -> None:
        prof = _make_profile("a/b")
        prof.embedding = [0.3, 0.4]
        indexer._save_index({"a/b": prof}, scope="global")

        loaded = indexer._load_single_index(indexer.global_index_path)
        assert loaded["a/b"].embedding == [0.3, 0.4]

    def test_compute_profile_text_concatenates_fields(self, indexer: SkillIndexer) -> None:
        prof = SkillProfile(
            skill_id="x",
            scenarios=["scenario one", "scenario two"],
            query_patterns=["query a", "query b"],
            differentiation="diff sentence",
            confidence_boosters=["boost1", "boost2"],
        )
        text = indexer._compute_profile_text(prof)
        assert "scenario one" in text
        assert "query a" in text
        assert "diff sentence" in text
        assert "boost1" in text

    def test_compute_embeddings_skips_when_library_missing(self, indexer: SkillIndexer) -> None:
        """If sentence-transformers is not installed, embeddings stay None."""
        import sys

        prof = _make_profile("a/b")
        # None in sys.modules simulates a missing library even when the
        # semantic extra is installed in the test environment.
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            indexer._compute_embeddings({"a/b": prof})
        assert prof.embedding is None

    def test_compute_embeddings_uses_fake_module(self, indexer: SkillIndexer) -> None:
        """When a fake sentence_transformers module is present, embeddings are computed."""
        import sys
        from unittest.mock import MagicMock

        prof = _make_profile("a/b")
        prof.scenarios = ["scenario one"]

        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.1, 0.2, 0.3]]

        fake_st = MagicMock()
        fake_st.SentenceTransformer.return_value = mock_model

        with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
            indexer._compute_embeddings({"a/b": prof})

        assert prof.embedding == [0.1, 0.2, 0.3]
