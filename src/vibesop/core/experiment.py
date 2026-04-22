"""A/B Testing Framework for VibeSOP routing strategies.

Allows users to run controlled experiments comparing different
routing configurations and automatically select winners.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VariantConfig:
    """Configuration for a single experiment variant."""

    name: str
    description: str = ""
    # RoutingConfig overrides for this variant
    overrides: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "overrides": self.overrides,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VariantConfig:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            overrides=data.get("overrides", {}),
        )


@dataclass
class RouteMetrics:
    """Metrics from a single route() call."""

    query: str
    matched: bool
    skill_id: str | None
    confidence: float
    layer: str | None
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "matched": self.matched,
            "skill_id": self.skill_id,
            "confidence": self.confidence,
            "layer": self.layer,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouteMetrics:
        return cls(
            query=data["query"],
            matched=data["matched"],
            skill_id=data.get("skill_id"),
            confidence=data["confidence"],
            layer=data.get("layer"),
            duration_ms=data["duration_ms"],
        )


@dataclass
class VariantResult:
    """Aggregated results for a single variant."""

    variant: VariantConfig
    metrics: list[RouteMetrics] = field(default_factory=list)

    @property
    def match_rate(self) -> float:
        if not self.metrics:
            return 0.0
        return sum(1 for m in self.metrics if m.matched) / len(self.metrics)

    @property
    def avg_confidence(self) -> float:
        if not self.metrics:
            return 0.0
        matched = [m.confidence for m in self.metrics if m.matched]
        return sum(matched) / len(matched) if matched else 0.0

    @property
    def avg_duration_ms(self) -> float:
        if not self.metrics:
            return 0.0
        return sum(m.duration_ms for m in self.metrics) / len(self.metrics)

    @property
    def fallback_rate(self) -> float:
        if not self.metrics:
            return 0.0
        return sum(1 for m in self.metrics if m.layer == "fallback_llm") / len(self.metrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant.to_dict(),
            "metrics": [m.to_dict() for m in self.metrics],
            "summary": {
                "match_rate": self.match_rate,
                "avg_confidence": self.avg_confidence,
                "avg_duration_ms": self.avg_duration_ms,
                "fallback_rate": self.fallback_rate,
            },
        }


@dataclass
class Experiment:
    """An A/B testing experiment."""

    name: str
    description: str
    queries: list[str]
    variants: list[VariantConfig]
    created_at: str
    status: str = "draft"  # draft | running | completed
    results: dict[str, VariantResult] = field(default_factory=dict)
    winner: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "queries": self.queries,
            "variants": [v.to_dict() for v in self.variants],
            "created_at": self.created_at,
            "status": self.status,
            "results": {k: v.to_dict() for k, v in self.results.items()},
            "winner": self.winner,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Experiment:
        exp = cls(
            name=data["name"],
            description=data.get("description", ""),
            queries=data.get("queries", []),
            variants=[VariantConfig.from_dict(v) for v in data.get("variants", [])],
            created_at=data.get("created_at", ""),
            status=data.get("status", "draft"),
            winner=data.get("winner"),
        )
        exp.results = {
            k: VariantResult(
                variant=next(v for v in exp.variants if v.name == k),
                metrics=[RouteMetrics.from_dict(m) for m in v["metrics"]],
            )
            for k, v in data.get("results", {}).items()
        }
        return exp


class ExperimentStore:
    """Persistent storage for experiments."""

    def __init__(self, storage_dir: str | Path = ".vibe/experiments") -> None:
        self._storage_dir = Path(storage_dir)

    def _file_path(self, name: str) -> Path:
        safe_name = name.replace(" ", "_").replace("/", "_")
        return self._storage_dir / f"{safe_name}.json"

    def save(self, experiment: Experiment) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        path = self._file_path(experiment.name)
        with path.open("w", encoding="utf-8") as f:
            json.dump(experiment.to_dict(), f, ensure_ascii=False, indent=2)

    def load(self, name: str) -> Experiment | None:
        path = self._file_path(name)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return Experiment.from_dict(data)

    def list_experiments(self) -> list[str]:
        if not self._storage_dir.exists():
            return []
        return [p.stem.replace("_", " ") for p in self._storage_dir.glob("*.json")]

    def delete(self, name: str) -> bool:
        path = self._file_path(name)
        if path.exists():
            path.unlink()
            return True
        return False


class ExperimentRunner:
    """Run experiments and collect metrics."""

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()

    def run(
        self,
        experiment: Experiment,
        progress_callback: callable | None = None,
    ) -> Experiment:
        """Run the experiment against all variants."""
        from vibesop.core.config import RoutingConfig as ConfigRoutingConfig
        from vibesop.core.routing import UnifiedRouter

        experiment.status = "running"

        for variant in experiment.variants:
            variant_result = VariantResult(variant=variant)

            # Build router with variant overrides
            config = ConfigRoutingConfig(**variant.overrides)
            router = UnifiedRouter(project_root=self.project_root, config=config)

            for i, query in enumerate(experiment.queries):
                start = time.perf_counter()
                result = router.route(query)
                duration_ms = (time.perf_counter() - start) * 1000

                metrics = RouteMetrics(
                    query=query,
                    matched=result.has_match,
                    skill_id=result.primary.skill_id if result.primary else None,
                    confidence=result.primary.confidence if result.primary else 0.0,
                    layer=result.primary.layer.value if result.primary else None,
                    duration_ms=duration_ms,
                )
                variant_result.metrics.append(metrics)

                if progress_callback:
                    progress_callback(variant.name, i + 1, len(experiment.queries))

            experiment.results[variant.name] = variant_result

        experiment.status = "completed"
        return experiment


class ExperimentAnalyzer:
    """Analyze experiment results and recommend winners."""

    @staticmethod
    def analyze(experiment: Experiment) -> dict[str, Any]:
        """Analyze completed experiment and return recommendations."""
        if experiment.status != "completed":
            return {"error": "Experiment not completed"}

        if len(experiment.results) < 2:
            return {"error": "Need at least 2 variants to compare"}

        # Score each variant on multiple dimensions
        scores: dict[str, float] = {}
        details: dict[str, dict[str, Any]] = {}

        for name, result in experiment.results.items():
            # Composite score: match_rate * 0.4 + avg_confidence * 0.3 + (1-fallback_rate) * 0.2 + speed * 0.1
            # Speed factor: faster is better, normalized against fastest
            all_durations = [
                r.avg_duration_ms for r in experiment.results.values() if r.avg_duration_ms > 0
            ]
            min_duration = min(all_durations) if all_durations else 1.0

            speed_score = min_duration / max(result.avg_duration_ms, 0.001)

            score = (
                result.match_rate * 0.4
                + result.avg_confidence * 0.3
                + (1 - result.fallback_rate) * 0.2
                + speed_score * 0.1
            )
            scores[name] = score
            details[name] = {
                "match_rate": result.match_rate,
                "avg_confidence": result.avg_confidence,
                "avg_duration_ms": result.avg_duration_ms,
                "fallback_rate": result.fallback_rate,
                "speed_score": speed_score,
                "composite_score": score,
            }

        winner = max(scores, key=scores.get)  # type: ignore[arg-type]
        experiment.winner = winner

        return {
            "winner": winner,
            "scores": scores,
            "details": details,
            "recommendation": f"Variant '{winner}' performed best with composite score {scores[winner]:.3f}",
        }
