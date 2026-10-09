#!/usr/bin/env python3
"""E2E validation of the LLM routing path (runs inside docker/val-base image).

Validates the M2/M3 milestone behavior end-to-end with a real LLM
(DEEPSEEK_API_KEY must be set in the environment):

  T1  scenario-matching query (11 chars, project scenario vibesop_dev) ->
      AI triage must arbitrate (scenario short-circuit authority removed,
      force=True path).
  T2  identical repeat query -> persistent triage cache hit (2nd run skips LLM).
      The row is the one ``TriageCache.lookup`` actually received; a negative
      hit is a legal zero-call pass and is labeled as negative.
  T3  <system-reminder> junk query -> no-match, zero telemetry written.
  T4  stale cache entry + broken LLM endpoint -> last-good degradation.
      Without a positive row for the lookup query, this stays
      PRECONDITION_MISSING (fail), and does not rewrite the cache.
  T5  short non-scenario query -> recorded for observation.

``--controlled-lastgood`` is a separate harness. It never touches the live
``.vibe`` cache and never calls a live model. Its confidences are controlled
fixtures (``SkillRoute.to_dict`` → ``TriageCache.store``).

Usage (inside container, repo copy at /work):
    uv run --frozen python scripts/e2e_llm_routing.py --project-root /work
    uv run --frozen python scripts/e2e_llm_routing.py --controlled-lastgood
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

INCIDENT_QUERY = "全面审查这个仓库的代码质量"  # 13 chars — original scenario misfire case
# Scenario query whose target is a *builtin* skill, resolvable even in a
# minimal container candidate set (builtin skills only — no gstack/omx packs).
# All registry scenarios now fail closed without their declared primary_source
# pack (code_review pins gstack; the old builtin-resolvable 'planning' scenario
# was removed for over-triggering riper-workflow on generic plan/design
# queries). The remaining builtin-resolvable scenario is the project-level
# 'vibesop_dev' pattern from .vibe/skill-routing.yaml (tracked + mounted into
# the container): 改进路由 -> builtin/riper-workflow. That target is a guarded
# skill, but scenario bindings are user-declared intent and deliberately
# exempt from the guard (see TriageService.guarded_skill_name), so the
# scenario hit still demotes to a candidate and forces AI triage — the exact
# mechanism under test. Token-overlap index score for this query is ~0.05,
# far below threshold, so no index hit can pre-empt the scenario candidate.
SCENARIO_QUERY = "帮我改进路由的匹配逻辑"
JUNK_QUERY = "<system-reminder>Auto permission mode is active.</system-reminder>"


def _ensure_llm_config(project_root: Path, api_base: str = "") -> None:
    """Append/replace the [llm] section in .vibe/config.toml for DeepSeek."""
    config_path = project_root / ".vibe" / "config.toml"
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    # Drop an existing [llm] section (up to the next [section] header or EOF).
    lines = text.splitlines()
    out: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[llm]":
            skip = True
            continue
        if skip and stripped.startswith("["):
            skip = False
        if not skip:
            out.append(line)
    llm_section = [
        "",
        "[llm]",
        'provider = "deepseek"',
        'model = "deepseek-v4-flash"',
        # The CLI factory (vibesop.cli.main._build_llm_factory) only honors
        # provider/api_base from config when api_key is non-empty; otherwise
        # it falls back to env-only create_provider(). Write the key so the
        # config path is exercised (and T4's blackhole api_base takes effect).
        f'api_key = "{os.environ.get("DEEPSEEK_API_KEY", "")}"',
        f'api_base = "{api_base}"',
        "temperature = 0.0",
        "max_tokens = 512",
        "",
    ]
    config_path.write_text("\n".join(out + llm_section), encoding="utf-8")


def _build_router(project_root: Path):
    """Build a UnifiedRouter with the LLM factory injected (same as the CLI
    composition root in vibesop.cli.main). NOTE: scripts/replay_routing.py
    deliberately does NOT inject the factory (offline replay) — do not reuse it."""
    from vibesop.core.config import ConfigManager
    from vibesop.core.routing.unified import UnifiedRouter
    from vibesop.llm.triage_prompts import TriagePromptRegistry

    def llm_factory():
        # Mirror vibesop.cli.main._build_llm_factory exactly: config is
        # honored only when api_key is non-empty, else env-only fallback.
        from vibesop.core.llm_config import VibeSOPConfigManager
        from vibesop.llm.factory import create_provider

        llm_config = VibeSOPConfigManager.get_llm_config()
        if llm_config and llm_config.api_key:
            return create_provider(
                provider=llm_config.provider,
                api_key=llm_config.api_key,
                base_url=llm_config.api_base,
            )
        return create_provider()

    def prompt_builder(query: str, skills_summary: str, version: str) -> str:
        # Same wiring as vibesop.cli.main._build_prompt_builder — without it
        # the fallback one-liner prompt lets the LLM answer conversationally
        # instead of selecting a skill.
        return TriagePromptRegistry.render(
            query=query, skills_summary=skills_summary, version=version
        )

    config = ConfigManager(project_root=project_root).get_routing_config()
    return UnifiedRouter(
        project_root=project_root,
        config=config,
        llm_factory=llm_factory,
        prompt_builder=prompt_builder,
    )


def _triage_log_lines(project_root: Path) -> int:
    for name in ("ai_triage_log.jsonl",):
        path = project_root / ".vibe" / name
        if path.exists():
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return 0


def _analytics_lines(project_root: Path) -> int:
    path = project_root / ".vibe" / "analytics.jsonl"
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _read_cache(project_root: Path) -> dict:
    path = project_root / ".vibe" / "triage_cache.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _json_number(value: object) -> float | None:
    """Accept a real JSON number. bool is an int subclass and is not a confidence."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def install_lookup_observer(cache: Any) -> dict[str, Any]:
    """Record the query ``TriageCache.lookup`` actually receives, then delegate.

    The key is ``TriageCache.key_for`` of that argument. Callers must not
    recompute an augmented query or read ``RoutingResult.query`` instead.
    """
    captured: dict[str, Any] = {"reached": False, "query": None, "key": None, "calls": 0}
    original = cache.lookup

    def lookup(
        query: str,
        candidates: list[Any],
        ttl_hours: float,
    ) -> tuple[Any, Any]:
        captured["reached"] = True
        captured["calls"] = int(captured["calls"]) + 1
        captured["query"] = query
        captured["key"] = type(cache).key_for(query)
        return original(query, candidates, ttl_hours)

    cache.lookup = lookup
    return captured


