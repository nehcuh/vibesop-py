"""Tests for OptimizationConfig models."""

import pytest

from vibesop.core.config import (
    ClusteringConfig,
    OptimizationConfig,
    PreferenceBoostConfig,
    PrefilterConfig,
)
from vibesop.core.config.manager import ConfigManager


class TestPrefilterConfig:
    def test_defaults(self):
        config = PrefilterConfig()
        assert config.enabled is True
        assert config.min_candidates == 5
        assert config.max_candidates == 15
        assert config.always_include_p0 is True
        assert config.namespace_relevance_threshold == 0.3

    def test_custom_values(self):
        config = PrefilterConfig(
            enabled=False,
            min_candidates=10,
            max_candidates=30,
            always_include_p0=False,
            namespace_relevance_threshold=0.5,
        )
        assert config.enabled is False
        assert config.min_candidates == 10
        assert config.max_candidates == 30
        assert config.always_include_p0 is False
        assert config.namespace_relevance_threshold == 0.5


class TestPreferenceBoostConfig:
    def test_defaults(self):
        config = PreferenceBoostConfig()
        assert config.enabled is True
        assert config.weight == 0.3
        assert config.min_samples == 2
        assert config.decay_days == 30

    def test_custom_values(self):
        config = PreferenceBoostConfig(
            enabled=False,
            weight=0.5,
            min_samples=5,
            decay_days=14,
        )
        assert config.enabled is False
        assert config.weight == 0.5
        assert config.min_samples == 5
        assert config.decay_days == 14


class TestClusteringConfig:
    def test_defaults(self):
        config = ClusteringConfig()
        assert config.enabled is True
        assert config.auto_resolve is True
        assert config.confidence_gap_threshold == 0.1
        assert config.min_skills_for_clustering == 10
        assert config.max_clusters == 12

    def test_custom_values(self):
        config = ClusteringConfig(
            enabled=False,
            auto_resolve=False,
            confidence_gap_threshold=0.2,
            min_skills_for_clustering=5,
            max_clusters=8,
        )
        assert config.enabled is False
        assert config.auto_resolve is False
        assert config.confidence_gap_threshold == 0.2
        assert config.min_skills_for_clustering == 5
        assert config.max_clusters == 8


class TestOptimizationConfig:
    def test_optimization_config_defaults(self):
        config = OptimizationConfig()
        assert config.enabled is True
        assert isinstance(config.prefilter, PrefilterConfig)
        assert isinstance(config.preference_boost, PreferenceBoostConfig)
        assert isinstance(config.clustering, ClusteringConfig)
        assert config.prefilter.enabled is True
        assert config.preference_boost.enabled is True
        assert config.clustering.enabled is True

    def test_optimization_config_disabled(self):
        config = OptimizationConfig().disable_all()
        assert config.enabled is False
        assert config.prefilter.enabled is False
        assert config.preference_boost.enabled is False
        assert config.clustering.enabled is False

    def test_optimization_config_custom_values(self):
        config = OptimizationConfig(
            enabled=True,
            prefilter=PrefilterConfig(enabled=False, min_candidates=10),
            preference_boost=PreferenceBoostConfig(weight=0.5),
            clustering=ClusteringConfig(max_clusters=5),
        )
        assert config.enabled is True
        assert config.prefilter.enabled is False
        assert config.prefilter.min_candidates == 10
        assert config.preference_boost.weight == 0.5
        assert config.clustering.max_clusters == 5


class TestConfigManagerOptimization:
    def test_get_optimization_config_defaults(self):
        manager = ConfigManager(project_root=".")
        config = manager.get_optimization_config()
        assert isinstance(config, OptimizationConfig)
        assert config.enabled is True
        assert config.prefilter.min_candidates == 5
        assert config.prefilter.max_candidates == 15
        assert config.preference_boost.weight == 0.3
        assert config.preference_boost.decay_days == 30
        assert config.clustering.confidence_gap_threshold == 0.1
        assert config.clustering.max_clusters == 12

    def test_get_optimization_config_with_cli_override(self):
        manager = ConfigManager(project_root=".")
        manager.set_cli_override("optimization.enabled", False)
        config = manager.get_optimization_config()
        assert config.enabled is False
