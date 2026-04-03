"""Experiment management system.

This module provides capabilities for running A/B tests and
managing experiments with metrics tracking.
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from collections import defaultdict


class ExperimentStatus(Enum):
    """Status of an experiment.

    Attributes:
        DRAFT: Experiment is being designed
        RUNNING: Experiment is currently running
        PAUSED: Experiment is paused
        COMPLETED: Experiment has completed
        CANCELLED: Experiment was cancelled
    """
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VariantStatus(Enum):
    """Status of a variant.

    Attributes:
        ACTIVE: Variant is active
        DISABLED: Variant is disabled
        WON: Variant won the experiment
    """
    ACTIVE = "active"
    DISABLED = "disabled"
    WON = "won"


@dataclass
class Variant:
    """Experiment variant.

    Attributes:
        variant_id: Unique variant identifier
        name: Variant name
        description: Variant description
        config: Variant configuration
        traffic_allocation: Traffic percentage (0-100)
        metrics: Collected metrics
        status: Variant status
    """
    variant_id: str
    name: str
    description: str
    config: Dict[str, Any]
    traffic_allocation: int
    metrics: Dict[str, float]
    status: VariantStatus


@dataclass
class Experiment:
    """A/B test experiment.

    Attributes:
        experiment_id: Unique experiment identifier
        name: Experiment name
        description: Experiment description
        hypothesis: Hypothesis being tested
        variants: List of variants
        primary_metric: Primary success metric
        status: Experiment status
        created_at: Creation timestamp
        started_at: Start timestamp
        ended_at: End timestamp
        metadata: Additional metadata
    """
    experiment_id: str
    name: str
    description: str
    hypothesis: str
    variants: List[Variant]
    primary_metric: str
    status: ExperimentStatus
    created_at: str
    started_at: Optional[str]
    ended_at: Optional[str]
    metadata: Dict[str, Any]


class ExperimentManager:
    """Manage A/B testing experiments.

    Provides functionality for creating, running, and analyzing
    A/B test experiments with proper metrics tracking.

    Example:
        >>> manager = ExperimentManager()
        >>> experiment = manager.create_experiment(...)
        >>> manager.start_experiment(experiment.experiment_id)
        >>> result = manager.get_variant(user_id, experiment_id)
    """

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        """Initialize the experiment manager.

        Args:
            storage_dir: Directory for experiment data storage
        """
        self._storage_dir = storage_dir or Path.cwd() / ".vibe" / "experiments"
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        self._experiments: Dict[str, Experiment] = {}
        self._user_assignments: Dict[str, Dict[str, str]] = defaultdict(dict)

        # Load existing experiments
        self._load_experiments()

    def create_experiment(
        self,
        name: str,
        description: str,
        hypothesis: str,
        variants: List[Dict[str, Any]],
        primary_metric: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Experiment:
        """Create a new experiment.

        Args:
            name: Experiment name
            description: Experiment description
            hypothesis: Hypothesis being tested
            variants: List of variant configurations
            primary_metric: Primary success metric name
            metadata: Additional metadata

        Returns:
            Created experiment
        """
        experiment_id = str(uuid.uuid4())

        # Create variant objects
        variant_objs = []
        for i, var_config in enumerate(variants):
            variant = Variant(
                variant_id=str(uuid.uuid4()),
                name=var_config.get("name", f"Variant {i+1}"),
                description=var_config.get("description", ""),
                config=var_config.get("config", {}),
                traffic_allocation=var_config.get("traffic_allocation", 50),
                metrics={},
                status=VariantStatus.ACTIVE if i == 0 else VariantStatus.DISABLED,
            )
            variant_objs.append(variant)

        experiment = Experiment(
            experiment_id=experiment_id,
            name=name,
            description=description,
            hypothesis=hypothesis,
            variants=variant_objs,
            primary_metric=primary_metric,
            status=ExperimentStatus.DRAFT,
            created_at=datetime.now().isoformat(),
            started_at=None,
            ended_at=None,
            metadata=metadata or {},
        )

        self._experiments[experiment_id] = experiment
        self._save_experiment(experiment)

        return experiment

    def start_experiment(
        self,
        experiment_id: str,
    ) -> Dict[str, Any]:
        """Start an experiment.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Result dictionary
        """
        result = {
            "success": False,
            "errors": [],
        }

        if experiment_id not in self._experiments:
            result["errors"].append("Experiment not found")
            return result

        experiment = self._experiments[experiment_id]

        if experiment.status != ExperimentStatus.DRAFT:
            result["errors"].append(f"Cannot start experiment in {experiment.status.value} status")
            return result

        # Validate variants
        if len(experiment.variants) < 2:
            result["errors"].append("Experiment must have at least 2 variants")
            return result

        # Check traffic allocation
        total_allocation = sum(v.traffic_allocation for v in experiment.variants)
        if total_allocation != 100:
            result["errors"].append(f"Traffic allocation must sum to 100, got {total_allocation}")
            return result

        # Start experiment
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now().isoformat()

        # Activate all variants
        for variant in experiment.variants:
            if variant.status != VariantStatus.DISABLED:
                variant.status = VariantStatus.ACTIVE

        self._save_experiment(experiment)
        result["success"] = True

        return result

    def get_variant(
        self,
        user_id: str,
        experiment_id: str,
    ) -> Optional[Variant]:
        """Get variant for a user in an experiment.

        Args:
            user_id: User identifier
            experiment_id: Experiment identifier

        Returns:
            Assigned variant, or None if experiment not running
        """
        if experiment_id not in self._experiments:
            return None

        experiment = self._experiments[experiment_id]

        if experiment.status != ExperimentStatus.RUNNING:
            return None

        # Check if user already assigned
        if user_id in self._user_assignments[experiment_id]:
            variant_id = self._user_assignments[experiment_id][user_id]
            for variant in experiment.variants:
                if variant.variant_id == variant_id:
                    return variant

        # Assign user to variant based on traffic allocation
        import random
        rand = random.randint(0, 99)
        cumulative = 0

        for variant in experiment.variants:
            if variant.status != VariantStatus.ACTIVE:
                continue

            cumulative += variant.traffic_allocation
            if rand < cumulative:
                self._user_assignments[experiment_id][user_id] = variant.variant_id
                return variant

        return None

    def track_metric(
        self,
        user_id: str,
        experiment_id: str,
        metric_name: str,
        value: float,
    ) -> Dict[str, Any]:
        """Track a metric for a user in an experiment.

        Args:
            user_id: User identifier
            experiment_id: Experiment identifier
            metric_name: Metric name
            value: Metric value

        Returns:
            Result dictionary
        """
        result = {
            "success": False,
            "errors": [],
        }

        if experiment_id not in self._experiments:
            result["errors"].append("Experiment not found")
            return result

        # Get user's variant
        variant = self.get_variant(user_id, experiment_id)
        if variant is None:
            result["errors"].append("User not assigned to active variant")
            return result

        # Track metric
        variant.metrics[metric_name] = variant.metrics.get(metric_name, 0) + value

        self._save_experiment(self._experiments[experiment_id])
        result["success"] = True

        return result

    def get_experiment_results(
        self,
        experiment_id: str,
    ) -> Dict[str, Any]:
        """Get experiment results and analysis.

        Args:
            experiment_id: Experiment identifier

        Returns:
            Results dictionary
        """
        result = {
            "experiment_id": experiment_id,
            "exists": False,
            "status": None,
            "variants": [],
            "winner": None,
            "metrics_summary": {},
            "errors": [],
        }

        if experiment_id not in self._experiments:
            result["errors"].append("Experiment not found")
            return result

        experiment = self._experiments[experiment_id]
        result["exists"] = True
        result["status"] = experiment.status.value

        # Aggregate metrics by variant
        for variant in experiment.variants:
            result["variants"].append({
                "variant_id": variant.variant_id,
                "name": variant.name,
                "status": variant.status.value,
                "traffic_allocation": variant.traffic_allocation,
                "metrics": variant.metrics.copy(),
            })

        # Calculate winner (if completed)
        if experiment.status == ExperimentStatus.COMPLETED:
            winner = self._calculate_winner(experiment)
            result["winner"] = winner

        # Summary statistics
        for metric_name in {experiment.primary_metric}:
            values = []
            for variant in experiment.variants:
                if metric_name in variant.metrics:
                    values.append(variant.metrics[metric_name])

            if values:
                result["metrics_summary"][metric_name] = {
                    "total": sum(values),
                    "average": sum(values) / len(values),
                    "count": len(values),
                }

        return result

    def end_experiment(
        self,
        experiment_id: str,
        select_winner: bool = True,
    ) -> Dict[str, Any]:
        """End an experiment.

        Args:
            experiment_id: Experiment identifier
            select_winner: Whether to automatically select winner

        Returns:
            Result dictionary
        """
        result = {
            "success": False,
            "errors": [],
        }

        if experiment_id not in self._experiments:
            result["errors"].append("Experiment not found")
            return result

        experiment = self._experiments[experiment_id]

        if experiment.status != ExperimentStatus.RUNNING:
            result["errors"].append(f"Cannot end experiment in {experiment.status.value} status")
            return result

        # End experiment
        experiment.status = ExperimentStatus.COMPLETED
        experiment.ended_at = datetime.now().isoformat()

        # Select winner if requested
        if select_winner:
            winner = self._calculate_winner(experiment)
            if winner:
                winner.status = VariantStatus.WON
                # Disable other variants
                for variant in experiment.variants:
                    if variant.variant_id != winner.variant_id:
                        variant.status = VariantStatus.DISABLED

        self._save_experiment(experiment)
        result["success"] = True

        return result

    def list_experiments(
        self,
        status: Optional[ExperimentStatus] = None,
    ) -> List[Experiment]:
        """List experiments.

        Args:
            status: Filter by status (None = all)

        Returns:
            List of experiments
        """
        experiments = list(self._experiments.values())

        if status:
            experiments = [e for e in experiments if e.status == status]

        return experiments

    def _calculate_winner(self, experiment: Experiment) -> Optional[Variant]:
        """Calculate winning variant.

        Args:
            experiment: Experiment

        Returns:
            Winning variant, or None
        """
        best_variant = None
        best_value = None

        for variant in experiment.variants:
            if variant.status == VariantStatus.DISABLED:
                continue

            if experiment.primary_metric in variant.metrics:
                value = variant.metrics[experiment.primary_metric]

                if best_value is None or value > best_value:
                    best_value = value
                    best_variant = variant

        return best_variant

    def _save_experiment(self, experiment: Experiment) -> None:
        """Save experiment to storage.

        Args:
            experiment: Experiment to save
        """
        experiment_file = self._storage_dir / f"{experiment.experiment_id}.json"

        data = {
            "experiment_id": experiment.experiment_id,
            "name": experiment.name,
            "description": experiment.description,
            "hypothesis": experiment.hypothesis,
            "variants": [
                {
                    "variant_id": v.variant_id,
                    "name": v.name,
                    "description": v.description,
                    "config": v.config,
                    "traffic_allocation": v.traffic_allocation,
                    "metrics": v.metrics,
                    "status": v.status.value,
                }
                for v in experiment.variants
            ],
            "primary_metric": experiment.primary_metric,
            "status": experiment.status.value,
            "created_at": experiment.created_at,
            "started_at": experiment.started_at,
            "ended_at": experiment.ended_at,
            "metadata": experiment.metadata,
        }

        with open(experiment_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_experiments(self) -> None:
        """Load experiments from storage."""
        if not self._storage_dir.exists():
            return

        for experiment_file in self._storage_dir.glob("*.json"):
            try:
                with open(experiment_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                variants = [
                    Variant(
                        variant_id=v["variant_id"],
                        name=v["name"],
                        description=v["description"],
                        config=v["config"],
                        traffic_allocation=v["traffic_allocation"],
                        metrics=v["metrics"],
                        status=VariantStatus(v["status"]),
                    )
                    for v in data["variants"]
                ]

                experiment = Experiment(
                    experiment_id=data["experiment_id"],
                    name=data["name"],
                    description=data["description"],
                    hypothesis=data["hypothesis"],
                    variants=variants,
                    primary_metric=data["primary_metric"],
                    status=ExperimentStatus(data["status"]),
                    created_at=data["created_at"],
                    started_at=data.get("started_at"),
                    ended_at=data.get("ended_at"),
                    metadata=data.get("metadata", {}),
                )

                self._experiments[experiment.experiment_id] = experiment

            except Exception:
                # Skip invalid experiment files
                continue
