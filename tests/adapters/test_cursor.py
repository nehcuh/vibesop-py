"""Tests for CursorAdapter."""

import json
from pathlib import Path

import pytest

from vibesop.adapters.cursor import CursorAdapter
from vibesop.adapters.models import Manifest, ManifestMetadata


class TestCursorLLMConfigSecretHandling:
    """D03 counterexample (B1, cursor sibling): rendering the Cursor config
    must not copy ambient API key VALUES into llm-config.json — only the env
    var NAME (the parent FileBasedAdapter ``api_key_env`` convention). Dummy
    credentials only; no real key is involved.
    """

    DUMMY_ANTHROPIC = "sk-dummy-anthropic-value-must-not-be-written"
    DUMMY_OPENAI = "sk-dummy-openai-value-must-not-be-written"

    def test_render_does_not_write_api_key_values(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        adapter = CursorAdapter()
        manifest = Manifest(metadata=ManifestMetadata(platform="cursor"))

        monkeypatch.setenv("ANTHROPIC_API_KEY", self.DUMMY_ANTHROPIC)
        monkeypatch.setenv("OPENAI_API_KEY", self.DUMMY_OPENAI)
        monkeypatch.delenv("VIBE_LLM_PROVIDER", raising=False)

        result = adapter.render_config(manifest, tmp_path)

        assert result.success, f"render failed: {result.errors}"
        llm_path = tmp_path / "llm-config.json"
        assert llm_path.exists(), "render must produce llm-config.json"
        raw = llm_path.read_text(encoding="utf-8")

        assert self.DUMMY_ANTHROPIC not in raw
        assert self.DUMMY_OPENAI not in raw

        # Compatibility contract: the env var NAME stays available so the
        # generated config remains functional without embedding the secret.
        data = json.loads(raw)
        assert data["api_key_env"] == "ANTHROPIC_API_KEY"
