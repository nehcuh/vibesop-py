"""Tests for AlgorithmRegistry."""

from vibesop.core.algorithms import AlgorithmRegistry
from vibesop.core.algorithms.interview.ambiguity import compute_ambiguity


class TestAlgorithmRegistry:
    """Test algorithm registration and lookup."""

    def test_get_existing_algorithm(self) -> None:
        fn = AlgorithmRegistry.get("interview/compute_ambiguity")
        assert fn is compute_ambiguity

    def test_get_unknown_algorithm_returns_none(self) -> None:
        assert AlgorithmRegistry.get("unknown/missing") is None

    def test_is_registered(self) -> None:
        assert AlgorithmRegistry.is_registered("ralph/scan_file")
        assert not AlgorithmRegistry.is_registered("not/registered")

    def test_list_algorithms(self) -> None:
        algorithms = AlgorithmRegistry.list_algorithms()
        names = {a["name"] for a in algorithms}
        assert "interview/compute_ambiguity" in names
        assert "ralph/scan_file" in names
        assert "ralph/scan_files" in names

    def test_register_new_algorithm(self) -> None:
        def demo_fn(x: int) -> int:
            return x * 2

        AlgorithmRegistry.register("demo/double", demo_fn, description="Doubles a number")
        assert AlgorithmRegistry.get("demo/double") is demo_fn
        assert AlgorithmRegistry.is_registered("demo/double")