def row_for_captured_key(cache: object, key: object) -> dict[str, Any] | None:
    """Return the one row stored at ``key``. Never scans other rows."""
    if not isinstance(cache, dict) or not isinstance(key, str) or not key:
        return None
    row = cache.get(key)
    return row if isinstance(row, dict) else None


def live_t4_precondition(row: object) -> str:
    """POSITIVE only for a skill id plus a real confidence. Never PASS."""
    if not isinstance(row, dict):
        return "PRECONDITION_MISSING"
    skill_id = row.get("skill_id")
    if not isinstance(skill_id, str) or not skill_id:
        return "PRECONDITION_MISSING"
    if _json_number(row.get("confidence")) is None:
        return "PRECONDITION_MISSING"
    return "POSITIVE"


def _cache_row_kind(row: object) -> str:
    if live_t4_precondition(row) == "POSITIVE":
        return "positive"
    if not isinstance(row, dict):
        return "missing"
    if row.get("skill_id") is None and _json_number(row.get("confidence")) is not None:
        return "negative"
    return "invalid"


def _snapshot_files(root: Path) -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    if not root.exists():
        return snap
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        snap[str(path.relative_to(root))] = path.read_bytes()
    return snap


def _restore_files(root: Path, snap: dict[str, bytes]) -> None:
    if root.exists():
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_symlink() or not path.is_file():
                continue
            if str(path.relative_to(root)) not in snap:
                path.unlink()
    for rel, data in snap.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def _discard_store(_query: object, _candidates: object, _route: object) -> None:
    """Identity probe must not persist a row."""
    return None


class _RaisingTransport:
    """Configured transport that fails before any network call."""

    def configured(self) -> bool:
        return True

    def call(self, *_args: object, **_kwargs: object) -> object:
        raise RuntimeError("controlled transport down")


