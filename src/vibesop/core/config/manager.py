"""Unified configuration manager for VibeSOP.

This module consolidates configuration from multiple sources:
- Built-in defaults
- Global config (~/.vibe/config.toml or ~/.vibe/config.yaml)
- Project config (.vibe/config.toml or .vibe/config.yaml)
- Environment variables
- CLI arguments
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import Field

from vibesop.core.config._base import TolerantConfig

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from vibesop.core.config.optimization_config import OptimizationConfig


class ConfigSourcePriority(StrEnum):
    """Configuration source priority levels (low to high)."""

    DEFAULTS = "defaults"  # 1. Built-in defaults
    GLOBAL = "global"  # 2. Global config (~/.vibe/config.toml)
    PROJECT = "project"  # 3. Project config (.vibe/config.toml)
    PREFERENCES = "preferences"  # 4. Legacy preferences (.vibe/preferences.json)
    ENV = "env"  # 5. Environment variables
    CLI = "cli"  # 6. Command-line arguments


@dataclass
class ConfigSource:
    """A configuration source."""

    priority: ConfigSourcePriority
    data: dict[str, Any]
    path: Path | None = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from this source (supports dot notation)."""
        # Support dot notation
        keys = key.split(".")
        value = self.data

        _MISSING = object()

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, _MISSING)
                if value is _MISSING:
                    return default
            else:
                return default

        return default if value is _MISSING else value

    def has(self, key: str) -> bool:
        """Check if this source has a key."""
        keys = key.split(".")
        value = self.data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return False

        return True

    def reload(self) -> None:
        if self.path and self.path.exists():
            self.load_from_file()

    def load_from_file(self) -> None:
        if self.path is None:
            self.data = {}
            return
        try:
            suffix = self.path.suffix.lower()
            if suffix == ".toml":
                from vibesop.utils.encoding import load_toml_with_fallback

                self.data = load_toml_with_fallback(self.path)
            else:
                import yaml

                from vibesop.utils.encoding import read_text_with_fallback

                self.data = yaml.safe_load(read_text_with_fallback(self.path)) or {}
        except FileNotFoundError:
            # Config file absent — normal (callers gate on _resolve_config_path,
            # so this only fires on a TOCTOU race between resolve and open).
            # Stay quiet; this is not a parse error worth an ERROR log.
            logger.debug("Config file not found: %s", self.path)
            self.data = {}
        except Exception as e:
            # A malformed config silently falls back to defaults with zero
            # signal at the default log level (WARNING). Log loudly so
            # operators see their config was rejected — mirrors load_registry().
            logger.error(
                "Failed to parse config %s: %s — falling back to defaults. "
                "Check the file for syntax errors.",
                self.path,
                e,
            )
            self.data = {}

    @staticmethod
    def _resolve_config_path(base_dir: Path, name: str) -> Path | None:
        """Resolve config file path, preferring .toml over .yaml."""
        toml_path = base_dir / f"{name}.toml"
        if toml_path.exists():
            return toml_path
        yaml_path = base_dir / f"{name}.yaml"
        if yaml_path.exists():
            return yaml_path
        return None


