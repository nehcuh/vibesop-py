"""gate36 阶段二 — promote shadow verifier (D1, 修订 A/B/D/J/K).

A non-blocking "灯, 不是闸" for ``vibe skill promote``: after a draft is
materialized, replay the cluster's queries against the draft's declared
triggers and report a DESCRIPTIVE verdict — which queries the draft would
catch, which it would miss (with the nearest trigger for each miss), and
which installed skills' triggers it would contend with. The badge has two
levels only — PASS / WARN, NO fail level, NEVER blocks activation, and the
activate path never needs ``--force`` for the verifier (修订 A/J).

What it measures — and what it does NOT: the badge answers "触发召回"
(would the draft's triggers recall the very pattern that produced it?),
NOT "内容质量" (is the SKILL.md body any good?). Lane C's objection
(verifier issuing a false pass to an empty shell) is absorbed by making
that scope explicit in every badge rendering (CLI + dashboard).

Trigger-side semantics (修订 B): the containment rule is the PRODUCTION
one, extracted as ``triage_service.query_matches_triggers`` from
``has_explicit_guard_signal`` (lowercase + apostrophe-stripped, NO
whitespace folding, NO length floor, first-hit-wins). The guarded-only
``explicit_guarded_skill_match`` is deliberately NOT used — the guarded
set only recognizes table-listed ids (riper/session-end), so a draft id
would never match and the trigger side would silently no-op.

Embedding side: two INDEPENDENT lines, each fail-open (修订 B 细化):

- recall line: ``EmbeddingRecall._candidate_text`` semantics over the
  draft (id + description + intent + triggers), floor 0.25
  (``DEFAULT_MIN_SIMILARITY``);
- index line: ``SkillIndexer._compute_profile_text`` semantics
  (triggers are the only deterministic pre-LLM profile field, gate32 A2)
  with the SEMANTIC_INDEX fallback gates — 0.45 absolute floor
  (``index_embedding_threshold`` default) + top1-vs-top2 margin
  (``index_embedding_min_margin`` default) against the loaded skill
  index catalog when available.

The model handle is a MODULE-LEVEL SINGLETON (the real
paraphrase-multilingual-MiniLM-L12-v2 load costs 10-12s; per-call
construction is banned). Any line whose model/encode fails is marked
``unavailable``; an unavailable line does not participate in the verdict
and the overall badge is at most WARN(degraded) — degraded runs NEVER
emit PASS (修订 J 细化).

Capture denominator (修订 J): cluster queries hitting the gate35 prefix
predicate ``_has_agent_prompt_prefix`` (agent-echo rows) are legitimate
pool members (gate32 A1 — bd1bc217 was promoted from such a cluster) but
are EXCLUDED from the shadow denominator; the lint "≥1 representative
query" check uses the same denominator (lint 与 shadow 同口径).

Verdict schema (修订 A 细化): embeds the sha256 of the CURRENT draft file
bytes (never ``ClusterCandidate.draft_sha256``, which is a frozen
generation-time baseline that survives edits) + a trigger-set hash +
``RULESET_VERSION`` + the pipeline inventory that actually ran +
per-line results + detail.

Privacy (修订 D): verdicts land in the INITIATING project's
``.vibe/observability/promote_verdicts.jsonl``; verdicts for
``scope="global"`` drafts store counts + truncated query hashes only,
never raw query text (M12 M5 boundary); project-scope text fields pass
through ``sanitize_body_text``. Capacity: keep the most recent
``MAX_VERDICTS`` rows or ``VERDICT_TTL_DAYS`` days (仓内轮转惯例).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from vibesop.core.observability.skill_promote import (
    ClusterCandidate,
    _has_agent_prompt_prefix,
    _is_agent_prompt_shape,
    sanitize_body_text,
)
from vibesop.core.routing.triage_recall import (
    DEFAULT_MIN_SIMILARITY,
    MODEL_NAME,
    EmbeddingRecall,
    _cosine_similarity,
)
from vibesop.core.routing.triage_service import query_matches_triggers

logger = logging.getLogger(__name__)

__all__ = [
    "RULESET_VERSION",
    "PromoteVerdict",
    "PromoteVerdictStore",
    "verify_draft",
]

# Bumped whenever the verdict semantics change, so a future ≥30-verdict
# threshold discussion never mixes rulesets (修订 B: 攒 ≥30 条后的阈值
# 讨论才不吃非生产数字).
RULESET_VERSION = "gate36-r1"

# Index-line gates mirror the RoutingConfig defaults used by the
# SEMANTIC_INDEX embedding fallback (_layers.py): absolute floor
# ``index_embedding_threshold`` (0.45) + top1/top2 margin
# ``index_embedding_min_margin`` (0.05). Pinned by tests against the
# config defaults so a config re-calibration surfaces here.
_INDEX_GATE = 0.45
_INDEX_MIN_MARGIN = 0.05

MAX_VERDICTS = 200
VERDICT_TTL_DAYS = 90

_MAX_HIJACK_ENTRIES = 20

Scope = Literal["project", "global"]

# ---------------------------------------------------------------------------
# Embedding model — module-level singleton (修订 A 细化: 真模型 10–12s/次,
# 不得每次新建). Sticky failure mirrors ``EmbeddingRecall._get_model``.
# ---------------------------------------------------------------------------
_MODEL_STATE: dict[str, Any] = {"model": None, "failed": False}
_MODEL_LOCK = threading.Lock()


def _get_embedding_model() -> Any | None:
    """Lazy module-level singleton; None when unavailable (fail-open)."""
    with _MODEL_LOCK:
        if _MODEL_STATE["model"] is not None or _MODEL_STATE["failed"]:
            return _MODEL_STATE["model"]
        try:
            from sentence_transformers import (
                SentenceTransformer,  # pyright: ignore[reportMissingImports]
            )

            _MODEL_STATE["model"] = SentenceTransformer(MODEL_NAME)
        except Exception as e:  # missing dep / no network / OOM — all fail-open
            logger.debug("promote verifier: embedding model unavailable: %s", e)
            _MODEL_STATE["failed"] = True
            return None
        return _MODEL_STATE["model"]


def _encode(model: Any, texts: list[str]) -> list[list[float]]:
    raw = model.encode(texts, show_progress_bar=False)
    return [v.tolist() if hasattr(v, "tolist") else list(v) for v in raw]


def _query_hash(text: str) -> str:
    """Full-sha256 query reference for global-scope verdicts (pi-3 收敛:
    对齐 M5 边界的哈希强度 —— 存全量; 展示层需要短显时在渲染侧截断)."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _token_jaccard(a: str, b: str) -> float:
    """Whitespace-token Jaccard over lowercased text (nearest-trigger detail).

    Deterministic and model-free — the nearest-neighbor detail must be
    computable in degraded environments too (embedding unavailable).
    """
    sa, sb = set(str(a).lower().split()), set(str(b).lower().split())
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def _nearest_trigger(query: str, triggers: list[str]) -> tuple[str | None, float]:
    """Closest declared trigger to a missed query, by token Jaccard.

    Returns (None, 0.0) when no trigger shares a single token — an honest
    "no neighbor" beats a misleading argmax over zeros.
    """
    best: str | None = None
    best_score = 0.0
    for trigger in triggers:
        score = _token_jaccard(query, trigger)
        if score > best_score:
            best, best_score = str(trigger), score
    return best, best_score


