"""Tests for featured skills registry."""

import json
from pathlib import Path

from vibesop.core.skills.featured_registry import (
    FeaturedRegistry,
    FeaturedSkill,
)


class TestFeaturedSkill:
    def test_from_dict(self):
        data = {
            "skill_id": "test/skill",
            "name": "Test Skill",
            "description": "A test skill",
            "stacks": ["python"],
        }
        fs = FeaturedSkill.from_dict(data)
        assert fs.skill_id == "test/skill"
        assert fs.name == "Test Skill"
        assert fs.stacks == ["python"]

    def test_to_dict_roundtrip(self):
        fs = FeaturedSkill(
            skill_id="test/skill",
            name="Test",
            description="Desc",
            stacks=["python"],
            tags=["tdd"],
        )
        d = fs.to_dict()
        fs2 = FeaturedSkill.from_dict(d)
        assert fs2.skill_id == fs.skill_id
        assert fs2.tags == ["tdd"]

    def test_defaults(self):
        fs = FeaturedSkill.from_dict({"skill_id": "x"})
        assert fs.quality_rating == 0.7
        assert fs.priority == 50
        assert fs.stacks == []


class TestFeaturedRegistry:
    def test_loads_defaults(self):
        reg = FeaturedRegistry()
        assert reg.count() > 0
        skills = reg.skills
        assert any(s.skill_id == "superpowers/test-driven-development" for s in skills)
        assert any(s.skill_id == "mattpocock/tdd" for s in skills)

    def test_for_stack(self):
        reg = FeaturedRegistry()
        python_skills = reg.for_stack("python")
        assert len(python_skills) > 0
        for s in python_skills:
            assert "python" in [st.lower() for st in s.stacks]

    def test_for_stack_fallback(self):
        reg = FeaturedRegistry()
        skills = reg.for_stack_or_default("nonexistent-lang", limit=3)
        assert len(skills) > 0
        assert skills[0].quality_rating >= skills[-1].quality_rating

    def test_top_rated(self):
        reg = FeaturedRegistry()
        top = reg.top_rated(limit=3)
        assert len(top) <= 3
        for i in range(len(top) - 1):
            assert top[i].quality_rating >= top[i + 1].quality_rating

    def test_search(self):
        reg = FeaturedRegistry()
        results = reg.search("debug")
        assert len(results) > 0
        for r in results:
            assert (
                "debug" in r.name.lower()
                or "debug" in r.description.lower()
                or any("debug" in t.lower() for t in r.tags)
                or "debug" in r.category.lower()
            )

    def test_wayfinder_batch_present(self):
        """v1.1 wayfinder batch is registered with wayfinder as top priority.

        Verifies the seven mattpocock v1.1 skills (wayfinder + grilling +
        domain-modeling + to-spec + to-tickets + research + prototype)
        are all in the default registry and discoverable via search.
        """
        reg = FeaturedRegistry()
        expected = {
            "mattpocock/wayfinder",
            "mattpocock/grilling",
            "mattpocock/domain-modeling",
            "mattpocock/to-spec",
            "mattpocock/to-tickets",
            "mattpocock/research",
            "mattpocock/prototype",
        }
        actual = {s.skill_id for s in reg.skills}
        missing = expected - actual
        assert not missing, f"wayfinder batch missing from registry: {missing}"

    def test_wayfinder_is_top_priority_mattpocock(self):
        """wayfinder has the highest priority among mattpocock skills —
        it's the headline of the v1.1 batch."""
        reg = FeaturedRegistry()
        mp_skills = [s for s in reg.skills if s.install_source == "mattpocock"]
        assert mp_skills, "expected mattpocock skills in registry"
        top = max(mp_skills, key=lambda s: s.priority)
        assert top.skill_id == "mattpocock/wayfinder", (
            f"wayfinder should be top mattpocock skill; got {top.skill_id} "
            f"(priority={top.priority})"
        )

    def test_search_wayfinder_returns_dependencies(self):
        """Searching 'wayfinder' returns the headline skill plus its
        tagged dependencies (grilling, domain-modeling, etc.)."""
        reg = FeaturedRegistry()
        results = reg.search("wayfinder")
        result_ids = {s.skill_id for s in results}
        assert "mattpocock/wayfinder" in result_ids
        # At least 2 dependencies should be discoverable via the
        # wayfinder-dependency / wayfinder-output tags.
        deps = result_ids - {"mattpocock/wayfinder"}
        assert len(deps) >= 2, (
            f"expected ≥2 wayfinder dependencies in search results; got {deps}"
        )

    def test_get_by_id(self):
        reg = FeaturedRegistry()
        s = reg.get_by_id("superpowers/test-driven-development")
        assert s is not None
        assert s.skill_id == "superpowers/test-driven-development"
        assert s.install_source == "superpowers"

    def test_get_by_id_missing(self):
        reg = FeaturedRegistry()
        assert reg.get_by_id("nonexistent/skill") is None

    def test_stacks_available(self):
        reg = FeaturedRegistry()
        stacks = reg.stacks_available()
        assert "python" in stacks or "typescript" in stacks

    def test_load_from_local_file(self, tmp_path: Path):
        local_file = tmp_path / ".vibe" / "featured-skills.json"
        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "skills": [
                        {"skill_id": "local/skill", "name": "Local", "description": "From file"}
                    ],
                }
            ),
            encoding="utf-8",
        )

        reg = FeaturedRegistry(project_root=tmp_path)
        assert any(s.skill_id == "local/skill" for s in reg.skills)

    def test_export_local(self, tmp_path: Path):
        reg = FeaturedRegistry(project_root=tmp_path)
        path = reg.export_local()
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "skills" in data
        assert len(data["skills"]) > 0

    def test_merge_remote(self):
        reg = FeaturedRegistry()
        before = reg.count()
        added = reg.merge_remote(
            [{"skill_id": "remote/new-skill", "name": "New", "description": "Remote skill"}]
        )
        assert added == 1
        assert reg.count() == before + 1

    def test_merge_no_duplicates(self):
        reg = FeaturedRegistry()
        before = reg.count()
        added = reg.merge_remote(
            [{"skill_id": "superpowers/test-driven-development", "name": "Duplicate"}]
        )
        assert added == 0
        assert reg.count() == before

    def test_reload(self, tmp_path: Path):
        reg = FeaturedRegistry(project_root=tmp_path)
        count = reg.reload()
        assert count > 0