# Diagnosis gate the controlled accept/reject pair is defined against.
# The oracle reads the router's actual min_confidence; this is only the
# RoutingConfig value handed to that router. RoutingConfig's default is untouched.
_CONTROLLED_GATE = 0.6


def _observe_query_key(root: Path, query: str) -> int:
    """Fresh-process lookup identity. Does not call the network or keep writes."""
    router = _build_router(root)
    cache = router._triage_service._triage_cache
    observed: dict[str, Any] = {"reached": False, "query": None, "key": None}
    if cache is not None:
        observed = install_lookup_observer(cache)
        cache.store = _discard_store
    router._llm = _RaisingTransport()
    result = router.route(query, record_telemetry=False)
    payload = {
        "reached": bool(observed.get("reached")),
        "query": observed.get("query"),
        "key": observed.get("key"),
        "result_query": result.query,
    }
    print("OBSERVE_RESULT " + json.dumps(payload, ensure_ascii=False))
    return 0


def _t4_child(root: Path, query: str) -> int:
    """One live route. The payload carries the lookup key, not a scanned confidence."""
    from vibesop.core.llm_config import VibeSOPConfigManager

    cfg = VibeSOPConfigManager.get_llm_config()
    print(
        f"T4_DEBUG llm_config={cfg.to_safe_dict() if cfg else None}",
        file=sys.stderr,
    )
    router = _build_router(root)
    cache = router._triage_service._triage_cache
    observed: dict[str, Any] = {"reached": False, "query": None, "key": None}
    if cache is not None:
        observed = install_lookup_observer(cache)
    llm = router._triage_service.init_llm_client()
    inner = getattr(llm, "_provider", llm)
    print(
        f"T4_DEBUG provider={type(llm).__name__} base_url={getattr(inner, 'base_url', '?')}",
        file=sys.stderr,
    )
    result = router.route(query)
    for detail in result.layer_details:
        print(
            f"T4_DEBUG layer={detail.layer.value} matched={detail.matched} reason={detail.reason}",
            file=sys.stderr,
        )
    payload = {
        "route": result.to_dict(),
        "captured_key": observed.get("key"),
        "captured_query": observed.get("query"),
        "lookup_reached": bool(observed.get("reached")),
        "result_query": result.query,
        "min_confidence": router._config.min_confidence,
        "marker": "live",
    }
    print("T4_RESULT " + json.dumps(payload, ensure_ascii=False))
    return 0


def _route_parts(route: object) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    body = route if isinstance(route, dict) else {}
    primary = body.get("primary") if isinstance(body.get("primary"), dict) else {}
    meta = primary.get("metadata") if isinstance(primary.get("metadata"), dict) else {}
    details = body.get("layer_details") if isinstance(body.get("layer_details"), list) else []
    triage = next(
        (item for item in details if isinstance(item, dict) and item.get("layer") == "ai_triage"),
        {},
    )
    if not isinstance(triage, dict):
        triage = {}
    return primary, meta, triage


def _decay_matches_row(
    route: dict[str, Any],
    row: dict[str, Any],
    min_confidence: float,
) -> tuple[bool, float | None, float | None, str]:
    """Accept/reject using the captured row's confidence and the router's gate."""
    from vibesop.core.routing.triage_service import LAST_GOOD_CONFIDENCE_DECAY

    primary, meta, triage = _route_parts(route)
    original = _json_number(row.get("confidence"))
    gate = _json_number(min_confidence)
    skill_id = row.get("skill_id")
    if original is None or gate is None or not isinstance(skill_id, str) or not skill_id:
        return False, original, None, "PRECONDITION_MISSING row is not a positive confidence"
    decayed = original * LAST_GOOD_CONFIDENCE_DECAY
    accepted = decayed >= gate
    reason = str(triage.get("reason") or "")
    fired = triage.get("matched") is True and skill_id in reason
    scenario_fallback = meta.get("scenario_fallback") is True
    last_good = meta.get("last_good") is True
    if accepted:
        recorded = _json_number(meta.get("last_good_original_confidence"))
        primary_confidence = _json_number(primary.get("confidence"))
        confidence_ok = (
            primary_confidence is not None
            and math.isfinite(primary_confidence)
            and math.isfinite(decayed)
            and abs(primary_confidence - decayed) <= 1e-9
        )
        skill_ok = primary.get("skill_id") == skill_id
        ok = (
            fired
            and last_good
            and not scenario_fallback
            and recorded is not None
            and abs(recorded - original) <= 1e-9
            and skill_ok
            and confidence_ok
        )
    else:
        # Scenario fallback owns primary.confidence; do not require the decay number.
        ok = fired and scenario_fallback and not last_good
    detail = (
        f"skill={primary.get('skill_id')} layer={primary.get('layer')} "
        f"original={original} decayed={decayed} min_confidence={gate} "
        f"accepted={accepted} last_good={meta.get('last_good')} "
        f"scenario_fallback={meta.get('scenario_fallback')} triage={triage.get('reason')}"
    )
    return ok, original, decayed, detail


