"""Prompt registry for AI Triage (Layer 0).

Supports versioned prompt templates for A/B testing and iterative refinement.
"""

from __future__ import annotations

from typing import ClassVar


class TriagePromptRegistry:
    """Registry of AI Triage prompt templates."""

    VERSIONS: ClassVar[dict[str, str]] = {
        "v1": (
            "You are a skill routing assistant. Your job is to select the single most appropriate "
            "skill for the user's request.\n\n"
            "Instructions:\n"
            "1. Read the user request carefully.\n"
            "2. Consider the intent, not just keywords.\n"
            "3. Select the skill that best matches the request.\n"
            "4. Return ONLY the skill ID. No explanation. No markdown.\n\n"
            "User request: {query}\n\n"
            "Available skills:\n{skills_summary}\n\n"
            "Return ONLY the skill ID (e.g., gstack/review or systematic-debugging):\n"
        ),
    }

    DEFAULT_VERSION = "v1"

    @classmethod
    def get_prompt(cls, version: str | None = None) -> str:
        """Get a prompt template by version.

        Args:
            version: Prompt version. Defaults to DEFAULT_VERSION.

        Returns:
            Prompt template string.
        """
        version = version or cls.DEFAULT_VERSION
        if version not in cls.VERSIONS:
            raise ValueError(f"Unknown triage prompt version: {version}")
        return cls.VERSIONS[version]

    @classmethod
    def list_versions(cls) -> list[str]:
        """List available prompt versions."""
        return list(cls.VERSIONS.keys())

    @classmethod
    def render(
        cls,
        query: str,
        skills_summary: str,
        version: str | None = None,
    ) -> str:
        """Render a prompt for AI Triage.

        Args:
            query: User query.
            skills_summary: Summary of available skills.
            version: Prompt version.

        Returns:
            Rendered prompt string.
        """
        template = cls.get_prompt(version)
        return template.format(query=query, skills_summary=skills_summary)
