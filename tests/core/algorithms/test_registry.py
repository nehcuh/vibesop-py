"""Tests for AlgorithmRegistry."""

from vibesop.core.algorithms import AlgorithmRegistry


class TestAlgorithmRegistry:
    """Test algorithm registration and lookup."""

    def _register_demo(self) -> None:
        def demo_fn(x: int) -> int:
            return x * 2

        AlgorithmRegistry.register("demo/double", demo_fn, description="Doubles a number")

    def test_register_and_get(self) -> None:
        def add_fn(x: int, y: int) -> int:
            return x + y

        AlgorithmRegistry.register("demo/add", add_fn, description="Adds two numbers")
        assert AlgorithmRegistry.get("demo/add") is add_fn

    def test_is_registered(self) -> None:
        self._register_demo()
        assert AlgorithmRegistry.is_registered("demo/double")
        assert not AlgorithmRegistry.is_registered("not/registered")

    def test_list_algorithms(self) -> None:
        self._register_demo()
        algorithms = AlgorithmRegistry.list_algorithms()
        names = {a["name"] for a in algorithms}
        assert "demo/double" in names

    def test_get_unknown_algorithm_returns_none(self) -> None:
        assert AlgorithmRegistry.get("unknown/missing") is None
