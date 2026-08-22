"""Sanity tests for scripts/measure_echo_share.py (gate35 回声基线).

Synthetic fixtures only — never reads real project data. Covers: 空池
fail-closed、(b) 卡片口径的 project+global 双 scope 合并去重 (复审
claude-MAJOR)、双报数字自洽（完整谓词 ⊇ 前缀谓词, 风险人口与前缀
集合不相交）、渲染的关键行。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = ROOT / "scripts" / "measure_echo_share.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("measure_echo_share", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("measure_echo_share", module)
    spec.loader.exec_module(module)
    return module


mes = _load_module()


def _cid(seed: str) -> str:
    """hashlib — never the builtin ``hash()`` (process-randomized)."""
    return hashlib.sha1(seed.encode()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _miss_span(task_id: str, query: str) -> dict:
    """Minimal route-miss span per ``is_route_miss_span`` 口径."""
    return {
        "id": f"span-{task_id}",
        "name": f"route:{task_id}",
        "task_id": task_id,
        "project_id": "proj",
        "span_kind": "task",
        "started_at": "2026-08-01T00:00:00+00:00",
        "metadata": {"query": query, "has_match": False, "mode": "auto"},
    }


def _pending_card(seed: str, query: str, projects: dict[str, int] | None = None) -> dict:
    return {
        "cluster_id": _cid(seed),
        "task_ids": [f"{seed}-t0"],
        "queries": [query],
        "span_count": 3,
        "gold_rate": 0.0,
        "status": "pending",
        "project_distribution": projects or {},
    }


class TestMissPoolDualReport:
    def test_dual_report_self_consistent(self) -> None:
        """完整谓词命中数 ≥ 前缀谓词命中数（长度规则只多不少）;
        风险人口与前缀集合不相交。"""
        spans = [
            _miss_span("t1", "You are an adversarial SKEPTIC"),  # prefix hit
            _miss_span("t2", "<system-reminder> hook fired"),  # prefix hit
            _miss_span("t3", "x" * 200),  # length-rule only (full hit, no prefix)
            _miss_span("t4", "请帮我重构这个模块，保持 API 兼容，" * 8),  # risk population
            _miss_span("t5", "how do I run the tests"),  # clean
        ]
        m = mes.measure(spans, [])
        assert m["miss_pool_size"] == 5
        assert m["miss_prefix_shape"] == 2
        # 完整谓词 = 前缀命中 ∪ 长度规则命中（"x"*200 与长中文 query 都
        # >150 字符）—— 风险人口是完整谓词命中的子集。
        assert m["miss_full_shape"] == 4
        assert m["miss_full_shape"] >= m["miss_prefix_shape"]
        assert m["miss_long_non_prefix"] == 2  # "x"*200 + 长中文 query, 均长且非前缀
        assert m["miss_long_non_prefix"] <= m["miss_full_shape"] - m["miss_prefix_shape"]

    def test_empty_miss_pool_reports_zero(self) -> None:
        m = mes.measure([], [])
        assert m["miss_pool_size"] == 0
        text = mes.render(Path("/tmp/x"), m)
        assert "SAMPLE TOO THIN" in text
        assert "无 pending 候选卡片" in text


class TestPendingCardsDualScope:
    def test_global_only_cards_counted(self, tmp_path: Path, monkeypatch) -> None:
        """复审 claude-MAJOR: --cross-project 候选只落 global store,
        (b) 口径漏掉它会系统性低估。"""
        home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", lambda: home)
        project = tmp_path / "proj"
        _write_jsonl(
            project / ".vibe" / "observability" / "cluster_candidates.jsonl",
            [_pending_card("proj", "how do I run the tests")],
        )
        _write_jsonl(
            home / ".vibe" / "observability" / "cluster_candidates.jsonl",
            [_pending_card("glob", "You are a cross-project echo", {"/p/a": 2, "/p/b": 2})],
        )
        cards = mes._pending_cards(project)
        assert len(cards) == 2
        m = mes.measure([], cards)
        assert m["pending_cards"] == 2
        assert m["echo_cards"] == 1

    def test_same_cluster_id_deduped_preferring_heterogeneous(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """与 discover 队列 lockstep: cluster_id 去重, 保留
        project_distribution 更大的记录。"""
        home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", lambda: home)
        project = tmp_path / "proj"
        dup = _pending_card("dup", "You are a dup echo")  # project copy, 0 projects
        _write_jsonl(project / ".vibe" / "observability" / "cluster_candidates.jsonl", [dup])
        _write_jsonl(
            home / ".vibe" / "observability" / "cluster_candidates.jsonl",
            [
                {**dup, "project_distribution": {"/p/a": 1, "/p/b": 1}},
                _pending_card("gone", "You are a dismissed echo"),  # pending here…
            ],
        )
        cards = mes._pending_cards(project)
        # dup 只计一次, 且保留 global 的异构副本
        assert len(cards) == 2
        dup_card = next(c for c in cards if c["cluster_id"] == _cid("dup"))
        assert len(dup_card["project_distribution"]) == 2

    def test_non_pending_rows_excluded(self, tmp_path: Path, monkeypatch) -> None:
        home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", lambda: home)
        project = tmp_path / "proj"
        dismissed = {**_pending_card("term", "You are a terminal echo"), "status": "dismissed"}
        _write_jsonl(project / ".vibe" / "observability" / "cluster_candidates.jsonl", [dismissed])
        assert mes._pending_cards(project) == []


class TestMainEntry:
    def test_empty_pool_fails_closed(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """空池（无 spans 且无候选）→ exit 1, 不写 artifact。"""
        home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", lambda: home)
        monkeypatch.setattr(sys, "argv", ["measure_echo_share.py", "--project-root", str(tmp_path)])
        assert mes.main() == 1
        err = capsys.readouterr().err
        assert "FATAL" in err
        assert not (tmp_path / ".omx" / "artifacts" / "gate35-echo-measure.md").exists()

    def test_writes_artifact(self, tmp_path: Path, monkeypatch) -> None:
        home = tmp_path / "home"
        monkeypatch.setattr(Path, "home", lambda: home)
        project = tmp_path / "proj"
        _write_jsonl(
            project / ".vibe" / "observability" / "spans.jsonl",
            [_miss_span("t1", "You are an echo")],
        )
        _write_jsonl(
            project / ".vibe" / "observability" / "cluster_candidates.jsonl",
            [_pending_card("c1", "You are a card echo")],
        )
        monkeypatch.setattr(sys, "argv", ["measure_echo_share.py", "--project-root", str(project)])
        assert mes.main() == 0
        text = (project / ".omx" / "artifacts" / "gate35-echo-measure.md").read_text(
            encoding="utf-8"
        )
        assert "完整谓词" in text
        assert "1/1 = 100.0%" in text  # 池与卡片各 1/1 回声
