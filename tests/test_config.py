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

    def test_routing_config_session_aware_default(self) -> None:
        """Test that session_aware defaults to True."""
        from vibesop.core.config import RoutingConfig

        config = RoutingConfig()
        assert config.session_aware is True

    def test_routing_config_session_aware_override(self) -> None:
        """Test that session_aware can be disabled."""
        from vibesop.core.config import RoutingConfig

        config = RoutingConfig(session_aware=False)
        assert config.session_aware is False

    def test_routing_config_stickiness_boost_default(self) -> None:
        """Test that session_stickiness_boost defaults to 0.03."""
        from vibesop.core.config import RoutingConfig

        config = RoutingConfig()
        assert config.session_stickiness_boost == 0.08

    def test_routing_config_stickiness_boost_bounds(self) -> None:
        """Test that session_stickiness_boost respects bounds."""
        from pydantic import ValidationError

        from vibesop.core.config import RoutingConfig

        # Valid values
        config = RoutingConfig(session_stickiness_boost=0.1)
        assert config.session_stickiness_boost == 0.1

        config_zero = RoutingConfig(session_stickiness_boost=0.0)
        assert config_zero.session_stickiness_boost == 0.0

        # Out of bounds
        try:
            RoutingConfig(session_stickiness_boost=0.5)
            raise AssertionError("Should have raised ValidationError")
        except ValidationError:
            pass

        try:
            RoutingConfig(session_stickiness_boost=-0.1)
            raise AssertionError("Should have raised ValidationError")
        except ValidationError:
            pass

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
