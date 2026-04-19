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
        "v2": (
            "You are a skill routing assistant. Your job is to select the single most appropriate "
            "skill for the user's request.\n\n"
            "Instructions:\n"
            "1. Read the user request carefully.\n"
            "2. Consider the intent, not just keywords.\n"
            "3. Select the skill that best matches the request from the available skills.\n"
            "4. Respond with a JSON object containing ONLY the selected skill_id.\n"
            "5. If no skill matches well, use skill_id: null\n\n"
            "User request: {query}\n\n"
            "Available skills:\n{skills_summary}\n\n"
            "Return JSON in this exact format (no markdown, no explanation):\n"
            '{{"skill_id": "<selected-skill-id>"}}\n'
        ),
        "v3": (
            "You are an expert skill routing assistant. Your job is to select the most appropriate "
            "skill for the user's request by analyzing semantic intent.\n\n"
            "Guidelines:\n"
            "1. Analyze the USER'S INTENT, not just keywords. What do they want to accomplish?\n"
            "2. Consider the CONTEXT: Is this debugging, testing, reviewing, or planning?\n"
            "3. Match to the skill whose PRIMARY PURPOSE aligns with the user's goal.\n"
            "4. Prefer specific skills over general ones (e.g., 'gstack/qa' over 'superpowers/tdd' for testing).\n"
            "5. If multiple skills could apply, choose the one that best matches the specific scenario.\n\n"
            "Common patterns:\n"
            "- 'review code', 'check PR' → gstack/review or superpowers/review\n"
            "- 'test this', 'QA' → gstack/qa (for browser testing) or superpowers/tdd (for test-writing)\n"
            "- 'optimize', 'slow' → superpowers/optimize (performance) or systematic-debugging (if investigating)\n"
            "- 'design', 'architecture' → gstack/architect (system design) or gstack/plan-design-review (review)\n"
            "- 'refactor', 'clean up' → superpowers/refactor\n"
            "- 'debug', 'error', 'broken' → systematic-debugging or gstack/investigate (complex cases)\n\n"
            "User request: {query}\n\n"
            "Available skills:\n{skills_summary}\n\n"
            "Respond with a JSON object (no markdown, no explanation):\n"
            '{{"skill_id": "<selected-skill-id>", "confidence": <0.0-1.0>}}\n'
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
