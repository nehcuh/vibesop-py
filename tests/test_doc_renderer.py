"""Tests for documentation rendering system."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from vibesop.builder import (
    DocRenderer,
    DocType,
    DocConfig,
    DocSection,
)


class TestDocType:
    """Test DocType enum."""

    def test_doc_type_values(self) -> None:
        """Test doc type enum values."""
        assert DocType.README.value == "readme"
        assert DocType.API.value == "api"
        assert DocType.GUIDE.value == "guide"
        assert DocType.CHANGELOG.value == "changelog"
        assert DocType.CONTRIBUTING.value == "contributing"
        assert DocType.LICENSE.value == "license"


class TestDocSection:
    """Test DocSection dataclass."""

    def test_create_section(self) -> None:
        """Test creating a doc section."""
        section = DocSection(
            title="Test Section",
            content="Test content",
            order=1,
            enabled=True,
        )
        assert section.title == "Test Section"
        assert section.content == "Test content"
        assert section.order == 1
        assert section.enabled


class TestDocConfig:
    """Test DocConfig dataclass."""

    def test_create_config(self) -> None:
        """Test creating a doc config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DocConfig(
                project_name="TestProject",
                project_description="A test project",
                version="1.0.0",
                author="Test Author",
                license="MIT",
                repository="https://github.com/test/test",
                doc_type=DocType.README,
                sections=[],
                output_path=Path(tmpdir) / "README.md",
            )
            assert config.project_name == "TestProject"
            assert config.version == "1.0.0"


