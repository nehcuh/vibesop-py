"""P1: single-route telemetry — opt-in analytics write point + always-on miss counter.

Covers the ``route()`` exit point in ``UnifiedRouter``:
- opt-in on: hit, no-match, and fallback-llm all persist ``mode="single"`` records
- opt-in off: nothing is written
- orchestrate() path: the single-route write points do NOT fire (no double write;
  the orchestration path is recorded by ``_record_execution`` at orchestrator level)
- always-on miss counter: fires only on no-match/fallback, never on a real hit
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from vibesop.core.config import RoutingConfig
from vibesop.core.models import RoutingResult
from vibesop.core.routing.unified import UnifiedRouter

if TYPE_CHECKING:
    import pytest

_CANDIDATES = [{"id": "test-skill", "description": "Test skill", "namespace": "project"}]
_NO_MATCH_QUERY = "xyzqwerty_no_match_12345"


def _analytics_file(root: Path) -> Path:
    return root / ".vibe" / "analytics.jsonl"


def _miss_file(root: Path) -> Path:
    return root / ".vibe" / "miss_counter.json"


def _read_records(root: Path) -> list[dict[str, object]]:
    path = _analytics_file(root)
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _no_match_config(fallback_mode: str = "disabled") -> RoutingConfig:
    return RoutingConfig(fallback_mode=fallback_mode, min_confidence=0.99, enable_ai_triage=False)


def test_hit_records_mode_single_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIBE_ANALYTICS_ENABLED", "true")
    router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=False))

    result = router.route("/test-skill", candidates=_CANDIDATES)

    assert result.has_match
    records = _read_records(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record["mode"] == "single"
    assert record["primary_skill"] == "test-skill"
    assert record["plan_steps"] == []
    assert record["step_count"] == 0
    assert "explicit" in record["routing_layers"]


def test_no_match_records_mode_single_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIBE_ANALYTICS_ENABLED", "true")
    router = UnifiedRouter(project_root=tmp_path, config=_no_match_config())

    result = router.route(_NO_MATCH_QUERY)

    assert not result.has_match
    assert result.primary is None
    records = _read_records(tmp_path)
    assert len(records) == 1
    assert records[0]["mode"] == "single"
    assert records[0]["primary_skill"] is None


def test_fallback_llm_records_mode_single_when_opted_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIBE_ANALYTICS_ENABLED", "true")
    router = UnifiedRouter(
        project_root=tmp_path, config=_no_match_config(fallback_mode="transparent")
    )

    result = router.route(_NO_MATCH_QUERY)

    assert not result.has_match
    records = _read_records(tmp_path)
    assert len(records) == 1
    assert records[0]["mode"] == "single"
    assert records[0]["primary_skill"] == "fallback-llm"


def test_nothing_written_when_opted_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBE_ANALYTICS_ENABLED", raising=False)
    router = UnifiedRouter(project_root=tmp_path, config=_no_match_config())

    router.route("/test-skill", candidates=_CANDIDATES)  # hit
    router.route(_NO_MATCH_QUERY)  # miss

    assert not _analytics_file(tmp_path).exists()


def test_orchestrate_path_does_not_double_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """orchestrate() calls _single_skill_route internally but must not trigger the
    single-route write point — orchestration analytics belong to _record_execution."""
    monkeypatch.setenv("VIBE_ANALYTICS_ENABLED", "true")
    router = UnifiedRouter(project_root=tmp_path, config=_no_match_config())

    calls: list[str] = []
    original = UnifiedRouter._record_single_route_execution

    def spy(self: UnifiedRouter, query: str, result: RoutingResult) -> None:
        calls.append(query)
        original(self, query, result)

    monkeypatch.setattr(UnifiedRouter, "_record_single_route_execution", spy)

    router.orchestrate(_NO_MATCH_QUERY)

    assert calls == []
    assert not _analytics_file(tmp_path).exists()
    assert not _miss_file(tmp_path).exists()


def test_miss_counter_fires_on_no_match(tmp_path: Path) -> None:
    router = UnifiedRouter(project_root=tmp_path, config=_no_match_config())

    router.route("unmatched alpha beta")
    router.route("  UNMATCHED   alpha  beta ")  # same after normalization

    content = _miss_file(tmp_path).read_text(encoding="utf-8")
    data = json.loads(content)
    assert len(data) == 1
    assert next(iter(data.values()))["n"] == 2
    assert "unmatched" not in content  # hash-only, no raw query


def test_miss_counter_fires_on_fallback_llm(tmp_path: Path) -> None:
    router = UnifiedRouter(
        project_root=tmp_path, config=_no_match_config(fallback_mode="transparent")
    )

    result = router.route(_NO_MATCH_QUERY)

    assert result.primary is not None and result.primary.skill_id == "fallback-llm"
    data = json.loads(_miss_file(tmp_path).read_text(encoding="utf-8"))
    assert next(iter(data.values()))["n"] == 1


def test_miss_counter_not_fired_on_hit(tmp_path: Path) -> None:
    router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=False))

    result = router.route("/test-skill", candidates=_CANDIDATES)

    assert result.has_match
    assert not _miss_file(tmp_path).exists()
