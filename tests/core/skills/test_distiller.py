"""Tests for the LLM skill distiller (P4, design doc §7.2)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from vibesop.core.skills.distiller import DistillError, DistillResult, SkillDistiller
from vibesop.core.skills.suggestion_collector import SkillSuggestion
from vibesop.llm.base import LLMResponse

VALID_LLM_OUTPUT = """---
id: custom/my-flow
name: my-flow
description: Automates the repeated my-flow workflow
tags: [workflow, automation]
trigger_when: user repeats the my-flow steps
namespace: evil-override-attempt
version: 1.0.0
type: workflow
auto_generated: false
---

# My Flow

## Overview

Does things.

## Workflow Steps

1. read:a
2. edit:b
3. write:c

## Usage

vibe route "run my flow"
"""


def _suggestion() -> SkillSuggestion:
    return SkillSuggestion(
        id="sug_abc123",
        pattern_steps=["read:a", "edit:b", "write:c"],
        success_rate=0.9,
        occurrences=8,
        suggested_name="my-flow",
        suggested_description="Auto-detected workflow: read:a → edit:b → write:c",
        confidence=0.85,
        context_tags=["python"],
    )


def _mock_provider(content: str = VALID_LLM_OUTPUT, *, configured: bool = True) -> MagicMock:
    provider = MagicMock()
    provider.configured.return_value = configured
    provider.provider_name = "MockProvider"
    provider.default_model.return_value = "mock-model-1"
    provider.call.return_value = LLMResponse(
        content=content,
        model="mock-model-1",
        provider="MockProvider",
    )
    return provider


def _frontmatter(content: str) -> dict:
    parts = content.split("---", 2)
    assert len(parts) >= 3, "output must contain frontmatter delimiters"
    data = yaml.safe_load(parts[1])
    assert isinstance(data, dict)
    return data


class TestAvailability:
    def test_unavailable_when_factory_fails(self, tmp_path: Path) -> None:
        with patch("vibesop.llm.factory.create_provider", side_effect=RuntimeError("no sdk")):
            distiller = SkillDistiller(tmp_path)
        assert not distiller.is_available()

    def test_unavailable_when_provider_not_configured(self, tmp_path: Path) -> None:
        provider = _mock_provider(configured=False)
        distiller = SkillDistiller(tmp_path, provider=provider)
        assert not distiller.is_available()

    def test_available_with_injected_provider(self, tmp_path: Path) -> None:
        distiller = SkillDistiller(tmp_path, provider=_mock_provider())
        assert distiller.is_available()
        assert distiller.provider_name == "MockProvider"
        assert distiller.model == "mock-model-1"

    def test_auto_detect_uses_factory(self, tmp_path: Path) -> None:
        provider = _mock_provider()
        with patch("vibesop.llm.factory.create_provider", return_value=provider) as factory:
            distiller = SkillDistiller(tmp_path)
        factory.assert_called_once_with()
        assert distiller.is_available()


class TestPromptConstruction:
    def test_prompt_contains_sequence_and_metadata(self, tmp_path: Path) -> None:
        provider = _mock_provider()
        distiller = SkillDistiller(tmp_path, provider=provider)
        distiller.distill(_suggestion())

        prompt = provider.call.call_args.args[0]
        assert "1. read:a" in prompt
        assert "2. edit:b" in prompt
        assert "3. write:c" in prompt
        assert "my-flow" in prompt
        assert "8 times" in prompt
        assert "90% success" in prompt
        assert "NEVER include secrets" in prompt

    def test_representative_queries_are_redacted(self, tmp_path: Path) -> None:
        provider = _mock_provider()
        distiller = SkillDistiller(tmp_path, provider=provider)
        distiller.distill(
            _suggestion(),
            representative_queries=[
                "email me at alice@corp.com about the deploy",
                "my key is sk-abcdefghijklmnop1234",
            ],
        )

        prompt = provider.call.call_args.args[0]
        assert "alice@corp.com" not in prompt
        assert "sk-abcdefghijklmnop1234" not in prompt
        assert "[REDACTED_EMAIL]" in prompt
        assert "[REDACTED_KEY]" in prompt

    def test_no_queries_no_queries_section(self, tmp_path: Path) -> None:
        provider = _mock_provider()
        distiller = SkillDistiller(tmp_path, provider=provider)
        distiller.distill(_suggestion())

        prompt = provider.call.call_args.args[0]
        assert "privacy-redacted" not in prompt


class TestOutputCleaning:
    def test_happy_path_overrides_and_result(self, tmp_path: Path) -> None:
        provider = _mock_provider()
        distiller = SkillDistiller(tmp_path, provider=provider)
        result = distiller.distill(_suggestion())

        assert isinstance(result, DistillResult)
        assert result.provider_name == "MockProvider"
        assert result.model == "mock-model-1"

        fm = _frontmatter(result.content)
        # Required fields survive.
        assert fm["id"] == "custom/my-flow"
        assert fm["name"] == "my-flow"
        assert fm["description"]
        # Forced overrides — LLM attempts must not win.
        assert fm["namespace"] == "custom"
        assert fm["auto_generated"] is True
        assert fm["source_suggestion"] == "sug_abc123"
        # Body survives.
        assert "## Workflow Steps" in result.content

    def test_fenced_output_is_unwrapped(self, tmp_path: Path) -> None:
        fenced = f"```markdown\n{VALID_LLM_OUTPUT}```\n"
        provider = _mock_provider(content=fenced)
        distiller = SkillDistiller(tmp_path, provider=provider)
        result = distiller.distill(_suggestion())

        assert result.content.startswith("---")
        assert "```" not in result.content
        assert _frontmatter(result.content)["name"] == "my-flow"

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        no_name = VALID_LLM_OUTPUT.replace("name: my-flow\n", "")
        provider = _mock_provider(content=no_name)
        distiller = SkillDistiller(tmp_path, provider=provider)
        with pytest.raises(DistillError, match="name"):
            distiller.distill(_suggestion())

    def test_missing_frontmatter_raises(self, tmp_path: Path) -> None:
        provider = _mock_provider(content="# Just markdown, no frontmatter\n")
        distiller = SkillDistiller(tmp_path, provider=provider)
        with pytest.raises(DistillError, match="frontmatter"):
            distiller.distill(_suggestion())

    def test_non_mapping_frontmatter_raises(self, tmp_path: Path) -> None:
        provider = _mock_provider(content="---\n- a\n- b\n---\nbody\n")
        distiller = SkillDistiller(tmp_path, provider=provider)
        with pytest.raises(DistillError, match="mapping"):
            distiller.distill(_suggestion())

    def test_invalid_yaml_frontmatter_raises(self, tmp_path: Path) -> None:
        provider = _mock_provider(content="---\nid: [unclosed\n---\nbody\n")
        distiller = SkillDistiller(tmp_path, provider=provider)
        with pytest.raises(DistillError, match="YAML"):
            distiller.distill(_suggestion())

    def test_yaml_unsafe_description_is_escaped(self, tmp_path: Path) -> None:
        # Valid YAML on input (single-quoted), but the value would break a
        # bare re-emission — safe_dump must re-quote it.
        tricky = VALID_LLM_OUTPUT.replace(
            "description: Automates the repeated my-flow workflow",
            "description: 'has: colon, [brackets], #hash and \"quotes\"'",
        )
        provider = _mock_provider(content=tricky)
        distiller = SkillDistiller(tmp_path, provider=provider)
        result = distiller.distill(_suggestion())

        # Re-serialized frontmatter must parse back cleanly.
        fm = _frontmatter(result.content)
        assert "colon" in fm["description"]
        assert "#hash" in fm["description"]

    def test_llm_supplied_id_is_overridden(self, tmp_path: Path) -> None:
        # The id must match the directory / registered skill_id — both derive
        # from the suggested name, never from the LLM.
        wrong_id = VALID_LLM_OUTPUT.replace("id: custom/my-flow", "id: custom/not-my-flow")
        provider = _mock_provider(content=wrong_id)
        distiller = SkillDistiller(tmp_path, provider=provider)
        result = distiller.distill(_suggestion())

        assert _frontmatter(result.content)["id"] == "custom/my-flow"

    def test_body_secrets_are_redacted_and_flagged(self, tmp_path: Path) -> None:
        leaky = VALID_LLM_OUTPUT.replace(
            'vibe route "run my flow"',
            'vibe route "run my flow" --key sk-abcdefghijklmnop1234',
        )
        provider = _mock_provider(content=leaky)
        distiller = SkillDistiller(tmp_path, provider=provider)
        result = distiller.distill(_suggestion())

        assert result.redacted is True
        assert "sk-abcdefghijklmnop1234" not in result.content
        assert "[REDACTED_KEY]" in result.content
        # Frontmatter is re-serialized, not redacted.
        assert _frontmatter(result.content)["id"] == "custom/my-flow"

    def test_clean_body_is_not_redacted(self, tmp_path: Path) -> None:
        provider = _mock_provider()
        distiller = SkillDistiller(tmp_path, provider=provider)
        result = distiller.distill(_suggestion())
        assert result.redacted is False


class TestDistillErrors:
    def test_distill_raises_when_unavailable(self, tmp_path: Path) -> None:
        provider = _mock_provider(configured=False)
        distiller = SkillDistiller(tmp_path, provider=provider)
        with pytest.raises(DistillError, match="No configured LLM provider"):
            distiller.distill(_suggestion())
        provider.call.assert_not_called()

    def test_llm_call_failure_is_wrapped(self, tmp_path: Path) -> None:
        provider = _mock_provider()
        provider.call.side_effect = ConnectionError("network down")
        distiller = SkillDistiller(tmp_path, provider=provider)
        with pytest.raises(DistillError, match="LLM call failed"):
            distiller.distill(_suggestion())

    def test_result_falls_back_to_provider_identity(self, tmp_path: Path) -> None:
        provider = _mock_provider()
        provider.call.return_value = LLMResponse(content=VALID_LLM_OUTPUT, model="", provider="")
        distiller = SkillDistiller(tmp_path, provider=provider)
        result = distiller.distill(_suggestion())
        assert result.provider_name == "MockProvider"
        assert result.model == "mock-model-1"