class RoutingConfig(TolerantConfig):
    """Configuration for routing behavior."""

    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    auto_select_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    confirmation_mode: str = Field(
        default="ambiguous_only",
        description=(
            "User confirmation mode: ambiguous_only (default — confirm only when "
            "primary confidence < auto_select_threshold, per PHILOSOPHY.md "
            "'延续 > 启动'), always, or never"
        ),
    )
    enable_orchestration: bool = Field(
        default=True,
        description="Enable multi-skill orchestration for multi-intent queries",
    )
    enable_ai_triage: bool = True
    enable_embedding: bool = Field(
        default=False,
        description=(
            "Enable embedding-based matching in the Stage-4 matcher aggregation. "
            "Opt-in enhancement — disabled by default: it requires the optional "
            "sentence-transformers dependency (~20ms/route), and the keyword + "
            "TFIDF matchers already cover the same signal for most queries. "
            "Enable only if the model is installed and deeper semantic matching "
            "is needed."
        ),
    )
    max_candidates: int = Field(default=3, ge=1, le=10)
    use_cache: bool = True
    ai_triage_max_skills: int = Field(default=20, ge=5, le=50)
    ai_triage_max_tokens: int = Field(default=100, ge=50, le=500)
    ai_triage_prompt_version: str = Field(default="v1")
    ai_triage_budget_monthly: float = Field(default=5.0, ge=0.0)
    ai_triage_log_calls: bool = True
    ai_triage_circuit_breaker_enabled: bool = True
    ai_triage_circuit_breaker_failure_threshold: int = Field(default=3, ge=1, le=10)
    ai_triage_circuit_breaker_latency_threshold_ms: float = Field(default=500.0, ge=100.0)
    ai_triage_circuit_breaker_cooldown_seconds: int = Field(default=60, ge=10)
    ai_triage_timeout_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=120.0,
        description="Hard timeout for a single AI triage LLM call. Provider "
        "clients carry their own ~30s transport timeouts; this caps triage "
        "lower for interactive routing. A timed-out call falls back to the "
        "persistent last-good entry when available.",
    )
    triage_cache_ttl_hours: int = Field(
        default=72,
        ge=1,
        description="TTL for the persistent cross-process triage cache "
        "(.vibe/triage_cache.json). Expired entries are treated as misses "
        "but retained as last-good fallbacks when the LLM fails.",
    )
    ai_triage_short_query_bypass_chars: int = Field(
        default=15,
        ge=0,
        le=200,
        description="Skip AI Triage when query character length is below this threshold. "
        "Uses character count (not word count) to correctly handle CJK and "
        "other languages without whitespace word boundaries.",
    )
    keyword_match_max_chars: int = Field(
        default=15,
        ge=0,
        le=200,
        description="Skip keyword-based routing (scenario, keyword, TF-IDF, Levenshtein) "
        "when query character length exceeds this threshold. "
        "Short queries (<=N chars) use fast keyword matching; "
        "long queries rely on LLM semantic triage. "
        "Set to 0 to always use LLM, 200 to always use keyword matching.",
    )
    index_match_threshold: float = Field(
        default=0.20,
        ge=0.0,
        lt=1.0,
        description="Hit threshold for bigram token-overlap matching in the "
        "SEMANTIC_INDEX routing layer. Kept at 0.20: re-calibrated 2026-08-19 "
        "after the routing_eval_extended label audit "
        "(.omx/artifacts/tier3-eval-label-audit.md), but the cleaned set has "
        "only 8 confirmed positives — too thin to justify a change (raw "
        "accuracy argmax of 0.05 is dominated by wrong accepts: main-set "
        "precision of accepted hits is 0.455 at 0.05 vs 0.750 at 0.20; see "
        "scripts/calibrate_index_threshold.py). Must be < 1.0: the "
        "confidence scaling in _layers.py divides by (1.0 - threshold).",
    )
    index_external_match_threshold: float = Field(
        default=0.30,
        ge=0.0,
        lt=1.0,
        description="Token-overlap hit threshold in the SEMANTIC_INDEX layer "
        "for skills OUTSIDE the curated namespaces (builtin/project/custom/"
        "cross-cutting) — i.e. external packs. "
        "Pack profiles are LLM-generated across dozens of same-pack skills "
        "with heavily overlapping vocabulary, so a marginal bigram overlap "
        "with a pack profile is far weaker evidence than the same overlap "
        "with a curated builtin/project profile (M9: 27 of 40 residual eval "
        "misroutes were marginal index hits on locally-installed packs). "
        "Effective threshold is max(index_match_threshold, this value), so "
        "lowering index_match_threshold never lowers the external bar below "
        "it. Values below index_match_threshold are therefore inert.",
    )
    index_embedding_threshold: float = Field(
        default=0.45,
        ge=0.0,
        lt=1.0,
        description="Absolute cosine-similarity floor for the SEMANTIC_INDEX "
        "embedding fallback (paraphrase-multilingual-MiniLM-L12-v2). 0.45 "
        "sits just above the model's ~0.1-0.3 noise floor for unrelated "
        "pairs (see ai_triage_recall_min_similarity), and was the only "
        "acceptance criterion pre-M9 — necessary but not sufficient once the "
        "catalog is large, which is what index_embedding_min_margin adds. "
        "Must be < 1.0: the confidence scaling divides by (1.0 - threshold).",
    )
    index_embedding_min_margin: float = Field(
        default=0.05,
        ge=0.0,
        le=0.5,
        description="Minimum cosine-similarity gap between the top-1 and "
        "top-2 profile for the SEMANTIC_INDEX embedding fallback to accept a "
        "match. The fallback is an argmax over the whole profile catalog; "
        "with ~100 LLM-generated profiles installed, the nearest profile of "
        "an UNRELATED query lands in the model's 0.45-0.55 noise band, so an "
        "absolute floor alone always accepts something. Genuine intent "
        "separates from the runner-up; noise does not. 0 disables the check. "
        "MEASURED FRAGILITY (2026-08, routing_eval_extended): the sole "
        "passing entry routed by this layer sits at margin 0.071 while the "
        "nearest accepted noise hit sits at 0.0702 — the gate is sharp, and "
        "an index rebuild (fresh LLM-generated profiles/embeddings) can flip "
        "either side of it. Recalibrate against the eval set after any "
        "rebuild before tuning this value.",
    )
    index_external_trusted_floor: float = Field(
        default=0.35,
        ge=0.0,
        lt=1.0,
        description="Pack-vs-trusted arbitration floor (M10) for the "
        "SEMANTIC_INDEX embedding fallback: an external pack winner is "
        "accepted only when NO trusted-namespace (builtin/project/custom/"
        "cross-cutting) profile reaches this cosine similarity — i.e. no "
        "trusted skill shows real evidence. 0.35 sits just above the "
        "paraphrase-multilingual-MiniLM-L12-v2 noise band for unrelated "
        "pairs (~0.1-0.3, see ai_triage_recall_min_similarity) and below the "
        "0.45 hard-match floor: a trusted profile in between is evidence the "
        "query has trusted-catalog content but not enough to route to it, so "
        "a pack winner there is crowd-out, not a genuine hit, and the layer "
        "abstains to AI triage. Calibration (2026-08, routing_eval_extended): "
        "the one passing pack positive (omx/git-master) has best-trusted "
        "0.274 (safely below) — that keep-side positive is the binding "
        "constraint on raising this floor, while abstain-side failures fail "
        "soft (no-match, then AI triage). The strong-overlap misroute "
        "cluster sits at 0.351-0.502. Fragility note: TWO cluster members "
        "(0.351 and 0.352) sit within 0.002 of the floor. Re-embedding "
        "identical profile text is near-deterministic, so a plain index "
        "rebuild will NOT move these; the real trigger is pack profile TEXT "
        "drift when a skill's content is updated and re-analyzed. "
        "Recalibrate before tuning after any pack content change. 0 disables "
        "the arbitration (every pack win is accepted); values approaching "
        "1.0 make pack acceptance nearly impossible (any trusted profile "
        "above the noise band arbitrates).",
    )
    keyword_coverage_ref: float = Field(
        default=0.5,
        gt=0.0,
        le=1.0,
        description="Coverage-gate saturation point (M11) for KeywordMatcher "
        "evidence scoring: additive bonuses (partial + name/keyword hits) are "
        "scaled by g = min(1, cov / keyword_coverage_ref), where cov is the "
        "IDF-weighted share of meaningful query tokens that hit the "
        "candidate. This kills the pre-M11 failure mode where a 100-token "
        "log-dump query mentioning two generic words (复审/review/design) "
        "reached 0.9+ on additive bonuses alone. Calibration (2026-08, "
        ".omx/artifacts/m11-design-a.md): REF band 0.4-0.6 re-verified on "
        "production code with the FULL mechanism (coverage gate + anchor "
        "gate + stopword table + TF-IDF gate) — extended eval is 98/107 at "
        "every point of the band, base 31/34 and oneshot 10/11 unchanged; "
        "the mechanism is insensitive inside this band, 0.5 is the "
        "midpoint.",
    )
    keyword_anchor_idf_min: float = Field(
        default=0.78,
        ge=0.0,
        le=1.0,
        description="Minimum normalized pool-IDF weight for a query token to "
        "count as an anchor (M11). Without any anchor, a keyword score is "
        "capped at keyword_anchor_cap. Anchors are also gated on an English "
        "stopword list: in a skill-catalog corpus, function words like "
        "'not' are RARE (high IDF) yet semantically empty. Calibration "
        "(2026-08): the binding interval is (0.724, 0.78] — 'type' (0.724) "
        "must NOT anchor, while CJK domain bigrams like 模式 (0.786) must. "
        "Weights are normalized (pool-size-agnostic), but tokens near this "
        "boundary can flip when the installed pool changes significantly; "
        "re-run the routing evals after major pool changes. SMALL POOLS: "
        "normalized weights compress as N shrinks (e.g. df=2 gives w≈0.68 "
        "at N=10 vs 0.83 at N=239), so the anchor gate gets STRICTER — "
        "recall drops, not precision. Lower this value on small pools.",
    )
    keyword_anchor_cap: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Score cap for anchorless keyword matches (M11). Set "
        "below the 0.3 matcher min_confidence default so anchorless matches "
        "abstain even on installations whose routing.min_confidence "
        "preference has not been raised to 0.6.",
    )
    keyword_multi_anchor_min: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Multi-anchor exemption (M11): with at least this many "
        "anchor hits in the CURATED fields (name/keywords — description hits "
        "are free-text coincidences and do not count) plus coverage >= "
        "keyword_multi_anchor_cov_floor, the coverage gate saturates (g=1). "
        "This is what keeps genuine focused queries ('深度诊断…优化建议', "
        "coverage only 0.14 but two distinctive keyword hits) routable while "
        "long noisy queries with a single generic hit stay gated.",
    )
    keyword_multi_anchor_cov_floor: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
        description="Coverage floor for the multi-anchor exemption (M11) — "
        "prevents the exemption from rescuing queries whose anchors are "
        "incidental mentions inside a long unrelated text. Calibration "
        "(2026-08): the binding interval is (0.049, 0.139), between the "
        "meeting-notes misroute (0.049, must not exempt) and the closest "
        "base-set positive (0.139, must exempt); 0.08 sits near the "
        "log-midpoint.",
    )
    keyword_name_idf_min: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum normalized IDF weight for a SINGLE-token skill "
        "name to earn the 0.4 name bonus when it appears in the query "
        "(M11). Generic one-word names ('design', w=0.465 in the calibration "
        "pool) no longer trigger the bonus inside arbitrary long queries; "
        "distinctive names ('instinct', w=0.83) still do — being named "
        "literally is explicit intent. Multi-token names are exempt (already "
        "specific).",
    )
    tfidf_anchor_gate_enabled: bool = Field(
        default=True,
        description="Result-level anchor gate (M11) for TFIDFMatcher: TF-IDF "
        "results without any anchor (non-stopword, high-IDF query token with "
        "exact/name/keyword evidence) are dropped. TF-IDF cosine keys on "
        "surface overlap, so short queries sharing one generic term with a "
        "candidate reach routable scores on noise ('按批次拆 commit' -> "
        "setup-pre-commit at 0.63). The gate uses the same anchor definition "
        "and threshold (keyword_anchor_idf_min) as the keyword matcher. "
        "Disable to restore pre-M11 behavior if it false-negative-filters a "
        "genuine generic-vocabulary positive.",
    )
    ai_triage_recall_min_similarity: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity for the AI-triage embedding "
        "recall prefilter (paraphrase-multilingual-MiniLM-L12-v2). Candidates "
        "below this floor are dropped from the LLM triage window; when nothing "
        "clears the floor, triage is skipped instead of sending garbage. Only "
        "applies when the eligible candidate count exceeds ai_triage_max_skills "
        "— smaller sets are forwarded whole (protective for terse/CJK queries). "
        "0.25 sits just above the model's ~0.1-0.3 noise floor for unrelated "
        "pairs (recall is a top-N prefilter, so it stays lower than the 0.45 "
        "hard-match floor used by the SEMANTIC_INDEX embedding fallback).",
    )
    session_aware: bool = Field(
        default=True,
        description="Enable session-state-aware routing for multi-turn conversations",
    )
    session_stickiness_boost: float = Field(
        default=0.08,
        ge=0.0,
        le=0.2,
        description="Confidence boost for current skill in multi-turn continuity",
    )
    fallback_mode: Literal["transparent", "silent", "disabled"] = Field(
        default="transparent",
        description="Behavior when no skill matches: transparent (explain + suggest), silent (quiet fallback), disabled (show 'no match')",
    )
    default_strategy: Literal["auto", "sequential", "parallel", "hybrid"] = Field(
        default="auto",
        description="Default execution strategy for multi-skill orchestration: auto, sequential, parallel, hybrid",
    )
    degradation_enabled: bool = Field(
        default=True,
        description="Enable confidence-gated layered degradation instead of binary fallback",
    )
    degradation_auto_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for auto-selection (>= this = auto)",
    )
    degradation_suggest_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for suggest mode (>= this but < auto = suggest)",
    )
    degradation_degrade_threshold: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for degrade mode (>= this but < suggest = degrade, below = fallback)",
    )
    degradation_fallback_always_ask: bool = Field(
        default=True,
        description="When in fallback mode, ask user before proceeding with raw LLM",
    )
    transparency: Literal["full", "compact"] = Field(
        default="full",
        description="Routing transparency mode: 'full' (default, show decision tree) or 'compact' (summary only)",
    )