def _spawn_json(root: Path, flag: str, query: str, prefix: str) -> dict[str, Any] | None:
    proc = subprocess.run(
        [sys.executable, __file__, "--project-root", str(root), flag, query],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=root,
        check=False,
    )
    line = next((item for item in proc.stdout.splitlines() if item.startswith(prefix)), None)
    if line is None:
        return None
    payload = json.loads(line[len(prefix) :])
    return payload if isinstance(payload, dict) else None


def _run_live_t4(root: Path, record: Any) -> None:
    """Classify the lookup row before any cache write. Stage only a positive row."""
    name = "T4 last-good decay vs configured min_confidence"
    vibe = root / ".vibe"
    snap = _snapshot_files(vibe)
    try:
        observed = _spawn_json(root, "--observe-query-key", SCENARIO_QUERY, "OBSERVE_RESULT ")
    finally:
        _restore_files(vibe, snap)
    if not observed or not observed.get("reached"):
        record(name, False, "PRECONDITION_MISSING lookup not reached")
        return
    row = row_for_captured_key(_read_cache(root), observed.get("key"))
    if live_t4_precondition(row) != "POSITIVE":
        record(
            name,
            False,
            f"PRECONDITION_MISSING cache_row={_cache_row_kind(row)} "
            f"captured_key={observed.get('key')}",
        )
        return

    staged_key = observed.get("key")
    try:
        entries = _read_cache(root)
        if not isinstance(staged_key, str) or staged_key not in entries:
            record(name, False, "PRECONDITION_MISSING staged key missing before mutation")
            return
        entries[staged_key]["candidates_hash"] = "deadbeefdeadbeef"
        (root / ".vibe" / "triage_cache.json").write_text(json.dumps(entries), encoding="utf-8")
        cache_dir = root / ".vibe" / "cache"
        if cache_dir.exists():
            for leftover in cache_dir.glob("cache_*.json"):
                leftover.unlink()
        _ensure_llm_config(root, api_base="http://127.0.0.1:9")
        payload = _spawn_json(root, "--t4-query", SCENARIO_QUERY, "T4_RESULT ")
        if payload is None:
            record(name, False, "no T4_RESULT")
            return
        if not payload.get("lookup_reached"):
            record(name, False, "PRECONDITION_MISSING child lookup not reached")
            return
        child_key = payload.get("captured_key")
        child_row = row_for_captured_key(_read_cache(root), child_key)
        if live_t4_precondition(child_row) != "POSITIVE" or not isinstance(child_row, dict):
            record(
                name,
                False,
                f"PRECONDITION_MISSING child cache_row={_cache_row_kind(child_row)} "
                f"captured_key={child_key}",
            )
            return
        route = payload.get("route") if isinstance(payload.get("route"), dict) else {}
        gate = _json_number(payload.get("min_confidence"))
        if gate is None:
            record(name, False, "PRECONDITION_MISSING min_confidence missing")
            return
        ok, _original, _decayed, detail = _decay_matches_row(route, child_row, gate)
        if child_key != staged_key:
            ok = False
            detail = f"captured_key mismatch staged={staged_key} child={child_key} {detail}"
        record(name, ok, f"captured_key={child_key} {detail}")
    finally:
        _ensure_llm_config(root)


def _write_skill(root: Path, skill_id: str, description: str) -> dict[str, str]:
    path = root / "skills" / skill_id.replace("/", "-") / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {skill_id}\nname: Dummy\ndescription: {description}\n---\n# dummy\n",
        encoding="utf-8",
    )
    return {
        "id": skill_id,
        "description": description,
        "namespace": "builtin",
        "source_file": str(path),
    }


