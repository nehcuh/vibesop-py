"""Tests for documentation renderer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibesop.builder.doc_models import DocConfig, DocSection
from vibesop.builder.doc_renderer import DocRenderer
from vibesop.builder.doc_templates import DocType
from vibesop.builder.manifest import Manifest


class TestDocRenderer:
    """Tests for DocRenderer."""

    def test_render_success(self, monkeypatch, tmp_path) -> None:
        """Test successful documentation rendering."""
        monkeypatch.chdir(tmp_path)
        renderer = DocRenderer()

        config = DocConfig(
            project_name="TestProject",
            project_description="A test project",
            version="1.0.0",
            author="Test Author",
            license="MIT",
            repository=None,
            doc_type=DocType.README,
            sections=[],
            output_path=tmp_path / "README.md",
        )

        with patch.object(renderer, "_path_safety") as mock_safety:
            mock_safety.verify_writable.return_value = True
            result = renderer.render(config)

        assert result["success"] is True
        assert result["output_path"] == str(tmp_path / "README.md")
        assert (tmp_path / "README.md").exists()

    def test_render_path_safety_fail(self) -> None:
        """Test render when output path is not writable."""
        renderer = DocRenderer()
        config = DocConfig(
            project_name="TestProject",
            project_description="A test project",
            version="1.0.0",
            author="Test Author",
            license="MIT",
            repository=None,
            doc_type=DocType.README,
            sections=[],
            output_path=Path("/nonexistent/output.md"),
        )

        with patch.object(renderer, "_path_safety") as mock_safety:
            mock_safety.verify_writable.return_value = False
            result = renderer.render(config)

        assert result["success"] is False
        assert "Invalid output path" in result["errors"]

    def test_render_from_manifest(self, monkeypatch, tmp_path) -> None:
        """Test render_from_manifest."""
        monkeypatch.chdir(tmp_path)
        renderer = DocRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        manifest.metadata.version = "1.0.0"
        manifest.skills = []
        manifest.policies.behavior = {}

        with patch.object(renderer, "_path_safety") as mock_safety:
            mock_safety.verify_writable.return_value = True
            result = renderer.render_from_manifest(manifest, tmp_path / "docs")

        assert result["success"] is True
        assert len(result["generated"]) > 0

    def test_generate_api_docs(self, monkeypatch, tmp_path) -> None:
        """Test generate_api_docs."""
        monkeypatch.chdir(tmp_path)
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text('"""A module."""\n')

        renderer = DocRenderer()
        with patch.object(renderer, "_path_safety") as mock_safety:
            mock_safety.verify_writable.return_value = True
            result = renderer.generate_api_docs(
                source_dir=src_dir,
                output_path=tmp_path / "API.md",
                project_name="TestProject",
            )

        assert result["success"] is True
        assert result["modules_documented"] >= 1

    def test_generate_all(self, monkeypatch, tmp_path) -> None:
        """Test generate_all."""
        monkeypatch.chdir(tmp_path)
        renderer = DocRenderer()
        manifest = MagicMock()
        manifest.metadata.platform = "claude-code"
        manifest.metadata.version = "1.0.0"
        manifest.skills = []
        manifest.policies.behavior = {}

        with patch.object(renderer, "_path_safety") as mock_safety:
            mock_safety.verify_writable.return_value = True
            result = renderer.generate_all(manifest, tmp_path / "docs")

        assert result["success"] is True
        assert "generated" in result
        assert len(result["generated"]) > 0

    def test_extract_module_docstring(self) -> None:
        """Test _extract_module_docstring static method."""
        content = '"""This is a docstring."""\nprint("hello")\n'
        result = DocRenderer._extract_module_docstring(content)
        assert "This is a docstring" in result