class SecurityConfig(TolerantConfig):
    """Configuration for security settings."""

    scan_external: bool = True
    require_audit: bool = True
    allowed_paths: list[str] = Field(
        default_factory=lambda: [
            "~/.claude/skills",
            "~/.config/skills",
            ".vibe/skills",
        ]
    )
    block_patterns: list[str] = Field(default_factory=list)


class SemanticConfig(TolerantConfig):
    """Configuration for semantic matching."""

    enabled: bool = False
    model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    cache_embeddings: bool = True
    batch_size: int = 32


class PromptChainConfig(TolerantConfig):
    """Configuration for prompt chain generation (v7.0)."""

    enabled: bool = Field(
        default=True,
        description="Enable prompt chain generation for multi-agent workflows",
    )
    multi_agent_complexity_threshold: int = Field(
        default=3,
        ge=2,
        le=10,
        description="Number of distinct skill domains to trigger multi_agent mode",
    )
    output_dir: str = Field(
        default=".vibe/prompts",
        description="Directory for generated prompt chain files (relative to project root)",
    )


class PlatformsConfig(TolerantConfig):
    """Configuration for which AI agent platforms receive skill installs.

    VibeSOP supports multiple AI coding agents (Claude Code, Kimi CLI,
    OpenCode, Cursor, Pi). To avoid surprise writes to ``~/.pi/`` or
    ``~/.kimi-code/`` for users who only use one agent, the default scope
    is just ``claude-code``. Set ``install_targets`` to declare the full set.
    """

    install_targets: list[str] = Field(
        default_factory=lambda: ["claude-code"],
        description=(
            "Platforms that receive symlinks when ``vibe install`` runs "
            "without --platform. Valid values: claude-code, kimi-cli, "
            "opencode, cursor, pi. Default: ['claude-code']."
        ),
    )