@dataclass
class PromoteVerdict:
    """One shadow-verifier verdict (one JSONL line in the verdict store).

    ``embedding`` / ``shadow`` / ``hijack`` / ``lint`` are plain dicts —
    the schema is descriptive, not contractual, and ``from_dict`` must
    tolerate missing keys (bad-line policy like the other observability
    stores). For ``scope="global"`` the query text fields inside
    ``shadow``/``embedding``/``hijack`` carry ``query_hash`` entries
    instead of raw text (修订 D) — the redaction happens at CONSTRUCTION
    time in ``verify_draft``, so the stored object never holds raw
    cross-project queries.
    """

    cluster_id: str
    skill_id: str
    scope: str
    phase: str  # "promote" | "activate-rerun"
    badge: str  # "PASS" | "WARN" — two levels only, never FAIL
    degraded: bool  # True when any embedding line was unavailable
    draft_sha256: str  # sha256 of the CURRENT draft file bytes
    trigger_set_sha256: str
    ruleset_version: str
    created_at: datetime | None = None
    pipelines: list[str] = field(default_factory=list)
    lint: dict[str, Any] = field(default_factory=dict)
    shadow: dict[str, Any] = field(default_factory=dict)
    embedding: dict[str, Any] = field(default_factory=dict)
    hijack: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat() if self.created_at else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PromoteVerdict:
        """Tolerant deserialization — missing keys fall back to defaults."""
        payload = dict(d)
        raw = payload.get("created_at")
        if isinstance(raw, str):
            try:
                parsed = datetime.fromisoformat(raw)
                payload["created_at"] = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                payload["created_at"] = None
        elif raw is None:
            payload["created_at"] = None
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in payload.items() if k in known})


