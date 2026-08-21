"""M12 M2 — vibe skill discover CLI tests (unified Discovery queue).

Covers: 列表排序 / dismiss 粘性 / mute 恢复 / 冷却降档 / history 指标 +
闭环检查 / 空队列引导。Synthetic fixtures only (no eval-set data).
Storage helpers are patched to tmp_path (same pattern as
test_skill_promote_cli.py).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import skill_commands
from vibesop.cli.main import app
from vibesop.core.observability.discovery import (
    DISMISS_TIGHTEN_THRESHOLD,
    DiscoveryObservationStore,
    DiscoverySignalStore,
    cluster_fingerprint,
)
from vibesop.core.observability.skill_promote import ClusterCandidate, ClusterCandidateStore

T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner(env={"COLUMNS": "200"})


def _candidate(
    cluster_id: str,
    queries: list[str],
    span_count: int = 5,
    gold_rate: float = 0.8,
    source: str = "gold",
    project_distribution: dict[str, int] | None = None,
) -> ClusterCandidate:
    return ClusterCandidate(
        cluster_id=cluster_id,
        task_ids=[f"{cluster_id[:4]}-t{i}" for i in range(3)],
        queries=queries,
        span_count=span_count,
        gold_rate=gold_rate,
        gold_task_ids=[],
        source=source,  # type: ignore[arg-type]
        project_distribution=project_distribution or {},
    )


@pytest.fixture
def discovery_env(tmp_path: Path):
    """Per-scope candidate stores + discovery dirs rooted at tmp_path."""
    stores = {
        "project": ClusterCandidateStore(storage_dir=tmp_path / "proj"),
        "global": ClusterCandidateStore(storage_dir=tmp_path / "glob"),
    }
    dirs = {"project": tmp_path / "proj", "global": tmp_path / "glob"}
    with (
        patch.object(
            skill_commands,
            "_get_candidate_store",
            side_effect=lambda scope="project": stores[scope],
        ),
        patch.object(
            skill_commands,
            "_get_discovery_dir",
            side_effect=lambda scope="project": dirs[scope],
        ),
    ):
        yield stores, dirs


class TestList:
    def test_empty_queue_shows_guidance(self, cli_runner: CliRunner, discovery_env) -> None:
        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "暂无候选" in result.output
        assert "scan-candidates" in result.output

    def test_sorted_by_evidence_score(self, cli_runner: CliRunner, discovery_env) -> None:
        stores, _ = discovery_env
        low = _candidate("l" * 40, ["low evidence query"], span_count=3, gold_rate=0.6)
        high = _candidate("h" * 40, ["high evidence query"], span_count=12, gold_rate=0.95)
        stores["project"].upsert(low)
        stores["project"].upsert(high)
        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert result.output.index("high evidence query") < result.output.index(
            "low evidence query"
        )

    def test_shows_all_sources_and_markers(self, cli_runner: CliRunner, discovery_env) -> None:
        stores, _ = discovery_env
        stores["project"].upsert(_candidate("g" * 40, ["gold cluster query"], gold_rate=0.8))
        stores["global"].upsert(
            _candidate(
                "m" * 40,
                ["miss cluster query"],
                gold_rate=0.0,
                source="miss_recurrence",
                project_distribution={"/p/a": 2, "/p/b": 2},
            )
        )
        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "miss" in result.output  # miss×复现 source marker
        assert "[XP]" in result.output
        assert "未采集" in result.output  # behavior evidence not collected yet (M3)

    def test_cooling_annotation(self, cli_runner: CliRunner, discovery_env) -> None:
        stores, dirs = discovery_env
        candidate = _candidate("c" * 40, ["cooling cluster query"])
        stores["project"].upsert(candidate)
        # Backdate the growth observation beyond the 14-day cooling window.
        observations = DiscoveryObservationStore(dirs["project"])
        fingerprint = cluster_fingerprint(candidate.queries)
        old = (datetime.now(UTC) - timedelta(days=20)).isoformat()
        observations._save(  # pyright: ignore[reportPrivateUsage]
            {fingerprint: {"span_count": 5, "first_seen_at": old, "last_growth_at": old}}
        )
        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "冷却中" in result.output


class TestDismiss:
    def test_dismiss_hides_by_default_visible_with_all(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, _ = discovery_env
        candidate = _candidate("d" * 40, ["dismiss me query"])
        stores["project"].upsert(candidate)

        result = cli_runner.invoke(
            app, ["skill", "discover", "dismiss", candidate.cluster_id, "--reason", "noise"]
        )
        assert result.exit_code == 0
        assert "Dismissed" in result.output

        hidden = cli_runner.invoke(app, ["skill", "discover"])
        assert "dismiss me query" not in hidden.output

        shown = cli_runner.invoke(app, ["skill", "discover", "--all"])
        assert "dismiss me query" in shown.output
        assert "dismissed" in shown.output

    def test_dismiss_accepts_id_prefix(self, cli_runner: CliRunner, discovery_env) -> None:
        stores, _ = discovery_env
        candidate = _candidate("e" * 40, ["prefix dismiss query"])
        stores["project"].upsert(candidate)
        result = cli_runner.invoke(app, ["skill", "discover", "dismiss", candidate.cluster_id[:8]])
        assert result.exit_code == 0
        assert "Dismissed" in result.output

    def test_dismiss_unknown_id_fails(self, cli_runner: CliRunner, discovery_env) -> None:
        result = cli_runner.invoke(app, ["skill", "discover", "dismiss", "f" * 40])
        assert result.exit_code == 1

    def test_dismiss_does_not_flip_candidate_status(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        """Negative-list dismiss leaves the candidate row pending (—all 可见)."""
        stores, _ = discovery_env
        candidate = _candidate("d" * 40, ["status stays pending query"])
        stores["project"].upsert(candidate)
        cli_runner.invoke(app, ["skill", "discover", "dismiss", candidate.cluster_id])
        assert stores["project"].get(candidate.cluster_id).status == "pending"  # type: ignore[union-attr]

    def test_threshold_suggestion_after_five_dismissals(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, _ = discovery_env
        for i in range(DISMISS_TIGHTEN_THRESHOLD):
            candidate = _candidate(f"{i}" + "0" * 39, [f"unique dismiss query number {i}"])
            stores["project"].upsert(candidate)
            result = cli_runner.invoke(app, ["skill", "discover", "dismiss", candidate.cluster_id])
            assert result.exit_code == 0
        assert "建议上调" in result.output  # only on the 5th dismissal


class TestMute:
    def test_mute_hides_until_expiry_then_restores(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, dirs = discovery_env
        candidate = _candidate("a" * 40, ["mutable cluster query"])
        stores["project"].upsert(candidate)

        result = cli_runner.invoke(app, ["skill", "discover", "--mute", candidate.cluster_id])
        assert result.exit_code == 0
        assert "Muted" in result.output
        assert "到期自动恢复" in result.output

        hidden = cli_runner.invoke(app, ["skill", "discover"])
        assert "mutable cluster query" not in hidden.output

        # Mute is NOT a dismissal.
        signals = DiscoverySignalStore(dirs["project"])
        assert signals.dismiss_count() == 0

        # Expire the mute in place → candidate auto-restores to the list.
        fingerprint = cluster_fingerprint(candidate.queries)
        path = dirs["project"] / DiscoverySignalStore.FILENAME
        expired = {
            "kind": "mute",
            "fingerprint": fingerprint,
            "cluster_id": candidate.cluster_id,
            "reason": None,
            "created_at": (datetime.now(UTC) - timedelta(days=20)).isoformat(),
            "expires_at": (datetime.now(UTC) - timedelta(days=6)).isoformat(),
        }
        path.write_text(json.dumps(expired) + "\n", encoding="utf-8")
        restored = cli_runner.invoke(app, ["skill", "discover"])
        assert "mutable cluster query" in restored.output

    def test_mute_visible_with_all(self, cli_runner: CliRunner, discovery_env) -> None:
        stores, _ = discovery_env
        candidate = _candidate("b" * 40, ["mute all query"])
        stores["project"].upsert(candidate)
        cli_runner.invoke(app, ["skill", "discover", "--mute", candidate.cluster_id])
        shown = cli_runner.invoke(app, ["skill", "discover", "--all"])
        assert "mute all query" in shown.output
        assert "muted" in shown.output


class TestHistory:
    def test_history_metrics_and_closed_loop(
        self, cli_runner: CliRunner, discovery_env, tmp_path: Path, monkeypatch
    ) -> None:
        stores, _ = discovery_env
        promoted = _candidate("1" * 40, ["promoted cluster query"])
        dismissed = _candidate("2" * 40, ["dismissed cluster query"])
        stores["project"].upsert(promoted)
        stores["project"].upsert(dismissed)
        stores["project"].promote(promoted.cluster_id, "custom/promoted-skill")
        # dismiss via the discover negative list
        cli_runner.invoke(app, ["skill", "discover", "dismiss", dismissed.cluster_id])

        # analytics.jsonl with 5 route hits for the promoted skill
        vibe_dir = tmp_path / ".vibe"
        vibe_dir.mkdir(exist_ok=True)
        (vibe_dir / "analytics.jsonl").write_text(
            "".join(
                json.dumps({"query": "q", "primary_skill": "custom/promoted-skill"}) + "\n"
                for _ in range(5)
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(app, ["skill", "discover", "--history"])
        assert result.exit_code == 0
        assert "5 次命中" in result.output
        assert "50%" in result.output  # 1 promoted / (1 promoted + 1 dismissed)

    def test_history_marks_missing_data_source(
        self, cli_runner: CliRunner, discovery_env, tmp_path: Path, monkeypatch
    ) -> None:
        stores, _ = discovery_env
        promoted = _candidate("3" * 40, ["no analytics query"])
        stores["project"].upsert(promoted)
        stores["project"].promote(promoted.cluster_id, "custom/no-analytics")
        monkeypatch.chdir(tmp_path)  # no .vibe/analytics.jsonl here

        result = cli_runner.invoke(app, ["skill", "discover", "--history"])
        assert result.exit_code == 0
        assert "暂无数据源" in result.output

    def test_history_empty(self, cli_runner: CliRunner, discovery_env) -> None:
        result = cli_runner.invoke(app, ["skill", "discover", "--history"])
        assert result.exit_code == 0
        assert "暂无闭环记录" in result.output


class TestScanCandidatesRendering:
    """gate17 pi BLOCK-1/BLOCK-2 + claude nit 3: scan-candidates output."""

    def _invoke(self, cli_runner: CliRunner, discovery_env, summary, extra_args=None):
        from unittest.mock import MagicMock

        from vibesop.core.observability import skill_promote

        stores, _ = discovery_env
        mock_writer = MagicMock()
        mock_writer.query_recent.return_value = []
        captured: dict = {}

        def fake_scan(spans, learner, store, **kwargs):
            captured.update(kwargs)
            return summary

        with (
            patch.object(
                skill_commands,
                "_get_candidate_store",
                side_effect=lambda scope="project": stores[scope],
            ),
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=MagicMock()),
            patch(
                "vibesop.core.observability.embedding.get_embedding_cache",
                return_value=MagicMock(),
            ),
            patch.object(skill_promote, "scan_candidates", side_effect=fake_scan),
        ):
            return cli_runner.invoke(
                app, ["skill", "scan-candidates", *(extra_args or [])]
            ), captured

    def test_embedding_degraded_warning_rendered(self, cli_runner, discovery_env) -> None:
        from vibesop.core.observability.skill_promote import ScanSummary

        result, _ = self._invoke(
            cli_runner,
            discovery_env,
            ScanSummary(miss_pool_size=7, miss_admitted_count=2, embedding_degraded=True),
        )
        assert result.exit_code == 0
        assert "embedding 不可用" in result.output
        assert "task_id 硬分组" in result.output

    def test_miss_metrics_rendered(self, cli_runner, discovery_env) -> None:
        from vibesop.core.observability.skill_promote import ScanSummary

        result, _ = self._invoke(
            cli_runner, discovery_env, ScanSummary(miss_pool_size=7, miss_admitted_count=2)
        )
        assert result.exit_code == 0
        assert "miss pool: 7 span(s)" in result.output
        assert "2 miss_recurrence candidate(s) admitted" in result.output

    def test_no_degraded_warning_when_embedding_ok(self, cli_runner, discovery_env) -> None:
        from vibesop.core.observability.skill_promote import ScanSummary

        result, _ = self._invoke(cli_runner, discovery_env, ScanSummary())
        assert result.exit_code == 0
        assert "embedding 不可用" not in result.output

    def test_miss_knobs_wire_to_scan_kwargs(self, cli_runner, discovery_env) -> None:
        from vibesop.core.observability.skill_promote import ScanSummary

        result, captured = self._invoke(
            cli_runner,
            discovery_env,
            ScanSummary(),
            extra_args=[
                "--miss-min-pairs",
                "5",
                "--miss-min-days",
                "3",
                "--miss-cosine-threshold",
                "0.9",
            ],
        )
        assert result.exit_code == 0
        assert captured["miss_min_pairs"] == 5
        assert captured["miss_min_days"] == 3
        assert captured["miss_cosine_threshold"] == 0.9

    def test_miss_knob_bounds_validated(self, cli_runner, discovery_env) -> None:
        from vibesop.core.observability.skill_promote import ScanSummary

        result, _ = self._invoke(
            cli_runner, discovery_env, ScanSummary(), extra_args=["--miss-min-pairs", "0"]
        )
        assert result.exit_code == 1
        result, _ = self._invoke(
            cli_runner,
            discovery_env,
            ScanSummary(),
            extra_args=["--miss-cosine-threshold", "1.5"],
        )
        assert result.exit_code == 1

    def test_behavior_threshold_wires_to_scan_kwargs(self, cli_runner, discovery_env) -> None:
        """gate24 pi#9b: M3 knob 接线 + 越界拒绝。"""
        from vibesop.core.observability.skill_promote import ScanSummary

        result, captured = self._invoke(
            cli_runner, discovery_env, ScanSummary(), extra_args=["--behavior-threshold", "0.7"]
        )
        assert result.exit_code == 0
        assert captured["behavior_threshold"] == 0.7

    def test_behavior_threshold_bounds_validated(self, cli_runner, discovery_env) -> None:
        from vibesop.core.observability.skill_promote import ScanSummary

        for bad in ("1.5", "-0.1"):
            result, _ = self._invoke(
                cli_runner,
                discovery_env,
                ScanSummary(),
                extra_args=["--behavior-threshold", bad],
            )
            assert result.exit_code == 1
            assert "--behavior-threshold" in result.output


