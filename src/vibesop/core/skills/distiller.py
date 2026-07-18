"""LLM skill distiller (P4: task distillation, design doc §7.2).

Summarizes a repeated tool/skill sequence (a ``SkillSuggestion`` collected by
``SkillSuggestionCollector``) into a complete SKILL.md via an LLM provider.
The provider is auto-detected through ``vibesop.llm.factory.create_provider``
(no-arg); when no provider is configured, :meth:`SkillDistiller.is_available`
returns False and callers fall back to the template-based generation path.

Privacy: representative queries are passed through
``vibesop.utils.redaction.redact_sensitive`` before entering the prompt, and
the prompt explicitly forbids secrets/paths/usernames in the output. The CLI
layer additionally obtains user consent before anything leaves the machine.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from vibesop.utils.redaction import redact_sensitive

if TYPE_CHECKING:
    from vibesop.core.skills.suggestion_collector import SkillSuggestion

logger = logging.getLogger(__name__)

#: Frontmatter fields the LLM output must carry to be usable at all.
REQUIRED_FRONTMATTER_FIELDS = ("id", "name", "description")


class DistillError(Exception):
    """Raised when LLM distillation fails or yields unusable output."""


@dataclass
class DistillResult:
    """Result of a successful distillation."""

    content: str  # Full SKILL.md text (frontmatter + body).
    provider_name: str
    model: str
    redacted: bool = False  # True when the body carried sensitive-looking tokens.


class SkillDistiller:
    """Distill a sequence suggestion into a SKILL.md via an LLM provider.

    Example:
        >>> distiller = SkillDistiller(Path.cwd())
        >>> if distiller.is_available():
        ...     result = distiller.distill(suggestion)
    """

    MAX_TOKENS = 2000
    MAX_QUERIES = 5

    def __init__(self, project_root: Path, provider: Any | None = None) -> None:
        self._project_root = Path(project_root)
        self._provider: Any = provider
        if self._provider is None:
            try:
                from vibesop.llm.factory import create_provider

                self._provider = create_provider()
            except Exception as e:  # auto-detect must never break the caller
                logger.warning("LLM provider auto-detect failed: %s", e)
                self._provider = None

    def is_available(self) -> bool:
        """True when a configured LLM provider is available."""
        if self._provider is None:
            return False
        try:
            return bool(self._provider.configured())
        except Exception:
            return False

    @property
    def provider_name(self) -> str:
        """Display name of the active provider (for consent/provenance)."""
        if self._provider is None:
            return "none"
        try:
            return str(self._provider.provider_name)
        except Exception:
            return "unknown"

    @property
    def model(self) -> str:
        """Default model of the active provider (for consent/provenance)."""
        if self._provider is None:
            return "unknown"
        try:
            return str(self._provider.default_model())
        except Exception:
            return "unknown"

    def distill(
        self,
        suggestion: SkillSuggestion,
        *,
        representative_queries: list[str] | None = None,
    ) -> DistillResult:
        """Generate a SKILL.md for *suggestion* via the LLM provider.

        Raises:
            DistillError: No provider available, the LLM call failed, or the
                output could not be cleaned into a valid SKILL.md.
        """
        if not self.is_available():
            raise DistillError(
                "No configured LLM provider. Set one of ANTHROPIC_API_KEY / "
                "OPENAI_API_KEY / DEEPSEEK_API_KEY / KIMI_API_KEY / ZHIPU_API_KEY, "
                "or run a local ollama server."
            )

        prompt = self._build_prompt(suggestion, representative_queries)
        try:
            response = self._provider.call(prompt, max_tokens=self.MAX_TOKENS, temperature=0.3)
        except Exception as e:
            raise DistillError(f"LLM call failed ({self.provider_name}): {e}") from e

        content, redacted = self._clean_output(response.content, suggestion)
        provider_name = getattr(response, "provider", None) or self.provider_name
        model = getattr(response, "model", None) or self.model
        return DistillResult(
            content=content,
            provider_name=str(provider_name),
            model=str(model),
            redacted=redacted,
        )

    def _build_prompt(
        self,
        suggestion: SkillSuggestion,
        representative_queries: list[str] | None,
    ) -> str:
        """Build the distillation prompt from the sequence + optional queries.

        Representative queries are redacted BEFORE entering the prompt — the
        prompt is the data that leaves the machine.
        """
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(suggestion.pattern_steps, 1))
        queries_section = ""
        if representative_queries:
            lines = [
                f"- {redact_sensitive(q)}"
                for q in representative_queries[: self.MAX_QUERIES]
                if q.strip()
            ]
            if lines:
                queries_section = (
                    "\nRecent user queries for context (already privacy-redacted,"
                    " may be unrelated):\n" + "\n".join(lines) + "\n"
                )

        return f"""You are converting a repeated developer workflow into a reusable VibeSOP skill.

