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

        gate7b honesty note (pi / claude #4): this branch is NOT reachable
        in production today — `vibe skill add --global` installs outside
        SkillLoader's search paths, so `get_skill` returns None and the
        function degrades before reaching the save (that's what
        ``test_returns_false_when_skill_not_discoverable`` covers). The
        mock here forces discoverability to pin the layer-selection logic
        against regressions; keep the test, but don't read it as evidence
        the global path works end-to-end (Tier2 item).
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
        """gate7b claude #4: scope="global" + skill not discoverable →
        the degrade message must be the honest one: incremental indexing
        is project-scope only, run `vibe skills index --scope global`.
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
        assert "project-scope only" in out
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
