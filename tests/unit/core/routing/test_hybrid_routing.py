"""Independent lexical/dense evidence and intent boundaries across routing paths."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from vibesop.core.config import RoutingConfig
from vibesop.core.models import RoutingLayer, SkillRoute
from vibesop.core.routing.explicit_layer import check_explicit_override
from vibesop.core.routing.intent_constraints import candidate_scope_allows, intent_clauses
from vibesop.core.routing.lexical_recall import bm25_recall, fuse_rankings, lexical_tokens
from vibesop.core.routing.triage_cache import TriageCache
from vibesop.core.routing.triage_service import TriageService
from vibesop.core.routing.unified import UnifiedRouter


def backed_candidates(tmp_path, candidates):
    result = []
    for candidate in candidates:
        source = tmp_path / "skills" / candidate["id"] / "SKILL.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Real skill source\n", encoding="utf-8")
        result.append(
            {"namespace": "builtin", "priority": "P1", **candidate, "source_file": str(source)}
        )
    return result


def service(tmp_path, dense=None):
    cost = MagicMock()
    cost.get_monthly_cost.return_value = 0.0
    instance = TriageService(
        config=RoutingConfig(ai_triage_max_skills=5),
        cost_tracker=cost,
        prefilter=MagicMock(),
        cache_manager=MagicMock(),
        get_skill_source=lambda sid, _ns: sid,
        triage_cache=TriageCache(tmp_path),
        embedding_recall=dense,
    )
    instance._llm = MagicMock()
    instance._llm.configured.return_value = True
    instance._llm.call.return_value = MagicMock(
        content='{"skill_id": "builtin/riper-workflow", "confidence": 0.9}',
        model="fixture",
        input_tokens=1,
        output_tokens=1,
    )
    return instance


def test_identifier_atoms_survive_adjacent_chinese():
    tokens = lexical_tokens("帮我接入Gemma2模型和pytest-rerunfailures16.7")
    assert "gemma2" in tokens
    assert "pytest-rerunfailures16.7" in tokens
    assert "模型" in tokens
    assert "g" not in tokens
    candidates = [
        {"id": "tool/gemma1", "keywords": ["Gemma1"]},
        {"id": "tool/gemma2", "keywords": ["Gemma2"]},
        {"id": "tool/phone", "keywords": ["红富士手机"]},
    ]
    assert bm25_recall("Gemma2模型", candidates, 1) == ["tool/gemma2"]
    assert bm25_recall("12345unrelated", candidates, 3) == []


def test_fusion_counts_id_once_per_lane_and_is_order_stable():
    assert fuse_rankings(["x", "x", "y"], ["y", "z"], top_n=3)[0] == "y"
    assert fuse_rankings(["z"], ["a"], top_n=2) == ["a", "z"]
    assert fuse_rankings([], [], top_n=20) == []


def test_rrf_k60_rewards_cross_lane_consensus_over_single_rank1():
    """Pin the k=60 consensus semantics (panel T3, kimi gate). Asymmetric
    ranks (consensus at 61 in lane_a, 62 in lane_b) remove the integer tie,
    so the consensus/single crossover lands strictly at k >= 60: any
    production change of k to 59 or below flips the second assertion red."""
    lane_a = [f"z-noise-{i}" for i in range(60)] + ["consensus"]
    lane_b = ["single-rank1"] + [f"y-noise-{i}" for i in range(60)] + ["consensus"]
    assert fuse_rankings(lane_a, lane_b, top_n=5)[0] == "consensus"
    assert fuse_rankings(lane_a, lane_b, top_n=5, k=59)[0] == "single-rank1"


@pytest.mark.parametrize("dense_ids", [[], None, ["uninstalled"]])
def test_lexical_hit_rescues_dense_miss_without_padding(tmp_path, dense_ids):
    dense = MagicMock()
    dense.recall.return_value = dense_ids
    instance = service(tmp_path, dense)
    candidates = [{"id": "tool/gemma2", "keywords": ["Gemma2"]}] + [
        {"id": f"unrelated/{i}"} for i in range(6)
    ]
    assert [
        c["id"] for c in instance.prefilter_ai_triage_candidates("Gemma2模型", candidates, 2)
    ] == ["tool/gemma2"]
    dense.recall.assert_called_once()
    assert instance._last_recall_method == ("bm25" if dense_ids is None else "hybrid")


def test_fusion_preserves_candidate_governance_and_rank(tmp_path):
    dense = MagicMock()
    dense.recall.return_value = ["ns/b", "ns/a"]
    instance = service(tmp_path, dense)
    candidates = [
        {"id": "ns/a"},
        {"id": "ns/b", "source_file": "/b/SKILL.md"},
        {"id": "disabled", "disable_model_invocation": True},
        {"id": "slash", "management_only": True},
        {"id": "ns/c"},
    ]
    result = instance.prefilter_ai_triage_candidates("unrelated", candidates, 2)
    assert [c["id"] for c in result] == ["ns/b", "ns/a"]
    assert result[0] is candidates[1]
    assert {c["id"] for c in dense.recall.call_args.args[1]} == {"ns/a", "ns/b", "ns/c"}


_GUARDS = [
    {"id": "builtin/session-end", "triggers": ["收工", "今天就到这里", "I'm done"]},
    {"id": "builtin/riper-workflow", "triggers": ["use riper", "riper workflow"]},
]


@pytest.mark.parametrize(
    "query, rejected",
    [
        ("工地上的工人六点准时收工下班", "builtin/session-end"),
        ("请解释“收工”是什么意思", "builtin/session-end"),
        ("不要收工，继续工作", "builtin/session-end"),
        ("收工了吗？", "builtin/session-end"),
        ("收工？", "builtin/session-end"),
        ("Alice will use builtin/riper-workflow tomorrow", "builtin/riper-workflow"),
        ("The worker will use RIPER to implement it", "builtin/riper-workflow"),
        ("My colleague plans to use builtin/riper-workflow", "builtin/riper-workflow"),
        ("不要用RIPER执行这个任务", "builtin/riper-workflow"),
        ("Use ripers to implement this", "builtin/riper-workflow"),
        ('Explain "use builtin/riper-workflow"', "builtin/riper-workflow"),
        ("do not use builtin/riper-workflow", "builtin/riper-workflow"),
        ("tell me about riper", "builtin/riper-workflow"),
        ("不要使用 RIPER 流程", "builtin/riper-workflow"),
        ("收工日志丢失了，帮我修复", "builtin/session-end"),
        ("我收工的时间请写到这个表中", "builtin/session-end"),
        ("我收工后继续调试这个接口", "builtin/session-end"),
        ("cannot use builtin/riper-workflow", "builtin/riper-workflow"),
        ("I can't use builtin/riper-workflow here", "builtin/riper-workflow"),
        ("unable to use builtin/riper-workflow for this", "builtin/riper-workflow"),
        ("I wont use builtin/riper-workflow again", "builtin/riper-workflow"),
        ("不能使用 RIPER 流程做这个", "builtin/riper-workflow"),
        ("无法使用 riper workflow，换个方案", "builtin/riper-workflow"),
        ("请勿用RIPER流程执行此任务", "builtin/riper-workflow"),
        ("莫用RIPER流程", "builtin/riper-workflow"),
    ],
)
def test_guard_blocks_inferred_routes_and_explicit_verb_references(tmp_path, query, rejected):
    instance = service(tmp_path)
    assert not instance.has_explicit_guard_signal(query, _GUARDS, rejected)
    assert rejected not in {
        c["id"] for c in instance.prefilter_ai_triage_candidates(query, _GUARDS, 20)
    }
    assert check_explicit_override(query, _GUARDS)[0] is None
    router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=False))
    router._candidate_manager.get_cached_candidates = lambda: backed_candidates(tmp_path, _GUARDS)
    router._scenario_cache = {"strategies": [], "keywords": {}}
    result = router.route(query)
    assert not result.primary or result.primary.skill_id != rejected


@pytest.mark.parametrize(
    "query, skill",
    [
        ("收工了", "builtin/session-end"),
        ("今天就到这里，保存一下进度", "builtin/session-end"),
        ("I'm done", "builtin/session-end"),
        ("I'm done here", "builtin/session-end"),
        ("I'm done with this", "builtin/session-end"),
        ("不要重构，用 RIPER 流程来做这个功能", "builtin/riper-workflow"),
        ("Let's do this refactor with RIPER", "builtin/riper-workflow"),
        ("Use builtin/riper-workflow without changing the public API", "builtin/riper-workflow"),
        (
            "Can you use builtin/riper-workflow to implement an example endpoint?",
            "builtin/riper-workflow",
        ),
        ("麻烦使用 RIPER 流程实现这个功能好吗？", "builtin/riper-workflow"),
        ("Please use `builtin/riper-workflow` to implement this", "builtin/riper-workflow"),
        ("Do not use another workflow but use riper workflow", "builtin/riper-workflow"),
        ("别用其他流程，而是用 RIPER 流程", "builtin/riper-workflow"),
        ("Explain the alternative then use RIPER to implement this", "builtin/riper-workflow"),
        ("kick off the riper workflow", "builtin/riper-workflow"),
        ("进行 RIPER 流程实现功能", "builtin/riper-workflow"),
        ("用RIPER执行这个任务", "builtin/riper-workflow"),
        ("请使用RIPER流程实现功能", "builtin/riper-workflow"),
        ("让我们收工", "builtin/session-end"),
        ("我想收工了", "builtin/session-end"),
        ("咱们收工了", "builtin/session-end"),
    ],
)
def test_affirmative_intent_remains_routable(tmp_path, query, skill):
    assert service(tmp_path).has_explicit_guard_signal(query, _GUARDS, skill)


@pytest.mark.parametrize(
    "query, candidate, allowed",
    [
        ("please use go now", {"id": "builtin/go", "name": "go"}, True),
        ("don't use go for this task", {"id": "builtin/go", "name": "go"}, False),
        ("cannot use go here", {"id": "builtin/go", "name": "go"}, False),
        ("请测试这个功能", {"id": "builtin/qa", "name": "测试"}, True),
        ("不要测试，直接上线", {"id": "builtin/qa", "name": "测试"}, False),
    ],
)
def test_short_identities_honor_inactive_mention_gate(query, candidate, allowed):
    assert candidate_scope_allows(query, candidate) is allowed


def test_unquote_prefix_stops_at_clause_separator():
    assert intent_clauses("use `a:b` now") == ["use a:b now"]
    assert intent_clauses("use `a:b`; but `c:d`") == ["use a:b"]
    assert intent_clauses("use `a:b`。use `c:d`") == ["use a:b", "use c:d"]


def test_quote_flood_intent_clauses_stays_bounded():
    # 8000 atoms took 6.5-8s per call with per-atom head re-splitting; the
    # linear path stays under a generous bound even on slow CI runners.
    query = " ".join(f"`atom{i}`" for i in range(8000))
    start = time.monotonic()
    clauses = intent_clauses(query)
    assert time.monotonic() - start < 3.0
    # Shape guard: a future "speedup" must not come from skipping the work —
    # 8000 bare atoms (no affirmative verb prefix) stay fully quoted out.
    assert clauses == []


@pytest.mark.parametrize(
    "cached, gate", [(False, "open"), (True, "fresh"), (True, "budget"), (True, "circuit")]
)
def test_guard_constraints_cover_llm_and_cache_fallbacks(tmp_path, cached, gate):
    instance = service(tmp_path)
    query = "do not use builtin/riper-workflow"
    candidates = [*_GUARDS, {"id": "other", "intent": "general coding"}]
    if cached:
        route = SkillRoute(
            skill_id="builtin/riper-workflow",
            confidence=0.9,
            layer=RoutingLayer.AI_TRIAGE,
            source="builtin",
        )
        instance._triage_cache.store(query, candidates, route.to_dict())
    if gate == "budget":
        instance._cost_tracker.get_monthly_cost.return_value = 99.0
    if gate == "circuit":
        instance._circuit_breaker.trip("fixture")
    result = instance.try_ai_triage(query, candidates)
    assert result is None or result.match.skill_id != "builtin/riper-workflow"


@pytest.mark.parametrize("negative", [False, True])
def test_changed_applicability_invalidates_positive_and_negative_cache(tmp_path, negative):
    cache = TriageCache(tmp_path)
    candidates = [{"id": "skill", "description": "any review", "intent": "review"}]
    route = SkillRoute(
        skill_id="skill", confidence=0.9, layer=RoutingLayer.AI_TRIAGE, source="builtin"
    ).to_dict()
    if negative:
        route["skill_id"] = None
    cache.store("query", candidates, route)
    changed = [{**candidates[0], "description": "ONLY review code; NOT documents"}]
    fresh, stale = cache.lookup("query", changed, ttl_hours=72)
    assert fresh is None and stale is not None
    assert service(tmp_path)._last_good_route(stale, changed) is None


def test_expired_unchanged_candidate_can_still_decay(tmp_path):
    cache = TriageCache(tmp_path)
    candidates = [{"id": "skill", "description": "review code"}]
    route = SkillRoute(
        skill_id="skill", confidence=0.9, layer=RoutingLayer.AI_TRIAGE, source="builtin"
    )
    cache.store("query", candidates, route.to_dict())
    payload = json.loads(cache.cache_path.read_text(encoding="utf-8"))
    payload[cache.key_for("query")]["ts"] = time.time() - 100 * 3600
    cache.cache_path.write_text(json.dumps(payload), encoding="utf-8")
    _, stale = cache.lookup("query", candidates, ttl_hours=72)
    result = service(tmp_path)._last_good_route(stale, candidates)
    assert result.confidence == pytest.approx(0.63)


@pytest.mark.parametrize(
    "query, allowed",
    [
        ("只拉取最新代码，不做评审", False),
        ("不要使用 adversarial-panel，只解释它的作用", False),
        ('解释 "拉取最新并进行对抗评审"', False),
        ("拉取最新代码并进行多路对抗评审", True),
    ],
)
def test_declarative_scope_and_negated_mentions_cover_fuzzy_fallback(tmp_path, query, allowed):
    candidates = [
        {
            "id": "builtin/adversarial-panel",
            "name": "adversarial-panel",
            "description": "Pull and review",
            "triggers": ["拉取最新"],
            "routing_requires_any": ["评审", "review", "对抗"],
        }
    ]
    instance = service(tmp_path)
    assert instance.has_explicit_guard_signal(query, candidates, candidates[0]["id"]) is allowed
    router = UnifiedRouter(project_root=tmp_path, config=RoutingConfig(enable_ai_triage=False))
    candidates = backed_candidates(tmp_path, candidates)
    router._candidate_manager.get_cached_candidates = lambda: candidates
    router._scenario_cache = {"strategies": [], "keywords": {}}
    result = router.route(query)
    if not allowed:
        assert not result.primary or result.primary.skill_id != candidates[0]["id"]
    assert (
        check_explicit_override("/builtin/adversarial-panel", candidates)[0] == candidates[0]["id"]
    )


def test_inactive_best_candidate_cannot_displace_affirmative_request(tmp_path):
    candidates = [
        {
            "id": "builtin/code-review",
            "name": "code-review",
            "triggers": ["review code"],
            "keywords": ["code-review", "review"],
            "description": "Review code",
        },
        {
            "id": "builtin/systematic-debugging",
            "name": "systematic-debugging",
            "triggers": ["debug"],
            "keywords": ["debug"],
            "description": "Debug parser",
        },
    ]
    router = UnifiedRouter(
        project_root=tmp_path,
        config=RoutingConfig(
            enable_ai_triage=False,
            keyword_match_max_chars=200,
            ai_triage_short_query_bypass_chars=200,
        ),
    )
    candidates = backed_candidates(tmp_path, candidates)
    router._candidate_manager.get_cached_candidates = lambda: candidates
    router._scenario_cache = {"strategies": [], "keywords": {}}
    result = router.route("不要使用 code-review，而是 debug parser")
    assert result.primary and result.primary.skill_id == "builtin/systematic-debugging"


def test_declared_keywords_and_scope_survive_real_discovery(tmp_path):
    from vibesop.core.routing.candidate_manager import CandidateManager

    root = tmp_path / "skills"
    source = root / "embedding" / "SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "---\nid: local/embedding\nname: embedding\ndescription: Choose an embedding model\n"
        "keywords: [Gemma2, MiniLM]\nrouting_requires_any: [embedding, 模型]\n---\n# Workflow\n",
        encoding="utf-8",
    )
    manager = CandidateManager(tmp_path)
    manager.pin_search_paths([root], enable_external=False)
    candidate = next(c for c in manager.get_cached_candidates() if c["id"] == "local/embedding")
    assert {"Gemma2", "MiniLM"} <= set(candidate["keywords"])
    assert candidate["routing_requires_any"] == ["embedding", "模型"]
    assert Path(candidate["source_file"]).resolve() == source.resolve()
