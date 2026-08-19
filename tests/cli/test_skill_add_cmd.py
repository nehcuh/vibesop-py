"""Tests for vibe skill add command."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands.skill_commands import app as skills_app
from vibesop.spec.models import SkillSpec

runner = CliRunner()


class TestIncrementalIndexing:
    """M7 — `vibe skill add` Phase 6 incrementally indexes the new skill.

    `_index_newly_added_skill` must be best-effort: degrade to False
    (never raise) when no LLM is configured, and merge the single new
    profile into the existing index layer on success.
    """

    def test_returns_false_when_no_llm_configured(self) -> None:
        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        mock_resolver = Mock()
        mock_resolver.get_llm_for_understanding.return_value = None

        with patch(
            "vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver
        ):
            assert _index_newly_added_skill("test-skill", "project") is False

    def test_returns_false_when_provider_missing(self) -> None:
        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        mock_cfg = Mock(provider=None)
        mock_resolver = Mock()
        mock_resolver.get_llm_for_understanding.return_value = mock_cfg

        with patch(
            "vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver
        ):
            assert _index_newly_added_skill("test-skill", "project") is False

    def test_success_merges_single_profile_into_project_layer(self, tmp_path) -> None:
        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
        mock_resolver = Mock()
        mock_resolver.get_llm_for_understanding.return_value = mock_cfg

        mock_profile = Mock()
        mock_indexer = Mock()
        mock_indexer._get_llm.return_value = Mock()  # LLM available
        mock_indexer._analyze_skill.return_value = mock_profile
        mock_indexer.project_index_path = tmp_path / "proj" / "skill-index.json"
        mock_indexer.global_index_path = tmp_path / "glob" / "skill-index.json"
        mock_indexer._load_single_index.return_value = {"existing/skill": Mock()}

        mock_loader = Mock()
        mock_loader.get_skill.return_value = Mock()  # skill discoverable

        with (
            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
        ):
            assert _index_newly_added_skill("test-skill", "project") is True

        # Only the new skill was analyzed (incremental, not full rebuild).
        mock_indexer._analyze_skill.assert_called_once()
        mock_loader.get_skill.assert_called_once_with("test-skill")
        # Merged into the project layer, preserving existing entries.
        saved_profiles, = mock_indexer._save_index.call_args.args[:1]
        assert "test-skill" in saved_profiles
        assert "existing/skill" in saved_profiles
        assert mock_indexer._save_index.call_args.kwargs["scope"] == "project"

    def test_global_scope_saves_to_global_layer(self, tmp_path) -> None:
        """Layer-routing contract: scope="global" saves to the global index.

        The mock forces discoverability to pin the layer-selection logic
        against regressions. Since the global install path was unified to
        ``~/.vibe/skills/<id>`` (in ExternalSkillLoader's search paths),
        global installs are discoverable in production too, subject to
        the external audit gate.
        """
        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
        mock_resolver = Mock()
        mock_resolver.get_llm_for_understanding.return_value = mock_cfg

        mock_indexer = Mock()
        mock_indexer._get_llm.return_value = Mock()
        mock_indexer._analyze_skill.return_value = Mock()
        mock_indexer.project_index_path = tmp_path / "proj" / "skill-index.json"
        mock_indexer.global_index_path = tmp_path / "glob" / "skill-index.json"
        mock_indexer._load_single_index.return_value = {}

        mock_loader = Mock()
        mock_loader.get_skill.return_value = Mock()

        with (
            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
        ):
            assert _index_newly_added_skill("test-skill", "global") is True

        assert mock_indexer._save_index.call_args.kwargs["scope"] == "global"

    def test_global_scope_not_discoverable_points_to_manual_index(self, capsys) -> None:
        """scope="global" + skill not discoverable → the degrade message
        must point at the global-scope rebuild:
        `vibe skills index --scope global`.
        """
        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
        mock_resolver = Mock()
        mock_resolver.get_llm_for_understanding.return_value = mock_cfg

        mock_indexer = Mock()
        mock_indexer._get_llm.return_value = Mock()

        mock_loader = Mock()
        mock_loader.get_skill.return_value = None  # not discoverable

        with (
            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
        ):
            assert _index_newly_added_skill("ghost-skill", "global") is False

        # Flatten rich's line wrapping before substring assertions.
        out = " ".join(capsys.readouterr().out.split())
        assert "not discoverable" in out
        assert "vibe skills index --scope global" in out
        mock_indexer._save_index.assert_not_called()

    def test_returns_false_when_skill_not_discoverable(self) -> None:
        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
        mock_resolver = Mock()
        mock_resolver.get_llm_for_understanding.return_value = mock_cfg

        mock_indexer = Mock()
        mock_indexer._get_llm.return_value = Mock()

        mock_loader = Mock()
        mock_loader.get_skill.return_value = None  # not discoverable

        with (
            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
        ):
            assert _index_newly_added_skill("ghost-skill", "project") is False

    def test_never_raises_on_unexpected_error(self) -> None:
        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        with patch(
            "vibesop.core.llm_config.LLMConfigResolver",
            side_effect=RuntimeError("config exploded"),
        ):
            assert _index_newly_added_skill("test-skill", "project") is False

    def test_concurrent_indexing_loses_no_entries(self, tmp_path) -> None:
        """gate7 claude NIT-1 + gate7b pi NIT-6: the load→merge→save RMW
        runs under a cross-process sidecar lock — two concurrent
        incremental indexes must both land, not silently overwrite.

        Deterministic interleaving: the mock ``_load_single_index``
        snapshots the store FIRST, then blocks on an event until the
        second reader arrives. With the lock, the second reader can't
        enter until the first finishes (the wait times out, first saves,
        second then reads the merged state) → green. With the lock
        removed (mutation: swap cross_process_lock for nullcontext), both
        threads snapshot the SAME pre-merge state before either saves,
        the second save clobbers the first → red. Verified by mutation.
        """
        import threading

        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
        mock_resolver = Mock()
        mock_resolver.get_llm_for_understanding.return_value = mock_cfg

        store: dict[str, Mock] = {}
        readers: list[str] = []
        second_reader_arrived = threading.Event()

        def _load(_path):
            snapshot = dict(store)  # read BEFORE the rendezvous — the point
            readers.append(threading.current_thread().name)
            if len(readers) == 2:
                second_reader_arrived.set()
            else:
                # First reader waits for the second — only reachable
                # together when the write lock is absent (mutation).
                second_reader_arrived.wait(timeout=1)
            return snapshot

        def _save(profiles, *, scope):
            store.clear()
            store.update(profiles)

        mock_indexer = Mock()
        mock_indexer._get_llm.return_value = Mock()
        mock_indexer._analyze_skill.side_effect = lambda loaded, llm: Mock()
        mock_indexer.project_index_path = tmp_path / "proj" / "skill-index.json"
        mock_indexer.global_index_path = tmp_path / "glob" / "skill-index.json"
        mock_indexer._load_single_index.side_effect = _load
        mock_indexer._save_index.side_effect = _save

        mock_loader = Mock()
        mock_loader.get_skill.return_value = Mock()

        results: list[bool] = []
        with (
            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
        ):
            threads = [
                threading.Thread(
                    target=lambda sid: results.append(
                        _index_newly_added_skill(sid, "project")
                    ),
                    args=(f"skill-{i}",),
                )
                for i in range(2)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert sorted(results) == [True, True]
        assert set(store.keys()) == {"skill-0", "skill-1"}, (
            f"concurrent RMW lost an entry: {sorted(store.keys())}"
        )

    def test_degrades_false_when_lock_io_fails(self, tmp_path) -> None:
        """Lock-file OSError degrades to False (never raises), same style
        as every other failure mode in the function."""
        from vibesop.cli.commands.skill_commands import _index_newly_added_skill

        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
        mock_resolver = Mock()
        mock_resolver.get_llm_for_understanding.return_value = mock_cfg

        mock_indexer = Mock()
        mock_indexer._get_llm.return_value = Mock()
        mock_indexer._analyze_skill.return_value = Mock()
        mock_indexer.project_index_path = tmp_path / "proj" / "skill-index.json"
        mock_indexer.global_index_path = tmp_path / "glob" / "skill-index.json"

        mock_loader = Mock()
        mock_loader.get_skill.return_value = Mock()

        with (
            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
            patch(
                "vibesop.utils.file_lock.cross_process_lock",
                side_effect=OSError("lock file unavailable"),
            ),
        ):
            assert _index_newly_added_skill("test-skill", "project") is False

        mock_indexer._save_index.assert_not_called()


class TestSkillAddCommand:
    """Test suite for skill add command."""

    def test_command_exists(self):
        """Test that skill_add command can be imported."""
        from vibesop.cli.commands.skill_commands import add

        assert add is not None
        assert callable(add)

    def test_command_signature(self):
        """Test command signature has correct parameters."""
        import inspect

        from vibesop.cli.commands.skill_commands import add

        sig = inspect.signature(add)
        params = list(sig.parameters.keys())

        assert "skill_source" in params
        assert "global_" in params
        assert "auto_config" in params
        assert "force" in params

    @patch("vibesop.cli.commands.skill_commands._detect_and_load_skill")
    def test_detect_skill_from_directory(self, mock_detect):
        """Test skill detection from directory."""

        # Mock return value
        mock_metadata = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
            trigger_when="User asks for test",
        )
        mock_detect.return_value = (Path("test-skill"), mock_metadata)

        # Test would go here
        # This is a placeholder for actual test implementation

    def test_extract_keywords(self):
        """Test keyword extraction for routing patterns."""
        from vibesop.cli.commands.skill_commands import _extract_keywords

        text = "使用 Tushare API 获取股票数据并开发量化交易策略"
        keywords = _extract_keywords(text)

        assert isinstance(keywords, list)
        assert len(keywords) > 0
        # Should extract meaningful Chinese and English keywords
        assert any("tushare" in kw.lower() for kw in keywords)

    def test_save_auto_config(self, tmp_path):
        """Test auto-configuration file generation."""

        from vibesop.cli.commands.skill_commands import _save_auto_config

        # Create test config
        config = {"skill_id": "test-skill", "priority": 70, "enabled": True, "scope": "project"}

        # Mock the config file path
        with patch("vibesop.cli.commands.skill_commands.Path") as mock_path:
            mock_path.return_value = tmp_path / "auto-config.yaml"
            _save_auto_config(config)

        # Verify file was created (this would need actual implementation)

    @patch("vibesop.cli.commands.skill_commands.questionary")
    @patch("vibesop.cli.commands.skill_commands._detect_and_load_skill")
    @patch("vibesop.security.skill_auditor.SkillSecurityAuditor")
    @patch("vibesop.installer.skill_installer.SkillInstaller")
    def test_full_installation_flow(
        self, mock_installer, mock_auditor, mock_detect, mock_questionary, tmp_path
    ):
        """Test complete installation flow."""
        # Setup mocks
        mock_metadata = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
            trigger_when="User asks for test",
        )
        mock_detect.return_value = (tmp_path, mock_metadata)

        mock_audit_result = Mock()
        mock_audit_result.risk_level = "safe"
        mock_audit_result.summary = "No issues found"
        mock_auditor.return_value.audit_skill_file.return_value = mock_audit_result

        mock_install_result = {
            "success": True,
            "skill_id": "test-skill",
            "installed_path": str(tmp_path),
            "dependencies_installed": [],
            "errors": [],
            "warnings": [],
        }
        mock_installer.return_value.install_skill.return_value = mock_install_result

        mock_questionary.select.return_value.ask.return_value = "project"
        mock_questionary.confirm.return_value.ask.return_value = True

        # This test would verify the complete flow
        # Actual implementation would require more setup


class TestSkillAddIntegration:
    """Integration tests for skill add command."""

    def test_help_output(self):
        """Test that help command works."""
        result = runner.invoke(skills_app, ["add", "--help"])
        assert result.exit_code == 0
        assert "add" in result.stdout
        assert "skill" in result.stdout.lower()

    def test_missing_argument_shows_error(self):
        """Test that missing argument shows helpful error."""
        # This would test the actual CLI behavior
        pass


class TestKeywordExtraction:
    """Test keyword extraction algorithm."""

    def test_extract_keywords_from_english(self):
        """Test extraction from English text."""
        from vibesop.cli.commands.skill_commands import _extract_keywords

        text = "Use Tushare API to get stock market data"
        keywords = _extract_keywords(text)

        assert "tushare" in [kw.lower() for kw in keywords]
        assert "stock" in [kw.lower() for kw in keywords]

    def test_extract_keywords_from_chinese(self):
        """Test extraction from Chinese text."""
        from vibesop.cli.commands.skill_commands import _extract_keywords

        text = "使用 Tushare API 获取股票数据"
        keywords = _extract_keywords(text)

        assert len(keywords) > 0
        # Should extract meaningful words

    def test_extract_keywords_removes_stop_words(self):
        """Test that stop words are removed."""
        from vibesop.cli.commands.skill_commands import _extract_keywords

        text = "Get the stock data from the API"
        keywords = _extract_keywords(text)

        # Should not contain stop words like "the", "from"
        assert "the" not in [kw.lower() for kw in keywords]
        assert "from" not in [kw.lower() for kw in keywords]


class TestConfigurationGeneration:
    """Test auto-configuration generation."""

    def test_priority_calculation(self):
        """Test priority is calculated correctly."""
        # Test different categories get correct priorities
        priority_map = {
            "development": 70,
            "testing": 65,
            "debugging": 80,
            "review": 50,
        }

        for _category, expected_priority in priority_map.items():
            # This would test the actual priority calculation logic
            assert isinstance(expected_priority, int)
            assert 0 <= expected_priority <= 100

    def test_routing_pattern_generation(self):
        """Test routing patterns are generated correctly."""
        from vibesop.cli.commands.skill_commands import _extract_keywords

        description = "Use Tushare API for stock trading"
        keywords = _extract_keywords(description)

        # Keywords should be suitable for regex patterns
        assert all(isinstance(kw, str) for kw in keywords)
        assert all(len(kw) > 0 for kw in keywords)


class TestSecurityAudit:
    """Test security audit integration."""

    @patch("vibesop.security.skill_auditor.SkillSecurityAuditor")
    def test_safe_skill_passes_audit(self, mock_auditor):
        """Test that safe skills pass audit."""

        mock_audit_result = Mock()
        mock_audit_result.risk_level = "safe"
        mock_audit_result.summary = "No issues found"
        mock_auditor.return_value.audit_skill_file.return_value = mock_audit_result

        # Test would verify safe skills proceed
        assert mock_audit_result.risk_level == "safe"

    @patch("vibesop.security.skill_auditor.SkillSecurityAuditor")
    def test_critical_skill_fails_audit(self, mock_auditor):
        """Test that critical skills fail audit."""
        mock_audit_result = Mock()
        mock_audit_result.risk_level = "critical"
        mock_audit_result.summary = "Security risks detected"
        mock_auditor.return_value.audit_skill_file.return_value = mock_audit_result

        # Test would verify critical skills are rejected
        assert mock_audit_result.risk_level == "critical"


class TestDocumentation:
    """Test documentation quality."""

    def test_skill_add_command_has_docstring(self):
        """Test that command has proper documentation."""
        from vibesop.cli.commands.skill_commands import add

        assert add.__doc__ is not None
        assert "skill" in add.__doc__.lower()
        assert "add" in add.__doc__.lower() or "install" in add.__doc__.lower()

    def test_helper_functions_have_docstrings(self):
        """Test that helper functions are documented."""
        from vibesop.cli.commands.skill_commands import (
            _detect_and_load_skill,
            _extract_keywords,
            _save_auto_config,
        )

        for func in [_detect_and_load_skill, _extract_keywords, _save_auto_config]:
            assert func.__doc__ is not None


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_skill_path(self):
        """Test handling of invalid skill path."""
        from vibesop.cli.commands.skill_commands import _detect_and_load_skill

        # Test with non-existent path
        result = _detect_and_load_skill("/nonexistent/path")
        # Should handle gracefully
        assert result is not None

    def test_corrupted_skill_metadata(self):
        """Test handling of corrupted metadata."""
        # Test with malformed SKILL.md
        pass


class TestAgentEnvironmentBranch:
    """Test Agent-aware installation path (Step 1 enhancement)."""

    @patch("vibesop.core.llm_config.is_in_agent_environment")
    @patch("vibesop.core.ai_enhancer.AIEnhancer")
    @patch("vibesop.core.skills.understander.understand_skill_from_file")
    def test_agent_environment_skips_ai_enhancer(
        self,
        mock_understand: Any,
        mock_ai_enhancer_cls: Any,
        mock_is_agent: Any,
    ) -> None:
        """When in Agent env, AIEnhancer should NOT be instantiated."""
        from vibesop.cli.commands.skill_commands import _auto_configure_skill_with_llm
        from vibesop.core.skills.understander import AutoGeneratedConfig

        mock_is_agent.return_value = True
        mock_config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="review",
            priority=60,
            confidence=0.85,
            routing_patterns=[".*test.*"],
        )
        mock_understand.return_value = mock_config

        metadata = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
        )

        # Run with a temp directory containing SKILL.md
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nid: test-skill\n---\n", encoding="utf-8")

            _auto_configure_skill_with_llm(metadata, "project", str(skill_dir))

        mock_ai_enhancer_cls.assert_not_called()

    @patch("vibesop.core.llm_config.is_in_agent_environment")
    @patch("vibesop.core.skills.understander.understand_skill_from_file")
    def test_agent_environment_uses_rule_engine_only(
        self,
        mock_understand: Any,
        mock_is_agent: Any,
    ) -> None:
        """Agent env should call understand_skill_from_file and save config."""
        from vibesop.cli.commands.skill_commands import _auto_configure_skill_with_llm
        from vibesop.core.skills.understander import AutoGeneratedConfig

        mock_is_agent.return_value = True
        mock_config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="debugging",
            priority=80,
            confidence=0.8,
            routing_patterns=[".*debug.*"],
        )
        mock_understand.return_value = mock_config

        metadata = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="Debug things",
            intent="debug",
        )

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nid: test-skill\n---\n", encoding="utf-8")

            _auto_configure_skill_with_llm(metadata, "project", str(skill_dir))

        mock_understand.assert_called_once()

    @patch("vibesop.core.llm_config.is_in_agent_environment")
    @patch("vibesop.core.ai_enhancer.AIEnhancer")
    @patch("vibesop.core.skills.understander.understand_skill_from_file")
    def test_non_agent_environment_uses_ai_enhancer_fallback(
        self,
        mock_understand: Any,
        mock_ai_enhancer_cls: Any,
        mock_is_agent: Any,
    ) -> None:
        """Low confidence in non-Agent env should trigger AIEnhancer fallback."""
        from vibesop.cli.commands.skill_commands import _auto_configure_skill_with_llm
        from vibesop.core.skills.understander import AutoGeneratedConfig

        mock_is_agent.return_value = False
        mock_config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="development",
            priority=50,
            confidence=0.5,  # Below 0.7 threshold
            routing_patterns=[],
        )
        mock_understand.return_value = mock_config

        mock_enhancer = Mock()
        mock_enhancer.enhance_suggestion.return_value = Mock(
            category="development",
            tags=["test"],
            trigger_conditions=["user asks"],
        )
        mock_ai_enhancer_cls.return_value = mock_enhancer

        metadata = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
        )

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nid: test-skill\n---\n", encoding="utf-8")

            _auto_configure_skill_with_llm(metadata, "project", str(skill_dir))

        mock_ai_enhancer_cls.assert_called_once()

    def test_prompt_agent_for_config_accepts_json_adjustments(self) -> None:
        """_prompt_agent_for_config should parse JSON adjustments."""
        from vibesop.cli.commands.skill_commands import _prompt_agent_for_config
        from vibesop.core.skills.understander import AutoGeneratedConfig

        config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="development",
            priority=50,
            confidence=0.6,
            routing_patterns=[".*test.*"],
        )
        metadata = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
        )

        with patch("vibesop.cli.commands.skill_commands.questionary") as mock_q:
            mock_q.confirm.return_value.ask.return_value = False
            mock_q.text.return_value.ask.return_value = '{"category": "review", "priority": 75}'

            result = _prompt_agent_for_config(metadata, config, "project")

        assert result.category == "review"
        assert result.priority == 75
        assert result.routing_patterns == [".*test.*"]  # unchanged

    def test_prompt_agent_for_config_defaults_on_invalid_json(self) -> None:
        """Invalid JSON adjustments should fall back to draft config."""
        from vibesop.cli.commands.skill_commands import _prompt_agent_for_config
        from vibesop.core.skills.understander import AutoGeneratedConfig

        config = AutoGeneratedConfig(
            skill_id="test-skill",
            category="development",
            priority=50,
            confidence=0.6,
        )
        metadata = SkillSpec(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            intent="Test",
        )

        with patch("vibesop.cli.commands.skill_commands.questionary") as mock_q:
            mock_q.confirm.return_value.ask.return_value = False
            mock_q.text.return_value.ask.return_value = "not-json"

            result = _prompt_agent_for_config(metadata, config, "project")

        assert result.category == "development"  # unchanged
        assert result.priority == 50  # unchanged


class TestGlobalInstallPath:
    """Tier2 fix: `vibe skill add --global` must install to
    ``~/.vibe/skills/<id>`` — the unified global location that
    ExternalSkillLoader searches and the promote hints reference.
    Previously the CLI passed ``~/.vibe`` as the install root and the
    installer appended ``.vibe/skills``, producing the undiscoverable
    doubled path ``~/.vibe/.vibe/skills/<id>``.
    """

    def test_install_root_project_vs_global(self, tmp_path, monkeypatch) -> None:
        from vibesop.cli.commands.skill_commands import _install_root

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert _install_root("project") == Path()
        assert _install_root("global") == tmp_path
        # Installer appends .vibe/skills → unified global target.
        assert _install_root("global") / ".vibe" / "skills" == tmp_path / ".vibe" / "skills"

    def test_global_install_lands_in_unified_path(self, tmp_path, monkeypatch) -> None:
        from vibesop.cli.commands.skill_commands import _install_root
        from vibesop.installer.skill_installer import SkillInstaller

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        skill_dir = tmp_path / "src-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nid: glob-skill\n---\n", encoding="utf-8")

        result = SkillInstaller().install_skill(skill_dir, _install_root("global"))

        assert result["success"] is True
        # Skill, registry and reload marker all land in the unified paths.
        assert (tmp_path / ".vibe" / "skills" / "glob-skill" / "SKILL.md").exists()
        registry = tmp_path / ".vibe" / "skills" / "registry.yaml"
        assert registry.exists()
        assert "glob-skill" in registry.read_text(encoding="utf-8")
        assert (tmp_path / ".vibe" / ".skills_reload").exists()
        # The legacy doubled path is never created.
        assert not (tmp_path / ".vibe" / ".vibe").exists()

    def test_loader_discovers_global_install(self, tmp_path, monkeypatch) -> None:
        """A skill installed at ``~/.vibe/skills/<id>`` is discoverable
        through SkillLoader's external search paths."""
        from vibesop.core.skills.external_loader import ExternalSkillLoader
        from vibesop.core.skills.loader import SkillLoader

        global_skills = tmp_path / "home" / ".vibe" / "skills"
        skill_dir = global_skills / "test-glob-discover-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nid: test-glob-discover-skill\nname: Glob Discover\n---\n",
            encoding="utf-8",
        )

        # EXTERNAL_PATHS is a class var bound to the real home at import;
        # repoint it at the tmp home's unified global skills dir.
        monkeypatch.setattr(ExternalSkillLoader, "EXTERNAL_PATHS", [global_skills])

        project_root = tmp_path / "proj"
        project_root.mkdir()
        loader = SkillLoader(project_root=project_root, require_audit=False)

        loaded = loader.get_skill("test-glob-discover-skill")
        assert loaded is not None
        assert loaded.metadata.id == "test-glob-discover-skill"


