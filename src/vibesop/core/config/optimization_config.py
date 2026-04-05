"""Optimization configuration for skill routing.

Controls three optimization layers:
- Prefilter: Reduces candidate set before routing
- PreferenceBoost: Adjusts scores based on user preferences
- Clustering: Groups similar skills for better selection
"""

from pydantic import BaseModel, Field


class PrefilterConfig(BaseModel):
    """Configuration for pre-filtering candidates before routing.

    Attributes:
        enabled: Enable pre-filtering
        min_candidates: Minimum number of candidates to keep
        max_candidates: Maximum number of candidates to keep
        always_include_p0: Always include P0 (critical) skills
        namespace_relevance_threshold: Minimum relevance score for namespace matching
    """

    enabled: bool = True
    min_candidates: int = Field(default=5, ge=1, le=50)
    max_candidates: int = Field(default=15, ge=1, le=50)
    always_include_p0: bool = True
    namespace_relevance_threshold: float = Field(default=0.3, ge=0.0, le=1.0)


class PreferenceBoostConfig(BaseModel):
    """Configuration for preference-based score boosting.

    Attributes:
        enabled: Enable preference boosting
        weight: Weight of preference score in final ranking
        min_samples: Minimum samples needed before boosting activates
        decay_days: Days after which preference weight decays
    """

    enabled: bool = True
    weight: float = Field(default=0.3, ge=0.0, le=1.0)
    min_samples: int = Field(default=2, ge=1)
    decay_days: int = Field(default=30, ge=1)


class ClusteringConfig(BaseModel):
    """Configuration for semantic clustering of skills.

    Attributes:
        enabled: Enable clustering
        auto_resolve: Automatically resolve cluster conflicts
        confidence_gap_threshold: Minimum confidence gap to skip clustering
        min_skills_for_clustering: Minimum skills needed before clustering activates
        max_clusters: Maximum number of clusters to create
    """

    enabled: bool = True
    auto_resolve: bool = True
    confidence_gap_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    min_skills_for_clustering: int = Field(default=10, ge=3)
    max_clusters: int = Field(default=12, ge=2)


class OptimizationConfig(BaseModel):
    """Top-level optimization configuration.

    Controls all three optimization layers for skill routing.

    Attributes:
        enabled: Master switch for all optimizations
        prefilter: Pre-filtering configuration
        preference_boost: Preference boosting configuration
        clustering: Semantic clustering configuration
    """

    enabled: bool = True
    prefilter: PrefilterConfig = Field(default_factory=PrefilterConfig)
    preference_boost: PreferenceBoostConfig = Field(default_factory=PreferenceBoostConfig)
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)

    def disable_all(self) -> "OptimizationConfig":
        """Create a new config with all optimizations disabled.

        Returns:
            New OptimizationConfig with all features disabled
        """
        return OptimizationConfig(
            enabled=False,
            prefilter=PrefilterConfig(enabled=False),
            preference_boost=PreferenceBoostConfig(enabled=False),
            clustering=ClusteringConfig(enabled=False),
        )
