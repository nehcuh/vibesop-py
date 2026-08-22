"""gate36 阶段二 — promote shadow verifier tests (D1, 修订 A/B/D/J).

Coverage map (定稿验收口径):
- 已知良好簇 → PASS（捕获分母排除 agent-echo, 两 embedding 线过门）;
- 回声簇 → WARN 且明细列出未捕获 query + 最近邻;
- 降级 (embedding unavailable) → WARN(degraded), 永不发 PASS;
- global scope verdict 不含原始 query (只计数 + query 哈希);
- verdict store 容量裁剪 (200 条 / 90 天) + 坏行跳过 + from_dict 容忍缺键;
- activate 复用/重算选择逻辑 (latest_for_cluster prefer_complete);
- trigger 语义抽取钉住生产口径 (修订 B: lowercase+剥撇号、无空白折叠、
  无长度下限、first-hit-wins) 且 has_explicit_guard_signal 委托后行为不变.

The conftest embedding stub (``sys.modules["sentence_transformers"] = None``)
makes the module-level model singleton fail-open → the degraded path is
testable without any DI; the PASS/margin paths inject ``_FakeModel`` via the
``embedding_model`` seam (never the real 10-12s model load).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from vibesop.core.observability import promote_verifier
from vibesop.core.observability.promote_verifier import (
    MAX_VERDICTS,
    RULESET_VERSION,
    _INDEX_GATE,
    _INDEX_MIN_MARGIN,
    PromoteVerdict,
    PromoteVerdictStore,
    verify_draft,
)
from vibesop.core.observability.skill_promote import ClusterCandidate
from vibesop.core.routing.triage_service import TriageService, query_matches_triggers


@pytest.fixture(autouse=True)
def _reset_model_singleton():
    """pi-2/claude-4 收敛: 重置模块级 embedding 单例, 消除顺序耦合 flake.

    DI 路径 (``embedding_model``) 不碰单例, 但无 DI 的降级测试会把
    ``failed=True`` 写进 ``_MODEL_STATE`` —— 不重置的话, 后续/前序测试
    的行为取决于执行顺序。
    """
    snapshot = dict(promote_verifier._MODEL_STATE)
    promote_verifier._MODEL_STATE.update(model=None, failed=False)
    yield
    promote_verifier._MODEL_STATE.update(snapshot)


def _mk_candidate(
    cluster_id: str = "c" * 40,
    queries: list[str] | None = None,
    **overrides,
) -> ClusterCandidate:
    payload = {
        "cluster_id": cluster_id,
        "task_ids": [f"{cluster_id[:8]}-t1"],
        "queries": queries if queries is not None else ["fix the login redirect loop"],
        "span_count": 4,
        "gold_rate": 0.8,
        "gold_task_ids": [f"{cluster_id[:8]}-t1"],
        "source_skill_id": "custom/login-fix-" + cluster_id[:8],
    }
    payload.update(overrides)
    return ClusterCandidate(**payload)


def _write_draft(
    tmp_path: Path,
    triggers: list[str],
    *,
    description: str = "login redirect fix workflow",
    skill_id: str = "custom/login-fix-cccccccc",
) -> Path:
    trig = ", ".join(f'"{t}"' for t in triggers)
    path = tmp_path / "SKILL.md"
    path.write_text(
        "---\n"
        f"id: {skill_id}\n"
        "name: login-fix\n"
        f'description: "{description}"\n'
        f"triggers: [{trig}]\n"
        "intent: workflow\n"
        "---\n\n## Overview\n\nbody\n",
        encoding="utf-8",
    )
    return path


class _FakeModel:
    """Deterministic bag-of-words embedding: token → dim via sha1.

    Cosine similarity between texts ≈ token overlap, so a query sharing
    the trigger's tokens scores high and an unrelated text scores ~0.
    ``hashlib`` only — the builtin ``hash()`` is process-randomized and
    banned in this repo's tests.
    """

    dim = 64

    def encode(self, texts: list[str], show_progress_bar: bool = False) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in str(text).lower().split():
                vec[int(hashlib.sha1(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
            out.append(vec)
        return out


def _fake_catalog(model: _FakeModel, text: str, skill_id: str = "builtin/other-skill"):
    """One-entry skill index with a real embedding for the margin gate."""
    from vibesop.core.skills.indexer import SkillProfile

    return {
        skill_id: SkillProfile(skill_id=skill_id, embedding=model.encode([text])[0]),
    }


class TestQueryMatchesTriggers:
    """修订 B: pin the extracted PRODUCTION containment semantics (and the
    deliberate divergence from p0_shadow's whitespace-folding/≥6-char rule)."""

    def test_lowercase_and_apostrophe_stripped(self) -> None:
        assert query_matches_triggers("Let's GO now", ["lets go"]) == "lets go"
        assert query_matches_triggers("lets go", ["let’s go"]) == "let’s go"

    def test_no_whitespace_folding(self) -> None:
        """Production does NOT fold whitespace — "foo  bar" (two spaces)
        must NOT match trigger "foo bar" (p0_shadow would match)."""
        assert query_matches_triggers("foo  bar", ["foo bar"]) is None
        assert query_matches_triggers("foo bar", ["foo bar"]) == "foo bar"

    def test_no_length_floor(self) -> None:
        """A 2-char trigger matches (p0_shadow's ≥6 floor would reject it)."""
        assert query_matches_triggers("ok do it", ["ok"]) == "ok"

    def test_first_hit_wins_in_trigger_order(self) -> None:
        assert query_matches_triggers("a b c", ["b", "a"]) == "b"

    def test_empty_trigger_never_matches(self) -> None:
        assert query_matches_triggers("anything", ["", "  "]) is None
        assert query_matches_triggers("anything", []) is None

    def test_guard_signal_delegation_behavior_unchanged(self) -> None:
        """has_explicit_guard_signal keeps its exact behavior after the
        extraction (trigger containment + always-explicit extra tokens)."""
        service = TriageService.__new__(TriageService)  # guard path is attr-free
        candidates = [{"id": "builtin/riper-workflow", "triggers": ["use riper"]}]
        assert (
            service.has_explicit_guard_signal(
                "please use riper now", candidates, "builtin/riper-workflow"
            )
            is True
        )
        # Extra always-explicit token path still works with no trigger hit.
        assert (
            service.has_explicit_guard_signal(
                "用 RIPER 流程来做", candidates, "builtin/riper-workflow"
            )
            is True
        )
        assert (
            service.has_explicit_guard_signal(
                "generic workflow please", candidates, "builtin/riper-workflow"
            )
            is False
        )
        # Non-guarded skill: no guard to satisfy.
        assert service.has_explicit_guard_signal("anything", candidates, "custom/x") is True


class TestVerifyDraftBadges:
    def test_known_good_cluster_passes(self, tmp_path: Path) -> None:
        """已知良好簇 → PASS: lint 全过 + shadow 全捕获 + 两 embedding 线过门."""
        candidate = _mk_candidate(
            queries=[
                "fix the login redirect loop",
                "fix the login redirect loop again please",
            ]
        )
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        model = _FakeModel()
        verdict = verify_draft(
            candidate,
            draft,
            installed_candidates=[{"id": "builtin/x", "triggers": ["deploy staging"]}],
            index_profiles=_fake_catalog(model, "deploy the staging environment"),
            embedding_model=model,
        )
        assert verdict.badge == "PASS"
        assert verdict.degraded is False
        assert verdict.shadow["all_caught"] is True
        assert verdict.embedding["recall"]["status"] == "ok"
        assert verdict.embedding["recall"]["all_caught"] is True
        assert verdict.embedding["index"]["status"] == "ok"
        assert verdict.embedding["index"]["all_accepted"] is True
        assert verdict.embedding["index"]["margin_mode"] == "catalog"
        assert set(verdict.pipelines) == {
            "trigger_lint",
            "shadow_replay",
            "hijack",
            "embedding_recall",
            "embedding_index",
        }

    def test_good_cluster_with_mixed_echo_rows_still_passes(self, tmp_path: Path) -> None:
        """pi-5 收敛: 已知良好簇混入 agent-echo 行 (bd1bc217 类) —— 回声行
        进不了分母, PASS 不被稀释 (修订 J 细化的核心动机)."""
        candidate = _mk_candidate(
            queries=[
                "fix the login redirect loop",
                "fix the login redirect loop for the admin path",
                "You are an adversarial SKEPTIC reviewing the plan",
                "<system-reminder> wrapper noise",
            ]
        )
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        model = _FakeModel()
        verdict = verify_draft(
            candidate,
            draft,
            installed_candidates=[],
            index_profiles=_fake_catalog(model, "deploy the staging environment"),
            embedding_model=model,
        )
        assert verdict.shadow["denominator"] == 2
        assert verdict.shadow["echo_excluded"] == 2
        assert verdict.badge == "PASS"
        assert verdict.degraded is False

    def test_echo_cluster_warns_with_uncaught_detail(self, tmp_path: Path) -> None:
        """回声簇 → WARN: 回声行不进分母, 明细列出未捕获 query + 最近邻."""
        candidate = _mk_candidate(
            queries=[
                "You are an adversarial SKEPTIC reviewing this plan",
                "<system-reminder> injected wrapper",
                "重构会话中间件逻辑",
            ]
        )
        draft = _write_draft(tmp_path, ["upgrade the database schema"])
        verdict = verify_draft(
            candidate, draft, installed_candidates=[], embedding_model=_FakeModel()
        )
        assert verdict.badge == "WARN"
        # 标集口径: 2 条前缀谓词回声行排除, 分母只剩真实 query.
        assert verdict.shadow["denominator"] == 1
        assert verdict.shadow["echo_excluded"] == 2
        missed = verdict.shadow["missed"]
        assert len(missed) == 1
        assert missed[0]["query"] == "重构会话中间件逻辑"
        # 最近邻: 唯一 trigger 与 query 无共享 token → 诚实的 "无近邻".
        assert missed[0]["nearest_trigger"] is None
        assert "no representative cluster query matches any trigger" in verdict.warnings

    def test_nearest_trigger_picks_token_overlap(self, tmp_path: Path) -> None:
        candidate = _mk_candidate(queries=["refactor the session middleware stack"])
        draft = _write_draft(tmp_path, ["refactor the auth middleware", "deploy now"])
        verdict = verify_draft(candidate, draft, embedding_model=_FakeModel())
        missed = verdict.shadow["missed"]
        assert len(missed) == 1
        assert missed[0]["nearest_trigger"] == "refactor the auth middleware"
        assert missed[0]["nearest_score"] > 0

    def test_all_echo_cluster_warns(self, tmp_path: Path) -> None:
        """分母为空的纯回声簇: WARN (bd1bc217 类混回声良好簇不被 PASS 卡死,
        但也拿不到 PASS —— 分母为空即 lint 警告)."""
        candidate = _mk_candidate(queries=["You are a reviewer", "[{json echo"])
        draft = _write_draft(tmp_path, ["some trigger"])
        verdict = verify_draft(candidate, draft, embedding_model=_FakeModel())
        assert verdict.badge == "WARN"
        assert verdict.shadow["denominator"] == 0
        assert "capture denominator is empty" in " ".join(verdict.warnings)

    def test_degraded_never_emits_pass(self, tmp_path: Path) -> None:
        """降级 (conftest stub → 模型不可用): 两线 unavailable, WARN(degraded),
        即使 trigger 侧完美也不发 PASS."""
        candidate = _mk_candidate(queries=["fix the login redirect loop"])
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        verdict = verify_draft(candidate, draft, installed_candidates=[])
        assert verdict.badge == "WARN"
        assert verdict.degraded is True
        assert verdict.embedding["recall"]["status"] == "unavailable"
        assert verdict.embedding["index"]["status"] == "unavailable"
        assert verdict.embedding["recall"]["all_caught"] is None
        assert "embedding_recall" not in verdict.pipelines
        # trigger 侧照常出结果 (廉价且必跑).
        assert verdict.shadow["all_caught"] is True

    def test_encode_failure_is_fail_open(self, tmp_path: Path) -> None:
        class _BoomModel:
            def encode(self, texts, show_progress_bar=False):
                raise RuntimeError("boom")

        candidate = _mk_candidate(queries=["fix the login redirect loop"])
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        verdict = verify_draft(candidate, draft, embedding_model=_BoomModel())
        assert verdict.badge == "WARN"
        assert verdict.degraded is True
        assert verdict.embedding["recall"]["status"] == "unavailable"
        assert verdict.embedding["index"]["status"] == "unavailable"

    def test_index_line_skipped_without_triggers(self, tmp_path: Path) -> None:
        """pi-4/claude-3 收敛: skipped 是内容态 (无 triggers 可嵌), 不是
        降级态 —— degraded=False, badge 仍 WARN (all_accepted=None → 不过门)."""
        candidate = _mk_candidate(queries=["fix the login redirect loop"])
        draft = _write_draft(tmp_path, [])  # TODO placeholder draft
        verdict = verify_draft(candidate, draft, embedding_model=_FakeModel())
        assert verdict.badge == "WARN"
        assert verdict.embedding["index"]["status"] == "skipped"
        assert verdict.degraded is False  # skipped ≠ degraded
        assert any("draft declares no triggers" in w for w in verdict.warnings)

    def test_poison_model_wrong_length_degrades_both_lines(self, tmp_path: Path) -> None:
        """pi-1/claude-8 收敛: encode 返回错长向量列表 → zip(strict) 抛错
        被线内 try 捕获, 两线各自降级, verify_draft 整体不抛."""

        class _ShortModel:
            def encode(self, texts, show_progress_bar=False):
                return [[0.1, 0.2]]  # 恒 1 条向量, 与请求数不符

        candidate = _mk_candidate(queries=["fix the login redirect loop"])
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        verdict = verify_draft(candidate, draft, embedding_model=_ShortModel())
        assert verdict.embedding["recall"]["status"] == "unavailable"
        assert verdict.embedding["index"]["status"] == "unavailable"
        assert verdict.degraded is True
        assert verdict.badge == "WARN"

    def test_poison_model_ragged_vectors_degrade_per_line(self, tmp_path: Path) -> None:
        """pi-1/claude-8 收敛: 参差维度向量 → cosine zip(strict) 抛错; 且
        降级是逐线的 —— recall 线 (profile 文本含 description 标记) 中毒
        时 index 线 (triggers only) 照常出结果."""

        class _RaggedOnMarkerModel:
            def __init__(self) -> None:
                self._good = _FakeModel()

            def encode(self, texts, show_progress_bar=False):
                if "POISON" in str(texts[0]):
                    return [[1.0, 0.0]] + [[1.0] * 7 for _ in texts[1:]]
                return self._good.encode(texts, show_progress_bar=show_progress_bar)

        candidate = _mk_candidate(queries=["fix the login redirect loop"])
        draft = _write_draft(
            tmp_path, ["fix the login redirect loop"], description="POISON workflow"
        )
        verdict = verify_draft(candidate, draft, embedding_model=_RaggedOnMarkerModel())
        # recall 线文本 = id+description+intent+triggers → 含 POISON → 降级;
        # index 线文本 = triggers only → 正常过门.
        assert verdict.embedding["recall"]["status"] == "unavailable"
        assert verdict.embedding["index"]["status"] == "ok"
        assert verdict.embedding["index"]["all_accepted"] is True
        assert verdict.degraded is True
        assert verdict.badge == "WARN"

    def test_margin_gate_rejects_catalog_noise(self, tmp_path: Path) -> None:
        """index 线 margin 门: 目录里一个几乎一样强的 profile → margin≈0 →
        不接受 → WARN (即使 0.45 绝对门已过)."""
        model = _FakeModel()
        candidate = _mk_candidate(queries=["fix the login redirect loop"])
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        verdict = verify_draft(
            candidate,
            draft,
            index_profiles=_fake_catalog(model, "fix the login redirect loop"),
            embedding_model=model,
        )
        index = verdict.embedding["index"]
        assert index["status"] == "ok"
        assert index["results"][0]["similarity"] >= _INDEX_GATE  # 绝对门过了
        assert index["results"][0]["accepted"] is False  # margin 门拦下
        assert index["all_accepted"] is False
        assert verdict.badge == "WARN"
        assert verdict.degraded is False

    def test_margin_skipped_without_catalog(self, tmp_path: Path) -> None:
        candidate = _mk_candidate(queries=["fix the login redirect loop"])
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        verdict = verify_draft(candidate, draft, embedding_model=_FakeModel())
        assert verdict.embedding["index"]["margin_mode"] == "skipped-no-catalog"
        assert verdict.embedding["index"]["results"][0]["margin"] is None

    def test_hijack_detects_competing_trigger(self, tmp_path: Path) -> None:
        candidate = _mk_candidate(queries=["fix the login redirect loop"])
        draft = _write_draft(tmp_path, ["login redirect"])
        verdict = verify_draft(
            candidate,
            draft,
            installed_candidates=[
                {"id": "builtin/session-end", "triggers": ["login redirect"]},
                {"id": "custom/unrelated", "triggers": ["deploy"]},
            ],
            embedding_model=_FakeModel(),
        )
        entries = verdict.hijack["entries"]
        assert len(entries) == 1
        assert entries[0]["competing_skill_id"] == "builtin/session-end"
        # hijack 分析用语义抽取后的生产 containment 口径.
        assert entries[0]["competing_trigger"] == "login redirect"

    def test_hijack_skipped_without_catalog_input(self, tmp_path: Path) -> None:
        candidate = _mk_candidate()
        draft = _write_draft(tmp_path, ["fix the login"])
        verdict = verify_draft(candidate, draft, installed_candidates=None)
        assert verdict.hijack["status"] == "skipped"
        assert "hijack" not in verdict.pipelines


class TestVerdictSchemaAndPrivacy:
    def test_schema_hashes_and_ruleset(self, tmp_path: Path) -> None:
        """修订 A 细化: draft_sha256 = 当前文件字节哈希 (≠ 生成时基线),
        另含 trigger 集哈希 + ruleset_version."""
        candidate = _mk_candidate()
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        verdict = verify_draft(candidate, draft, embedding_model=_FakeModel())
        assert verdict.draft_sha256 == hashlib.sha256(draft.read_bytes()).hexdigest()
        # 显式不是 ClusterCandidate.draft_sha256 (None 生成基线).
        assert verdict.draft_sha256 != candidate.draft_sha256
        assert verdict.ruleset_version == RULESET_VERSION
        expected_trigger_hash = hashlib.sha256(
            json.dumps(["fix the login redirect loop"], ensure_ascii=False).encode()
        ).hexdigest()
        assert verdict.trigger_set_sha256 == expected_trigger_hash

    def test_edit_changes_draft_hash(self, tmp_path: Path) -> None:
        candidate = _mk_candidate()
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        v1 = verify_draft(candidate, draft, embedding_model=_FakeModel())
        draft.write_text(draft.read_text(encoding="utf-8") + "\nhuman edit\n", encoding="utf-8")
        v2 = verify_draft(candidate, draft, embedding_model=_FakeModel())
        assert v1.draft_sha256 != v2.draft_sha256

    def test_global_scope_stores_hashes_not_raw_queries(self, tmp_path: Path) -> None:
        """修订 D / M5 边界: global verdict 只存计数 + query 哈希."""
        secret_query = "refactor the session middleware stack"
        candidate = _mk_candidate(queries=[secret_query, "You are an echo wrapper"])
        draft = _write_draft(tmp_path, ["unrelated trigger phrase"])
        verdict = verify_draft(candidate, draft, scope="global", embedding_model=_FakeModel())
        blob = json.dumps(verdict.to_dict(), ensure_ascii=False)
        assert secret_query not in blob
        assert "echo wrapper" not in blob
        assert verdict.shadow["denominator"] == 1
        missed = verdict.shadow["missed"][0]
        assert "query" not in missed
        assert missed["query_hash"] == hashlib.sha256(secret_query.encode()).hexdigest()

    def test_project_scope_sanitizes_text(self, tmp_path: Path) -> None:
        candidate = _mk_candidate(queries=["multi\n\nline   query about refactoring modules"])
        draft = _write_draft(tmp_path, ["other trigger"])
        verdict = verify_draft(candidate, draft, embedding_model=_FakeModel())
        missed_query = verdict.shadow["missed"][0]["query"]
        assert "\n" not in missed_query
        assert "   " not in missed_query


class TestPromoteVerdictStore:
    def _verdict(self, cluster_id: str = "c" * 40, **overrides) -> PromoteVerdict:
        payload = {
            "cluster_id": cluster_id,
            "skill_id": "custom/x",
            "scope": "project",
            "phase": "promote",
            "badge": "WARN",
            "degraded": False,
            "draft_sha256": "d" * 64,
            "trigger_set_sha256": "t" * 64,
            "ruleset_version": RULESET_VERSION,
            "created_at": datetime.now(UTC),
        }
        payload.update(overrides)
        return PromoteVerdict(**payload)

    def test_roundtrip_and_bad_line_skip(self, tmp_path: Path) -> None:
        store = PromoteVerdictStore(tmp_path)
        store.append(self._verdict())
        with store._path.open("a", encoding="utf-8") as f:
            f.write("{not json\n")
            f.write('{"cluster_id": "only-id"}\n')  # schema-invalid (missing required)
        rows = store.list_all()
        assert len(rows) == 1
        assert rows[0].cluster_id == "c" * 40

    def test_from_dict_tolerates_missing_optional_keys(self) -> None:
        v = PromoteVerdict.from_dict(
            {
                "cluster_id": "x",
                "skill_id": "s",
                "scope": "project",
                "phase": "promote",
                "badge": "WARN",
                "degraded": True,
                "draft_sha256": "d",
                "trigger_set_sha256": "t",
                "ruleset_version": "gate36-r1",
                # created_at / lint / shadow / embedding / hijack / pipelines missing
                "unknown_future_key": 1,  # dropped, not raised
            }
        )
        assert v.created_at is None
        assert v.shadow == {}

    def test_capacity_keeps_latest_200(self, tmp_path: Path) -> None:
        store = PromoteVerdictStore(tmp_path)
        for i in range(MAX_VERDICTS + 5):
            store.append(self._verdict(cluster_id=f"cluster-{i:04d}"))
        rows = store.list_all()
        assert len(rows) == MAX_VERDICTS
        ids = {r.cluster_id for r in rows}
        assert "cluster-0000" not in ids  # oldest dropped
        assert f"cluster-{MAX_VERDICTS + 4:04d}" in ids

    def test_ttl_drops_rows_older_than_90_days(self, tmp_path: Path) -> None:
        """TTL 裁剪发生在 append 时 —— 直接落盘一条 100 天前的旧行
        (绕过 append 的即裁), 再 append 一条新行, 旧行应被裁掉."""
        store = PromoteVerdictStore(tmp_path)
        old = self._verdict(cluster_id="old", created_at=datetime.now(UTC) - timedelta(days=100))
        with store._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(old.to_dict(), ensure_ascii=False) + "\n")
        store.append(self._verdict(cluster_id="fresh"))
        assert [r.cluster_id for r in store.list_all()] == ["fresh"]
        # 边界: 恰好 90 天内的行保留.
        recent = self._verdict(
            cluster_id="recent", created_at=datetime.now(UTC) - timedelta(days=89)
        )
        store.append(recent)
        assert [r.cluster_id for r in store.list_all()] == ["fresh", "recent"]

    def test_latest_for_cluster_prefers_complete_over_degraded(self, tmp_path: Path) -> None:
        """修订 A 细化: 降级重跑追加新行, 但展示优先完整版."""
        store = PromoteVerdictStore(tmp_path)
        now = datetime.now(UTC)
        store.append(
            self._verdict(phase="promote", degraded=False, created_at=now - timedelta(hours=1))
        )
        store.append(self._verdict(phase="activate-rerun", degraded=True, created_at=now))
        latest = store.latest_for_cluster("c" * 40, draft_sha256="d" * 64)
        assert latest is not None and latest.phase == "activate-rerun"
        complete = store.latest_for_cluster("c" * 40, draft_sha256="d" * 64, prefer_complete=True)
        assert complete is not None and complete.phase == "promote"
        # Hash mismatch → no reuse.
        assert store.latest_for_cluster("c" * 40, draft_sha256="e" * 64) is None

    def test_verify_appends_to_store(self, tmp_path: Path) -> None:
        candidate = _mk_candidate()
        draft = _write_draft(tmp_path, ["fix the login redirect loop"])
        store = PromoteVerdictStore(tmp_path / "verdicts")
        verify_draft(candidate, draft, store=store)
        rows = store.for_cluster(candidate.cluster_id)
        assert len(rows) == 1
        assert rows[0].phase == "promote"


class TestConfigPin:
    def test_index_gates_match_routing_config_defaults(self) -> None:
        """index 线门值钉住 RoutingConfig 默认 —— 配置再标定时此处必须同改."""
        from vibesop.core.config import RoutingConfig

        config = RoutingConfig()
        assert config.index_embedding_threshold == _INDEX_GATE
        assert config.index_embedding_min_margin == _INDEX_MIN_MARGIN
