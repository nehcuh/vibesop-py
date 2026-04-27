"""Algorithm registry for VibeSOP.

Provides a central registry for reusable algorithms that skills can reference
in their SKILL.md frontmatter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable


class AlgorithmRegistry:
    """Registry of callable algorithms available to skills.

    Algorithms are registered by a namespaced name (e.g., "demo/double")
    and can be retrieved by skills that declare them in their frontmatter.
    """

    _algorithms: ClassVar[dict[str, Callable[..., Any]]] = {}
    _descriptions: ClassVar[dict[str, str]] = {}

    @classmethod
    def register(cls, name: str, fn: Callable[..., Any], description: str = "") -> None:
        """Register an algorithm.

        Args:
            name: Namespaced algorithm identifier.
            fn: Callable implementing the algorithm.
            description: Human-readable description.
        """
        cls._algorithms[name] = fn
        cls._descriptions[name] = description

    @classmethod
    def get(cls, name: str) -> Callable[..., Any] | None:
        """Get a registered algorithm by name.

        Args:
            name: Algorithm identifier.

        Returns:
            The callable if found, otherwise None.
        """
        return cls._algorithms.get(name)

    @classmethod
    def list_algorithms(cls) -> list[dict[str, str]]:
        """List all registered algorithms."""
        return [
            {
                "name": name,
                "description": cls._descriptions.get(name, ""),
            }
            for name in sorted(cls._algorithms.keys())
        ]

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if an algorithm is registered."""
        return name in cls._algorithms
