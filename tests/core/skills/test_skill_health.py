"""Tests for vibesop.core.skills.skill_health (gate37 L2-lite read model)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vibesop.core.skills.skill_health import (
    count_skill_feedback,
    count_skill_fires,
    spans_file_for,
)

NOW = datetime(2026, 8, 23, tzinfo=UTC)


def _span(
    skill_id: str = "demo/skill",
    *,
    has_match: bool | None = True,
    kind: str = "task",
    name: str = "route:demo",
    age_days: float = 1,
    meta_as_string: bool = True,
) -> dict:
    meta: dict = {"skill_id": skill_id}
    if has_match is not None:
        meta["has_match"] = has_match
    return {
        "span_kind": kind,
        "name": name,
        "metadata": json.dumps(meta) if meta_as_string else meta,
        "started_at": (NOW - timedelta(days=age_days)).isoformat(),
    }


def _write_spans(project_root: Path, spans: list[dict]) -> Path:
    """Under pytest, is_dev_environment() routes to spans.dev.jsonl."""
    path = project_root / ".vibe" / "observability" / "spans.dev.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in spans) + "\n",
        encoding="utf-8",
    )
    return path


class TestSpansFileFor:
    def test_missing_file_returns_none_and_never_mkdirs(self, tmp_path: Path) -> None:
        assert spans_file_for(tmp_path) is None
        assert not (tmp_path / ".vibe").exists()

    def test_selects_dev_file_under_pytest(self, tmp_path: Path) -> None:
        path = _write_spans(tmp_path, [])
        assert spans_file_for(tmp_path) == path


class TestCountSkillFires:
    def test_counts_route_hits_per_skill(self, tmp_path: Path) -> None:
        _write_spans(
            tmp_path,
            [
                _span("a/x"),
                _span("a/x"),
                _span("b/y", meta_as_string=False),  # dict metadata also counts
            ],
        )
        assert count_skill_fires(tmp_path, now=NOW) == {"a/x": 2, "b/y": 1}

    def test_misses_and_unknowns_are_not_fires(self, tmp_path: Path) -> None:
        _write_spans(
            tmp_path,
            [
                _span(has_match=False),  # explicit miss
                _span(has_match=None),  # unknown (missing key)
                _span(kind="llm"),  # not a task span
                _span(name="tool:call"),  # not a route span
            ],
        )
        assert count_skill_fires(tmp_path, now=NOW) == {}

    def test_old_spans_outside_window_not_counted(self, tmp_path: Path) -> None:
        _write_spans(tmp_path, [_span(age_days=31), _span(age_days=29)])
        assert count_skill_fires(tmp_path, now=NOW) == {"demo/skill": 1}

    def test_bad_lines_and_bad_metadata_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / ".vibe" / "observability" / "spans.dev.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "not json\n"
            + json.dumps({"span_kind": "task", "name": "route:x", "metadata": "{broken"})
            + "\n"
            + json.dumps(_span("ok/skill"))
            + "\n",
            encoding="utf-8",
        )
        assert count_skill_fires(tmp_path, now=NOW) == {"ok/skill": 1}

    def test_missing_file_is_empty_not_error(self, tmp_path: Path) -> None:
        assert count_skill_fires(tmp_path, now=NOW) == {}
        assert not (tmp_path / ".vibe").exists()

    def test_hit_without_skill_id_not_attributed(self, tmp_path: Path) -> None:
        _write_spans(tmp_path, [_span(skill_id="")])
        assert count_skill_fires(tmp_path, now=NOW) == {}

    def test_fallback_sentinel_is_not_a_fire(self, tmp_path: Path) -> None:
        """gate40 项4: pre-gate40 producers wrote the ``fallback-llm``
        sentinel into hit spans (活洞群 B; cmspark measured it as the
        largest 30d fire bucket, 1061/2822). A fallback is a routing
        miss, not a skill — excluded from the fire column."""
        _write_spans(
            tmp_path,
            [
                _span(skill_id="fallback-llm"),
                _span(skill_id="fallback-llm", meta_as_string=False),  # dict form too
                _span(skill_id="demo/skill"),
            ],
        )
        assert count_skill_fires(tmp_path, now=NOW) == {"demo/skill": 1}


class TestRouteHitSkillIdRaw:
    """gate40 项4: the raw extraction keeps the sentinel/empty string so
    bucketing layers (skill_outcomes) can tell them apart; the fire
    predicate excludes both."""

    def test_raw_extraction_vs_fire_predicate(self, tmp_path: Path) -> None:
        from vibesop.core.skills.skill_health import (
            _route_hit_skill_id,
            _route_hit_skill_id_raw,
        )

        sentinel = _span(skill_id="fallback-llm")
        assert _route_hit_skill_id_raw(sentinel) == "fallback-llm"
        assert _route_hit_skill_id(sentinel) is None

        empty = _span(skill_id="")
        assert _route_hit_skill_id_raw(empty) == ""
        assert _route_hit_skill_id(empty) is None

        real = _span(skill_id="demo/skill")
        assert _route_hit_skill_id_raw(real) == "demo/skill"
        assert _route_hit_skill_id(real) == "demo/skill"

        miss = _span(skill_id="demo/skill", has_match=False)
        assert _route_hit_skill_id_raw(miss) is None
        assert _route_hit_skill_id(miss) is None


class TestParseSpanTime:
    """Timezone handling of the 30-day window (pi NIT)."""

    def _count_with_started_at(self, tmp_path: Path, started_at: str) -> dict[str, int]:
        span = _span("demo/skill")
        span["started_at"] = started_at
        _write_spans(tmp_path, [span])
        return count_skill_fires(tmp_path, now=NOW)

    def test_naive_timestamp_assumed_utc(self, tmp_path: Path) -> None:
        naive = (NOW - timedelta(days=1)).replace(tzinfo=None).isoformat()
        assert self._count_with_started_at(tmp_path, naive) == {"demo/skill": 1}

    def test_z_suffix_parsed(self, tmp_path: Path) -> None:
        zulu = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        assert self._count_with_started_at(tmp_path, zulu) == {"demo/skill": 1}

    def test_offset_timestamp_compared_correctly(self, tmp_path: Path) -> None:
        # Wall-clock 29d20h before NOW labelled +08:00 is really 30d4h old
        # in UTC — OUTSIDE the 30-day window only if the offset is honoured
        # (naive-as-UTC misreading would count it).
        outside = (NOW - timedelta(days=29, hours=20)).isoformat().replace("+00:00", "+08:00")
        assert self._count_with_started_at(tmp_path, outside) == {}
        # Wall-clock 30d4h before NOW labelled -08:00 is really 29d20h old
        # in UTC — INSIDE only if the offset is honoured.
        inside = (NOW - timedelta(days=30, hours=4)).isoformat().replace("+00:00", "-08:00")
        assert self._count_with_started_at(tmp_path, inside) == {"demo/skill": 1}

    def test_future_timestamp_counts_within_window(self, tmp_path: Path) -> None:
        future = (NOW + timedelta(hours=1)).isoformat()
        assert self._count_with_started_at(tmp_path, future) == {"demo/skill": 1}


class TestCountSkillFeedback:
    def _write_feedback(self, project_root: Path, records: list[dict]) -> None:
        vibe = project_root / ".vibe"
        vibe.mkdir(parents=True, exist_ok=True)
        (vibe / "execution_feedback.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
            encoding="utf-8",
        )

    def test_raw_yes_no_counts(self, tmp_path: Path) -> None:
        self._write_feedback(
            tmp_path,
            [
                {"skill_id": "a/x", "query": "q", "was_helpful": True},
                {"skill_id": "a/x", "query": "q", "was_helpful": True},
                {"skill_id": "a/x", "query": "q", "was_helpful": False},  # incl. partial
                {"skill_id": "b/y", "query": "q", "was_helpful": None},  # no vote — uncounted
            ],
        )
        assert count_skill_feedback(tmp_path) == {"a/x": (2, 1)}

    def test_missing_store_is_empty(self, tmp_path: Path) -> None:
        assert count_skill_feedback(tmp_path) == {}