class TestResolveCandidateHardening:
    """gate22 follow-up: _resolve_discovery_candidate aligned with the
    mutation resolver — empty-string guard + scope-annotated ambiguous
    listing with ``+N more`` truncation."""

    def test_empty_id_takes_not_found_path(self, cli_runner: CliRunner, discovery_env) -> None:
        stores, _ = discovery_env
        candidate = _candidate("a" * 40, ["single pending query"])
        stores["project"].upsert(candidate)
        # startswith("") is always True — without the guard this would
        # silently dismiss the only pending row.
        result = cli_runner.invoke(app, ["skill", "discover", "dismiss", ""])
        assert result.exit_code == 1
        assert "not in Discovery queue" in result.output
        shown = cli_runner.invoke(app, ["skill", "discover"])
        assert "single pending query" in shown.output

    def test_empty_mute_id_takes_not_found_path(self, cli_runner: CliRunner, discovery_env) -> None:
        """gate23 pi#3/claude#3: the ``--mute`` entry shares the same
        resolver — empty string must take the not-found path too, with no
        mute recorded."""
        stores, dirs = discovery_env
        candidate = _candidate("a" * 40, ["single pending query"])
        stores["project"].upsert(candidate)
        result = cli_runner.invoke(app, ["skill", "discover", "--mute", ""])
        assert result.exit_code == 1
        assert "not in Discovery queue" in result.output
        assert DiscoverySignalStore(dirs["project"]).active_mutes() == {}
        assert DiscoverySignalStore(dirs["global"]).active_mutes() == {}
        shown = cli_runner.invoke(app, ["skill", "discover"])
        assert "single pending query" in shown.output

    def test_ambiguous_prefix_lists_full_ids_with_scope(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, _ = discovery_env
        project_id = "ab" + "1" * 38
        global_id = "ab" + "2" * 38
        stores["project"].upsert(_candidate(project_id, ["proj ambiguous query"]))
        stores["global"].upsert(_candidate(global_id, ["glob ambiguous query"]))
        result = cli_runner.invoke(app, ["skill", "discover", "dismiss", "ab"])
        assert result.exit_code == 1
        assert "ambiguous" in result.output
        assert f"{project_id} (project)" in result.output
        assert f"{global_id} (global)" in result.output

    def test_ambiguous_listing_truncates_with_more(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, _ = discovery_env
        for i in range(10):
            stores["project"].upsert(_candidate(f"cd{i:038d}", [f"bulk ambiguous query {i}"]))
        result = cli_runner.invoke(app, ["skill", "discover", "dismiss", "cd"])
        assert result.exit_code == 1
        assert "ambiguous" in result.output
        assert "+2 more" in result.output


class TestBehaviorColumn:
    """M3 — discover 表格 Behavior 列渲染三态 + 未采集。"""

    def test_three_states_rendered(self, cli_runner: CliRunner, discovery_env) -> None:
        stores, _ = discovery_env
        consistent = _candidate("c1" + "0" * 38, ["consistent behavior query"])
        consistent.behavior_evidence = "consistent"
        consistent.behavior_score = 0.9
        divergent = _candidate("c2" + "0" * 38, ["divergent behavior query"])
        divergent.behavior_evidence = "divergent"
        divergent.behavior_score = 0.2
        unavailable = _candidate("c3" + "0" * 38, ["unavailable behavior query"])
        unavailable.behavior_evidence = "unavailable"
        legacy = _candidate("c4" + "0" * 38, ["not collected behavior query"])
        for c in (consistent, divergent, unavailable, legacy):
            stores["project"].upsert(c)

        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "consistent" in result.output
        assert "divergent" in result.output
        assert "unavailable" in result.output
        assert "未采集" in result.output


class TestFirstSeenColumn:
    """M12 NIT-B — discover 表格 First seen 列显示簇首见年龄(模式首见
    至今),而非候选入池年龄。"""

    def test_first_seen_column_uses_pattern_first_sight(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, _ = discovery_env
        candidate = _candidate("f5" + "0" * 38, ["old pattern query"])
        # 入池是刚刚(created_at=now),但模式首见在 20 天前。
        candidate.first_seen_at = datetime.now(UTC) - timedelta(days=20)
        stores["project"].upsert(candidate)
        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "First seen" in result.output
        assert "20d" in result.output

    def test_legacy_row_without_first_seen_falls_back_to_created_at(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, _ = discovery_env
        # first_seen_at=None(存量行)→ 回退 created_at 语义 → 0d。
        candidate = _candidate("f6" + "0" * 38, ["fresh pattern query"])
        stores["project"].upsert(candidate)
        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "First seen" in result.output
        assert "0d" in result.output
        assert "20d" not in result.output


class TestCrossScopeDismiss:
    """gate17 claude nit 1 / pi nit 3: one dismissal covers both scopes."""

    def test_dismiss_in_global_store_hides_project_candidate(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, dirs = discovery_env
        candidate = _candidate("9" * 40, ["cross scope dismiss query"])
        stores["project"].upsert(candidate)
        DiscoverySignalStore(dirs["global"]).record_dismiss(
            cluster_fingerprint(candidate.queries), candidate.cluster_id
        )

        hidden = cli_runner.invoke(app, ["skill", "discover"])
        assert "cross scope dismiss query" not in hidden.output
        shown = cli_runner.invoke(app, ["skill", "discover", "--all"])
        assert "cross scope dismiss query" in shown.output
        assert "dismissed" in shown.output

    def test_mute_in_other_scope_hides_candidate(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, dirs = discovery_env
        candidate = _candidate("8" * 40, ["cross scope mute query"])
        stores["project"].upsert(candidate)
        DiscoverySignalStore(dirs["global"]).record_mute(
            cluster_fingerprint(candidate.queries), candidate.cluster_id
        )

        hidden = cli_runner.invoke(app, ["skill", "discover"])
        assert "cross scope mute query" not in hidden.output

    def test_double_dismiss_via_other_scope_is_noop(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, dirs = discovery_env
        candidate = _candidate("7" * 40, ["already dismissed elsewhere query"])
        stores["project"].upsert(candidate)
        DiscoverySignalStore(dirs["global"]).record_dismiss(
            cluster_fingerprint(candidate.queries), candidate.cluster_id
        )
        result = cli_runner.invoke(app, ["skill", "discover", "dismiss", candidate.cluster_id])
        assert result.exit_code == 0
        assert "already dismissed" in result.output


class TestHistoryClosedLoopWindow:
    """gate17 pi nit 4 + claude nit 9: since-window +口径 disclosure."""

    def test_pre_promotion_hits_excluded_and_disclosure_shown(
        self, cli_runner: CliRunner, discovery_env, tmp_path: Path, monkeypatch
    ) -> None:
        stores, _ = discovery_env
        promoted = _candidate("4" * 40, ["windowed history query"])
        stores["project"].upsert(promoted)
        stores["project"].promote(promoted.cluster_id, "custom/windowed-skill")

        vibe_dir = tmp_path / ".vibe"
        vibe_dir.mkdir(exist_ok=True)
        now = datetime.now(UTC)
        records = [
            # pre-promotion hits (old timestamps) — must NOT count
            {"primary_skill": "custom/windowed-skill", "timestamp": "2020-01-01T00:00:00+00:00"},
            {"primary_skill": "custom/windowed-skill", "timestamp": "2020-06-01T00:00:00+00:00"},
        ] + [
            # post-promotion hits
            {"primary_skill": "custom/windowed-skill", "timestamp": now.isoformat()}
            for _ in range(5)
        ]
        (vibe_dir / "analytics.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(app, ["skill", "discover", "--history"])
        assert result.exit_code == 0
        assert "提升后 5 次命中" in result.output
        assert "仅统计当前项目" in result.output