class LoopConfig(TolerantConfig):
    """Configuration for the autonomous Loop System (v8.0).

    Set ``enabled = true`` to allow ``vibe loop tick`` to actually execute
    loops. When false, ``tick`` reports eligible loops but skips execution
    (useful for dry-running a deployment before flipping the switch).
    """

    enabled: bool = Field(
        default=False,
        description="Master switch for loop execution. When false, tick reports only.",
    )
    default_tick_seconds: int = Field(
        default=60,
        ge=10,
        description="Recommended interval for external cron to call `vibe loop tick`.",
    )
    max_active_loops: int = Field(
        default=20,
        ge=1,
        description="Soft cap on simultaneously active loops. tick warns when exceeded.",
    )


class ObservabilityConfig(TolerantConfig):
    """Configuration for agent-internal observability (span tracing).

    Controls span emission, retention, and payload limits. Spans are
    written to ``.vibe/observability/spans.jsonl`` regardless of backend.
    """

    enabled: bool = Field(
        default=True,
        description="Master switch for span tracing. When false, no spans are emitted.",
    )
    panel_url: str = Field(
        default="http://127.0.0.1:14500",
        description="Panel OTLP endpoint URL (for future Panel integration).",
    )
    span_max_payload_chars: int = Field(
        default=16384,
        ge=1024,
        le=1048576,
        description="Maximum characters for input_data / output_data in spans.",
    )
    span_retention_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Number of days to retain spans before auto-cleanup.",
    )
    span_max_total: int = Field(
        default=100000,
        ge=1000,
        description="Hard cap on total spans; oldest spans are evicted when exceeded.",
    )