def _positive_route_dict(
    skill_id: str,
    confidence: float,
    description: str,
    source_file: Path,
) -> dict[str, Any]:
    from vibesop.core.models import RoutingLayer, SkillRoute

    return SkillRoute(
        skill_id=skill_id,
        confidence=confidence,
        layer=RoutingLayer.AI_TRIAGE,
        source="builtin",
        description=description,
        metadata={"source_file": str(source_file)},
    ).to_dict()


def _controlled_router(root: Path) -> tuple[Any, float]:
    from vibesop.core.config.manager import RoutingConfig
    from vibesop.core.routing.unified import UnifiedRouter

    router = UnifiedRouter(
        project_root=root,
        config=RoutingConfig(
            enable_ai_triage=True,
            min_confidence=_CONTROLLED_GATE,
            session_aware=False,
        ),
    )
    router._llm = _RaisingTransport()
    return router, float(router._config.min_confidence)


def _route_controlled(
    router: Any,
    query: str,
    candidates: list[dict[str, str]],
    context: Any = None,
) -> Any:
    from unittest.mock import patch

    from vibesop.core.models import LayerDetail, RoutingLayer, SkillRoute

    source = next(item["source_file"] for item in candidates if item["id"] == "builtin/commit")
    scenario = SkillRoute(
        skill_id="builtin/commit",
        confidence=0.9,
        layer=RoutingLayer.SCENARIO,
        source="builtin",
        description="Commit code",
        metadata={"scenario": "commit", "source_file": source},
    )
    scenario_detail = LayerDetail(
        layer=RoutingLayer.SCENARIO,
        matched=True,
        reason="Scenario matched: commit",
    )
    index_detail = LayerDetail(
        layer=RoutingLayer.SEMANTIC_INDEX,
        matched=False,
        reason="controlled index miss",
    )
    with (
        patch(
            "vibesop.core.routing._layers.try_scenario_layer",
            return_value=(scenario, scenario_detail),
        ),
        patch(
            "vibesop.core.routing._layers.try_index_layer",
            return_value=(None, index_detail),
        ),
    ):
        return router.route(query, candidates=candidates, context=context, record_telemetry=False)


def _controlled_base(root: Path) -> list[dict[str, str]]:
    root.mkdir(parents=True, exist_ok=True)
    return [
        _write_skill(root, "builtin/review", "Review code"),
        _write_skill(root, "builtin/commit", "Commit code"),
    ]


def _controlled_case(
    root: Path,
    case: str,
    *,
    query: str,
    stores: list[tuple[str, float]],
    negative: bool = False,
    expect_no_last_good: bool = False,
    context: Any = None,
    other_query: str | None = None,
) -> dict[str, Any]:
    """Stale a real store by adding a candidate, then let UnifiedRouter consume it."""
    from vibesop.core.routing.triage_cache import TriageCache
    from vibesop.core.routing.triage_service import LAST_GOOD_CONFIDENCE_DECAY

    base = _controlled_base(root)
    review_path = Path(base[0]["source_file"])
    router, gate = _controlled_router(root)
    cache = router._triage_service._triage_cache
    assert cache is not None
    if negative:
        router._triage_service._store_negative(query, base)
    for stored_query, confidence in stores:
        cache.store(
            stored_query,
            base,
            _positive_route_dict("builtin/review", confidence, "Review code", review_path),
        )
    extra = _write_skill(root, "builtin/extra", "extra")
    observed = install_lookup_observer(cache)
    result = _route_controlled(router, query, [*base, extra], context)
    disk = _read_cache(root)
    row = row_for_captured_key(disk, observed.get("key"))
    route = result.to_dict()
    primary, meta, _triage = _route_parts(route)
    if expect_no_last_good:
        ok = (
            bool(observed.get("reached"))
            and meta.get("last_good") is not True
            and meta.get("scenario_fallback") is True
            and "last_good_original_confidence" not in meta
            and (row is None or row.get("skill_id") is None)
        )
        original = None
        decayed = None
    else:
        ok, original, decayed, _detail = (
            _decay_matches_row(route, row, gate)
            if isinstance(row, dict)
            else (False, None, None, "")
        )
    other_original = None
    if other_query is not None:
        other = row_for_captured_key(disk, TriageCache.key_for(other_query))
        other_original = None if other is None else _json_number(other.get("confidence"))
    stored_hash = None if not isinstance(row, dict) else row.get("candidates_hash")
    detail = (
        f"original={original} other_original={other_original} decayed={decayed} "
        f"min_confidence={gate} last_good={meta.get('last_good')} "
        f"scenario_fallback={meta.get('scenario_fallback')} "
        f"skill={primary.get('skill_id')} captured_key={observed.get('key')}"
    )
    return {
        "case": case,
        "ok": bool(ok),
        "marker": "controlled",
        "confidence_source": "controlled_fixture",
        "located_by": "captured_key",
        "detail": detail,
        "original": original,
        "other_original": other_original,
        "decayed": decayed,
        "min_confidence": gate,
        "router_min_confidence": gate,
        "scenario_fallback": meta.get("scenario_fallback"),
        "last_good": meta.get("last_good"),
        "stored_candidates_hash": stored_hash,
        "decay_constant": LAST_GOOD_CONFIDENCE_DECAY,
        "route": route,
        "row": row,
    }


