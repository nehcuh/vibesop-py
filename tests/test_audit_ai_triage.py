"""Pure-logic tests for the live AI-triage probe audit (scripts/audit_ai_triage.py).

The live run needs a real LLM provider and is executed manually; here only
the verdict classifier, rule-of-three bound, and dataset validation are
under test (kimi review F11: the regression asset itself must be sound).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "audit_ai_triage.py"
_spec = importlib.util.spec_from_file_location("audit_ai_triage", _SCRIPT)
audit = importlib.util.module_from_spec(_spec)
sys.modules["audit_ai_triage"] = audit
_spec.loader.exec_module(audit)


class TestClassify:
    def test_selected_line_is_routed(self) -> None:
        out = "│ Selected: builtin/systematic-debugging (confidence: 88%) │"
        v = audit.classify(out)
        assert v.outcome == "routed"
        assert v.detail == "builtin/systematic-debugging"

    def test_multi_agent_plan_is_routed(self) -> None:
        out = "Mode MULTI_AGENT\n│ Steps: 5\n├── Step 1: builtin/systematic-debugging"
        v = audit.classify(out)
        assert v.outcome == "routed"
        assert v.detail == "plan"

    def test_fallback_no_match(self) -> None:
        v = audit.classify("Fallback Mode: fallback-llm (no skill matched)")
        assert v.outcome == "no_match"

    def test_no_matching_skill_variant(self) -> None:
        v = audit.classify("No matching skill found. Proceeding in normal mode.")
        assert v.outcome == "no_match"

    def test_unparseable_is_unknown_not_silent_pass(self) -> None:
        assert audit.classify("something broke").outcome == "unknown"


class TestRuleOfThree:
    def test_seven_probes_wide_bound(self) -> None:
        # The original audit's power problem, made explicit: ~35%.
        assert audit.fp_upper_bound(7) == pytest.approx(0.354, abs=0.01)

    def test_twenty_two_probes_tight_bound(self) -> None:
        assert audit.fp_upper_bound(22) == pytest.approx(0.127, abs=0.005)

    def test_matches_three_over_n_heuristic(self) -> None:
        # 3/n is the textbook approximation; the exact bound is ln(1/alpha)/n.
        assert audit.fp_upper_bound(20) == pytest.approx(3 / 20, abs=0.02)

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            audit.fp_upper_bound(0)


class TestDataset:
    def test_checked_in_dataset_is_valid(self) -> None:
        negatives, positives = audit.load_probes(audit.DEFAULT_DATASET)
        assert len(negatives) >= 20
        assert len(positives) >= 5

    def test_checked_in_dataset_disjoint_from_original_audit(self) -> None:
        """Held-out means the texts must differ from the 2026-08-29 audit
        probes that calibrated the fix (a verbatim reuse would overstate
        precision)."""
        original_negatives = {
            "你是独立评审者。请评审以下实验设计并给出专业建议：我们计划用双容器 A/B 对照测量技能注入对完成质量的影响，样本量 15，指标是通过率差。请攻击这个设计的统计效度。",
            "帮我看看下面这个方案的优缺点，只需要分析，不要动代码：把缓存层从 Redis 换成本地 LRU。",
        }
        negatives, _ = audit.load_probes(audit.DEFAULT_DATASET)
        queries = {p.query for p in negatives}
        assert not queries & original_negatives

    def test_short_query_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "version: 1\nnegatives:\n"
            + "".join(f"  - id: N{i:02d}\n    query: 这条太短了\n" for i in range(20))
            + "positives:\n  - id: P1\n    query: 帮我实现一个完整的功能模块并写好单元测试\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="bypass"):
            audit.load_probes(bad)

    def test_too_few_negatives_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "version: 1\nnegatives:\n  - id: N1\n    query: " + "太" * 25 + "\n"
            "positives:\n"
            + "".join(
                f"  - id: P{i}\n    query: 帮我实现第 {i} 个功能并写好完整的单元测试\n"
                for i in range(5)
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="20"):
            audit.load_probes(bad)

    def test_duplicate_ids_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        body = "version: 1\nnegatives:\n" + "".join(
            f"  - id: DUP\n    query: 第 {i} 条完全不同的负样本查询内容各不相同\n"
            for i in range(20)
        )
        body += "positives:\n" + "".join(
            f"  - id: P{i}\n    query: 帮我实现第 {i} 个完整的功能模块并写好单元测试\n"
            for i in range(5)
        )
        bad.write_text(body, encoding="utf-8")
        with pytest.raises(ValueError, match="duplicate"):
            audit.load_probes(bad)


class TestCacheParking:
    """park_cache/restore_cache must never clobber a leftover backup and
    must leave no trace when there was no cache before the run."""

    @pytest.fixture()
    def cache_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
        cache = tmp_path / "triage_cache.json"
        backup = tmp_path / "triage_cache.json.audit-bak"
        monkeypatch.setattr(audit, "CACHE_PATH", cache)
        monkeypatch.setattr(audit, "CACHE_BACKUP", backup)
        return cache, backup

    def test_existing_cache_parked_and_restored(self, cache_paths: tuple[Path, Path]) -> None:
        cache, backup = cache_paths
        cache.write_text("{}", encoding="utf-8")
        assert audit.park_cache() is True
        assert not cache.exists() and backup.exists()
        audit.restore_cache(parked=True)
        assert cache.exists() and not backup.exists()

    def test_leftover_backup_recovered_before_park(self, cache_paths: tuple[Path, Path]) -> None:
        """A killed run leaves only the backup; the next run must recover it
        instead of ignoring it."""
        cache, backup = cache_paths
        backup.write_text("{}", encoding="utf-8")
        assert audit.park_cache() is True  # recovered, then parked again
        assert backup.exists() and not cache.exists()
        audit.restore_cache(parked=True)
        assert cache.read_text(encoding="utf-8") == "{}"

    def test_leftover_backup_with_cache_refuses(self, cache_paths: tuple[Path, Path]) -> None:
        """Both files present is ambiguous — parking would clobber the old
        backup, so it must refuse."""
        cache, backup = cache_paths
        cache.write_text("{}", encoding="utf-8")
        backup.write_text("{}", encoding="utf-8")
        with pytest.raises(RuntimeError, match="resolve manually"):
            audit.park_cache()
        assert cache.exists() and backup.exists()  # untouched

    def test_no_prior_cache_leaves_no_trace(self, cache_paths: tuple[Path, Path]) -> None:
        """With no cache before the run, the probes' freshly written cache
        must be deleted afterwards."""
        cache, _ = cache_paths
        assert audit.park_cache() is False
        cache.write_text("{}", encoding="utf-8")  # written by the probes
        audit.restore_cache(parked=False)
        assert not cache.exists()