class PromoteVerdictStore:
    """JSONL store for promote verdicts (``promote_verdicts.jsonl``).

    Same conventions as ``DiscoverySignalStore`` / ``ClusterCandidateStore``:
    ``threading.Lock`` + cross-process ``fcntl`` (``cross_process_lock``
    fallback), malformed lines skipped on read, atomic temp+rename
    rewrites. Capacity policy: on append, drop rows older than
    ``VERDICT_TTL_DAYS`` and keep at most the most recent ``MAX_VERDICTS``
    rows (append-only between compactions).
    """

    FILENAME = "promote_verdicts.jsonl"

    def __init__(self, storage_dir: Path | str) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / self.FILENAME
        self._lock = threading.Lock()

    def append(self, verdict: PromoteVerdict, *, now: datetime | None = None) -> PromoteVerdict:
        """Append one verdict, then enforce TTL + count capacity."""
        now = now or datetime.now(UTC)
        with self._lock:
            try:
                import fcntl
            except ImportError:
                from vibesop.utils.file_lock import cross_process_lock

                with cross_process_lock(self._path):
                    self._do_append(verdict, now)
                return verdict
            with self._path.open("a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    self._do_append(verdict, now)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return verdict

    def _do_append(self, verdict: PromoteVerdict, now: datetime) -> None:
        """Caller MUST hold threading.Lock + cross-process lock."""
        rows = self._read_all_locked()
        rows.append(verdict)
        cutoff = now - timedelta(days=VERDICT_TTL_DAYS)
        rows = [r for r in rows if r.created_at is None or r.created_at >= cutoff]
        if len(rows) > MAX_VERDICTS:
            rows = rows[-MAX_VERDICTS:]
        from vibesop.utils.atomic_writer import AtomicWriter

        writer = AtomicWriter()
        with writer.atomic_open(self._path, "w") as f:
            for r in rows:
                f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

    def list_all(self) -> list[PromoteVerdict]:
        """Every row in insertion order; malformed lines skipped."""
        if not self._path.exists():
            return []
        return self._parse_lines(self._path)

    def _read_all_locked(self) -> list[PromoteVerdict]:
        if not self._path.exists():
            return []
        return self._parse_lines(self._path)

    @staticmethod
    def _parse_lines(path: Path) -> list[PromoteVerdict]:
        out: list[PromoteVerdict] = []
        with path.open("r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    out.append(PromoteVerdict.from_dict(d))
                except (json.JSONDecodeError, ValueError, TypeError):
                    logger.debug("skipping malformed verdict line %d in %s", lineno, path)
                    continue
        return out

    def for_cluster(self, cluster_id: str) -> list[PromoteVerdict]:
        """All verdicts for one cluster, oldest first."""
        return [v for v in self.list_all() if v.cluster_id == cluster_id]

    def latest_for_cluster(
        self,
        cluster_id: str,
        *,
        draft_sha256: str | None = None,
        prefer_complete: bool = False,
    ) -> PromoteVerdict | None:
        """Most recent verdict for a cluster, optionally pinned to a draft hash.

        ``prefer_complete`` (修订 A 细化): a degraded activate-rerun appends
        a new row but must NOT shadow the complete promote-time verdict —
        display prefers a non-degraded match when one exists.
        """
        rows = self.for_cluster(cluster_id)
        if draft_sha256 is not None:
            rows = [v for v in rows if v.draft_sha256 == draft_sha256]
        if not rows:
            return None
        if prefer_complete:
            complete = [v for v in rows if not v.degraded]
            if complete:
                rows = complete
        return max(rows, key=lambda v: v.created_at or datetime.min.replace(tzinfo=UTC))


def _extract_draft_frontmatter(draft_bytes: bytes) -> dict[str, Any]:
    """Parse the draft's YAML frontmatter via the production parser."""
    try:
        from vibesop.core.skills.parser import extract_frontmatter

        frontmatter, _ = extract_frontmatter(draft_bytes.decode("utf-8"))
        return frontmatter if isinstance(frontmatter, dict) else {}
    except Exception as e:  # unparseable draft → lint warns, never raises
        logger.debug("promote verifier: frontmatter parse failed: %s", e)
        return {}


def _redact_query(text: str, scope: Scope) -> dict[str, str]:
    """Query reference for verdict detail: hash-only for global (修订 D)."""
    if scope == "global":
        return {"query_hash": _query_hash(text)}
    return {"query": sanitize_body_text(text)}


def verify_draft(
    candidate: ClusterCandidate,
    draft_path: Path | str,
    *,
    scope: Scope = "project",
    phase: str = "promote",
    installed_candidates: list[dict[str, Any]] | None = None,
    index_profiles: dict[str, Any] | None = None,
    embedding_model: Any | None = None,
    store: PromoteVerdictStore | None = None,
) -> PromoteVerdict:
    """Shadow-verify a promoted draft against its own cluster. Never raises.

    Parameters
    ----------
    candidate:
        The promoted ``ClusterCandidate`` (cluster queries are the replay
        corpus; status is not checked — the caller owns the lifecycle).
    draft_path:
        Path to the CURRENT SKILL.md draft; its bytes are hashed into the
        verdict (修订 A 细化: never ``ClusterCandidate.draft_sha256``).
    scope:
        ``"global"`` redacts raw queries to hashes in the stored verdict.
    phase:
        ``"promote"`` (initial diagnosis) or ``"activate-rerun"`` (修订 A).
    installed_candidates:
        Live routing catalog (``CandidateManager.get_candidates()`` shape)
        for the hijack analysis; None skips it (recorded, fail-open).
    index_profiles:
        ``SkillIndexer.load_index()`` output for the index-line margin
        gate; None/empty skips the margin (recorded as
        ``skipped-no-catalog``).
    embedding_model:
        DI seam for tests; None resolves the module-level singleton
        (which is None under the conftest stub → both lines unavailable).
    store:
        When given, the verdict is appended (double-locked, capacity
        enforced).
    """
    draft_path = Path(draft_path)
    warnings: list[str] = []
    pipelines: list[str] = []

    try:
        draft_bytes = draft_path.read_bytes()
    except OSError:
        draft_bytes = b""
        warnings.append(f"draft file unreadable: {draft_path}")
    draft_sha256 = hashlib.sha256(draft_bytes).hexdigest()

    frontmatter = _extract_draft_frontmatter(draft_bytes) if draft_bytes else {}
    raw_triggers = frontmatter.get("triggers") or []
    triggers = (
        [str(t) for t in raw_triggers if str(t).strip()] if isinstance(raw_triggers, list) else []
    )
    trigger_set_sha256 = hashlib.sha256(
        json.dumps(sorted(triggers), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    # 标集口径 (修订 J): agent-echo rows (gate35 prefix predicate) are
    # legitimate pool members but stay OUT of the capture denominator.
    all_queries = [str(q) for q in candidate.queries]
    denominator = [q for q in all_queries if not _has_agent_prompt_prefix(q)]
    echo_excluded = len(all_queries) - len(denominator)

    # --- 1) trigger lint (static) -------------------------------------
    pipelines.append("trigger_lint")
    lint_checks = {
        "triggers_nonempty": bool(triggers),
        "triggers_not_all_hygiene": bool(triggers)
        and not all(_is_agent_prompt_shape(t) for t in triggers),
        "representative_query_caught": any(
            query_matches_triggers(q, triggers) is not None for q in denominator
        ),
    }
    lint_warnings: list[str] = []
    if not lint_checks["triggers_nonempty"]:
        lint_warnings.append("draft declares no triggers (TODO placeholder?)")
    elif not lint_checks["triggers_not_all_hygiene"]:
        lint_warnings.append("every trigger is a hygiene/agent-prompt shape")
    if denominator and not lint_checks["representative_query_caught"]:
        lint_warnings.append("no representative cluster query matches any trigger")
    if not denominator:
        lint_warnings.append("capture denominator is empty (all cluster queries are agent-echo)")
    warnings.extend(lint_warnings)

    # --- 2) shadow replay (dynamic, trigger containment) ---------------
    pipelines.append("shadow_replay")
    caught: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    for q in denominator:
        hit = query_matches_triggers(q, triggers)
        if hit is not None:
            caught.append({**_redact_query(q, scope), "trigger": sanitize_body_text(hit)})
        else:
            nearest, score = _nearest_trigger(q, triggers)
            missed.append(
                {
                    **_redact_query(q, scope),
                    "nearest_trigger": sanitize_body_text(nearest) if nearest else None,
                    "nearest_score": round(score, 4),
                }
            )
    shadow = {
        "denominator": len(denominator),
        "echo_excluded": echo_excluded,
        "caught": caught,
        "missed": missed,
        "all_caught": bool(denominator) and not missed,
    }

    # --- 3) hijack analysis (production containment vs installed catalog)
    # Same idea as replay_routing_baseline.build_hit_hijack_risks (a
    # would-fire target different from the observed winner), but with
    # PRODUCTION containment semantics and against trigger collisions:
    # any installed skill whose trigger also matches a query the draft
    # catches is a contention risk once the draft is activated.
    if installed_candidates is None:
        hijack = {"status": "skipped", "entries": []}
    else:
        pipelines.append("hijack")
        own_id = str(candidate.source_skill_id or "")
        others = [
            (str(c.get("id", "")), [str(t) for t in (c.get("triggers") or [])])
            for c in installed_candidates
            if str(c.get("id", "")) and str(c.get("id", "")) != own_id
        ]
        entries: list[dict[str, Any]] = []
        for q in denominator:
            if query_matches_triggers(q, triggers) is None:
                continue  # draft would not fire here — nothing to hijack
            for other_id, other_triggers in others:
                hit = query_matches_triggers(q, other_triggers)
                if hit is not None:
                    entries.append(
                        {
                            **_redact_query(q, scope),
                            "competing_skill_id": other_id,
                            "competing_trigger": sanitize_body_text(hit),
                        }
                    )
                    break  # first competitor per query is enough detail
            if len(entries) >= _MAX_HIJACK_ENTRIES:
                break
        hijack = {"status": "ok", "entries": entries}

    # --- 4) embedding lines (each fail-open; singleton model) ----------
    model = embedding_model if embedding_model is not None else _get_embedding_model()
    embedding = {
        "recall": _embedding_recall_line(
            model, frontmatter, triggers, denominator, scope, pipelines
        ),
        "index": _embedding_index_line(
            model, triggers, denominator, index_profiles, scope, pipelines
        ),
    }

    # --- 5) badge (修订 J 细化: PASS 需 lint 全过 + shadow 全捕获 + 两
    # embedding 线均可用且过门; 其余一切 WARN; 无 FAIL, 降级永不 PASS) ---
    # pi-4/claude-3 收敛: degraded 只由 "unavailable" (模型/环境不可用)
    # 触发; "skipped" (draft 无 triggers 可嵌) 是内容态而非降级态 ——
    # badge 同样 WARN (all_accepted=None → index_ok False), 但展示层
    # 不应打 "embedding 线不可用" 文案.
    lint_ok = not lint_warnings
    recall_ok = embedding["recall"]["status"] == "ok" and embedding["recall"]["all_caught"]
    index_ok = embedding["index"]["status"] == "ok" and embedding["index"]["all_accepted"]
    degraded = "unavailable" in (
        embedding["recall"]["status"],
        embedding["index"]["status"],
    )
    badge = "PASS" if (lint_ok and shadow["all_caught"] and recall_ok and index_ok) else "WARN"

    verdict = PromoteVerdict(
        cluster_id=candidate.cluster_id,
        skill_id=str(candidate.source_skill_id or frontmatter.get("id") or ""),
        scope=scope,
        phase=phase,
        badge=badge,
        degraded=degraded,
        draft_sha256=draft_sha256,
        trigger_set_sha256=trigger_set_sha256,
        ruleset_version=RULESET_VERSION,
        created_at=datetime.now(UTC),
        pipelines=pipelines,
        lint={"checks": lint_checks, "warnings": lint_warnings},
        shadow=shadow,
        embedding=embedding,
        hijack=hijack,
        warnings=warnings,
    )
    if store is not None:
        store.append(verdict)
    return verdict


def _embedding_recall_line(
    model: Any | None,
    frontmatter: dict[str, Any],
    triggers: list[str],
    denominator: list[str],
    scope: Scope,
    pipelines: list[str],
) -> dict[str, Any]:
    """Recall line: ``EmbeddingRecall._candidate_text`` semantics, floor 0.25."""
    if model is None:
        return {"status": "unavailable", "floor": DEFAULT_MIN_SIMILARITY, "all_caught": None}
    candidate_dict = {
        "id": str(frontmatter.get("id", "")),
        "description": str(frontmatter.get("description", "")),
        "intent": str(frontmatter.get("intent", "")),
        "triggers": triggers,
        "keywords": frontmatter.get("tags") or [],
        "scenarios": [],
    }
    try:
        profile_text = EmbeddingRecall._candidate_text(candidate_dict)
        vectors = _encode(model, [profile_text, *denominator])
        profile_vec, query_vecs = vectors[0], vectors[1:]
        results = []
        # pi-1/claude-8 收敛: 结果循环也在 try 内 —— 行为异常的模型
        # (错长/参差向量, zip strict / cosine 抛错) 只降级本线, 不得穿出
        # verify_draft.
        for q, vec in zip(denominator, query_vecs, strict=True):
            sim = _cosine_similarity(vec, profile_vec)
            results.append(
                {
                    **_redact_query(q, scope),
                    "similarity": round(sim, 4),
                    "caught": sim >= DEFAULT_MIN_SIMILARITY,
                }
            )
    except Exception as e:  # encode/score failure is fail-open, same as load failure
        logger.debug("promote verifier: recall line failed: %s", e)
        return {"status": "unavailable", "floor": DEFAULT_MIN_SIMILARITY, "all_caught": None}
    pipelines.append("embedding_recall")
    return {
        "status": "ok",
        "floor": DEFAULT_MIN_SIMILARITY,
        "results": results,
        "all_caught": all(r["caught"] for r in results),
    }


def _embedding_index_line(
    model: Any | None,
    triggers: list[str],
    denominator: list[str],
    index_profiles: dict[str, Any] | None,
    scope: Scope,
    pipelines: list[str],
) -> dict[str, Any]:
    """Index line: ``_compute_profile_text`` + 0.45 gate + top1/top2 margin.

    The draft's profile text is its declared triggers — the only profile
    field populated deterministically pre-LLM (gate32 A2). The margin
    gate mirrors the SEMANTIC_INDEX embedding fallback: the draft must
    win the argmax over the (catalog + draft) set AND clear top1-top2 >=
    ``_INDEX_MIN_MARGIN``; without a loaded catalog the margin is
    skipped (``skipped-no-catalog``) and the 0.45 gate alone applies.
    """
    if model is None:
        return {"status": "unavailable", "gate": _INDEX_GATE, "all_accepted": None}

    from vibesop.core.skills.indexer import SkillIndexer, SkillProfile

    profile_text = SkillIndexer._compute_profile_text(
        SkillProfile(skill_id="__draft__", triggers=list(triggers))
    )
    if not profile_text.strip():
        # No triggers → nothing to embed; NOT a model-availability issue,
        # but still not "可用且过门" — the line cannot PASS the draft.
        return {
            "status": "skipped",
            "reason": "empty profile text (no declared triggers)",
            "gate": _INDEX_GATE,
            "all_accepted": None,
        }

    catalog: dict[str, list[float]] = {}
    for sid, profile in (index_profiles or {}).items():
        emb = getattr(profile, "embedding", None)
        if isinstance(emb, list) and emb:
            catalog[str(sid)] = emb
    margin_mode = "catalog" if catalog else "skipped-no-catalog"

    try:
        vectors = _encode(model, [profile_text, *denominator])
        profile_vec, query_vecs = vectors[0], vectors[1:]
        results = []
        # pi-1/claude-8 收敛: 同 recall 线 —— 打分/ margin 循环整体在
        # try 内, 毒模型只降级本线.
        for q, vec in zip(denominator, query_vecs, strict=True):
            sim = _cosine_similarity(vec, profile_vec)
            best_existing_sim = 0.0
            best_existing_id: str | None = None
            for sid, emb in catalog.items():
                try:
                    existing_sim = _cosine_similarity(vec, emb)
                except (TypeError, ValueError):
                    continue  # dimension-mismatched legacy vector — skip
                if existing_sim > best_existing_sim:
                    best_existing_sim, best_existing_id = existing_sim, sid
            accepted = sim >= _INDEX_GATE
            margin: float | None = None
            if catalog:
                # top1/top2 over (catalog + draft): the draft must WIN the
                # argmax and clear the margin — an existing profile outscoring
                # the draft means the draft would not win this query at all.
                margin = sim - best_existing_sim
                accepted = accepted and margin >= _INDEX_MIN_MARGIN
            results.append(
                {
                    **_redact_query(q, scope),
                    "similarity": round(sim, 4),
                    "best_existing_skill_id": best_existing_id,
                    "margin": round(margin, 4) if margin is not None else None,
                    "accepted": accepted,
                }
            )
    except Exception as e:
        logger.debug("promote verifier: index line failed: %s", e)
        return {"status": "unavailable", "gate": _INDEX_GATE, "all_accepted": None}
    pipelines.append("embedding_index")
    return {
        "status": "ok",
        "gate": _INDEX_GATE,
        "min_margin": _INDEX_MIN_MARGIN,
        "margin_mode": margin_mode,
        "results": results,
        "all_accepted": all(r["accepted"] for r in results),
    }
