"""Tests for vibesop.core.project_analyzer module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from vibesop.core.project_analyzer import ProjectAnalyzer, ProjectProfile

if TYPE_CHECKING:
    from pathlib import Path


class TestProjectProfile:
    """Test ProjectProfile dataclass."""

    def test_defaults(self) -> None:
        profile = ProjectProfile()
        assert profile.project_type is None
        assert profile.tech_stack == []
        assert profile.confidence == 0.0

    def test_to_dict(self) -> None:
        profile = ProjectProfile(
            project_type="python",
            tech_stack=["django", "docker"],
            confidence=0.85,
        )
        data = profile.to_dict()
        assert data["project_type"] == "python"
        assert data["tech_stack"] == ["django", "docker"]
        assert data["confidence"] == 0.85


class TestProjectAnalyzer:
    """Test ProjectAnalyzer detection logic."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert profile.project_type is None
        assert profile.tech_stack == []
        assert profile.confidence == 0.0

    def test_detect_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"test\"")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert profile.project_type == "python"
        assert profile.confidence > 0.0

    def test_detect_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]\nname = \"test\"")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert profile.project_type == "rust"

    def test_detect_javascript(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "test"}')
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert profile.project_type == "javascript"

    def test_detect_typescript(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert profile.project_type == "typescript"

    def test_detect_go(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/test")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert profile.project_type == "go"

    def test_detect_java(self, tmp_path: Path) -> None:
        (tmp_path / "pom.xml").write_text("<project></project>")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert profile.project_type == "java"

    def test_detect_docker(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("FROM python:3.12")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert "docker" in profile.tech_stack

    def test_detect_django(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("django>=4.0\n")
        (tmp_path / "manage.py").write_text("#!/usr/bin/env python")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert "django" in profile.tech_stack

    def test_detect_fastapi(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100\n")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert "fastapi" in profile.tech_stack

    def test_detect_flask(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["flask>=2.0"]')
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert "flask" in profile.tech_stack

    def test_detect_react(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18.0"}}')
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert "react" in profile.tech_stack

    def test_detect_nextjs(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"dependencies": {"next": "^14.0"}}')
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert "nextjs" in profile.tech_stack

    def test_multiple_tech_stack(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("django>=4.0\nfastapi>=0.100\n")
        (tmp_path / "Dockerfile").write_text("FROM python:3.12")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert "django" in profile.tech_stack
        assert "fastapi" in profile.tech_stack
        assert "docker" in profile.tech_stack

    def test_confidence_with_multiple_markers(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"test\"")
        (tmp_path / "requirements.txt").write_text("django\n")
        (tmp_path / "setup.py").write_text("from setuptools import setup")
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert profile.confidence > 0.6

    def test_cache(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"test\"")
        analyzer = ProjectAnalyzer(tmp_path)
        profile1 = analyzer.analyze()
        profile2 = analyzer.analyze()
        assert profile1 is profile2  # Same cached object

    def test_skill_relevance_boost_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"test\"")
        analyzer = ProjectAnalyzer(tmp_path)
        boost = analyzer.get_skill_relevance_boost(["python", "debug", "code"])
        assert boost > 0.0
        assert boost <= 0.1

    def test_skill_relevance_boost_no_match(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"test\"")
        analyzer = ProjectAnalyzer(tmp_path)
        boost = analyzer.get_skill_relevance_boost(["kubernetes", "deploy"])
        assert boost == 0.0

    def test_skill_relevance_boost_tech_stack(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("django\n")
        analyzer = ProjectAnalyzer(tmp_path)
        boost = analyzer.get_skill_relevance_boost(["django", "orm"])
        assert boost > 0.0