Observed tool/skill sequence (performed {suggestion.occurrences} times, \
{suggestion.success_rate:.0%} success):
{steps}

Suggested name: {suggestion.suggested_name}
Suggested description: {suggestion.suggested_description}
{queries_section}
Write a complete SKILL.md file for this workflow.

Hard requirements:
- Begin with YAML frontmatter delimited by `---` lines containing exactly these keys:
  id: custom/{suggestion.suggested_name}
  name: {suggestion.suggested_name}
  description: <one sentence — what the workflow automates and when to use it>
  tags: [<3-6 lowercase keywords>]
  trigger_when: <when the router should select this skill>
  namespace: custom
  version: 1.0.0
  type: workflow
- After the frontmatter, a markdown body with exactly these sections:
  # <title>
  ## Overview
  ## Workflow Steps  (numbered, concrete, one action per step, following the observed sequence)
  ## Usage  (example invocation)
- Output ONLY the SKILL.md content — no commentary, no explanation.
- NEVER include secrets, API keys, tokens, absolute file paths, home directories, or user names.
"""

    def _clean_output(self, raw: str, suggestion: SkillSuggestion) -> tuple[str, bool]:
        """Clean LLM output into a validated SKILL.md text.

        Tolerates a ```-fenced response, requires id/name/description in the
        frontmatter, force-overrides the id and provenance fields (they must
        never be trusted to the LLM — the id must stay identical to the
        directory / registered skill_id), redacts sensitive-looking tokens
        from the body, and re-serializes the frontmatter with
        ``yaml.safe_dump`` so free-form values (e.g. description) are always
        YAML-safe.

        Returns:
            ``(content, redacted)`` — the cleaned SKILL.md text and whether
            the body was modified by redaction.
        """
        text = raw.strip()

        # Tolerate a single fenced code block wrapping the whole document.
        fence = re.match(
            r"^```(?:markdown|md|yaml)?\s*\n(?P<body>.*?)\n?```\s*$",
            text,
            re.DOTALL,
        )
        if fence:
            text = fence.group("body").strip()

        if not text.startswith("---"):
            raise DistillError("LLM output has no YAML frontmatter")

        parts = text.split("---", 2)
        if len(parts) < 3:
            raise DistillError("LLM output has malformed YAML frontmatter")

        try:
            frontmatter: Any = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            raise DistillError(f"LLM output frontmatter is not valid YAML: {e}") from e

        if not isinstance(frontmatter, dict):
            raise DistillError("LLM output frontmatter is not a mapping")

        for field_name in REQUIRED_FRONTMATTER_FIELDS:
            value = frontmatter.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise DistillError(f"LLM output frontmatter missing required field: {field_name}")

        # Forced overrides — identity, scope and provenance are never trusted
        # to the LLM. The id must match the directory and the registered
        # skill_id (both derived from the suggested name).
        frontmatter["id"] = f"custom/{suggestion.suggested_name}"
        frontmatter["namespace"] = "custom"
        frontmatter["auto_generated"] = True
        frontmatter["source_suggestion"] = suggestion.id

        yaml_text = yaml.safe_dump(
            frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
        )
        body = parts[2].strip()
        # The prompt forbids secrets, but the LLM may not comply — scrub the
        # body (never the frontmatter we just re-serialized) before anything
        # downstream can persist it.
        redacted_body = redact_sensitive(body)
        redacted = redacted_body != body
        return f"---\n{yaml_text}---\n\n{redacted_body}\n", redacted


__all__ = [
    "DistillError",
    "DistillResult",
    "SkillDistiller",
]
