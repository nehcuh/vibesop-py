"""Tests for vibesop.core.skills.skill_outcomes + `vibe skill outcomes` (gate39)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import vibesop.core.skills.skill_outcomes as outcomes_mod
from vibesop.cli.commands.skill_commands import app as skill_app
from vibesop.core.skills.skill_outcomes import count_skill_outcomes, outcomes_file_for

runner = CliRunner()

FORBIDDEN_KEY_FRAGMENTS = ("rate", "ratio", "percent", "pct", "grade")


def _span(
    span_id: str,
    skill_id: str,
    *,
    meta_as_string: bool = True,
    started_at: str = "2026-08-20T10:00:00+00:00",
) -> dict:
    meta = {"skill_id": skill_id, "has_match": True}
    return {
        "id": span_id,
        "span_kind": "task",
        "name": "route:demo",
        "metadata": json.dumps(meta) if meta_as_string else meta,
        "started_at": started_at,
    }


def _outcome(
    span_id: str,
    reason: str,
    *,
    side: str | None = "hit",
    span_ts: str | None = "2026-08-20T10:00:00+00:00",
    recorded_at: str | None = "2026-08-23T09:00:00+00:00",
) -> dict:
    row: dict = {"span_id": span_id, "outcome": "weak_negative", "reason": reason}
    if side is not None:
        row["side"] = side
        row["population"] = "hook"
    if span_ts is not None:
        row["span_ts"] = span_ts
    if recorded_at is not None:
        row["recorded_at"] = recorded_at
    return row


def _write_lines(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _write_spans(project_root: Path, spans: list[dict]) -> Path:
    """Under pytest, is_dev_environment() routes to spans.dev.jsonl."""
    return _write_lines(project_root / ".vibe" / "observability" / "spans.dev.jsonl", spans)


def _write_outcomes(project_root: Path, rows: list[dict]) -> Path:
    """The outcomes file has NO dev variant — always route_outcomes.jsonl."""
    return _write_lines(project_root / ".vibe" / "observability" / "route_outcomes.jsonl", rows)


def _assert_no_forbidden_keys(obj: object) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert not any(f in str(key).lower() for f in FORBIDDEN_KEY_FRAGMENTS), key
            _assert_no_forbidden_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_forbidden_keys(item)


def _total_hit_rows(result: dict) -> int:
    per_skill = sum(c["reask"] + c["moved_on"] + c["expired"] for c in result["skills"].values())
    return per_skill + result["unjoined"] + result["fallback"]


class TestOutcomesFileFor:
    def test_missing_file_returns_none_and_never_mkdirs(self, tmp_path: Path) -> None:
        assert outcomes_file_for(tmp_path) is None
        assert not (tmp_path / ".vibe").exists()

    def test_always_route_outcomes_jsonl(self, tmp_path: Path) -> None:
        path = _write_outcomes(tmp_path, [])
        assert outcomes_file_for(tmp_path) == path


class TestCountSkillOutcomes:
    def test_counts_split_by_reason_and_sorted(self, tmp_path: Path) -> None:
        _write_spans(
            tmp_path,
            [
                _span("s1", "b/skill"),
                _span("s2", "a/skill"),
                _span("s3", "a/skill", meta_as_string=False),  # dict metadata joins too
                _span("s4", "a/skill"),
            ],
        )
        _write_outcomes(
            tmp_path,
            [
                _outcome("s1", "hit_session_expired"),
                _outcome("s2", "hit_reask_same_task_id"),
                _outcome("s3", "hit_session_moved_on"),
                _outcome("s4", "hit_reask_same_task_id"),
            ],
        )
        result = count_skill_outcomes(tmp_path)
        assert result["unjoined"] == 0
        assert list(result["skills"]) == ["a/skill", "b/skill"]  # lexicographic, pinned
        assert result["skills"]["a/skill"] == {
            "reask": 2,
            "moved_on": 1,
            "expired": 0,
            "last_at": "2026-08-20T10:00:00+00:00",
        }
        assert result["skills"]["b/skill"]["expired"] == 1
        assert _total_hit_rows(result) == 4  # reconciliation invariant

    def test_mixed_unjoined_double_lock(self, tmp_path: Path) -> None:
        """Missing span AND empty-skill_id span both land in unjoined, and the
        table never gains an empty-id row (claude-MAJOR visibility lock)."""
        _write_spans(
            tmp_path,
            [
                _span("s1", "a/x"),
                _span("s2", ""),  # dirty hit: has_match=true, empty skill_id
            ],
        )
        _write_outcomes(
            tmp_path,
            [
                _outcome("s1", "hit_reask_same_task_id"),  # attributable
                _outcome("s2", "hit_reask_same_task_id"),  # empty skill_id → unjoined
                _outcome("s3", "hit_session_moved_on"),  # span missing → unjoined
            ],
        )
        result = count_skill_outcomes(tmp_path)
        assert result["unjoined"] == 2
        assert result["skills"]["a/x"]["reask"] == 1
        assert "" not in result["skills"]
        assert _total_hit_rows(result) == 3

    def test_fallback_sentinel_rows_bucketed_separately(self, tmp_path: Path) -> None:
        """gate40 项4: hit rows joined to a ``fallback-llm`` sentinel span
        (pre-gate40 活洞群 B; cmspark measured 1088/2440) go to the
        top-level ``fallback`` count — NOT unjoined, NOT the per-skill
        columns — and the reconciliation invariant still holds."""
        _write_spans(
            tmp_path,
            [
                _span("s1", "a/x"),
                _span("s2", "fallback-llm"),
                _span("s3", "fallback-llm", meta_as_string=False),  # dict form too
                _span("s4", ""),  # dirty hit → unjoined (gate39 behavior unchanged)
                _span("s5", "fallback-llm"),
            ],
        )
        _write_outcomes(
            tmp_path,
            [
                _outcome("s1", "hit_reask_same_task_id"),  # attributable
                _outcome("s2", "hit_session_expired"),  # sentinel → fallback
                _outcome("s3", "hit_session_moved_on"),  # sentinel → fallback
                _outcome("s4", "hit_reask_same_task_id"),  # empty skill_id → unjoined
                # sentinel + unknown reason → fallback (sentinel wins; the
                # row is attributable to the fallback bucket, not a skill).
                _outcome("s5", "hit_future_reason"),
            ],
        )
        result = count_skill_outcomes(tmp_path)
        assert result["fallback"] == 3
        assert result["unjoined"] == 1
        assert list(result["skills"]) == ["a/x"]
        assert result["skills"]["a/x"]["reask"] == 1
        assert "fallback-llm" not in result["skills"]
        assert _total_hit_rows(result) == 5  # reconciliation incl. fallback

    def test_miss_rows_not_counted(self, tmp_path: Path) -> None:
        _write_spans(tmp_path, [_span("s1", "a/x")])
        _write_outcomes(
            tmp_path,
            [
                _outcome("s1", "reask_same_task_id", side=None),  # miss rows have no side key
                _outcome("s1", "reask_same_task_id", side="miss"),
            ],
        )
        result = count_skill_outcomes(tmp_path)
        assert result == {"skills": {}, "unjoined": 0, "fallback": 0}

    def test_last_at_uses_span_ts_not_recorded_at(self, tmp_path: Path) -> None:
        """recorded_at is the backfill day for replayed rows — Last must come
        from span_ts (grok/claude-MAJOR), and keep the MAX span_ts."""
        _write_spans(tmp_path, [_span("s1", "a/x"), _span("s2", "a/x")])
        _write_outcomes(
            tmp_path,
            [
                _outcome(
                    "s2",
                    "hit_session_expired",
                    span_ts="2026-08-22T10:00:00+00:00",
                    recorded_at="2026-08-23T09:00:00+00:00",
                ),
                _outcome(
                    "s1",
                    "hit_reask_same_task_id",
                    span_ts="2026-08-10T10:00:00+00:00",
                    recorded_at="2026-08-23T09:00:00+00:00",
                ),
            ],
        )
        result = count_skill_outcomes(tmp_path)
        # Newer span_ts first in file order — last_at must still pick the max.
        assert result["skills"]["a/x"]["last_at"] == "2026-08-22T10:00:00+00:00"

    def test_row_without_span_ts_does_not_update_last_at(self, tmp_path: Path) -> None:
        _write_spans(tmp_path, [_span("s1", "a/x"), _span("s2", "a/x")])
        _write_outcomes(
            tmp_path,
            [
                _outcome("s1", "hit_reask_same_task_id", span_ts="2026-08-10T10:00:00+00:00"),
                _outcome("s2", "hit_session_expired", span_ts=None),
            ],
        )
        assert count_skill_outcomes(tmp_path)["skills"]["a/x"]["last_at"] == (
            "2026-08-10T10:00:00+00:00"
        )

    def test_unknown_reason_is_unjoined_not_dropped(self, tmp_path: Path) -> None:
        """Defensive: an unrecognised reason must keep the reconciliation
        invariant instead of silently shrinking the table."""
        _write_spans(tmp_path, [_span("s1", "a/x")])
        _write_outcomes(tmp_path, [_outcome("s1", "hit_future_reason")])
        result = count_skill_outcomes(tmp_path)
        assert result == {"skills": {}, "unjoined": 1, "fallback": 0}
        assert _total_hit_rows(result) == 1

    def test_no_rates_or_grades_anywhere(self, tmp_path: Path) -> None:
        _write_spans(tmp_path, [_span("s1", "a/x")])
        _write_outcomes(tmp_path, [_outcome("s1", "hit_reask_same_task_id")])
        result = count_skill_outcomes(tmp_path)
        _assert_no_forbidden_keys(result)
        json.dumps(result)  # must stay JSON-serialisable (raw counts only)
        for counts in result["skills"].values():
            assert isinstance(counts["reask"], int)
            assert isinstance(counts["moved_on"], int)
            assert isinstance(counts["expired"], int)

    def test_missing_files_are_empty_not_error(self, tmp_path: Path) -> None:
        assert count_skill_outcomes(tmp_path) == {"skills": {}, "unjoined": 0, "fallback": 0}
        assert not (tmp_path / ".vibe").exists()

    def test_missing_spans_file_makes_every_hit_row_unjoined(self, tmp_path: Path) -> None:
        _write_outcomes(
            tmp_path,
            [_outcome("s1", "hit_reask_same_task_id"), _outcome("s2", "hit_session_expired")],
        )
        result = count_skill_outcomes(tmp_path)
        assert result == {"skills": {}, "unjoined": 2, "fallback": 0}

    def test_missing_outcomes_file_with_spans_is_empty(self, tmp_path: Path) -> None:
        _write_spans(tmp_path, [_span("s1", "a/x")])
        assert count_skill_outcomes(tmp_path) == {"skills": {}, "unjoined": 0, "fallback": 0}

    def test_bad_lines_and_bad_metadata_skipped(self, tmp_path: Path) -> None:
        spans_path = tmp_path / ".vibe" / "observability" / "spans.dev.jsonl"
        spans_path.parent.mkdir(parents=True, exist_ok=True)
        spans_path.write_text(
            "not json\n"
            + json.dumps(
                {"id": "s2", "span_kind": "task", "name": "route:x", "metadata": "{broken"}
            )
            + "\n"
            + json.dumps(_span("s1", "a/x"))
            + "\n",
            encoding="utf-8",
        )
        outcomes_path = tmp_path / ".vibe" / "observability" / "route_outcomes.jsonl"
        outcomes_path.write_text(
            "not json either\n"
            + json.dumps(_outcome("s1", "hit_reask_same_task_id"))
            + "\n"
            + json.dumps(_outcome("s2", "hit_session_expired"))  # bad metadata → unjoined
            + "\n",
            encoding="utf-8",
        )
        result = count_skill_outcomes(tmp_path)
        assert result["skills"]["a/x"]["reask"] == 1
        assert result["unjoined"] == 1

    def test_dev_mode_combination_pinned(self, tmp_path: Path) -> None:
        """Under pytest (dev) the spans side reads spans.dev.jsonl while the
        outcomes side ALWAYS reads route_outcomes.jsonl (gate39 §4.7 known
        asymmetry). A prod-named spans.jsonl must be ignored here."""
        _write_lines(
            tmp_path / ".vibe" / "observability" / "spans.jsonl", [_span("s1", "prod/skill")]
        )
        _write_spans(tmp_path, [_span("s2", "dev/skill")])
        _write_outcomes(
            tmp_path,
            [
                _outcome("s1", "hit_reask_same_task_id"),  # prod span → unjoined under pytest
                _outcome("s2", "hit_reask_same_task_id"),
            ],
        )
        result = count_skill_outcomes(tmp_path)
        assert list(result["skills"]) == ["dev/skill"]
        assert result["unjoined"] == 1


@pytest.fixture
def patched_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Wide terminal so rich doesn't wrap footnote lines mid-phrase.
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setattr(
        outcomes_mod,
        "count_skill_outcomes",
        lambda root: {
            "skills": {
                "b/skill": {"reask": 0, "moved_on": 0, "expired": 1, "last_at": None},
                "a/skill": {
                    "reask": 2,
                    "moved_on": 1,
                    "expired": 5,
                    "last_at": "2026-08-20T10:00:00+00:00",
                },
            },
            "unjoined": 3,
            "fallback": 2,
        },
    )


class TestOutcomesCommand:
    def test_table_renders_columns_rows_and_unjoined(self, patched_outcomes: None) -> None:
        result = runner.invoke(skill_app, ["outcomes"])
        assert result.exit_code == 0
        out = result.output
        for header in ("Skill", "Reask", "Moved-on", "Expired", "Last"):
            assert header in out
        # Lexicographic order pinned (never a count-sorted leaderboard).
        assert out.index("a/skill") < out.index("b/skill")
        assert "2026-08-20T10:00:00+00:00" in out
        assert "(unjoined: 3)" in out  # join failure stays visible (末行)
        assert "(fallback: 2)" in out  # sentinel bucket stays visible too

    def test_json_is_raw_counts_only(self, patched_outcomes: None) -> None:
        result = runner.invoke(skill_app, ["outcomes", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert set(payload) == {"skills", "unjoined", "fallback"}
        assert payload["unjoined"] == 3
        assert payload["fallback"] == 2
        assert payload["skills"]["a/skill"]["reask"] == 2
        _assert_no_forbidden_keys(payload)
        for counts in payload["skills"].values():
            assert set(counts) == {"reask", "moved_on", "expired", "last_at"}

    def test_footnotes_disclose_caveats(self, patched_outcomes: None) -> None:
        out = runner.invoke(skill_app, ["outcomes"]).output
        assert "禁止拼比率" in out  # 口径差异（路径+时间窗）
        assert "证据为任意非 CLI（hook/user-turn）路径的后续路由" in out
        assert "1268/2437" in out  # expired 回灌占主导实测
        assert "下界计数" in out
        assert "跨技能不可比" in out
        assert "n<30" in out
        assert "放弃" in out
        assert "37/2437" in out  # 空 skill_id 脏 hit 实测
        assert "unjoined 计数见末行" in out
        assert "fallback-llm=未命中兜底路由" in out  # gate40 项4 sentinel 脚注
        assert "发现队列" in out

    def test_no_rate_or_grade_tokens_in_output(self, patched_outcomes: None) -> None:
        out = runner.invoke(skill_app, ["outcomes"]).output
        assert "%" not in out
        assert "rate" not in out.lower()
        assert "grade" not in out.lower()