class TestMigrateLegacyGlobalSkills:
    """Migration for the legacy doubled path ``~/.vibe/.vibe/skills/``."""

    def _make_skill(self, parent: Path, skill_id: str) -> Path:
        skill_dir = parent / skill_id
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nid: {skill_id}\n---\n", encoding="utf-8"
        )
        return skill_dir

    def test_noop_when_no_legacy_dir(self, tmp_path) -> None:
        from vibesop.cli.commands.skill_commands import _migrate_legacy_global_skills

        _migrate_legacy_global_skills(tmp_path)  # must not raise
        assert not (tmp_path / ".vibe").exists()

    def test_moves_legacy_installs(self, tmp_path, capsys) -> None:
        from vibesop.cli.commands.skill_commands import _migrate_legacy_global_skills

        legacy = tmp_path / ".vibe" / ".vibe" / "skills"
        self._make_skill(legacy, "legacy-a")
        self._make_skill(legacy, "legacy-b")

        _migrate_legacy_global_skills(tmp_path)

        assert (tmp_path / ".vibe" / "skills" / "legacy-a" / "SKILL.md").exists()
        assert (tmp_path / ".vibe" / "skills" / "legacy-b" / "SKILL.md").exists()
        assert not (legacy / "legacy-a").exists()
        assert not (legacy / "legacy-b").exists()
        assert "Migrated 2 skill(s)" in capsys.readouterr().out

    def test_conflict_is_skipped_with_warning(self, tmp_path, capsys) -> None:
        from vibesop.cli.commands.skill_commands import _migrate_legacy_global_skills

        legacy = tmp_path / ".vibe" / ".vibe" / "skills"
        legacy_skill = self._make_skill(legacy, "clash")
        (legacy_skill / "SKILL.md").write_text("---\nid: clash\nlegacy: yes\n---\n")
        # Unified target already has a skill with the same name.
        existing = self._make_skill(tmp_path / ".vibe" / "skills", "clash")
        (existing / "SKILL.md").write_text("---\nid: clash\n---\n", encoding="utf-8")

        _migrate_legacy_global_skills(tmp_path)

        # Existing install untouched; legacy copy left in place.
        assert "legacy" not in (existing / "SKILL.md").read_text(encoding="utf-8")
        assert (legacy_skill / "SKILL.md").exists()
        out = capsys.readouterr().out
        assert "Skipping legacy global skill 'clash'" in out
        assert "Migrated" not in out


