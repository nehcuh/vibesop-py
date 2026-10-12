#!/usr/bin/env python3
"""Frozen, checkout-only candidate-recall experiment (never an injection test).

Examples:
  uv run python scripts/eval_hybrid_recall.py --freeze-only --output-dir /tmp/recall
  uv run --extra semantic python scripts/eval_hybrid_recall.py --snapshot /tmp/recall/snapshot.json --output-dir /tmp/recall --model minilm
  # Gemma2 additionally requires transformers 5.19 + ST[image] in the experiment env.

No LLM call, no full-router verdict, no false-injection claim. Generated files go
only to the explicitly chosen output directory; all runtime state uses a temp cwd.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

EXTRAS = [
    {
        "query": "拉取最新代码，只拉取，不做评审",
        "expect": [],
        "reject": ["builtin/adversarial-panel"],
        "category": "intent_negative",
    },
    {
        "query": "请解释‘riper workflow’是什么意思",
        "expect": [],
        "reject": ["builtin/riper-workflow"],
        "category": "intent_negative",
    },
    {
        "query": "do not run riper workflow; explain the name",
        "expect": [],
        "reject": ["builtin/riper-workflow"],
        "category": "intent_negative",
    },
    {
        "query": "有人说“收工了”，请翻译这句话",
        "expect": [],
        "reject": ["builtin/session-end"],
        "category": "intent_negative",
    },
    {
        "query": "不必收工了，继续修复代码",
        "expect": [],
        "reject": ["builtin/session-end"],
        "category": "intent_negative",
    },
    {
        "query": "the article explains herd instinct in markets",
        "expect": [],
        "reject": ["builtin/instinct"],
        "category": "intent_negative",
    },
    {
        "query": "run riper workflow without changing APIs",
        "expect": ["builtin/riper-workflow"],
        "category": "intent_positive",
    },
    {
        "query": "pull latest and run a multi-lane independent adversarial review",
        "expect": ["builtin/adversarial-panel"],
        "category": "intent_positive",
    },
    {
        "query": "帮我执行benchpack/quokka-todo，记录下一步任务",
        "expect": ["benchpack/quokka-todo"],
        "category": "identifier_positive",
    },
    {
        "query": "请做wombat-snapshot，然后再修改工作区",
        "expect": ["benchpack/wombat-snapshot"],
        "category": "identifier_positive",
    },
    {
        "query": "首先拉取最新代码，然后深入评审；清理非主分支，并分析 Hybrid Search + BM25 技能选择",
        "expect": ["builtin/deep-diagnosis-optimization", "builtin/adversarial-panel"],
        "category": "multi_intent_positive",
    },
]
MODEL_IDS = {
    "minilm": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "gemma2": "google/embeddinggemma-2",
}
MODEL_REVISIONS = {
    "minilm": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
    "gemma2": "914f7f89142e33e77833254d9c9b90c3cef7303b",
}
SOURCE_FILES = [
    "src/vibesop/core/routing/lexical_recall.py",
    "src/vibesop/core/routing/triage_recall.py",
    "src/vibesop/core/routing/triage_service.py",
    "src/vibesop/core/routing/intent_constraints.py",
    "src/vibesop/core/routing/candidate_manager.py",
    "src/vibesop/core/skills/parser.py",
    "src/vibesop/spec/models.py",
]


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value.replace(b"\r\n", b"\n")).hexdigest()


def freeze(
    repo: Path, out: Path, extra_candidates: Path | None = None, extra_queries: Path | None = None
) -> dict[str, Any]:
    import yaml

    from vibesop.core.config import RoutingConfig
    from vibesop.core.matching.tokenizers import DEFAULT_STOP_WORDS
    from vibesop.core.routing.triage_recall import EmbeddingRecall
    from vibesop.core.routing.unified import UnifiedRouter
    from vibesop.core.skills import SkillLoader

    roots = [repo / "core/skills", repo / "tests/fixtures/benchmark-pack"]
    dataset = repo / "tests/benchmark/routing_eval.yaml"
    rows = yaml.safe_load(dataset.read_text(encoding="utf-8")) + EXTRAS
    fixture_inputs = {}
    additions = []
    if extra_candidates:
        additions = yaml.safe_load(extra_candidates.read_text(encoding="utf-8"))
        if not isinstance(additions, list) or not all(
            isinstance(c, dict) and isinstance(c.get("id"), str) and c.get("description")
            for c in additions
        ):
            raise ValueError("Extra candidates must be a list of metadata with id and description")
        fixture_inputs["extra_candidates"] = digest(extra_candidates.read_bytes())
    if extra_queries:
        additional_rows = yaml.safe_load(extra_queries.read_text(encoding="utf-8"))
        if not isinstance(additional_rows, list) or not all(
            isinstance(r, dict) and isinstance(r.get("query"), str) for r in additional_rows
        ):
            raise ValueError("Extra queries must be a list with query strings")
        rows += additional_rows
        fixture_inputs["extra_queries"] = digest(extra_queries.read_bytes())
    with tempfile.TemporaryDirectory(prefix="vibesop-recall-") as temp:
        old_cwd = Path.cwd()
        os.chdir(temp)
        try:
            router = UnifiedRouter(
                project_root=temp,
                config=RoutingConfig(enable_ai_triage=False, enable_embedding=False),
            )
            router._candidate_manager.pin_search_paths(roots, enable_external=False)
            pinned = SkillLoader(
                project_root=temp,
                search_paths=roots,
                strict_search_paths=True,
                enable_external=False,
            )
            discovered_ids = sorted(pinned.discover_all())
            candidates, _ = router._candidate_manager.filter_routable(
                router._candidate_manager.get_cached_candidates()
            )
            candidates = sorted(candidates, key=lambda c: str(c["id"]))
            for addition in additions:
                candidate = dict(addition)
                candidate.setdefault("name", candidate["id"].rsplit("/", maxsplit=1)[-1])
                for key in ("triggers", "keywords", "scenarios", "routing_requires_any"):
                    candidate.setdefault(key, [])
                candidate.setdefault("management_only", False)
                candidate.setdefault("disable_model_invocation", False)
                candidate["source_file"] = "fixture:extra_candidates"
                candidate["fixture_metadata_only"] = True
                candidates.append(candidate)
            if len({c["id"] for c in candidates}) != len(candidates):
                raise ValueError("Candidate IDs must remain unique across both corpora")
            candidates.sort(key=lambda c: str(c["id"]))
            raw = [
                c
                for c in candidates
                if not c.get("management_only") and not c.get("disable_model_invocation")
            ]
            for row in rows:
                row["applicable_ids"] = sorted(
                    str(c["id"])
                    for c in router.triage_service.applicable_candidates(row["query"], candidates)
                )
                row["guard_removed_ids"] = sorted(
                    {str(c["id"]) for c in raw} - set(row["applicable_ids"])
                )
            for c in candidates:
                if not c.get("fixture_metadata_only"):
                    c["source_file"] = Path(c["source_file"]).relative_to(repo).as_posix()
                c["embedding_text"] = EmbeddingRecall._candidate_text(c)
                c.pop("priority", None)  # cold-start policy does not enter recall text/eligibility.
        finally:
            os.chdir(old_cwd)
    skills = {
        str(p.relative_to(repo)): digest(p.read_bytes())
        for root in roots
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink() and p.suffix.lower() in {".md", ".yaml", ".yml"}
    }
    snapshot = {
        "schema_version": 1,
        "posture": {
            "strict_search_paths": True,
            "enable_external": False,
            "llm": "never_called",
            "project_cwd": "fresh_tmp",
            "roots": [str(p.relative_to(repo)) for p in roots],
            "stress_metadata_fixture_candidates": len(additions),
        },
        "discovered_ids": discovered_ids,
        "candidates": candidates,
        "rows": rows,
        "skills_content_hashes": skills,
        "dataset_sha256": digest(dataset.read_bytes()),
        "fixture_inputs": fixture_inputs,
        "lexical_stop_words": sorted(DEFAULT_STOP_WORDS),
        "source_hashes": {p: digest((repo / p).read_bytes()) for p in SOURCE_FILES},
    }
    snapshot["fingerprint"] = digest(canonical(snapshot))
    (out / "snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for relative in SOURCE_FILES:
        target = out / "production-source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repo / relative).read_bytes())
    return snapshot


def summarize(details: list[dict[str, Any]], stages: list[str]) -> dict[str, Any]:
    positives = [r for r in details if r["positive_resolvable"]]
    result: dict[str, Any] = {
        "positive_queries_total": sum(r["is_positive"] for r in details),
        "positive_queries_resolvable_automatic": len(positives),
        "positive_queries_unresolvable_or_governance_excluded": [
            r["query"] for r in details if r["is_positive"] and not r["positive_resolvable"]
        ],
        "negative_or_reject_only_queries": sum(not r["is_positive"] for r in details),
        "guard_target_assertions": sum(len(r["reject"]) for r in details),
        "guard_target_rejections": sum(
            len(set(r["reject"]) & set(r["guard_removed_ids"])) for r in details
        ),
    }
    for stage in stages:
        metrics = {}
        for method in ("dense", "bm25", "union", "rrf"):
            ranks = [
                min(
                    (
                        r[stage][method].index(sid) + 1
                        for sid in r["expect"]
                        if sid in r[stage][method]
                    ),
                    default=None,
                )
                for r in positives
            ]
            metrics[method] = {
                f"recall_at_{k}": sum(rank is not None and rank <= k for rank in ranks)
                for k in (5, 10, 20)
            }
            metrics[method]["mrr_at_20"] = (
                sum(1 / rank if rank is not None and rank <= 20 else 0 for rank in ranks)
                / len(ranks)
                if ranks
                else None
            )
        result[stage] = metrics
    result["guarded_small_pool_bypass_queries"] = sum(
        len(r["applicable_ids"]) <= 20 for r in details
    )
    result["positive_expected_ids_lost_to_constraints"] = [
        {
            "query": r["query"],
            "expected": r["expect"],
            "removed_targets": sorted(set(r["expect"]) & set(r["guard_removed_ids"])),
        }
        for r in positives
        if not set(r["expect"]) & set(r["applicable_ids"])
    ]
    result["targeted_negative_details"] = [
        {
            "query": r["query"],
            "reject": r["reject"],
            "removed_targets": sorted(set(r["reject"]) & set(r["guard_removed_ids"])),
        }
        for r in details
        if r["reject"]
    ]
    result["guard_target_assertions_auto_resolvable"] = sum(
        len(r["automatic_reject_targets"]) for r in details
    )
    result["reject_targets_outside_automatic_universe"] = [
        {
            "query": r["query"],
            "targets": sorted(set(r["reject"]) - set(r["automatic_reject_targets"])),
        }
        for r in details
        if set(r["reject"]) - set(r["automatic_reject_targets"])
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        if (Path(__file__).resolve().parent.parent / "pyproject.toml").exists()
        else Path.cwd(),
    )
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument(
        "--extra-candidates",
        type=Path,
        help="Fixed synthetic metadata stress corpus; explicitly separate from injectable skills.",
    )
    parser.add_argument(
        "--extra-queries",
        type=Path,
        help="Fixed gold query dataset; content hashes enter snapshot fingerprint.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--model", choices=MODEL_IDS, default="minilm")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Allow first model download; otherwise use cached fixed revision offline.",
    )
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    repo = args.repo.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(repo / "src"))
    if args.snapshot and (args.extra_candidates or args.extra_queries):
        parser.error("Extra corpora are frozen once; do not combine --snapshot with extra inputs")
    snapshot = (
        json.loads(args.snapshot.read_text(encoding="utf-8"))
        if args.snapshot
        else freeze(repo, out, args.extra_candidates, args.extra_queries)
    )
    stored_fingerprint = snapshot["fingerprint"]
    if (
        digest(canonical({k: v for k, v in snapshot.items() if k != "fingerprint"}))
        != stored_fingerprint
    ):
        raise ValueError("Snapshot content changed after freezing")
    if args.freeze_only:
        print(
            json.dumps(
                {
                    "fingerprint": stored_fingerprint,
                    "discovered_candidates": len(snapshot["candidates"]),
                    "automatic_candidates": sum(
                        not c.get("management_only") and not c.get("disable_model_invocation")
                        for c in snapshot["candidates"]
                    ),
                    "queries": len(snapshot["rows"]),
                },
                indent=2,
            )
        )
        return 0
    # Guard decisions are frozen in the snapshot. Ranking helpers must match that
    # source exactly; changing production code requires a fresh snapshot for both arms.
    # Use the production source captured at freeze, so active implementation
    # work cannot silently change one model arm. The candidate text projection
    # is frozen in each entry; the copied helper invokes that exact projection.
    source_root = args.snapshot.parent if args.snapshot else out
    frozen_helper = source_root / "production-source" / SOURCE_FILES[0]
    if digest(frozen_helper.read_bytes()) != snapshot["source_hashes"][SOURCE_FILES[0]]:
        raise ValueError("Frozen production BM25/RRF source hash mismatch")
    module_spec = importlib.util.spec_from_file_location(
        "vibesop_frozen_lexical_recall", frozen_helper
    )
    if module_spec is None or module_spec.loader is None:
        raise ValueError("Frozen production helper cannot be loaded")
    helper = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(helper)

    class FrozenTextProjection:
        @staticmethod
        def _candidate_text(candidate: dict[str, Any]) -> str:
            return str(candidate["embedding_text"])

    helper.EmbeddingRecall = FrozenTextProjection
    helper.DEFAULT_STOP_WORDS = set(snapshot.get("lexical_stop_words", helper.DEFAULT_STOP_WORDS))
    bm25_recall = helper.bm25_recall
    fuse_rankings = helper.fuse_rankings
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(args.threads)
    kwargs: dict[str, Any] = {
        "device": "cpu",
        "local_files_only": not args.download,
        "revision": MODEL_REVISIONS[args.model],
        "model_kwargs": {"dtype": torch.float32},
    }
    if args.model == "gemma2":
        kwargs["config_kwargs"] = {"vision_config": None, "audio_config": None}
    start = time.perf_counter()
    model = SentenceTransformer(MODEL_IDS[args.model], **kwargs)
    load_seconds = time.perf_counter() - start
    if args.model == "gemma2":
        model.max_seq_length = 8192
    candidates = [
        c
        for c in snapshot["candidates"]
        if not c.get("management_only") and not c.get("disable_model_invocation")
    ]
    ids = [str(c["id"]) for c in candidates]
    lookup = {str(c["id"]): c for c in candidates}
    positions = {sid: i for i, sid in enumerate(ids)}
    texts = [c["embedding_text"] for c in candidates]
    doc_kwargs = {"normalize_embeddings": True, "show_progress_bar": False, "batch_size": 16}
    query_kwargs = dict(doc_kwargs)
    if args.model == "gemma2":
        texts = [f"title: {sid} | text: {text}" for sid, text in zip(ids, texts, strict=True)]
        # The title-bearing Document prompt is already serialized above. The
        # named Document prompt would prepend "title: none | text: " again.
        # Explicitly disable additional/default prompts, preserving the inputs
        # of the recorded experiment (fixed config default_prompt_name=None).
        doc_kwargs["prompt"] = ""
        query_kwargs["prompt_name"] = "SearchQuery"
    token_lengths = [len(model.tokenizer.encode(text)) for text in texts]
    start = time.perf_counter()
    dv = np.asarray(model.encode(texts, **doc_kwargs), dtype=np.float32)
    document_seconds = time.perf_counter() - start
    rows = snapshot["rows"]
    start = time.perf_counter()
    qv = np.asarray(model.encode([r["query"] for r in rows], **query_kwargs), dtype=np.float32)
    query_batch_seconds = time.perf_counter() - start
    if not np.isfinite(dv).all() or not np.isfinite(qv).all():
        raise ValueError("Non-finite model embeddings")
    warm = []
    for row in rows:
        start = time.perf_counter()
        model.encode(row["query"], **query_kwargs)
        warm.append((time.perf_counter() - start) * 1000)
    reports = {}
    for dimension in [384] if args.model == "minilm" else [768, 256]:
        docs = dv[:, :dimension]
        docs = docs / np.linalg.norm(docs, axis=1, keepdims=True)
        qs = qv[:, :dimension]
        qs = qs / np.linalg.norm(qs, axis=1, keepdims=True)
        stages = ["raw", "guarded"] + (
            ["raw_minilm_floor_025", "guarded_minilm_floor_025"] if args.model == "minilm" else []
        )
        details = []
        lexical_ms = []
        fusion_ms = []
        for row, sims in zip(rows, qs @ docs.T, strict=True):
            expect = list(row.get("expect") or [])
            reject = list(row.get("reject") or [])
            negative = (
                row.get("category") in {"must_not_inject", "near_miss", "intent_negative"}
                or row.get("subclass") == "near_miss"
                or not expect
            )
            detail = {
                "query": row["query"],
                "category": row.get("category"),
                "expect": expect,
                "reject": reject,
                "is_positive": bool(expect) and not negative,
                "positive_resolvable": bool(expect)
                and not negative
                and bool(set(expect) & set(ids)),
                "applicable_ids": row["applicable_ids"],
                "guard_removed_ids": row["guard_removed_ids"],
                "raw_top_cosine": float(max(sims)),
                "negative_label": negative,
            }
            detail["automatic_reject_targets"] = sorted(set(reject) & set(ids))
            for stage in stages:
                pool = (
                    [lookup[sid] for sid in row["applicable_ids"]]
                    if stage.startswith("guarded")
                    else candidates
                )
                ranked = sorted(
                    (str(c["id"]) for c in pool),
                    key=lambda sid: (-float(sims[positions[sid]]), sid),
                )[:20]
                dense = (
                    [sid for sid in ranked if float(sims[positions[sid]]) >= 0.25]
                    if stage.endswith("025")
                    else ranked
                )
                start = time.perf_counter()
                lexical = bm25_recall(row["query"], pool, 20)
                lexical_ms.append((time.perf_counter() - start) * 1000)
                start = time.perf_counter()
                fused = fuse_rankings(dense, lexical, top_n=20)
                fusion_ms.append((time.perf_counter() - start) * 1000)
                union = list(dict.fromkeys(dense + lexical))
                detail[stage] = {"dense": dense, "bm25": lexical, "union": union, "rrf": fused}
            details.append(detail)
        reports[str(dimension)] = {
            "summary": summarize(details, stages),
            "details": details,
            "lexical_call_p50_p95_ms": [
                float(np.percentile(lexical_ms, 50)),
                float(np.percentile(lexical_ms, 95)),
            ],
            "fusion_call_p50_p95_ms": [
                float(np.percentile(fusion_ms, 50)),
                float(np.percentile(fusion_ms, 95)),
            ],
        }
    metadata = {
        "snapshot_fingerprint": stored_fingerprint,
        "universe_posture": snapshot["posture"],
        "automatic_candidates": len(ids),
        "queries": len(rows),
        "model_id": MODEL_IDS[args.model],
        "revision": MODEL_REVISIONS[args.model],
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("sentence-transformers", "transformers", "torch", "numpy")
        },
        "hardware": platform.platform(),
        "device": "cpu",
        "dtype": "float32",
        "threads": args.threads,
        "max_seq_length": model.max_seq_length,
        "encoding_roles": {
            "model_default_prompt_name": model.default_prompt_name,
            "document": (
                {"format": "title: {skill_id} | text: {embedding_text}", "additional_prompt": ""}
                if args.model == "gemma2"
                else {"format": "{embedding_text}", "additional_prompt": None}
            ),
            "query": {"prompt_name": query_kwargs.get("prompt_name")},
        },
        "model_parameters": sum(p.numel() for p in model.parameters()),
        "load_seconds": load_seconds,
        "document_encoding_seconds": document_seconds,
        "query_batch_encoding_seconds": query_batch_seconds,
        "warm_query_p50_p95_ms": [float(np.percentile(warm, 50)), float(np.percentile(warm, 95))],
        "dense_threshold": "uncalibrated raw ranks; MiniLM current 0.25 additionally reported only for MiniLM",
        "limitations": [
            "Candidate recall and admission guards only; no LLM, full-router selection, injection or false-injection rate.",
            "Positive denominator includes only automatic-universe-resolvable targets; excluded queries explicitly listed.",
            "Union is unranked dense-first enumeration of up to40 IDs: recall@20 reflects that enumeration, not an optimized union selector; union_membership_at_up_to40 is reported separately.",
            "Pools<=20 make top20 recall trivial and productionprefilter bypasses ranking there; assess top5/top10 and explicit larger-pool regression tests.",
            "Single-host exploratory CPU timing; warm latencies exclude imports/download and include query-length distribution.",
        ],
    }
    metadata["documents_exceeding_model_token_limit"] = sum(
        n > model.max_seq_length for n in token_lengths
    )
    metadata["document_token_median_max"] = [float(np.median(token_lengths)), max(token_lengths)]
    metadata["fixture_inputs"] = snapshot.get("fixture_inputs", {})
    metadata["production_source_hashes"] = snapshot["source_hashes"]
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        metadata["peak_process_rss_bytes"] = peak if sys.platform == "darwin" else peak * 1024
    except ImportError:
        metadata["peak_process_rss_bytes"] = None
    for result in reports.values():
        positives = [r for r in result["details"] if r["positive_resolvable"]]
        for stage in stages:
            result["summary"][stage]["union_membership_at_up_to40"] = sum(
                bool(set(r["expect"]) & set(r[stage]["union"])) for r in positives
            )
    payload = {"metadata": metadata, "results": reports}
    (out / (args.model + ".json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"metadata": metadata, "summaries": {dim: r["summary"] for dim, r in reports.items()}},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
