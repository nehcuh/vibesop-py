#!/usr/bin/env python3
"""E2E validation of the LLM routing path (runs inside docker/val-base image).

Validates the M2/M3 milestone behavior end-to-end with a real LLM
(DEEPSEEK_API_KEY must be set in the environment):

  T1  scenario-matching query (11 chars, project scenario vibesop_dev) ->
      AI triage must arbitrate (scenario short-circuit authority removed,
      force=True path).
  T2  identical repeat query -> persistent triage cache hit (2nd run skips LLM).
  T3  <system-reminder> junk query -> no-match, zero telemetry written.
  T4  stale cache entry + broken LLM endpoint -> last-good degradation.
  T5  short non-scenario query -> recorded for observation.

Usage (inside container, repo copy at /work):
    uv run --frozen python scripts/e2e_llm_routing.py --project-root /work
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default="/work")
    parser.add_argument(
        "--t4-query",
        default=None,
        help="internal: run a single query in a fresh process (T4 staging) "
        "and print the result as JSON on the last stdout line",
    )
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    if not os.getenv("DEEPSEEK_API_KEY"):
        print("FATAL: DEEPSEEK_API_KEY not set")
        return 2

    if args.t4_query is not None:
        # Fresh-process single-route mode: LLM provider config is read at
        # process start, so T4's blackhole endpoint is only honored here.
        from vibesop.core.llm_config import VibeSOPConfigManager

        cfg = VibeSOPConfigManager.get_llm_config()
        print(
            f"T4_DEBUG llm_config={cfg.to_safe_dict() if cfg else None}",
            file=sys.stderr,
        )
        router = _build_router(root)
        llm = router._triage_service.init_llm_client()
        inner = getattr(llm, "_provider", llm)
        print(
            f"T4_DEBUG provider={type(llm).__name__} base_url={getattr(inner, 'base_url', '?')}",
            file=sys.stderr,
        )
        r = router.route(args.t4_query)
        for d in r.layer_details:
            print(f"T4_DEBUG layer={d.layer.value} matched={d.matched} reason={d.reason}", file=sys.stderr)
        payload = {
            "skill": r.primary.skill_id if r.primary else None,
            "layer": r.primary.layer.value if r.primary else None,
            "meta": (r.primary.metadata if r.primary else {}) or {},
            "details": [
                {"layer": d.layer.value, "matched": d.matched, "reason": d.reason}
                for d in r.layer_details
            ],
        }
        print("T4_RESULT " + json.dumps(payload, ensure_ascii=False))
        return 0

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

    # ---- T2: identical repeat on a FRESH router -> persistent cache hit ----
    router_b = _build_router(root)  # new process-level state: memory cache empty
    log_before = _triage_log_lines(root)
    t0 = time.perf_counter()
    r2 = router_b.route(SCENARIO_QUERY)
    d2 = time.perf_counter() - t0
    log_after = _triage_log_lines(root)
    cache = _read_cache(root)
    meta2 = (r2.primary.metadata if r2.primary else {}) or {}
    same_skill = (r2.primary.skill_id if r2.primary else None) == primary1
    record(
        "T2 repeat query: persistent cache hit, zero LLM calls",
        same_skill and len(cache) >= 1 and log_after == log_before,
        f"entries={len(cache)} persistent_cache={meta2.get('persistent_cache')} "
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

    # ---- T4: stale cache + broken LLM -> last-good ----
    try:
        cache_path = root / ".vibe" / "triage_cache.json"
        entries = _read_cache(root)
        if not entries:
            record("T4 last-good on stale entry + LLM down", False, "cache empty, cannot stage")
        else:
            for entry in entries.values():
                entry["candidates_hash"] = "deadbeefdeadbeef"  # force all entries stale
            cache_path.write_text(json.dumps(entries), encoding="utf-8")
            # Pre-M4a the triage "memory cache" was disk-backed via
            # CacheManager and would short-circuit this staging; M4a removed
            # that path, but clear any legacy files so old caches can never
            # interfere with the LLM failure path being exercised here.
            cache_dir = root / ".vibe" / "cache"
            if cache_dir.exists():
                for f in cache_dir.glob("cache_*.json"):
                    f.unlink()
            _ensure_llm_config(root, api_base="http://127.0.0.1:9")  # blackhole
            # LLM provider config is read at process start, so the blackhole
            # endpoint only takes effect in a fresh process (true CLI semantics).
            proc = subprocess.run(
                [sys.executable, __file__, "--project-root", str(root), "--t4-query", SCENARIO_QUERY],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=root,
                check=False,
            )
            result_line = next(
                (line for line in proc.stdout.splitlines() if line.startswith("T4_RESULT ")),
                None,
            )
            if result_line is None:
                record(
                    "T4 last-good on stale entry + LLM down",
                    False,
                    f"no T4_RESULT (rc={proc.returncode}): {proc.stdout[-300:]} {proc.stderr[-300:]}",
                )
            else:
                payload = json.loads(result_line[len("T4_RESULT "):])
                meta4 = payload["meta"]
                expected = {e.get("skill_id") for e in cache.values()}
                # M4a semantics: last-good fires at triage level with a 0.7
                # confidence decay (0.82 -> 0.57), which the min_confidence
                # gate then rejects (stale results must not auto-execute), so
                # the demoted scenario fallback wins the final route.
                triage_detail = next(
                    (d for d in payload["details"] if d["layer"] == "ai_triage"),
                    {},
                )
                last_good_fired = (
                    triage_detail.get("matched") is True
                    and any(s in triage_detail.get("reason", "") for s in expected)
                )
                final_is_scenario_fallback = meta4.get("scenario_fallback") is True
                record(
                    "T4 last-good fires (decayed) + scenario fallback wins",
                    last_good_fired and final_is_scenario_fallback,
                    f"skill={payload['skill']} layer={payload['layer']} "
                    f"triage={triage_detail.get('reason')} "
                    f"scenario_fallback={meta4.get('scenario_fallback')}",
                )
            _ensure_llm_config(root)  # restore working endpoint
    except Exception:
        record("T4 last-good on stale entry + LLM down", False, traceback.format_exc(limit=2))
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
