"""Tests for router_factory.py."""

from pathlib import Path

from vibesop.core.routing.router_factory import RouterFactory


class TestRouterFactory:
    """Tests for RouterFactory — construction and caching."""

    def test_factory_instantiates(self, tmp_path: Path):
        """RouterFactory can be instantiated."""
        factory = RouterFactory(project_root=tmp_path)
        assert factory is not None
        assert factory.project_root == tmp_path

    def test_factory_default_root_is_cwd(self):
        """RouterFactory falls back to cwd."""
        factory = RouterFactory()
        assert factory.project_root == Path.cwd()