def controlled_same_skill_two_query(root: Path) -> dict[str, Any]:
    """Two queries, one skill, .8 and .9. The oracle must return the .8 row."""
    query = "提交代码"
    other = "另一条正常查询"
    return _controlled_case(
        root,
        "same-skill-two-query",
        query=query,
        stores=[(query, 0.8), (other, 0.9)],
        other_query=other,
    )


def _context_history(root: Path) -> tuple[str, str]:
    from vibesop.core.conversation import ConversationContext
    from vibesop.core.memory import MemoryManager

    memory = MemoryManager(storage_dir=root / ".vibe" / "memory")
    conversation = memory.create_conversation()
    memory.add_user_message(conversation.id, "prior request from persistent memory")
    history = ConversationContext(
        conversation.id,
        storage_dir=root / ".vibe" / "conversations",
    )
    history.add_turn("analyze deterministic router architecture", "builtin/review")
    return "继续", conversation.id


def _routing_context(conversation_id: str) -> Any:
    from vibesop.core.matching import RoutingContext

    return RoutingContext(conversation_id=conversation_id)


def controlled_context_key(root: Path) -> dict[str, Any]:
    """Lookup query, raw prompt, and RoutingResult.query stay three different strings."""
    from vibesop.core.routing.triage_cache import TriageCache

    base = _controlled_base(root)
    raw, conversation_id = _context_history(root)
    snap = _snapshot_files(root / ".vibe")
    probe, _gate = _controlled_router(root)
    probe_cache = probe._triage_service._triage_cache
    assert probe_cache is not None
    probe_obs = install_lookup_observer(probe_cache)
    probe_cache.store = _discard_store
    _route_controlled(probe, raw, base, _routing_context(conversation_id))
    discovered = probe_obs.get("query")
    _restore_files(root / ".vibe", snap)

    router, gate = _controlled_router(root)
    cache = router._triage_service._triage_cache
    assert cache is not None
    review_path = Path(base[0]["source_file"])
    cache.store(
        raw,
        base,
        _positive_route_dict("builtin/review", 0.8, "Review code", review_path),
    )
    if isinstance(discovered, str):
        cache.store(
            discovered,
            base,
            _positive_route_dict("builtin/review", 0.9, "Review code", review_path),
        )
    extra = _write_skill(root, "builtin/extra", "extra")
    observed = install_lookup_observer(cache)
    result = _route_controlled(router, raw, [*base, extra], _routing_context(conversation_id))
    disk = _read_cache(root)
    row = row_for_captured_key(disk, observed.get("key"))
    route = result.to_dict()
    ok, original, decayed, detail = (
        _decay_matches_row(route, row, gate) if isinstance(row, dict) else (False, None, None, "")
    )
    raw_key = TriageCache.key_for(raw)
    result_key = TriageCache.key_for(result.query)
    decoy = row_for_captured_key(disk, raw_key)
    identity_ok = (
        isinstance(discovered, str)
        and observed.get("query") == discovered
        and observed.get("query") != raw
        and observed.get("query") != result.query
        and raw != result.query
        and observed.get("key") == TriageCache.key_for(discovered)
        and observed.get("key") != raw_key
        and observed.get("key") != result_key
        and isinstance(decoy, dict)
        and _json_number(decoy.get("confidence")) == 0.8
        and original is not None
        and abs(original - 0.9) <= 1e-9
    )
    return {
        "case": "context-key",
        "ok": bool(ok and identity_ok),
        "marker": "controlled",
        "confidence_source": "controlled_fixture",
        "located_by": "captured_key",
        "detail": (
            f"{detail} raw_query={raw!r} result_query={result.query!r} "
            f"captured_query={observed.get('query')!r}"
        ),
        "original": original,
        "decayed": decayed,
        "min_confidence": gate,
        "router_min_confidence": gate,
        "captured_query": observed.get("query"),
        "raw_query": raw,
        "result_query": result.query,
        "captured_key": observed.get("key"),
        "row_key": observed.get("key"),
        "raw_key_in_cache": raw_key in disk,
        "result_query_key_in_cache": result_key in disk,
        "decoy_original": None if decoy is None else _json_number(decoy.get("confidence")),
        "route": route,
        "row": row,
    }


