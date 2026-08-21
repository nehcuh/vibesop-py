"""W5.2 Task 1.1 — ClusterCandidate.project_distribution field + property.

Verifies the dataclass carries cross-project signal forward from W5.1's
``Cluster.project_distribution``. Consumers (candidates list, promote
guard, SKILL.md renderer) branch on ``is_cross_project`` without
re-reading spans.

Backwards compat: pre-W5.2 records stored on disk lack the field.
``from_dict`` must tolerate its absence (G-2 regression from grok review).
"""

from __future__ import annotations

from datetime import UTC, datetime

from vibesop.core.observability.skill_promote import ClusterCandidate


def _make(
    *,
    cluster_id: str = "c1",
    project_distribution: dict[str, int] | None = None,
) -> ClusterCandidate:
    return ClusterCandidate(
        cluster_id=cluster_id,
        task_ids=["t1"],
        queries=["q1"],
        span_count=3,
        gold_rate=0.8,
        gold_task_ids=["t1"],
        created_at=datetime(2026, 7, 30, tzinfo=UTC),
        project_distribution=project_distribution or {},
    )


class TestProjectDistributionField:
    def test_candidate_has_project_distribution_field(self) -> None:
        """Field exists with default empty dict."""
        c = _make()
        assert hasattr(c, "project_distribution")
        assert c.project_distribution == {}

    def test_candidate_project_distribution_preserves_values(self) -> None:
        """Non-default values round-trip through the dataclass."""
        c = _make(project_distribution={"/users/me/proj-a": 7, "/users/me/proj-b": 3})
        assert c.project_distribution == {"/users/me/proj-a": 7, "/users/me/proj-b": 3}


class TestIsCrossProjectProperty:
    def test_candidate_is_cross_project_true_when_heterogeneous(self) -> None:
        """Property returns True when distribution has >1 project."""
        c = _make(project_distribution={"/users/me/a": 1, "/users/me/b": 2})
        assert c.is_cross_project is True

    def test_candidate_is_cross_project_false_when_single_project(self) -> None:
        """Property returns False when distribution has exactly 1 project."""
        c = _make(project_distribution={"/users/me/a": 5})
        assert c.is_cross_project is False

    def test_candidate_is_cross_project_false_when_empty(self) -> None:
        """Property returns False when distribution is empty (pre-W5.2 record)."""
        c = _make(project_distribution={})
        assert c.is_cross_project is False


class TestRoundTrip:
    def test_candidate_round_trip_preserves_project_distribution(self) -> None:
        """to_dict → from_dict preserves project_distribution exactly."""
        c = _make(project_distribution={"/users/me/a": 4, "/users/me/b": 2})
        round_tripped = ClusterCandidate.from_dict(c.to_dict())
        assert round_tripped.project_distribution == c.project_distribution
        assert round_tripped.is_cross_project is True


class TestBackwardsCompat:
    def test_candidate_from_dict_tolerates_missing_field(self) -> None:
        """Pre-W5.2 records on disk lack project_distribution.

        ``from_dict`` must not raise; default factory kicks in.
        Regression for G-2 from grok review.
        """
        legacy_payload = {
            "cluster_id": "legacy-1",
            "task_ids": ["t1"],
            "queries": ["legacy query"],
            "span_count": 5,
            "gold_rate": 0.7,
            "gold_task_ids": ["t1"],
            "created_at": "2026-06-01T00:00:00+00:00",
            "ttl_expires_at": "2026-07-01T00:00:00+00:00",
            "step_freq": {},
            "step_labels": {},
            "core_steps": [],
            "status": "pending",
            "is_unstable": False,
            "reviewed_at": None,
            "source_skill_id": None,
            "dismiss_reason": None,
            # NOTE: no project_distribution key — simulates pre-W5.2 row
        }
        c = ClusterCandidate.from_dict(legacy_payload)
        assert c.project_distribution == {}
        assert c.is_cross_project is False


class TestFirstSeenAtField:
    """M12 NIT-B — ClusterCandidate.first_seen_at (模式首见时间)."""

    def test_round_trip_preserves_first_seen_at(self) -> None:
        first_seen = datetime(2026, 6, 15, 8, 30, tzinfo=UTC)
        c = _make()
        c.first_seen_at = first_seen
        round_tripped = ClusterCandidate.from_dict(c.to_dict())
        assert round_tripped.first_seen_at == first_seen

    def test_from_dict_tolerates_missing_first_seen_at(self) -> None:
        """Pre-NIT-B rows on disk lack the key → None → display falls back
        to created_at semantics."""
        legacy_payload = {
            "cluster_id": "legacy-2",
            "task_ids": ["t1"],
            "queries": ["legacy query"],
            "span_count": 5,
            "gold_rate": 0.7,
            "gold_task_ids": ["t1"],
            "created_at": "2026-06-01T00:00:00+00:00",
            "ttl_expires_at": "2026-07-01T00:00:00+00:00",
            "step_freq": {},
            "step_labels": {},
            "core_steps": [],
            "status": "pending",
            "is_unstable": False,
            "reviewed_at": None,
            "source_skill_id": None,
            "dismiss_reason": None,
            # NOTE: no first_seen_at key — simulates pre-NIT-B row
        }
        c = ClusterCandidate.from_dict(legacy_payload)
        assert c.first_seen_at is None

    def test_from_dict_parses_naive_first_seen_at_as_utc(self) -> None:
        c = _make()
        c.first_seen_at = datetime(2026, 6, 15, 8, 30, tzinfo=UTC)
        payload = c.to_dict()
        payload["first_seen_at"] = "2026-06-15T08:30:00"  # hand-edited, no offset
        parsed = ClusterCandidate.from_dict(payload)
        assert parsed.first_seen_at == datetime(2026, 6, 15, 8, 30, tzinfo=UTC)
