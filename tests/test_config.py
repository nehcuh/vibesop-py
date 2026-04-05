"""Test configuration manager (v3.0.0)."""

from pathlib import Path

from vibesop.core.config import ConfigManager


class TestConfigLoader:
    """Test ConfigManager class (renamed from ConfigLoader in v3.0.0)."""

    def test_init_with_default_path(self) -> None:
        """Test initialization with default path."""
        manager = ConfigManager()
        assert manager.project_root == Path().resolve()

    def test_init_with_custom_path(self) -> None:
        """Test initialization with custom path."""
        manager = ConfigManager(project_root="/tmp")
        assert manager.project_root == Path("/tmp").resolve()

    def test_get_routing_config(self) -> None:
        """Test getting routing configuration."""
        manager = ConfigManager(project_root=".")
        config = manager.get_routing_config()

        assert config is not None
        assert hasattr(config, "min_confidence")
        assert 0.0 <= config.min_confidence <= 1.0

    def test_get_security_config(self) -> None:
        """Test getting security configuration."""
        manager = ConfigManager(project_root=".")
        config = manager.get_security_config()

        assert config is not None
        assert hasattr(config, "scan_external")

    def test_get_semantic_config(self) -> None:
        """Test getting semantic configuration."""
        manager = ConfigManager(project_root=".")
        config = manager.get_semantic_config()

        assert config is not None
        assert hasattr(config, "enabled")

    def test_get_with_default(self) -> None:
        """Test getting config value with default."""
        manager = ConfigManager(project_root=".")

        # Non-existent key with default
        value = manager.get("non.existent.key", default="default_value")
        assert value == "default_value"

    def test_get_nested_value(self) -> None:
        """Test getting nested config value."""
        manager = ConfigManager(project_root=".")

        # Get min_confidence
        min_conf = manager.get("routing.min_confidence")
        assert min_conf is not None
        assert isinstance(min_conf, float)

    def test_set_cli_override(self) -> None:
        """Test setting CLI override."""
        manager = ConfigManager(project_root=".")

        # Set CLI override
        manager.set_cli_override("routing.min_confidence", 0.99)
        value = manager.get("routing.min_confidence")
        assert value == 0.99

    def test_reload(self) -> None:
        """Test reloading configuration."""
        manager = ConfigManager(project_root=".")

        # Should not raise
        manager.reload()

        # Config should still be accessible
        config = manager.get_routing_config()
        assert config is not None