def _controlled_outcomes(root: Path) -> list[dict[str, Any]]:
    from vibesop.core.routing.triage_service import LAST_GOOD_CONFIDENCE_DECAY

    query = "提交代码"
    boundary = _CONTROLLED_GATE / LAST_GOOD_CONFIDENCE_DECAY
    return [
        _controlled_case(root / "accept", "accept", query=query, stores=[(query, 0.9)]),
        _controlled_case(root / "reject", "reject", query=query, stores=[(query, 0.8)]),
        _controlled_case(
            root / "equality",
            "equality",
            query=query,
            stores=[(query, boundary)],
        ),
        _controlled_case(
            root / "negative",
            "negative",
            query=query,
            stores=[],
            negative=True,
            expect_no_last_good=True,
        ),
        _controlled_case(
            root / "no-entry",
            "no-entry",
            query=query,
            stores=[],
            expect_no_last_good=True,
        ),
        controlled_same_skill_two_query(root / "same-skill-two-query"),
        controlled_context_key(root / "context-key"),
    ]


def run_controlled_lastgood() -> int:
    """Independent last-good contract. Temporary directory only; no live cache."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="vibesop-b8-controlled-") as tmp:
        outcomes = _controlled_outcomes(Path(tmp))
    failed = 0
    for outcome in outcomes:
        ok = bool(outcome["ok"])
        failed += not ok
        print(
            f"{'PASS' if ok else 'FAIL'}  controlled {outcome['case']}  "
            f"marker=controlled confidence_source=controlled_fixture {outcome['detail']}"
        )
    total = len(outcomes)
    print(f"CONTROLLED SUMMARY: {total - failed}/{total} passed marker=controlled")
    print("LIVE SUMMARY: not run; controlled mode is independent of live wiring")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default="/work")
    parser.add_argument(
        "--controlled-lastgood",
        action="store_true",
        help="run the controlled last-good contract in a temp directory; "
        "does not call a live model or touch the project cache",
    )
    parser.add_argument(
        "--t4-query",
        default=None,
        help="internal: run a single query in a fresh process (T4 staging) "
        "and print the result as JSON on the last stdout line",
    )
    parser.add_argument(
        "--observe-query-key",
        default=None,
        help="internal: print the query TriageCache.lookup receives for one route",
    )
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    if args.controlled_lastgood:
        return run_controlled_lastgood()
    if args.observe_query_key is not None:
        return _observe_query_key(root, args.observe_query_key)

    if not os.getenv("DEEPSEEK_API_KEY"):
        print("FATAL: DEEPSEEK_API_KEY not set")
        return 2

    if args.t4_query is not None:
        # Fresh-process single-route mode: LLM provider config is read at
        # process start, so T4's blackhole endpoint is only honored here.
        return _t4_child(root, args.t4_query)

    _ensure_llm_config(root)
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)

    router = _build_router(root)

    # ---- T0: LLM wiring must be live (guard against silent offline runs) ----
    llm = router._triage_service.init_llm_client()
    record(
        "T0 LLM client configured (real LLM e2e)",
        llm is not None and llm.configured(),
        f"provider={type(llm).__name__ if llm else None}",
    )

    # ---- T1: scenario-matching query must force AI triage + real LLM call ----
    log_before = _triage_log_lines(root)
    t0 = time.perf_counter()
    r1 = router.route(SCENARIO_QUERY)
    d1 = time.perf_counter() - t0
    log_after = _triage_log_lines(root)
    path1 = [layer.value for layer in r1.routing_path]
    primary1 = r1.primary.skill_id if r1.primary else None
    layer1 = r1.primary.layer.value if r1.primary else None
    triage_ran = "ai_triage" in path1
    record(
        "T1 scenario query forces AI triage + real LLM call",
        triage_ran and r1.primary is not None and log_after > log_before,
        f"skill={primary1} layer={layer1} path={path1} {d1:.1f}s "
        f"triage_log {log_before}->{log_after}",
    )

    # ---- T1b: original incident query (observation; scenario target is a
    # user-scope skill absent in the minimal container candidate set) ----
    r1b = router.route(INCIDENT_QUERY)
    record(
        "T1b incident query (observation)",
        True,
        f"skill={r1b.primary.skill_id if r1b.primary else None} "
        f"layer={r1b.primary.layer.value if r1b.primary else None}",
    )

    # ---- T2: identical repeat on a FRESH router -> cache row for this lookup ----
    router_b = _build_router(root)  # new process-level state: memory cache empty
    t2_cache = router_b._triage_service._triage_cache
    t2_obs = (
        install_lookup_observer(t2_cache)
        if t2_cache is not None
        else {"reached": False, "query": None, "key": None}
    )
    log_before = _triage_log_lines(root)
    t0 = time.perf_counter()
    r2 = router_b.route(SCENARIO_QUERY)
    d2 = time.perf_counter() - t0
    log_after = _triage_log_lines(root)
    t2_row = row_for_captured_key(_read_cache(root), t2_obs.get("key"))
    t2_kind = _cache_row_kind(t2_row)
    meta2 = (r2.primary.metadata if r2.primary else {}) or {}
    same_skill = (r2.primary.skill_id if r2.primary else None) == primary1
    zero_calls = log_after == log_before and bool(t2_obs.get("reached"))
    if t2_kind == "negative" and zero_calls:
        t2_ok = True
        t2_hit = "positive_persistent_hit=false"
    elif (
        t2_kind == "positive"
        and zero_calls
        and meta2.get("persistent_cache") is True
        and same_skill
        and isinstance(t2_row, dict)
        and r2.primary is not None
        and r2.primary.skill_id == t2_row.get("skill_id")
    ):
        t2_ok = True
        t2_hit = "positive_persistent_hit=true"
    else:
        t2_ok = False
        t2_hit = "positive_persistent_hit=false"
    record(
        "T2 repeat query: captured-key cache row, zero LLM calls",
        t2_ok,
        f"cache_row={t2_kind} {t2_hit} captured_key={t2_obs.get('key')} "
        f"persistent_cache={meta2.get('persistent_cache')} "
        f"recall_method={meta2.get('recall_method')} {d2:.1f}s vs {d1:.1f}s "
        f"triage_log {log_before}->{log_after}",
    )

    # ---- T3: junk query -> no match, no telemetry ----
    before = _analytics_lines(root)
    r3 = router.route(JUNK_QUERY)
    after = _analytics_lines(root)
    record(
        "T3 junk query rejected without telemetry",
        not r3.has_match and after == before,
        f"has_match={r3.has_match} analytics {before}->{after}",
    )

    # ---- T4: positive row required before any cache mutation ----
    try:
        _run_live_t4(root, record)
    except Exception:
        record(
            "T4 last-good decay vs configured min_confidence",
            False,
            "PRECONDITION_MISSING " + traceback.format_exc(limit=2),
        )
        _ensure_llm_config(root)

    # ---- T5: short non-scenario query (observation only) ----
    r5 = router.route("提交代码")
    path5 = [layer.value for layer in r5.routing_path]
    record(
        "T5 short query routed (observation)",
        True,
        f"skill={r5.primary.skill_id if r5.primary else None} path={path5}",
    )

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{'=' * 60}\nE2E SUMMARY: {len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
