"""Tests for repository analyzer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibesop.installer.analyzer import RepoAnalysis, RepoAnalyzer


@pytest.fixture
def fake_repo(tmp_path):
    """Create a fake repository structure."""
    repo = tmp_path / "fake-repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Test Pack\n\n## Installation\n\nRun setup.")
    skills = repo / "skills" / "debug"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("---\nid: debug\nname: Debug\n---\n")
    (repo / "requirements.txt").write_text("requests")
    return repo


def test_repo_analysis_skill_count():
    analysis = RepoAnalysis(
        pack_name="test",
        source_url="https://example.com",
        skill_files=[Path("a/SKILL.md"), Path("b/SKILL.md")],
    )
    assert analysis.skill_count == 2
    assert analysis.has_readme is False


def test_repo_analysis_skill_ids_with_mock():
    analysis = RepoAnalysis(
        pack_name="test",
        source_url="https://example.com",
        skill_files=[Path("debug/SKILL.md")],
    )
    with patch("vibesop.installer.analyzer.parse_skill_md", return_value=MagicMock(id="mock-debug")):
        assert analysis.skill_ids() == ["mock-debug"]


def test_repo_analysis_skill_ids_fallback():
    analysis = RepoAnalysis(
        pack_name="test",
        source_url="https://example.com",
        skill_files=[Path("debug/SKILL.md")],
    )
    with patch("vibesop.installer.analyzer.parse_skill_md", return_value=None):
        assert analysis.skill_ids() == ["debug"]


def test_infer_pack_name():
    analyzer = RepoAnalyzer()
    assert analyzer.infer_pack_name("https://github.com/user/superpowers") == "superpowers"
    assert analyzer.infer_pack_name("https://github.com/user/superpowers.git") == "superpowers"
    assert analyzer.infer_pack_name("superpowers") == "superpowers"


def test_extract_install_hint_from_section(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Pack\n\n## Installation\n\nStep 1\nStep 2\n\n## Usage\n\nFoo")
    analyzer = RepoAnalyzer()
    hint = analyzer._extract_install_hint(readme)
    assert "Step 1" in hint
    assert "Usage" not in hint


def test_extract_install_hint_from_command(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Pack\n\nRun `pip install -r requirements.txt`")
    analyzer = RepoAnalyzer()
    hint = analyzer._extract_install_hint(readme)
    assert "pip install" in hint


def test_extract_install_hint_no_instructions(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Pack\n\nHello")
    analyzer = RepoAnalyzer()
    hint = analyzer._extract_install_hint(readme)
    assert "No explicit installation" in hint


def test_analyze_repo(fake_repo):
    analyzer = RepoAnalyzer()
    with (
        patch("tempfile.TemporaryDirectory") as mock_tmp,
        patch.object(analyzer, "git_clone", return_value=True),
        patch("vibesop.installer.analyzer.parse_skill_md", return_value=MagicMock(namespace="testpack")),
    ):
        mock_tmp.return_value.__enter__ = MagicMock(return_value=str(fake_repo))
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        result = analyzer.analyze("https://github.com/user/testpack")

    assert result.pack_name == "testpack"
    assert result.skill_count == 1
    assert "requirements.txt" in result.setup_scripts
    assert result.has_readme is True
    assert result.detected_namespace == "testpack"


def test_analyze_repo_clone_failure():
    analyzer = RepoAnalyzer()
    with patch.object(analyzer, "git_clone", return_value=False):
        result = analyzer.analyze("https://github.com/user/nonexistent")
    assert result.errors
    assert "Failed to clone" in result.errors[0]