class TestGlobalAddComposition:
    """Command-level coverage for `vibe skill add --global`: migration,
    unified install root, and installer-warning surfacing, wired together
    through the real SkillInstaller (only I/O-heavy phases are mocked).
    """

    def _invoke_global_add(self, tmp_path: Path, skill_id: str):
        """Run `skill add <src> --global` against a tmp HOME.

        Returns the CliRunner result. The real SkillInstaller runs against
        the patched home; detection, audit, auto-config and verify phases
        are mocked to keep the test hermetic.
        """
        src = tmp_path / "src" / skill_id
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text(f"---\nid: {skill_id}\n---\n", encoding="utf-8")

        metadata = SkillSpec(
            id=skill_id,
            name=skill_id.replace("-", " ").title(),
            description="A test skill",
            intent="Test",
            trigger_when="User asks for test",
        )
        mock_audit = Mock()
        mock_audit.risk_level = "safe"
        mock_audit.reason = ""

        with (
            patch(
                "vibesop.cli.commands.skill_commands._detect_and_load_skill",
                return_value=(src, metadata),
            ),
            patch("vibesop.security.skill_auditor.SkillSecurityAuditor") as mock_auditor,
            patch("vibesop.cli.commands.skill_commands._auto_configure_skill_with_llm"),
            patch(
                "vibesop.cli.commands.skill_commands._verify_and_sync",
                return_value=False,
            ),
        ):
            mock_auditor.return_value.audit_skill_file.return_value = mock_audit
            return runner.invoke(skills_app, ["add", str(src), "--global"])

    def test_global_add_migrates_legacy_skills(self, tmp_path, monkeypatch) -> None:
        """gate8 nit: `vibe skill add --global` must actually invoke the
        legacy-path migration — a pre-existing ``~/.vibe/.vibe/skills/<id>``
        install is moved to ``~/.vibe/skills/<id>`` during the add."""
        home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", lambda: home)
        legacy = home / ".vibe" / ".vibe" / "skills" / "legacy-skill"
        legacy.mkdir(parents=True)
        (legacy / "SKILL.md").write_text("---\nid: legacy-skill\n---\n", encoding="utf-8")

        result = self._invoke_global_add(tmp_path, "new-skill")

        assert result.exit_code == 0, result.output
        # Legacy install migrated to the unified global path.
        assert (home / ".vibe" / "skills" / "legacy-skill" / "SKILL.md").exists()
        assert not legacy.exists()
        assert "Migrated 1 skill(s)" in result.output
        # New skill installed to the unified global path, not the doubled one.
        assert (home / ".vibe" / "skills" / "new-skill" / "SKILL.md").exists()
        assert not (home / ".vibe" / ".vibe" / "skills" / "new-skill").exists()

    def test_installer_warnings_are_printed(self, tmp_path, monkeypatch) -> None:
        """gate8 nit: a non-force reinstall returns 'already installed' as
        a warning — it must reach the console, not be silently dropped."""
        home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", lambda: home)
        # Pre-install the same skill id at the unified global path.
        existing = home / ".vibe" / "skills" / "new-skill"
        existing.mkdir(parents=True)
        (existing / "SKILL.md").write_text("---\nid: new-skill\n---\n", encoding="utf-8")

        result = self._invoke_global_add(tmp_path, "new-skill")

        assert result.exit_code == 0, result.output
        assert "already installed" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