class ConfigManager:
    """Unified configuration manager.

    Consolidates configuration from defaults, global config, project config,
    environment variables, and CLI arguments.
    """

    # Default configuration
    DEFAULT_CONFIG: ClassVar[dict[str, Any]] = {
        "llm": {
            "provider": None,
            "model": None,
            "api_key": None,
            "api_base": None,
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "routing": RoutingConfig().model_dump(),
        "security": SecurityConfig().model_dump(),
        "semantic": SemanticConfig().model_dump(),
        "prompt_chain": PromptChainConfig().model_dump(),
        "platforms": PlatformsConfig().model_dump(),
        "loop": LoopConfig().model_dump(),
        "observability": ObservabilityConfig().model_dump(),
        "optimization": {
            "enabled": True,
            "prefilter": {
                "enabled": True,
                "min_candidates": 5,
                "max_candidates": 15,
                "always_include_p0": True,
                "namespace_relevance_threshold": 0.3,
            },
            "preference_boost": {
                "enabled": True,
                "weight": 0.3,
                "min_samples": 2,
                "decay_days": 30,
            },
            "clustering": {
                "enabled": True,
                "auto_resolve": True,
                "confidence_gap_threshold": 0.1,
                "min_skills_for_clustering": 10,
                "max_clusters": 12,
            },
        },
        # F-06: analytics persistence is opt-in (default off) — the user's raw
        # query is NOT written to .vibe/analytics.jsonl unless explicitly enabled.
        "analytics": {
            "enabled": False,
        },
    }

    # Environment variable prefix
    ENV_PREFIX = "VIBE_"

    @staticmethod
    def deep_merge_configs(*configs: dict[str, Any]) -> dict[str, Any]:
        """Deep merge multiple configuration dictionaries. Later configs override earlier."""
        from vibesop.utils.helpers import merge_dicts

        if not configs:
            return {}

        return merge_dicts(configs[0], *configs[1:])

    def __init__(self, project_root: str | Path = "."):
        self.project_root = Path(project_root).resolve()
        self._sources: dict[ConfigSourcePriority, ConfigSource] = {}
        self._cache: dict[str, Any] = {}

        # Initialize configuration sources
        self._init_sources()

    def _init_sources(self) -> None:
        self._sources[ConfigSourcePriority.DEFAULTS] = ConfigSource(
            priority=ConfigSourcePriority.DEFAULTS,
            data=self.DEFAULT_CONFIG.copy(),
            path=None,
        )

        global_config_path = ConfigSource._resolve_config_path(Path.home() / ".vibe", "config")  # pyright: ignore[reportPrivateUsage]
        if global_config_path:
            source = ConfigSource(
                priority=ConfigSourcePriority.GLOBAL,
                data={},
                path=global_config_path,
            )
            source.load_from_file()
            self._sources[ConfigSourcePriority.GLOBAL] = source

        project_config_path = ConfigSource._resolve_config_path(
            self.project_root / ".vibe", "config"
        )  # pyright: ignore[reportPrivateUsage]
        if project_config_path:
            source = ConfigSource(
                priority=ConfigSourcePriority.PROJECT,
                data={},
                path=project_config_path,
            )
            source.load_from_file()
            self._sources[ConfigSourcePriority.PROJECT] = source

        preferences_path = self.project_root / ".vibe" / "preferences.json"
        if preferences_path.exists():
            import json

            with preferences_path.open(encoding="utf-8") as f:
                data = json.load(f)

            mapped_data = self._map_legacy_preferences(data)
            self._sources[ConfigSourcePriority.PREFERENCES] = ConfigSource(
                priority=ConfigSourcePriority.PREFERENCES,
                data=mapped_data,
                path=preferences_path,
            )

    def _map_legacy_preferences(self, prefs: dict[str, Any]) -> dict[str, Any]:
        """Map legacy preferences to new config structure."""
        mapped = {}

        # Map routing preferences
        if "routing" in prefs:
            mapped["routing"] = {
                "min_confidence": prefs["routing"].get("min_confidence", 0.3),
                "enable_ai": prefs["routing"].get("enable_ai", False),
            }

        # Map semantic preferences
        if "semantic" in prefs:
            mapped["semantic"] = {
                "enabled": prefs["semantic"].get("enabled", False),
                "model": prefs["semantic"].get("model", "paraphrase-multilingual-MiniLM-L12-v2"),
            }

        return mapped

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key (supports dot notation)."""
        # Check cache first
        cache_key = f"get:{key}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check environment variables first (highest priority)
        env_key = self._key_to_env(key)
        if env_key in os.environ:
            value = os.environ[env_key]
            self._cache[cache_key] = value
            return value

        # Check sources in reverse priority order (highest first)
        for priority in reversed(ConfigSourcePriority):
            if priority in self._sources:
                source = self._sources[priority]
                if source.has(key):
                    value = source.get(key, default)
                    self._cache[cache_key] = value
                    return value

        self._cache[cache_key] = default
        return default

    def get_routing_config(self) -> RoutingConfig:
        return RoutingConfig(**self._get_section("routing"))

    def get_security_config(self) -> SecurityConfig:
        return SecurityConfig(**self._get_section("security"))

    def get_semantic_config(self) -> SemanticConfig:
        return SemanticConfig(**self._get_section("semantic"))

    def get_prompt_chain_config(self) -> PromptChainConfig:
        return PromptChainConfig(**self._get_section("prompt_chain"))

    def get_platforms_config(self) -> PlatformsConfig:
        return PlatformsConfig(**self._get_section("platforms"))

    def get_loop_config(self) -> LoopConfig:
        return LoopConfig(**self._get_section("loop"))

    def get_optimization_config(self) -> OptimizationConfig:
        from vibesop.core.config.optimization_config import OptimizationConfig

        return OptimizationConfig(**self._get_section("optimization"))

    def load_policy(self) -> dict[str, Any]:
        return {
            "security": self._get_section("security"),
            "routing": self._get_section("routing"),
            "behavior": self._get_section("behavior"),
            "custom": self._get_section("custom"),
        }

    def _get_section(self, section: str) -> dict[str, Any]:
        """Get a complete configuration section merged from all sources."""
        configs_to_merge = []

        if section in self.DEFAULT_CONFIG:
            configs_to_merge.append({section: self.DEFAULT_CONFIG[section]})

        for priority in ConfigSourcePriority:
            if priority in self._sources:
                source = self._sources[priority]
                if section in source.data:
                    configs_to_merge.append({section: source.data[section]})

        merged = self.deep_merge_configs(*configs_to_merge)

        prefix = f"{self.ENV_PREFIX}{section.upper()}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower()
                if section not in merged:
                    merged[section] = {}
                merged[section][config_key] = self._parse_env_value(value)

        return merged.get(section, {})

    def _key_to_env(self, key: str) -> str:
        return f"{self.ENV_PREFIX}{key.upper().replace('.', '_')}"

    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Try boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Try int
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Return as string
        return value

    def reload(self) -> None:
        self._cache.clear()

        for source in self._sources.values():
            source.reload()

    def set_cli_override(self, key: str, value: Any) -> None:
        """Set a CLI override (highest priority)."""
        # Create CLI source if it doesn't exist
        if ConfigSourcePriority.CLI not in self._sources:
            self._sources[ConfigSourcePriority.CLI] = ConfigSource(
                priority=ConfigSourcePriority.CLI,
                data={},
                path=None,
            )

        # Set the value (support dot notation)
        keys = key.split(".")
        data = self._sources[ConfigSourcePriority.CLI].data

        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]

        data[keys[-1]] = value

        self._cache.clear()

    # --- Registry loading (migrated from ConfigLoader) ---

    def load_registry(self, force_reload: bool = False) -> dict[str, Any]:
        """Load skill registry from core/registry.yaml."""
        cache_key = "_registry"
        if not force_reload and cache_key in self._cache:
            return self._cache[cache_key]

        # Repo checkout wins; wheel installs (pipx/uv tool) fall back to the
        # bundled copy so routing does not silently run with an empty registry.
        from vibesop.utils.bundled import bundled_core_file

        registry_path = bundled_core_file("registry.yaml", self.project_root)

        if not registry_path.exists():
            return {"skills": [], "version": "1.0.0"}

        try:
            from ruamel.yaml import YAML

            yaml = YAML()
            with registry_path.open("r", encoding="utf-8") as f:
                data = yaml.load(f) or {}  # nosec B506  # ruamel.yaml.YAML().load() is safe (no arbitrary object instantiation)

            self._cache[cache_key] = data
            return data
        except Exception as e:
            # A malformed registry silently lobotomizes routing: every consumer
            # (skills/manager, manifest builder, inspect, scenario layer) would
            # see ZERO skills with no signal. Log loudly (ERROR, not debug) so
            # misconfiguration is visible. We keep the documented return contract
            # (empty dict, not raise) — callers degrade to "no skills", but the
            # operator now sees exactly why.
            logger.error(
                "Failed to parse skill registry %s: %s — routing/manifest/inspect "
                "will see ZERO skills. Fix the YAML (see parse error above).",
                registry_path,
                e,
            )
            return {"skills": [], "version": "1.0.0"}

    def get_all_skills(self, force_reload: bool = False) -> list[dict[str, Any]]:
        registry = self.load_registry(force_reload=force_reload)
        return registry.get("skills", [])

    def get_skill_by_id(
        self,
        skill_id: str,
        force_reload: bool = False,
    ) -> dict[str, Any] | None:
        skills = self.get_all_skills(force_reload=force_reload)

        for skill in skills:
            if skill.get("id") == skill_id:
                return skill

        if skill_id.startswith("/"):
            shorthand = skill_id[1:]
            for skill in skills:
                sid = skill.get("id", "")
                if sid.endswith(f"/{shorthand}") or sid.endswith(f"-{shorthand}"):
                    return skill
        else:
            for skill in skills:
                sid = skill.get("id", "")
                if sid.endswith(f"/{skill_id}") or sid.endswith(f"-{skill_id}"):
                    return skill

        return None

    def get_skills_by_namespace(
        self,
        namespace: str,
        force_reload: bool = False,
    ) -> list[dict[str, Any]]:
        skills = self.get_all_skills(force_reload=force_reload)
        return [skill for skill in skills if skill.get("namespace") == namespace]

    def search_skills(
        self,
        query: str,
        force_reload: bool = False,
    ) -> list[dict[str, Any]]:
        """Search skills by keyword in intent or description."""
        skills = self.get_all_skills(force_reload=force_reload)
        query_lower = query.lower()
        return [skill for skill in skills if query_lower in (skill.get("intent") or "").lower()]

    def clear_cache(self) -> None:
        self._cache.clear()
