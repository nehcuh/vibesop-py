"""gate35 阶段一 — discover 队列可读性 + 展示层去噪 + 统计列 CLI 测试。

Covers: 列头自解释化 + --help 词汇表 / 「为什么在」列文案 /
agent-echo 打标沉底 + 计数行 / `discover dismiss --shape agent-echo`
批量否决（池状态翻转, 修订 E）/ shape-batch 豁免 threshold_suggestion
（修订 I）/ D3 来源统计行 / scan summary 机器形状计数。
Synthetic fixtures only。Storage helpers patched to tmp_path (same
pattern as test_skill_discover_cli.py)。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.commands import skill_commands
from vibesop.cli.main import app
from vibesop.core.observability.discovery import (
    DISMISS_TIGHTEN_THRESHOLD,
    SHAPE_BATCH_DISMISS_REASON,
    DiscoverySignalStore,
)
from vibesop.core.observability.skill_promote import ClusterCandidate, ClusterCandidateStore


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner(env={"COLUMNS": "200"})


def _candidate(
    cluster_id: str,
    queries: list[str],
    span_count: int = 5,
    gold_rate: float = 0.8,
    source: str = "gold",
) -> ClusterCandidate:
    return ClusterCandidate(
        cluster_id=cluster_id,
        task_ids=[f"{cluster_id}-t{i}" for i in range(3)],
        queries=queries,
        span_count=span_count,
        gold_rate=gold_rate,
        gold_task_ids=[],
        source=source,  # type: ignore[arg-type]
        project_distribution={},
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


class TestReadableHeaders:
    def test_self_explaining_headers_and_why_column(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, _ = discovery_env
        stores["project"].upsert(_candidate("h" * 40, ["how do I run the tests"]))
        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        for header in ("模式", "来源", "评分", "行为", "为什么在"):
            assert header in result.output
        # 「为什么在」文案与实存字段一致（防文案说谎）—— 表格会换行,
        # 断片段断言; 精确全文由 core 层 TestWhyHere 锁定。
        assert "来源 gold（成功簇" in result.output
        assert "首见" in result.output

    def test_help_contains_glossary(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["skill", "discover", "--help"])
        assert result.exit_code == 0
        assert "词汇表" in result.output
        assert "agent-echo" in result.output
        assert "miss" in result.output


class TestEchoSinking:
    def test_echo_marked_and_sunk_with_count_line(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, _ = discovery_env
        # Echo row scores HIGHER (bigger cluster) — it must still sink.
        echo = _candidate(
            "e" * 40, ["You are an adversarial SKEPTIC"], span_count=12, gold_rate=0.95
        )
        normal = _candidate("n" * 40, ["how do I run the tests"], span_count=3, gold_rate=0.6)
        stores["project"].upsert(echo)
        stores["project"].upsert(normal)

        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "shape: agent-echo" in result.output
        assert "队列含 1 条机器形状" in result.output
        assert "已沉底" in result.output
        # 沉底: 正常行在回声行之前（尽管评分更低）。
        assert result.output.index("how do I run the tests") < result.output.index(
            "You are an adversarial SKEPTIC"
        )


class TestShapeBatchDismiss:
    def _seed_echoes(self, store: ClusterCandidateStore, n: int) -> list[str]:
        ids = []
        for i in range(n):
            cid = f"{i:x}" + "e" * 39
            store.upsert(_candidate(cid, [f"You are reviewer number {i}"]))
            ids.append(cid)
        return ids

    def test_without_yes_prints_count_and_bd1bc217_precedent(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, dirs = discovery_env
        ids = self._seed_echoes(stores["project"], 2)
        result = cli_runner.invoke(app, ["skill", "discover", "dismiss", "--shape", "agent-echo"])
        assert result.exit_code == 0
        assert "将否决 2 条" in result.output
        assert "bd1bc217" in result.output  # 修订 E: 确认文案点名先例
        assert "--yes" in result.output
        # 未确认 → 无任何变更: 行仍 pending, 否定列表未创建。
        for cid in ids:
            assert stores["project"].get(cid).status == "pending"  # type: ignore[union-attr]
        assert not (dirs["project"] / DiscoverySignalStore.FILENAME).exists()

    def test_yes_flips_pool_status_not_negative_list(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        stores, dirs = discovery_env
        echo_ids = self._seed_echoes(stores["project"], 2)
        keep = _candidate("k" * 40, ["keep me — a legit query"])
        stores["project"].upsert(keep)
        # 代表规则: echo 只在 queries[1] 的行不在标集内（标集=否决集）。
        non_rep = _candidate("r" * 40, ["legit first query", "You are a reviewer"])
        stores["project"].upsert(non_rep)

        result = cli_runner.invoke(
            app, ["skill", "discover", "dismiss", "--shape", "agent-echo", "--yes"]
        )
        assert result.exit_code == 0
        assert "已否决 2 个" in result.output
        assert "2 行池状态翻转" in result.output
        # gate35 round2 (NIT): 无镜像行时括注不打印。
        assert "含跨 scope 镜像行" not in result.output
        for cid in echo_ids:
            row = stores["project"].get(cid)
            assert row.status == "dismissed"  # type: ignore[union-attr]
            assert row.dismiss_reason == SHAPE_BATCH_DISMISS_REASON  # type: ignore[union-attr]
        assert stores["project"].get(keep.cluster_id).status == "pending"  # type: ignore[union-attr]
        assert stores["project"].get(non_rep.cluster_id).status == "pending"  # type: ignore[union-attr]
        # 不走指纹负名单 (修订 E)。
        assert not (dirs["project"] / DiscoverySignalStore.FILENAME).exists()
        # terminal 粘性: 重跑批量否决无新增目标。
        again = cli_runner.invoke(
            app, ["skill", "discover", "dismiss", "--shape", "agent-echo", "--yes"]
        )
        assert "没有 shape: agent-echo 候选" in again.output

    def test_shape_batch_exempt_from_threshold_suggestion(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        """修订 I 字面收口: shape-batch 不得计入 threshold_suggestion 输入。"""
        stores, _ = discovery_env
        self._seed_echoes(stores["project"], DISMISS_TIGHTEN_THRESHOLD)
        result = cli_runner.invoke(
            app, ["skill", "discover", "dismiss", "--shape", "agent-echo", "--yes"]
        )
        assert result.exit_code == 0
        assert "建议上调" not in result.output

        history = cli_runner.invoke(app, ["skill", "discover", "--history"])
        assert history.exit_code == 0
        assert "建议上调" not in history.output  # 5 条 shape-batch 不触发收紧建议
        assert "shape-batch" in history.output  # 但单列展示
        # gate35 复审 (claude NIT): shape-batch 行由单列行呈现, 不再进
        # Dismissed 表双重展示 —— 只有 shape-batch 时表整体不渲染。
        assert "candidate pool" not in history.output

    def test_cross_scope_mirror_rows_flipped_together(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        """gate35 复审 (pi-MAJOR): 同 cluster_id 在 project+global 各有
        pending 副本时, 批量否决必须翻转两个 scope —— 否则去重败方的
        镜像行下次渲染复活。"""
        stores, _ = discovery_env
        mirror_id = "m" * 40
        # 去重规则: project_distribution 更大者胜出 (此处 global 胜出,
        # 证明翻转不依赖胜出 scope)。
        stores["project"].upsert(_candidate(mirror_id, ["You are a mirror echo reviewer"]))
        stores["global"].upsert(
            ClusterCandidate(
                cluster_id=mirror_id,
                task_ids=[f"{mirror_id}-t{i}" for i in range(3)],
                queries=["You are a mirror echo reviewer"],
                span_count=6,
                gold_rate=0.0,
                gold_task_ids=[],
                source="miss_recurrence",
                project_distribution={"/p/a": 2, "/p/b": 2},
            )
        )

        result = cli_runner.invoke(
            app, ["skill", "discover", "dismiss", "--shape", "agent-echo", "--yes"]
        )
        assert result.exit_code == 0
        assert "2 行池状态翻转" in result.output  # 两个 scope 各一行
        assert "含跨 scope 镜像行" in result.output  # round2 NIT: 有镜像才加括注
        for scope in ("project", "global"):
            row = stores[scope].get(mirror_id)
            assert row.status == "dismissed"  # type: ignore[union-attr]
            assert row.dismiss_reason == SHAPE_BATCH_DISMISS_REASON  # type: ignore[union-attr]
        # 队列不复活: 两个 scope 都不再出现该簇。
        shown = cli_runner.invoke(app, ["skill", "discover"])
        assert "mirror echo" not in shown.output
        shown_all = cli_runner.invoke(app, ["skill", "discover", "--all"])
        assert "mirror echo" not in shown_all.output  # terminal 行不进 pending 队列

    def test_already_terminal_mirror_not_counted(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        """gate35 复审 (NIT): 翻转计数只计 pending→dismissed 的真实翻转
        —— 镜像行已是 dismissed 时不虚高。"""
        stores, _ = discovery_env
        mirror_id = "t" * 40
        stores["project"].upsert(_candidate(mirror_id, ["You are a terminal mirror echo"]))
        stores["global"].upsert(_candidate(mirror_id, ["You are a terminal mirror echo"]))
        stores["global"].dismiss(mirror_id, reason="earlier decision")

        result = cli_runner.invoke(
            app, ["skill", "discover", "dismiss", "--shape", "agent-echo", "--yes"]
        )
        assert result.exit_code == 0
        assert "已否决 1 个" in result.output
        assert "1 行池状态翻转" in result.output  # global 已是 dismissed, 不计
        assert "含跨 scope 镜像行" not in result.output  # 1 簇 1 行, 无镜像括注
        assert stores["project"].get(mirror_id).status == "dismissed"  # type: ignore[union-attr]

    def test_shape_with_cluster_id_or_unknown_shape_rejected(
        self, cli_runner: CliRunner, discovery_env
    ) -> None:
        result = cli_runner.invoke(
            app, ["skill", "discover", "dismiss", "abcd1234", "--shape", "agent-echo"]
        )
        assert result.exit_code == 1
        result = cli_runner.invoke(app, ["skill", "discover", "dismiss", "--shape", "other"])
        assert result.exit_code == 1
        assert "unsupported" in result.output


class TestSourceStatsColumn:
    def test_stats_line_counts_and_excludes_shape_batch(
        self, cli_runner: CliRunner, discovery_env, tmp_path: Path, monkeypatch
    ) -> None:
        stores, _ = discovery_env
        stores["project"].upsert(_candidate("v" * 40, ["visible pending query"]))
        # promoted + 5 次提升后命中 → success 1
        promoted = _candidate("s" * 40, ["promoted query"])
        stores["project"].upsert(promoted)
        stores["project"].promote(promoted.cluster_id, "custom/stat-skill")
        # 普通池否决 → dismiss 1; shape-batch → 单列, 不进否决数
        normal_dismissed = _candidate("d" * 40, ["normal dismissed query"])
        stores["project"].upsert(normal_dismissed)
        stores["project"].dismiss(normal_dismissed.cluster_id, reason="noise")
        batch = _candidate("b" * 40, ["You are a batch echo"])
        stores["project"].upsert(batch)
        stores["project"].dismiss(batch.cluster_id, reason=SHAPE_BATCH_DISMISS_REASON)

        vibe_dir = tmp_path / ".vibe"
        vibe_dir.mkdir(exist_ok=True)
        (vibe_dir / "analytics.jsonl").write_text(
            "".join(json.dumps({"primary_skill": "custom/stat-skill"}) + "\n" for _ in range(5)),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "来源统计" in result.output
        assert "gold 成功 1 · 否决 1（shape-batch 1）" in result.output
        # gate35 复审 (claude NIT): 命中口径披露行, 与 --history 一致。
        assert "命中口径：仅统计当前项目" in result.output

    def test_stats_line_absent_without_outcomes(self, cli_runner: CliRunner, discovery_env) -> None:
        stores, _ = discovery_env
        stores["project"].upsert(_candidate("v" * 40, ["only pending query"]))
        result = cli_runner.invoke(app, ["skill", "discover"])
        assert result.exit_code == 0
        assert "来源统计" not in result.output


class TestScanSummaryEchoLine:
    def test_scan_summary_reports_echo_count(self, cli_runner: CliRunner, discovery_env) -> None:
        from vibesop.core.observability import skill_promote
        from vibesop.core.observability.skill_promote import ScanSummary

        stores, _ = discovery_env
        stores["project"].upsert(_candidate("e" * 40, ["<system-reminder> background task done"]))
        mock_writer = MagicMock()
        mock_writer.query_recent.return_value = []
        # discovery_env 已 patch _get_candidate_store (round2 NIT: 去重复 patch)。
        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=MagicMock()),
            patch(
                "vibesop.core.observability.embedding.get_embedding_cache",
                return_value=MagicMock(),
            ),
            patch.object(skill_promote, "scan_candidates", return_value=ScanSummary()),
        ):
            result = cli_runner.invoke(app, ["skill", "scan-candidates"])
        assert result.exit_code == 0
        assert "本次扫描范围含 1 条机器形状" in result.output
        assert "已沉底" in result.output

    def test_scan_summary_silent_without_echo(self, cli_runner: CliRunner, discovery_env) -> None:
        from vibesop.core.observability import skill_promote
        from vibesop.core.observability.skill_promote import ScanSummary

        stores, _ = discovery_env
        stores["project"].upsert(_candidate("n" * 40, ["normal query"]))
        mock_writer = MagicMock()
        mock_writer.query_recent.return_value = []
        with (
            patch("vibesop.core.observability.span_writer.SpanWriter", return_value=mock_writer),
            patch("vibesop.core.instinct.learner.InstinctLearner", return_value=MagicMock()),
            patch(
                "vibesop.core.observability.embedding.get_embedding_cache",
                return_value=MagicMock(),
            ),
            patch.object(skill_promote, "scan_candidates", return_value=ScanSummary()),
        ):
            result = cli_runner.invoke(app, ["skill", "scan-candidates"])
        assert result.exit_code == 0
        assert "机器形状" not in result.output
