"""Tests for documentation models."""

from pathlib import Path

from vibesop.builder.doc_models import DocConfig, DocSection
from vibesop.builder.doc_templates import DocType


class TestDocSection:
    """Tests for DocSection dataclass."""

    def test_create_doc_section(self) -> None:
        """Test creating a basic documentation section."""
        section = DocSection(
            title="Overview",
            content="Project overview content.",
            order=1,
        )

        assert section.title == "Overview"
        assert section.content == "Project overview content."
        assert section.order == 1
        assert section.enabled is True

    def test_doc_section_disabled(self) -> None:
        """Test creating a disabled documentation section."""
        section = DocSection(
            title="Hidden",
            content="This section is hidden.",
            order=2,
            enabled=False,
        )

        assert section.enabled is False


class TestDocConfig:
    """Tests for DocConfig dataclass."""

    def test_create_doc_config(self) -> None:
        """Test creating a documentation configuration."""
        sections = [
            DocSection(title="Intro", content="Welcome", order=1),
        ]
        config = DocConfig(
            project_name="VibeSOP",
            project_description="A test project",
            version="1.0.0",
            author="Test Author",
            license="MIT",
            repository="https://github.com/test/vibesop",
            doc_type=DocType.README,
            sections=sections,
            output_path=Path("README.md"),
        )

        assert config.project_name == "VibeSOP"
        assert config.project_description == "A test project"
        assert config.version == "1.0.0"
        assert config.author == "Test Author"
        assert config.license == "MIT"
        assert config.repository == "https://github.com/test/vibesop"
        assert config.doc_type == DocType.README
        assert config.sections == sections
        assert config.output_path == Path("README.md")

    def test_doc_config_no_repository(self) -> None:
        """Test creating a DocConfig without a repository."""
        config = DocConfig(
            project_name="VibeSOP",
            project_description="A test project",
            version="1.0.0",
            author="Test Author",
            license="MIT",
            repository=None,
            doc_type=DocType.GUIDE,
            sections=[],
            output_path=Path("docs/GUIDE.md"),
        )

        assert config.repository is None