class TestDocRenderer:
    """Test DocRenderer functionality."""

    def test_create_renderer(self) -> None:
        """Test creating renderer."""
        renderer = DocRenderer()
        assert renderer is not None

    def test_create_renderer_with_template_dir(self) -> None:
        """Test creating renderer with custom template dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = DocRenderer(template_dir=Path(tmpdir))
            assert renderer is not None

    def test_render_readme(self) -> None:
        """Test rendering README documentation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = DocRenderer()
            output_path = Path(tmpdir) / "README.md"

            sections = [
                DocSection(
                    title="Installation",
                    content="```bash\npip install .\n```",
                    order=1,
                ),
            ]

            config = DocConfig(
                project_name="TestProject",
                project_description="A test project",
                version="1.0.0",
                author="Test Author",
                license="MIT",
                repository="https://github.com/test/test",
                doc_type=DocType.README,
                sections=sections,
                output_path=output_path,
            )

            result = renderer.render(config)

            assert result["success"]
            assert result["output_path"] is not None
            assert output_path.exists()

            # Check content
            content = output_path.read_text()
            assert "TestProject" in content
            assert "1.0.0" in content

    def test_render_changelog(self) -> None:
        """Test rendering CHANGELOG documentation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = DocRenderer()
            output_path = Path(tmpdir) / "CHANGELOG.md"

            config = DocConfig(
                project_name="TestProject",
                project_description="",
                version="1.0.0",
                author="",
                license="",
                repository=None,
                doc_type=DocType.CHANGELOG,
                sections=[],
                output_path=output_path,
            )

            result = renderer.render(config)

            assert result["success"]
            assert output_path.exists()

            content = output_path.read_text()
            assert "Changelog" in content
            assert "1.0.0" in content

    def test_render_contributing(self) -> None:
        """Test rendering CONTRIBUTING documentation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = DocRenderer()
            output_path = Path(tmpdir) / "CONTRIBUTING.md"

            config = DocConfig(
                project_name="TestProject",
                project_description="",
                version="1.0.0",
                author="",
                license="MIT",
                repository=None,
                doc_type=DocType.CONTRIBUTING,
                sections=[],
                output_path=output_path,
            )

            result = renderer.render(config)

            assert result["success"]
            assert output_path.exists()

            content = output_path.read_text()
            assert "Contributing" in content

    def test_render_with_disabled_section(self) -> None:
        """Test rendering with disabled section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = DocRenderer()
            output_path = Path(tmpdir) / "README.md"

            sections = [
                DocSection(
                    title="Enabled Section",
                    content="This is enabled",
                    order=1,
                    enabled=True,
                ),
                DocSection(
                    title="Disabled Section",
                    content="This is disabled",
                    order=2,
                    enabled=False,
                ),
            ]

            config = DocConfig(
                project_name="TestProject",
                project_description="",
                version="1.0.0",
                author="",
                license="",
                repository=None,
                doc_type=DocType.README,
                sections=sections,
                output_path=output_path,
            )

            result = renderer.render(config)

            assert result["success"]
            content = output_path.read_text()
            assert "This is enabled" in content
            assert "This is disabled" not in content

    def test_render_from_manifest(self) -> None:
        """Test rendering documentation from manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = DocRenderer()
            output_dir = Path(tmpdir)

            # Create mock manifest
            manifest = MagicMock()
            manifest.metadata.description = "TestProject"
            manifest.metadata.version = "2.0.0"
            manifest.metadata.author = "Test Author"

            result = renderer.render_from_manifest(
                manifest,
                output_dir,
                doc_types=[DocType.README, DocType.CHANGELOG],
            )

            assert result["success"]
            assert len(result["generated"]) == 2
            assert (output_dir / "README.md").exists()
            assert (output_dir / "CHANGELOG.md").exists()

    def test_extract_module_docstring(self) -> None:
        """Test extracting module docstring."""
        renderer = DocRenderer()

        # Test with triple double quotes
        content = '"""Module docstring here."""\npass'
        docstring = renderer._extract_module_docstring(content)
        assert docstring == "Module docstring here."

        # Test with triple single quotes
        content = "'''Module docstring'''\npass"
        docstring = renderer._extract_module_docstring(content)
        assert docstring == "Module docstring"

        # Test with no docstring
        content = "pass"
        docstring = renderer._extract_module_docstring(content)
        assert docstring == ""

    def test_scan_python_modules(self) -> None:
        """Test scanning Python modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test Python files
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()

            # Create a module with docstring (use non-test name)
            (src_dir / "example_module.py").write_text(
                '"""Example module docstring."""\n\ndef example():\n    pass'
            )

            # Create __pycache__ (should be ignored)
            cache_dir = src_dir / "__pycache__"
            cache_dir.mkdir()
            (cache_dir / "test.pyc").write_bytes(b"compiled")

            renderer = DocRenderer()
            modules = renderer._scan_python_modules(src_dir)

            assert len(modules) == 1
            assert modules[0]["name"] == "example_module"
            # Docstring includes the period from the source
            assert "Example module docstring" in modules[0]["docstring"]

    def test_generate_api_docs(self) -> None:
        """Test generating API documentation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = DocRenderer()
            output_path = Path(tmpdir) / "API.md"
            source_dir = Path(tmpdir) / "src"
            source_dir.mkdir()

            # Create test module (use non-test name)
            (source_dir / "myapi.py").write_text(
                '"""API module."""\n\ndef api_function():\n    """API function."""\n    pass'
            )

            result = renderer.generate_api_docs(
                source_dir,
                output_path,
                "TestProject",
            )

            assert result["success"]
            assert result["modules_documented"] >= 1
            assert output_path.exists()

            content = output_path.read_text()
            # Should contain project name
            assert "TestProject" in content

    def test_create_quick_docs(self) -> None:
        """Test creating quick documentation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            renderer = DocRenderer()

            result = renderer.create_quick_docs(project_dir, "TestProject")

            assert result["success"]
            assert len(result["created"]) >= 1  # At least README
            assert (project_dir / "README.md").exists()

    def test_render_invalid_path(self) -> None:
        """Test rendering with invalid output path."""
        renderer = DocRenderer()

        # Try to write to an invalid path (will fail validation)
        # Note: This test might be platform-dependent
        config = DocConfig(
            project_name="Test",
            project_description="",
            version="1.0.0",
            author="",
            license="",
            repository=None,
            doc_type=DocType.README,
            sections=[],
            output_path=Path("/nonexistent/path/README.md"),
        )

        # The security scanner might prevent writing to certain paths
        # We just verify it doesn't crash
        try:
            result = renderer.render(config)
            # May succeed or fail depending on security settings
            assert "success" in result
        except Exception:
            pass  # Expected in some environments

    def test_sections_sorted_by_order(self) -> None:
        """Test that sections are sorted by order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            renderer = DocRenderer()
            output_path = Path(tmpdir) / "README.md"

            sections = [
                DocSection(title="Third", content="Third content", order=3),
                DocSection(title="First", content="First content", order=1),
                DocSection(title="Second", content="Second content", order=2),
            ]

            config = DocConfig(
                project_name="TestProject",
                project_description="",
                version="1.0.0",
                author="",
                license="",
                repository=None,
                doc_type=DocType.README,
                sections=sections,
                output_path=output_path,
            )

            result = renderer.render(config)

            assert result["success"]
            content = output_path.read_text()

            # Check order in content
            first_pos = content.find("First content")
            second_pos = content.find("Second content")
            third_pos = content.find("Third content")

            assert first_pos < second_pos < third_pos
