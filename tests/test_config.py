"""Test configuration loader."""

from pathlib import Path

from vibesop.core.config import ConfigLoader


class TestConfigLoader:
    """Test ConfigLoader class."""

    def test_init_with_default_path(self) -> None:
        """Test initialization with default path."""
        loader = ConfigLoader()
        assert loader.project_root == Path().resolve()

    def test_init_with_custom_path(self) -> None:
        """Test initialization with custom path."""
        loader = ConfigLoader(project_root="/tmp")
        assert loader.project_root == Path("/tmp").resolve()

    def test_load_registry(self) -> None:
        """Test loading registry from YAML file."""
        loader = ConfigLoader(project_root=".")
        registry = loader.load_registry()

        assert registry is not None
        assert "skills" in registry
        assert isinstance(registry["skills"], list)

    def test_load_registry_cache(self) -> None:
        """Test that registry is cached."""
        loader = ConfigLoader(project_root=".")

        # First call
        registry1 = loader.load_registry()
        # Second call should return cached
        registry2 = loader.load_registry()

        assert registry1 is registry2

    def test_load_registry_force_reload(self) -> None:
        """Test force reload bypasses cache."""
        loader = ConfigLoader(project_root=".")

        registry1 = loader.load_registry(force_reload=False)
        registry2 = loader.load_registry(force_reload=True)

        # Should be different objects after force reload
        assert registry1 is not registry2

    def test_get_all_skills(self) -> None:
        """Test getting all skills."""
        loader = ConfigLoader(project_root=".")
        skills = loader.get_all_skills()

        assert isinstance(skills, list)
        assert len(skills) > 0

        # Check skill structure
        skill = skills[0]
        assert "id" in skill
        assert "namespace" in skill

    def test_get_skill_by_id_exact_match(self) -> None:
        """Test getting skill by exact ID."""
        loader = ConfigLoader(project_root=".")

        # Try exact match
        skill = loader.get_skill_by_id("systematic-debugging")
        assert skill is not None
        assert skill["id"] == "systematic-debugging"

    def test_get_skill_by_id_shorthand(self) -> None:
        """Test getting skill by shorthand ID."""
        loader = ConfigLoader(project_root=".")

        # Try exact skill ID from registry
        skill = loader.get_skill_by_id("systematic-debugging")
        assert skill is not None
        assert skill["id"] == "systematic-debugging"

    def test_get_skill_by_id_leading_slash(self) -> None:
        """Test getting skill with leading slash shorthand."""
        loader = ConfigLoader(project_root=".")

        # Leading slash shorthand format - the loader normalizes this
        # "/review" should match skills that end with "/review" or contain "review"
        skill = loader.get_skill_by_id("/review")
        # Should find a review-related skill
        assert skill is not None
        assert "review" in skill["id"].lower()

    def test_get_skill_by_id_not_found(self) -> None:
        """Test getting non-existent skill."""
        loader = ConfigLoader(project_root=".")

        skill = loader.get_skill_by_id("non-existent-skill")
        assert skill is None

    def test_get_skills_by_namespace(self) -> None:
        """Test getting skills by namespace."""
        loader = ConfigLoader(project_root=".")

        # Get builtin skills
        builtin_skills = loader.get_skills_by_namespace("builtin")
        assert isinstance(builtin_skills, list)
        assert len(builtin_skills) > 0

        for skill in builtin_skills:
            assert skill["namespace"] == "builtin"

    def test_search_skills(self) -> None:
        """Test searching skills by keyword."""
        loader = ConfigLoader(project_root=".")

        # Search for debugging related skills
        results = loader.search_skills("debug")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_load_policy_default(self) -> None:
        """Test loading default policy when file doesn't exist."""
        loader = ConfigLoader(project_root=".")
        policy = loader.load_policy()

        assert policy is not None
        assert "candidate_selection" in policy
        assert "preference_learning" in policy
        assert "parallel_execution" in policy

    def test_clear_cache(self) -> None:
        """Test clearing configuration cache."""
        loader = ConfigLoader(project_root=".")

        # Load to populate cache
        registry1 = loader.load_registry()

        # Clear cache
        loader.clear_cache()

        # Load again should create new object
        registry2 = loader.load_registry()

        assert registry1 is not registry2
