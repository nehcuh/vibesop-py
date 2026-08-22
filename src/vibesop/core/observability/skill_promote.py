"""W4 — Skill promote: cluster candidates → human review → SKILL.md draft.

Closes the action side of the task-memory loop. The observation side
(W0-W3: task_id → embedding+cluster+gold → recall CLI → replay mode)
identifies what works. This module turns repeatedly-proven clusters into
*reviewable* skill candidates.

Pipeline:

1. ``scan_candidates`` clusters recent spans via ``cluster_queries`` +
   ``assess_gold_status`` (W1 primitives). Clusters with
   ``span_count >= 3 and gold_rate >= 0.60`` become pending candidates.
   Clusters with ``gold_rate < 0.30`` become *unstable* candidates
   (surfaced via ``--unstable`` for diagnosis). M12 M2: clusters made
   entirely of route-miss spans with sufficient cross-day recurrence
   (>=3 distinct (task_id, day) pairs AND >=2 distinct days) are
   admitted as ``source="miss_recurrence"`` candidates without a
   gold-rate requirement — pure-miss clusters previously sank into the
   unstable bucket, invisible to human review.
2. Human reviews the pool via ``vibe skill candidates``.
3. ``vibe skill promote <id>`` writes a SKILL.md draft to
   ``.vibe/observability/skill_drafts/<id>/`` and flips status to
   ``promoted``. The draft path is intentionally NOT under
   ``.vibe/skills/`` — that directory is auto-discovered by
   ``CandidateManager._build_search_paths``.
4. ``vibe skill dismiss <id>`` rejects with reason.

**"未审不注入" guarantee**: promote writes SKILL.md to a path that
``CandidateManager`` does NOT search. The drafted file is invisible
to routing until the user explicitly copies it into ``.vibe/skills/``
via ``vibe skill add <path>``. Two-layer guard: (a) draft lives
outside discovery paths; (b) candidate stays in the pool with
status=``promoted`` so re-scans don't re-suggest it.

Storage: ``<storage_dir>/cluster_candidates.jsonl`` — one
``ClusterCandidate`` per line, JSON-serialised. Production caller passes
``storage_dir=.vibe/observability`` (same convention as
``ReflectionStore``).

Concurrency: ``threading.Lock`` + cross-process ``fcntl`` on POSIX
(same pattern as ``ReflectionStore`` and ``SpanWriter``).

W4.A scope: dataclass + store only (no trigger logic, no CLI).
``step_freq`` / ``step_labels`` are empty placeholders here — W4.B adds
the ``label_step_frequency`` populator.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, get_args

from vibesop.core.observability.behavior_consistency import (
    _BEHAVIOR_JACCARD_THRESHOLD,
    _VALID_BEHAVIOR_STATES,
)

if TYPE_CHECKING:
    # Type-only imports — runtime imports happen inside ``scan_candidates``
    # to avoid forcing all callers to have clustering/gold_detection deps
    # loaded when they only want the dataclass / store.
    from vibesop.core.instinct.learner import InstinctLearner
    from vibesop.core.observability.clustering import Cluster
    from vibesop.core.observability.embedding import EmbeddingCache

logger = logging.getLogger(__name__)

__all__ = [
    "CandidateSource",
    "CandidateStatus",
    "ClusterCandidate",
    "ClusterCandidateStore",
    "MaterializeResult",
    "ScanSummary",
    "StepLabel",
    "label_step_frequency",
    "sanitize_body_text",
    "scan_candidates",
]

CandidateStatus = Literal["pending", "promoted", "dismissed"]
CandidateSource = Literal["gold", "miss_recurrence"]
StepLabel = Literal["core", "common", "optional"]

_VALID_STATUS: frozenset[str] = frozenset(get_args(CandidateStatus))
_VALID_SOURCE: frozenset[str] = frozenset(get_args(CandidateSource))
_VALID_STEP_LABEL: frozenset[str] = frozenset(get_args(StepLabel))
# M3: three-state behavior evidence — single source is
# behavior_consistency._VALID_BEHAVIOR_STATES (imported above, gate24
# pi#7); see that module's docstring for why "divergent" exists alongside
# the design doc's original two states.

_TTL_DAYS = 30
MAX_PENDING = 50
# F-a (2026-08-21, first full-history dogfood scan): the unstable
# diagnosis bucket gets its own SMALLER cap, separate from MAX_PENDING.
# Real-data evidence: 50 unstable gold rows (gold_rate=0.0) filled the
# shared cap and blocked ALL miss_recurrence admissions — the M2 exit
# criterion (≥1 real admitted candidate in `vibe skill discover`) was
# unreachable on every real scan. Diagnosis value scales with evidence
# size, so within the unstable class admit-only-if-better compares
# span_count and eviction drops the lowest span_count (ties → oldest).
MAX_PENDING_UNSTABLE = 20

# gate30: upsert identity is exact ``cluster_id`` FIRST, then task-set
# overlap. ``cluster_id`` = sha1 of sorted (project_id, task_id)
# composite keys (clustering.py W5.1), so it DRIFTS whenever a rescan
# adds/drops member tasks — exact-match-only upsert appended a duplicate
# row per growth step (dogfood evidence: cmspark pool carried 8 duplicate
# pairs, e.g. 61-task vs 63-task rows of the same pattern). Overlap-merge
# absorbs those rows instead.
# Threshold: Jaccard STRICTLY > 0.5 on task_id sets. Real-pool separation
# was clean — true growth-duplicates scored 0.88–0.99, genuinely-distinct
# patterns with shared generic tasks ("提交" etc.) scored ≤0.41. Strict >
# keeps the boundary case OUT: two 3-task clusters sharing 2 generic tasks
# score exactly 0.5 and must not merge (pi N2 — a mis-merge would
# repeatedly absorb a small distinct pattern so it never accumulates).
# Consecutive scans only differ by newly accumulated tasks (the stored row
# tracks the latest scan), so growth stays well above the threshold.
# Known edge: a rescan that SPLITS one cluster into two fragments can let
# the second fragment absorb-erode the first; conservative direction (pool
# loses a fragment, next full-window scan regenerates it), documented like
# the fingerprint 漏粘 note in discovery.cluster_fingerprint.
MERGE_JACCARD_THRESHOLD = 0.5

# Step-frequency thresholds (W4.B). Not in v3 spec — picked from
# workflow-mining conventions. Documented as reviewer Q3.
_CORE_THRESHOLD = 0.70  # step appears in ≥70% of cluster spans → core
_COMMON_THRESHOLD = 0.30  # 30–70% → common; <30% → optional

# Trigger thresholds (W4.C). min_cluster_size=3 is intentionally below
# W1's is_gold threshold of 5 — W4 surfaces *candidates* for human
# review, not confirmed gold. Reviewer Q1.
DEFAULT_MIN_CLUSTER_SIZE = 3
DEFAULT_MIN_GOLD_RATE = 0.60  # ≥60% gold member task_ids → stable candidate
DEFAULT_UNSTABLE_GOLD_RATE = 0.30  # <30% → unstable (diagnosis bucket)

# M12 M2 — miss_recurrence admission gate (design v3 §阈值哲学, gate15b).
# A cluster composed entirely of route-miss spans bypasses the gold gate
# when its recurrence evidence is strong enough. The gate is a CONJUNCTION
# (gate15b: v2 falsely claimed cross-day was implied by pair counting —
# it is not, both conditions are required):
#   distinct (task_key, natural-day) pairs >= MISS_RECURRENCE_MIN_PAIRS
#   AND distinct natural days        >= MISS_RECURRENCE_MIN_DAYS
# Pair counting blocks same-day repeat spam; the day condition blocks
# same-day multi-key iterative rephrasing bursts.
#
# Knob ownership: DiscoveryConfig domain — module constants + scan_candidates
# kwargs (the scan-candidates CLI flags wire onto those kwargs), deliberately
# NOT in RoutingConfig (design v3 §knob 归属, adopting B §9).
MISS_COSINE_THRESHOLD = 0.70  # Calibrated on 48 hand-labelled pairs
# (.omx/artifacts/m12-threshold-calibration.md): the should-merge /
# should-not-merge distributions overlap over 0.41–0.79 with a minimum-error
# plateau at 0.47–0.71; 0.70 takes the plateau's upper edge (merge errors
# cost more than splits under Union-Find chaining). The 0.82 starting point
# was REJECTED by calibration — it splits 17/20 same-intent pairs (it belongs
# to the gold near-neighbour distribution, not miss-vs-miss). Re-calibrate
# once the real miss pool reaches ≥30 distinct keys.
MISS_RECURRENCE_MIN_PAIRS = 3
MISS_RECURRENCE_MIN_DAYS = 2

# Known behaviour (gate17 claude nit 8, RESOLVED F-a 2026-08-21): when
# the candidate store is at MAX_PENDING, the admit-only-if-better policy
# compares gold_rate — and miss_recurrence candidates carry gold_rate=0.0,
# so they ALWAYS lose and are silently refused. The deferral note here
# used to say eviction policy was a DiscoveryConfig-era decision; the
# first full-history dogfood scan (780 clusters, 408-span miss pool)
# proved that deferral blocks the M2 exit: 50 unstable diagnosis rows
# filled the shared cap and 5 gate-passing miss candidates were all
# refused. Resolution: per-class budgets (MAX_PENDING for stable-visible,
# MAX_PENDING_UNSTABLE for the unstable diagnosis bucket) — see
# ClusterCandidateStore._do_locked_upsert.

# Fixed probe text for the embedding health check (gate17 pi BLOCK-1).
# One embed per scan; the fixed text makes repeat scans an EmbeddingCache
# hit, so the probe costs nothing after the first run.
_EMBEDDING_PROBE_TEXT = "vibesop embedding health probe"

# Degenerate content-free queries that must never enter the miss pool
# (calibration finding: they cosine-match EVERYTHING at 0.72–0.82, so no
# threshold can keep them from poisoning clusters).
_DEGENERATE_QUERIES = frozenset(
    {
        "继续",
        "可以",
        "好的",
        "好",
        "是",
        "行",
        "ok",
        "okay",
        "yes",
        "go",
        "continue",
        "proceed",
        "done",
        "next",
    }
)

# Insight-1 shape rules (retention-pool-insights.md §洞察 1): exact-match
# wordlists can't catch continuation traffic — the 12 retention fragments
# scored 1/12 against the wordlist. Two conservative shape rules below
# lift coverage to 7/12. OVER-FILTERING is the failure mode: every rule
# ships with a must-NOT-catch counterexample in the tests.
#
# Rule A verbs/particles/fillers. "做" doubles as a leading continuation
# verb ("做 D1c") and as a mid-remainder filler ("继续往后做吧") — both
# are stripped only from the FRONT, iteratively with the particles, so a
# real object ("继续做用户登录模块" → "用户登录模块" remains) always
# survives. "抛光" is a real verb, not a particle (gate19): it sits in
# the filler set because in continuation traffic it names a PHASE
# activity, not a routing target ("继续 P2 抛光" — insight fixture) —
# the same philosophy as "做 D1c".
_CONTINUATION_VERBS = ("继续", "接着", "开始", "做")
# 语气词 (吧/了/哦/啊/呢/嘛) + 连接词 (和/与/跟) + 续聊填充词 (往后/抛光 —
# 后者是实义动词，此处按相位行为词处理，见上).
_CONTINUATION_PARTICLES = frozenset(
    {"吧", "了", "哦", "啊", "呢", "嘛", "往后", "抛光", "和", "与", "跟"}
)
# Phase tokens: M1 / D1c / P2 / Phase2b / phase3 (whole-token fullmatch,
# so no whitespace inside a token — the space-separated form "phase 3"
# splits into ["phase", "3"] and is NOT caught: documented safe-omission,
# conservative direction, gate19 NIT-2).
_PHASE_TOKEN_RE = re.compile(r"(?:phase\d+[a-z]?|[a-z]?\d+[a-z]?)$", re.IGNORECASE)
# Punctuation stripped when checking "nothing remains" (ASCII + CJK,
# incl. full-width variants — gate19 NIT-4: 继续吧！ must peel like 继续吧!).
_STRIP_PUNCT = " \t　.,、。!?:;·…—-()（）[]【】\"'′！？：；"

# Rule B: enumeration option-reply — "1. 接受 C′ 2. D". Requires the
# numeric-enumeration opening, short length, AND a standalone bare-letter
# option token. gate19 NIT-1: the bare letter must be standalone on BOTH
# sides — (?<![A-Za-z]) so the E in "NPE" can't match, and a lookahead so
# it counts as an option only when followed by end-of-string, another
# enumeration marker, or separator punctuation ("C′ 2." / trailing "D"
# stay filtered; "A 模块" / "A 和 B" / "X 文件" are real task shapes and
# released).
_ENUMERATION_OPEN_RE = re.compile(r"^\s*\d+\s*[.、)]")
_OPTION_TOKEN_RE = re.compile(r"(?<![A-Za-z])[A-Z][′']?(?=\s*(?:\d+\s*[.、)]|[.,、;，。!！]|$))")
_ENUMERATION_MAX_LEN = 30


def _is_low_information_query(query: str) -> bool:
    """True for content-free queries (calibration: pre-pool filter, M2c).

    Rule inventory:

    1. Exact-match wordlist (``_DEGENERATE_QUERIES``).
    2. Latin-only length ≤4 — the length rule is Latin-only: short CJK
       strings CAN carry intent (清理吧 — a calibration pair), short
       Latin ones can't (gate17 pi).
    3. Rule A — continuation prefix + phase-token-only remainder
       (Insight 1): iteratively strip leading continuation verbs
       {继续,接着,开始,做} and particles {吧,了,…,和,与,跟}; if the
       remainder is empty or every whitespace-token is a phase token
       (M1/D1c/P2/Phase2b) or particle → low-information. gate19 NIT-3:
       the prefix is NOT required — a bare phase/particle list with no
       continuation verb (``M1 和 M2``, ``和 M1``) is also filtered,
       because a bare phase list carries no routing intent either.
    4. Rule B — enumeration option-reply (Insight 1): numeric-enumeration
       opening + ≤30 chars + a standalone bare-letter option token
       (``C′``/``D``) NOT followed by CJK/letter content (gate19 NIT-1:
       ``A 模块``/``A 和 B`` are task shapes, not option replies).

    Deliberately NOT filtered (known-safe omissions — honest
    documentation beats aggressive rules; retention-pool §洞察 1):
    ``加吧`` (2-char CJK verb+particle — the calibration counterexample
    ``清理吧`` proves this shape carries intent), ``我看下恢复了``
    (status update), ``reply with exactly: claude-ok`` (probe),
    ``我用的是 dist-package 下面的 chrome-extension`` (substantive
    answer), and the long multi-answer enumeration reply (>30 chars —
    Rule B's length cap is the accepted limit).
    """
    q = query.strip().lower()
    if q in _DEGENERATE_QUERIES:
        return True
    if len(q) <= 4 and not any("一" <= ch <= "鿿" for ch in q):
        return True
    if _is_continuation_phase_only(q):
        return True
    return _is_enumeration_option_reply(query.strip())


def _is_continuation_phase_only(q: str) -> bool:
    """Rule A — continuation prefix + phase-token-only remainder.

    ``q`` is already stripped+lowercased. Front-strips verbs and
    particles interchangeably (e.g. 继续往后做吧 → 继续,往后,做,吧 all
    peel off), then requires every remaining whitespace-token to be a
    phase token or a particle. Any substantive token (处理/backlog/
    用户登录模块) fails the check — conservative direction.

    gate19 NIT-3: stripping a continuation prefix is NOT required — a
    bare phase/particle list (``M1 和 M2``, ``和 M1``) also matches.
    Deliberate: a bare phase list carries no routing intent, so filtering
    it is the same judgment as the prefixed form, just documented now.
    """
    rest = q
    while rest:
        for prefix in (*_CONTINUATION_VERBS, *_CONTINUATION_PARTICLES):
            if rest.startswith(prefix):
                rest = rest[len(prefix) :].lstrip()
                break
        else:
            break
    rest = rest.strip(_STRIP_PUNCT)
    if not rest:
        return True
    tokens = [t.strip(_STRIP_PUNCT) for t in rest.split()]
    tokens = [t for t in tokens if t]
    return bool(tokens) and all(
        _PHASE_TOKEN_RE.fullmatch(t) or t in _CONTINUATION_PARTICLES for t in tokens
    )


def _is_enumeration_option_reply(q: str) -> bool:
    """Rule B — enumeration option-reply (original case; the option
    token is case-sensitive [A-Z] so words like NPE/evaluate never
    match, and gate19 NIT-1: the letter must be followed by end /
    another enumeration marker / separator punctuation — ``A 模块``,
    ``A 和 B``, ``X 文件`` are task shapes and are released). Accepted
    limit: replies longer than 30 chars pass through even when they are
    option answers (documented omission)."""
    if len(q) > _ENUMERATION_MAX_LEN or not _ENUMERATION_OPEN_RE.match(q):
        return False
    hit = _OPTION_TOKEN_RE.search(q)
    if hit:
        # gate19 (both reviewers): debug-level audit trail so false kills
        # are reconstructable post-hoc from scan logs.
        logger.debug("low-information Rule B hit (option-reply shape): %r", q)
    return hit is not None


# gate32 A1 (B4-lite): agent-prompt shapes that must NOT be auto-prefilled
# into a draft's ``triggers:`` field. Dogfood evidence (cmspark spans):
# ~64% of the miss pool is sub-agent prompt echoes / machine wrappers
# ("You are an adversarial SKEPTIC…", "<system-reminder>…",
# '[ { "type": "text"…'). They are legitimate pool members for human
# review (bd1bc217 was promoted from such a cluster), but copying them
# verbatim into triggers would auto-route future agent-prompt traffic
# onto the skill. The human editor can always add a cleaned trigger by
# hand — this filter only governs the AUTOMATIC prefill sample.
_AGENT_PROMPT_PREFIXES = (
    "you are ",
    "ou are ",  # span-name truncation drops the first char ("Y")
    "<system-reminder",
    "system-reminder",
    "<command-",
    "[ {",
    "[{",
    "background task ",
)
# Long prompts are delegation payloads, not vocabulary. Real user
# instructions in the dogfood pool run <100 chars; 150 leaves margin
# while excluding pasted prompt templates.
_AGENT_PROMPT_MAX_LEN = 150


def _is_agent_prompt_shape(query: str) -> bool:
    """True for machine/agent-prompt-shaped text (gate32 A1 hygiene).

    Conservative by design — false positives here only mean "human
    writes the trigger by hand", false negatives mean a garbage phrase
    becomes a live routing trigger after activation.
    """
    q = " ".join(str(query).split()).lower()
    if not q:
        return True
    if len(q) > _AGENT_PROMPT_MAX_LEN:
        return True
    return q.startswith(_AGENT_PROMPT_PREFIXES)


def _validate_choice(value: str, valid: frozenset[str], field_name: str) -> str:
    """Runtime-validate a Literal field (mirrors ``Reflection`` helper)."""
    if value not in valid:
        msg = f"{field_name}={value!r} is not one of {sorted(valid)}"
        raise ValueError(msg)
    return value


def _now_utc() -> datetime:
    """Single source of truth for ``datetime.now(UTC)`` — patchable in tests."""
    return datetime.now(UTC)


def _task_set_jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Jaccard similarity of two task_id sets; 0.0 when both are empty."""
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


@dataclass
class ClusterCandidate:
    """A skill candidate derived from a repeatedly-proven task cluster.

    Identity: ``cluster_id`` (sha1 of sorted (project_id, task_id)
    composite keys — matches ``Cluster.cluster_id`` from
    ``clustering.py`` W5.1). Two candidates with the same cluster_id are
    the same candidate across rescans. The id DRIFTS when a rescan
    grows/shrinks the membership; the store heals that by
    overlap-merging pending rows (``MERGE_JACCARD_THRESHOLD``), so
    identity in practice is "the same task-set pattern", not the
    literal hash.

    Lifecycle: ``pending`` → ``promoted`` | ``dismissed``. Terminal
    states are sticky: re-scans do NOT overwrite a promoted or dismissed
    row (the human's decision wins over fresh signal), and overlap-merge
    never absorbs terminal rows.

    TTL: pending rows expire after ``_TTL_DAYS`` (30 days). Promoted /
    dismissed rows do NOT expire (they're audit log of decisions).
    """

    cluster_id: str
    task_ids: list[str]
    queries: list[str]
    span_count: int
    gold_rate: float
    gold_task_ids: list[str]
    created_at: datetime = field(default_factory=_now_utc)
    # M12 NIT-B: earliest span timestamp observed in the cluster (模式首见
    # 时间). Filled at scan time from the cluster's spans; None for legacy
    # rows scanned before this field existed — display layers fall back to
    # ``created_at`` (入池时间). On rescan the earlier value wins (a
    # shorter --days window must not push first-sight forward).
    # gate23 (claude#2): NOT the same clock as
    # ``DiscoveryObservationStore.first_seen_at`` (discovery.py) — that one
    # records when the discovery queue first OBSERVED the candidate and
    # drives cooling; this one is pattern first-sight in the spans.
    first_seen_at: datetime | None = None
    ttl_expires_at: datetime | None = None  # set in __post_init__
    step_freq: dict[str, int] = field(default_factory=dict)
    step_labels: dict[str, StepLabel] = field(default_factory=dict)
    core_steps: list[str] = field(default_factory=list)
    status: CandidateStatus = "pending"
    is_unstable: bool = False
    source: CandidateSource = "gold"
    reviewed_at: datetime | None = None
    source_skill_id: str | None = None
    dismiss_reason: str | None = None
    project_distribution: dict[str, int] = field(default_factory=dict)
    # M12 M5: sha256 of the SKILL.md draft bytes as written at promote
    # time. ``promote --activate`` compares the CURRENT draft file hash
    # against this value — identical means the draft was never edited by
    # a human, so activation is refused (content-hash edit guard; mtime
    # checks are spoofable by whitespace-only edits and are not used).
    # None for candidates promoted before M5 (legacy) — activation then
    # requires --force.
    draft_sha256: str | None = None
    # M3 行为一致性门 (behavior_consistency.py): 三态标注 + 聚合分。
    # ``behavior_evidence``: consistent / divergent / unavailable;
    # None = 未采集 (pre-M3 存量行, 展示层 "未采集").
    # ``behavior_score``: mean pairwise bigram-Jaccard, None when
    # unavailable. 重扫语义: 用最新计算值覆盖 (与 first_seen_at 的
    # earliest-wins 不同 —— 行为证据随数据新鲜度更新, upsert 整行
    # 替换天然满足, 无需 merge 逻辑).
    behavior_evidence: str | None = None
    behavior_score: float | None = None

    def __post_init__(self) -> None:
        _validate_choice(self.status, _VALID_STATUS, "status")
        _validate_choice(self.source, _VALID_SOURCE, "source")
        if self.behavior_evidence is not None:
            _validate_choice(self.behavior_evidence, _VALID_BEHAVIOR_STATES, "behavior_evidence")
        # gate24 pi#6: 与 behavior_evidence 的严格校验对称 —— 非法值
        # 拒收(ValueError),不放行 None 化(静默吞掉脏数据会让
        # consistent/divergent 判定事后无法审计)。bool 是 int 子类,
        # 显式排除。
        if self.behavior_score is not None and (
            isinstance(self.behavior_score, bool)
            or not isinstance(self.behavior_score, int | float)
            or not (0.0 <= self.behavior_score <= 1.0)
        ):
            msg = f"behavior_score={self.behavior_score!r} is not a number in [0.0, 1.0]"
            raise ValueError(msg)
        if self.ttl_expires_at is None:
            self.ttl_expires_at = self.created_at + timedelta(days=_TTL_DAYS)
        for label in self.step_labels.values():
            _validate_choice(label, _VALID_STEP_LABEL, "step_labels value")

    @property
    def is_cross_project(self) -> bool:
        """True when the candidate spans >1 project (W5.2).

        Mirrors ``Cluster.is_cross_project`` from ``clustering.py`` so
        consumers can branch on heterogeneity without re-reading spans.
        """
        return len(self.project_distribution) > 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict.

        Datetimes become ISO 8601 with tz offset. Round-trip:
        ``ClusterCandidate.from_dict(c.to_dict()) == c``.
        """
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["first_seen_at"] = self.first_seen_at.isoformat() if self.first_seen_at else None
        d["ttl_expires_at"] = self.ttl_expires_at.isoformat() if self.ttl_expires_at else None
        d["reviewed_at"] = self.reviewed_at.isoformat() if self.reviewed_at else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClusterCandidate:
        """Deserialize from ``to_dict`` output.

        Re-parses all four datetime fields (ISO 8601 → aware datetime).
        Re-validates ``status`` Literal on construction (defensive
        against hand-edited files carrying invalid values). Rows written
        before ``first_seen_at`` existed simply lack the key → None →
        display layers fall back to ``created_at`` semantics (M12 NIT-B).

        tz-naive datetimes (hand-edited ISO without offset) are attached
        to UTC. Without this, ``prune_expired`` raises ``TypeError`` when
        comparing aware vs naive — one bad line would crash the whole
        scan (grok P1).
        """
        payload = dict(d)
        for key in ("created_at", "first_seen_at", "ttl_expires_at", "reviewed_at"):
            raw = payload.get(key)
            if isinstance(raw, str):
                parsed = datetime.fromisoformat(raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                payload[key] = parsed
        return cls(**payload)


class ClusterCandidateStore:
    """JSONL-backed store for ``ClusterCandidate`` rows.

    File layout: ``<storage_dir>/cluster_candidates.jsonl`` — one
    candidate per line. Production caller passes ``storage_dir`` as the
    leaf directory (matches ``ReflectionStore`` convention).

    Hard cap: PER-CLASS budgets (F-a, 2026-08-21). Stable-visible pending
    rows cap at ``MAX_PENDING``; unstable diagnosis rows cap at
    ``MAX_PENDING_UNSTABLE`` — the two classes never compete, so a full
    diagnosis bucket can no longer block stable/miss_recurrence
    admissions (real-data exit blocker on the first full-history dogfood
    scan). Upserting a NEW pending row when its class is at cap uses
    **admit-only-if-better** WITHIN the class: stable rows compare
    ``gold_rate`` (a new row is admitted iff its rate exceeds the lowest
    pending rate); unstable rows compare ``span_count`` (diagnosis value
    scales with evidence size). Refusals are logged at WARNING. Promoted
    / dismissed rows do NOT count against either cap (they're terminal
    audit records, not backlog).

    Failure mode: malformed JSON lines are skipped on read (same as
    ``ReflectionStore.list_all``) — a corrupt line must not crash the
    CLI or dashboard.
    """

    FILENAME = "cluster_candidates.jsonl"

    def __init__(self, storage_dir: Path | str) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / self.FILENAME
        self._lock = threading.Lock()

    def upsert(self, candidate: ClusterCandidate) -> ClusterCandidate:
        """Insert or refresh a candidate.

        - New cluster_id → enforce hard cap, then append.
        - Existing pending → refresh mutable fields (span_count,
          gold_rate, step_freq, etc.) but preserve ``created_at`` and
          ``ttl_expires_at`` (so TTL doesn't reset on every rescan).
        - Existing promoted / dismissed → no-op (terminal sticky).

        Returns the candidate as it now exists in the store (which may
        differ from the input if a pending row was refreshed).
        """
        with self._lock:
            return self._locked_upsert(candidate)

    def _locked_upsert(self, candidate: ClusterCandidate) -> ClusterCandidate:
        """Upsert under both threading.Lock and cross-process fcntl.

        See ``ReflectionStore._locked_update_status`` for the rationale
        on acquiring flock around the read-then-rewrite cycle.
        """
        try:
            import fcntl
        except ImportError:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self._path):
                return self._do_locked_upsert(candidate)

        with self._path.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                return self._do_locked_upsert(candidate)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _do_locked_upsert(self, candidate: ClusterCandidate) -> ClusterCandidate:
        """Caller MUST hold threading.Lock + cross-process lock."""
        rows = self._read_all_locked()
        existing_idx = next(
            (i for i, r in enumerate(rows) if r.cluster_id == candidate.cluster_id),
            None,
        )

        if existing_idx is not None and rows[existing_idx].status != "pending":
            # Terminal state — human decision wins. Return the stored row
            # unchanged. Terminal rows are also invisible to the overlap
            # match below: a regrown pattern under a drifted id inserts as
            # its own pending row (the discovery-layer fingerprint sticky
            # list, not the store, keeps dismissed patterns out of the
            # queue).
            return rows[existing_idx]

        # gate30 (+ round-2 pi M1/N1/BLOCK-1, claude MAJOR-1/2): the
        # matched set is the exact-id pending row (if any — UNCONDITIONAL,
        # preserving gate21 wholesale-refresh semantics including the
        # accepted class-flip; for the MISS path the scan-side guard is
        # what prevents a miss candidate from replacing an unstable
        # exact-id row — pi round-2 BLOCK-1) UNION every pending row of
        # the SAME CLASS whose task set overlaps the incoming one at
        # Jaccard > MERGE_JACCARD_THRESHOLD. cluster_id = sha1 of sorted
        # (project_id, task_id) composite keys (clustering.py W5.1), so it
        # drifts whenever a rescan grows/shrinks membership — matching on
        # exact id alone appended a duplicate row per growth step
        # (dogfood: cmspark pool carried 8 duplicate pairs), and matching
        # overlap ONLY on the exact-miss path let stable-size duplicate
        # pairs survive forever (pi N1).
        # Same-class restriction on the OVERLAP arm (claude MAJOR-1): a
        # stable miss candidate must not absorb UNSTABLE diagnosis rows —
        # the unstable bucket's evidence serves diagnosis, not review, and
        # would be silently destroyed by the wholesale replace.
        # Cross-class duplicates are the accepted price (rare gate21 flip
        # case; the stale row TTL-expires in 30d).
        # The incoming row replaces the whole matched set with
        # earliest-wins created_at / ttl_expires_at / first_seen_at and
        # union-summed project_distribution (claude MAJOR-2, explicitly
        # accepted: pool-level pattern identity IS the project-agnostic
        # task_id vocabulary — the same pattern in two projects is ONE
        # skill candidate, and W5.2's [XP] signal wants exactly that; the
        # distribution union keeps absorbed rows' cross-project evidence
        # visible. W5.1 composite keys remain authoritative for SPAN
        # attribution, not for pool identity). Other fields
        # (queries/gold_task_ids/gold_rate/span_count) are wholesale-
        # replaced by the incoming row (pi NIT-5): lossless for
        # growth-duplicates (incoming is the superset scan); a
        # cross-project merge drops the absorbed project's query
        # exemplars until the next full-window rescan regenerates them —
        # accepted, best-effort like the fingerprint 漏粘 note.
        # Replace-absorb-matched conserves TOTAL row count (k absorbed +
        # 1 inserted, k ≥ 1) but NOT the per-class count when the exact-id
        # row flip-merges — the incoming class can transiently exceed its
        # cap by ≤1, healing on the next same-class insert; same accepted
        # semantics as gate21 (claude NIT-1). Both paths bypass the
        # insert-time cap check.
        matched_idx = set()
        if existing_idx is not None:
            matched_idx.add(existing_idx)
        matched_idx.update(
            i
            for i, r in enumerate(rows)
            if r.status == "pending"
            and r.is_unstable == candidate.is_unstable
            and _task_set_jaccard(r.task_ids, candidate.task_ids) > MERGE_JACCARD_THRESHOLD
        )

        if matched_idx:
            matched = [rows[i] for i in sorted(matched_idx)]
            # claude round-2 NIT-3: log not only the pure-merge path but
            # also an exact hit that absorbs drifted siblings (the pi N1
            # self-heal main case) — otherwise cron diagnosis sees only
            # row-count changes.
            if existing_idx is None or len(matched) > 1:
                logger.info(
                    "cluster_candidates overlap-merge: %s absorbs %d drifted row(s) "
                    "%s (Jaccard > %.2f; sizes incoming=%d absorbed=%s)",
                    candidate.cluster_id,
                    len(matched),
                    [r.cluster_id for r in matched],
                    MERGE_JACCARD_THRESHOLD,
                    len(candidate.task_ids),
                    [len(r.task_ids) for r in matched],
                )
            candidate.created_at = min([candidate.created_at, *(r.created_at for r in matched)])
            # TTL earliest-wins across matched rows. Every stored row
            # carries a TTL (``__post_init__`` fills it, ``from_dict``
            # re-runs post-init — pi NIT-4: a None-ttl legacy row is not
            # reachable), so this is a plain min().
            candidate.ttl_expires_at = min(
                r.ttl_expires_at for r in matched if r.ttl_expires_at is not None
            )
            first_seens = [
                f
                for f in [candidate.first_seen_at, *(r.first_seen_at for r in matched)]
                if f is not None
            ]
            candidate.first_seen_at = min(first_seens) if first_seens else None
            merged_distribution: dict[str, int] = {}
            for r in matched:
                for pid, n in r.project_distribution.items():
                    merged_distribution[pid] = merged_distribution.get(pid, 0) + n
            for pid, n in candidate.project_distribution.items():
                merged_distribution[pid] = merged_distribution.get(pid, 0) + n
            candidate.project_distribution = merged_distribution
            rows = [r for i, r in enumerate(rows) if i not in matched_idx]
            rows.append(candidate)
            self._rewrite_all_locked(rows)
            return candidate

        # New row — enforce the per-class hard cap BEFORE insert (F-a:
        # stable and unstable budgets are separate; a row only ever
        # competes within its own class).
        class_rows = [
            r for r in rows if r.status == "pending" and r.is_unstable == candidate.is_unstable
        ]
        class_cap = MAX_PENDING_UNSTABLE if candidate.is_unstable else MAX_PENDING
        if len(class_rows) >= class_cap:
            # Admit-only-if-better within the class: stable rows compare
            # gold_rate (prevents a rate≈0.15 arrival from displacing a
            # rate≈0.65 row — grok+pi P1 on W4); unstable diagnosis rows
            # compare span_count (diagnosis value scales with evidence
            # size — F-a).
            if candidate.is_unstable:
                current_min = min(r.span_count for r in class_rows)
                if candidate.span_count <= current_min:
                    logger.warning(
                        "cluster_candidates unstable cap (%d) reached — rejecting new "
                        "unstable cluster %s (span_count=%d <= min pending %d).",
                        class_cap,
                        candidate.cluster_id,
                        candidate.span_count,
                        current_min,
                    )
                    return candidate  # not inserted; caller sees no error
            else:
                current_min_rate = min(r.gold_rate for r in class_rows)
                if candidate.gold_rate <= current_min_rate:
                    logger.warning(
                        "cluster_candidates stable cap (%d) reached — rejecting new "
                        "cluster %s (gold_rate=%.2f <= min pending %.2f). "
                        "Review backlog or dismiss to make room.",
                        class_cap,
                        candidate.cluster_id,
                        candidate.gold_rate,
                        current_min_rate,
                    )
                    return candidate  # not inserted; caller sees no error
            self._evict_for_class_locked(rows, unstable=candidate.is_unstable)

        rows.append(candidate)
        self._rewrite_all_locked(rows)
        return candidate

    def _evict_for_class_locked(self, rows: list[ClusterCandidate], *, unstable: bool) -> None:
        """Drop the weakest pending row of ONE class (stable or unstable).

        Mutates ``rows`` in place. No-op if the class has no pending rows.
        Called by ``_do_locked_upsert`` ONLY after the new candidate has
        passed its class's admit-only-if-better check.

        Eviction key (F-a): stable class drops lowest ``gold_rate``;
        unstable class drops lowest ``span_count``. Ties → oldest
        ``created_at`` first (FIFO) in both classes.

        Logs at WARNING (not INFO) so cron-scheduled scans surface the
        eviction in default log verbosity (pi P0: silent eviction
        violates "未审不注入" spirit when run via cron).
        """
        pending_indices = [
            (i, r)
            for i, r in enumerate(rows)
            if r.status == "pending" and r.is_unstable == unstable
        ]
        if not pending_indices:
            return
        if unstable:
            target_idx, evicted = min(
                pending_indices, key=lambda pair: (pair[1].span_count, pair[1].created_at)
            )
        else:
            target_idx, evicted = min(
                pending_indices, key=lambda pair: (pair[1].gold_rate, pair[1].created_at)
            )
        rows.pop(target_idx)
        logger.warning(
            "cluster_candidates %s cap reached — evicted %s (gold_rate=%.2f, span_count=%d)",
            "unstable" if unstable else "stable",
            evicted.cluster_id,
            evicted.gold_rate,
            evicted.span_count,
        )

    def list_pending(self, *, include_unstable: bool = False) -> list[ClusterCandidate]:
        """Pending candidates, sorted by gold_rate desc then span_count desc.

        Default (``include_unstable=False``) returns **stable only** —
        matches the CLI's default view and the user's mental model of
        "what should I review next?". Unstable candidates (gold_rate
        below the unstable threshold) are surfaced separately via
        ``list_unstable`` or included with ``include_unstable=True``.

        Grok+pi P1 consensus on W4 review: the prior "all pending"
        default polluted the review queue with diagnosis-only rows.
        """
        rows = self._read_all_unlocked()
        pending = [
            r for r in rows if r.status == "pending" and (include_unstable or not r.is_unstable)
        ]
        pending.sort(key=lambda r: (r.gold_rate, r.span_count), reverse=True)
        return pending

    def list_unstable(self) -> list[ClusterCandidate]:
        """Pending candidates with ``is_unstable=True``.

        Surfaced via ``vibe skill candidates --unstable``. Sorted by
        gold_rate asc (worst first) so the most pathological clusters
        are at the top.
        """
        rows = self._read_all_unlocked()
        unstable = [r for r in rows if r.status == "pending" and r.is_unstable]
        unstable.sort(key=lambda r: r.gold_rate)
        return unstable

    def list_all(self) -> list[ClusterCandidate]:
        """Every row in insertion order (including terminal states).

        Used for audit / debugging. Most callers want ``list_pending``.
        """
        return self._read_all_unlocked()

    def prune_expired(self, now: datetime | None = None) -> int:
        """Delete TTL-expired pending rows. Returns count pruned.

        Only pending rows are pruned. Promoted / dismissed rows are
        audit records and never expire (they record the human decision).

        Also trims each class to its budget (gate21 pi NIT-2): the
        insert path only gates NEW rows, so legacy pools that exceed a
        class cap (e.g. pre-F-a files with 50 unstable rows) are trimmed
        here using the class eviction order. Trims don't count toward
        the return value (TTL expiries only).

        Called at the start of every ``scan_candidates`` run so the pool
        stays bounded without manual cleanup.
        """
        now = now or _now_utc()
        with self._lock:
            return self._locked_prune_expired(now)

    def _locked_prune_expired(self, now: datetime) -> int:
        try:
            import fcntl
        except ImportError:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self._path):
                return self._do_locked_prune(now)

        with self._path.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                return self._do_locked_prune(now)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _do_locked_prune(self, now: datetime) -> int:
        rows = self._read_all_locked()
        survivors: list[ClusterCandidate] = []
        pruned = 0
        for r in rows:
            if r.status == "pending" and r.ttl_expires_at is not None and r.ttl_expires_at < now:
                pruned += 1
                continue
            survivors.append(r)
        # gate21 pi NIT-2: also trim each class to its cap. The insert
        # path only gates NEW rows, so a pre-F-a pool file (e.g. 50
        # unstable rows written before the per-class budgets) would sit
        # above the unstable cap for weeks, rendering "50 unstable
        # (cap 20)" on every scan. Trim using the class eviction order
        # (stable: lowest gold_rate; unstable: lowest span_count; ties →
        # oldest) via the shared eviction helper. Trims are NOT included
        # in the return value (that counts TTL expiries, surfaced as
        # ScanSummary.pruned_count); each trim is logged at WARNING by
        # the eviction helper.
        trimmed = 0
        for unstable, cap in ((False, MAX_PENDING), (True, MAX_PENDING_UNSTABLE)):
            while (
                sum(1 for r in survivors if r.status == "pending" and r.is_unstable == unstable)
                > cap
            ):
                self._evict_for_class_locked(survivors, unstable=unstable)
                trimmed += 1
        if pruned or trimmed:
            self._rewrite_all_locked(survivors)
        return pruned

    def promote(
        self, cluster_id: str, skill_id: str, *, draft_sha256: str | None = None
    ) -> ClusterCandidate | None:
        """Flip status pending → promoted, set ``source_skill_id`` and
        ``reviewed_at``. Returns the updated candidate, or None if not
        found / already terminal.

        Idempotent: re-promoting a promoted row updates ``skill_id`` and
        refreshes ``reviewed_at`` (supports change-of-mind on the skill
        name). Re-promoting a dismissed row is a no-op (explicit decision
        override would surprise the user — dismiss stays sticky).

        ``draft_sha256`` (M12 M5): content hash of the draft as generated,
        recorded for the ``promote --activate`` edit guard. Passed only by
        callers that just (re)materialized the draft; None leaves any
        previously recorded hash untouched.
        """

        def _apply(c: ClusterCandidate) -> None:
            c.status = "promoted"
            c.source_skill_id = skill_id
            c.reviewed_at = _now_utc()
            if draft_sha256 is not None:
                c.draft_sha256 = draft_sha256

        with self._lock:
            return self._locked_transition(
                cluster_id,
                _apply,
                allow_if_terminal=lambda c: c.status == "promoted",
            )

    def dismiss(self, cluster_id: str, reason: str | None = None) -> ClusterCandidate | None:
        """Flip status pending → dismissed, record ``dismiss_reason``.

        Like ``promote``, idempotent on dismissed rows (re-dismiss
        updates the reason). Re-dismissing a promoted row is a no-op.
        """
        with self._lock:
            return self._locked_transition(
                cluster_id,
                lambda c: (
                    setattr(c, "status", "dismissed"),
                    setattr(c, "dismiss_reason", reason),
                    setattr(c, "reviewed_at", _now_utc()),
                ),
                allow_if_terminal=lambda c: c.status == "dismissed",
            )

    def _locked_transition(
        self,
        cluster_id: str,
        apply: Callable[[ClusterCandidate], Any],
        allow_if_terminal: Callable[[ClusterCandidate], bool],
    ) -> ClusterCandidate | None:
        """Generic pending→terminal transition under both locks.

        ``apply`` runs against the candidate in place. ``allow_if_terminal``
        permits re-applying when the row is already in the matching
        terminal state (idempotency for promote-on-promoted etc.).
        """
        try:
            import fcntl
        except ImportError:
            from vibesop.utils.file_lock import cross_process_lock

            with cross_process_lock(self._path):
                return self._do_locked_transition(cluster_id, apply, allow_if_terminal)

        with self._path.open("a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                return self._do_locked_transition(cluster_id, apply, allow_if_terminal)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _do_locked_transition(
        self,
        cluster_id: str,
        apply: Callable[[ClusterCandidate], Any],
        allow_if_terminal: Callable[[ClusterCandidate], bool],
    ) -> ClusterCandidate | None:
        rows = self._read_all_locked()
        target_idx = next(
            (i for i, r in enumerate(rows) if r.cluster_id == cluster_id),
            None,
        )
        if target_idx is None:
            return None
        target = rows[target_idx]
        if target.status == "pending":
            apply(target)
            self._rewrite_all_locked(rows)
            return target
        if allow_if_terminal(target):
            apply(target)
            self._rewrite_all_locked(rows)
            return target
        # Wrong terminal state — no-op.
        return target

    def get(self, cluster_id: str) -> ClusterCandidate | None:
        """Return one candidate by cluster_id, or None."""
        for r in self._read_all_unlocked():
            if r.cluster_id == cluster_id:
                return r
        return None

    def find_all_overlapping_pending(
        self, task_ids: Iterable[str], *, threshold: float = MERGE_JACCARD_THRESHOLD
    ) -> list[ClusterCandidate]:
        """ALL pending rows overlapping a task_id set at Jaccard > threshold.

        gate30 round-2 (pi M1): the upsert merge absorbs ALL overlapping
        rows, so guards that reason about destruction risk must see the
        same full set — a best-match-only query lets a miss candidate
        slip past a guard when a DIFFERENT overlapping row wins the best
        match while a gold row gets absorbed anyway. Both classes are
        returned; class/source policy belongs to the caller (e.g.
        scan_candidates' guard ignores unstable rows — claude MAJOR-1).
        Terminal rows are invisible here, same as in the merge path.

        Read is unlocked (claude NIT-5 TOCTOU): a concurrent scan could
        insert between this check and the caller's ``upsert`` — worst
        case is one missed guard skip, never data corruption (upsert
        re-derives overlap under lock). Single-writer cron makes this
        theoretical.
        """
        return [
            r
            for r in self._read_all_unlocked()
            if r.status == "pending" and _task_set_jaccard(r.task_ids, task_ids) > threshold
        ]

    def pending_count(self, *, include_unstable: bool = False) -> int:
        """Count of pending rows — kill-switch input.

        Default (``include_unstable=False``) counts **stable only**.
        Kill-switch §5 says "candidate pool backlog < 10" — unstable
        rows are diagnosis buckets, not review backlog, so they don't
        count toward the freeze threshold. Grok+pi P1/P2 consensus.

        Pass ``include_unstable=True`` for the total pending row count
        (audit / dashboard use).
        """
        return sum(
            1
            for r in self._read_all_unlocked()
            if r.status == "pending" and (include_unstable or not r.is_unstable)
        )

    def _read_all_unlocked(self) -> list[ClusterCandidate]:
        """Read without cross-process lock — for read-only callers.

        ``list_pending`` / ``list_unstable`` / ``get`` / ``pending_count``
        use this. They tolerate slightly stale reads — a concurrent scan
        won't change the answer enough to matter for surfacing.
        """
        if not self._path.exists():
            return []
        return self._parse_lines(self._path)

    def _read_all_locked(self) -> list[ClusterCandidate]:
        """Read while holding flock — for read-modify-write callers.

        MUST be called under ``self._lock`` AND the cross-process lock.
        See ``ReflectionStore._do_locked_update`` for why flock must
        bracket the read, not just the rewrite.
        """
        if not self._path.exists():
            return []
        return self._parse_lines(self._path)

    @staticmethod
    def _parse_lines(path: Path) -> list[ClusterCandidate]:
        """Parse JSONL, skipping malformed / schema-invalid lines."""
        out: list[ClusterCandidate] = []
        with path.open("r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(
                        "skipping malformed candidate line %d in %s",
                        lineno,
                        path,
                    )
                    continue
                try:
                    out.append(ClusterCandidate.from_dict(d))
                except (ValueError, TypeError):
                    logger.debug(
                        "skipping schema-invalid candidate line %d in %s",
                        lineno,
                        path,
                    )
                    continue
        return out

    def _rewrite_all_locked(self, rows: Iterable[ClusterCandidate]) -> None:
        """Atomic rewrite under flock. Caller holds both locks."""
        from vibesop.utils.atomic_writer import AtomicWriter

        writer = AtomicWriter()
        with writer.atomic_open(self._path, "w") as f:
            for r in rows:
                f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")


def _extract_step_names(span: dict[str, Any]) -> set[str]:
    """Pull step names out of a span dict.

    Each span contributes a SET of names (deduplicated within the span).
    We count span-coverage — "what fraction of spans in the cluster
    include this step?" — NOT raw occurrences. A step that fires 10
    times in one span still counts as 1 toward that span's coverage.

    Sources, in order:
    - ``span["name"]`` — always present (e.g. ``route:query``,
      ``tool:edit``, ``llm:claude``).
    - ``span["metadata"]["steps"]`` or ``metadata.step_sequence`` —
      optional list (used when one span records multiple sibling steps).
    """
    names: set[str] = set()
    name = span.get("name")
    if isinstance(name, str) and name:
        names.add(name)
    metadata = span.get("metadata")
    if isinstance(metadata, dict):
        steps = metadata.get("steps") or metadata.get("step_sequence")
        if isinstance(steps, list):
            for s in steps:
                if isinstance(s, str) and s:
                    names.add(s)
    return names


def label_step_frequency(
    spans: list[dict[str, Any]],
    total_span_count: int,
) -> tuple[dict[str, int], dict[str, StepLabel], list[str]]:
    """Label each step name as core / common / optional by coverage.

    Parameters
    ----------
    spans:
        Span dicts belonging to ONE cluster (caller filters by
        ``cluster.task_ids``). Each span contributes a set of step names
        via ``_extract_step_names``.
    total_span_count:
        Denominator for coverage fraction. Pass ``cluster.span_count``
        — NOT ``len(spans)`` — when the caller has filtered spans (e.g.
        dropped child spans). When unfiltered, the two are equal.

    Returns
    -------
    tuple of ``(freq, labels, core_steps)``:
        - ``freq``: ``{step_name: count}`` — number of spans whose name
          set includes ``step_name``.
        - ``labels``: ``{step_name: "core" | "common" | "optional"}``.
        - ``core_steps``: step names with label ``"core"``, sorted by
          frequency desc then name asc.

    Thresholds (module constants; reviewer Q3):
        - ``core``: coverage ``>= _CORE_THRESHOLD`` (70%)
        - ``common``: coverage ``>= _COMMON_THRESHOLD`` (30%) and < 70%
        - ``optional``: coverage < 30%
    """
    if not spans or total_span_count <= 0:
        return {}, {}, []

    freq: dict[str, int] = {}
    for span in spans:
        for name in _extract_step_names(span):
            freq[name] = freq.get(name, 0) + 1

    labels: dict[str, StepLabel] = {}
    for name, count in freq.items():
        rate = count / total_span_count
        if rate >= _CORE_THRESHOLD:
            labels[name] = "core"
        elif rate >= _COMMON_THRESHOLD:
            labels[name] = "common"
        else:
            labels[name] = "optional"

    core_steps = sorted(
        [n for n, lbl in labels.items() if lbl == "core"],
        key=lambda n: (-freq[n], n),
    )
    return freq, labels, core_steps


@dataclass
class ScanSummary:
    """Result of one ``scan_candidates`` run.

    Fields
    ------
    promoted_count:
        Stable candidates emitted (``gold_rate >= min_gold_rate``).
        Named "promoted" because the scan *promoted* them from raw
        cluster signal to reviewable candidate — NOT because they were
        human-approved (that's ``ClusterCandidate.status == "promoted"``
        via the ``vibe skill promote`` CLI).
    unstable_count:
        Unstable candidates emitted (``gold_rate < unstable_gold_rate``).
        Surfaced for diagnosis via ``vibe skill candidates --unstable``.
    pruned_count:
        TTL-expired pending rows removed at scan start. Promoted /
        dismissed rows are NOT pruned (audit records).
    capped:
        True iff the store hit ``MAX_PENDING`` (stable-class cap) at any
        point during this scan. Past the cap, admit-only-if-better evicts
        the weakest row of the candidate's own class — lowest gold_rate
        for stable, lowest span_count for unstable (reviewer Q4; F-a
        per-class budgets).
    clusters_seen:
        Total clusters returned by ``cluster_queries`` across both
        clusterings (gold path over all spans + M12 M2 miss path over
        miss-only spans). Includes clusters too small or in the neutral
        gold_rate zone that did not become candidates.
    miss_pool_size:
        Number of route-miss spans in the input (M12 M2) — spans passing
        ``is_route_miss_span`` (explicit ``has_match=False``, mode not
        ``not_intercepted``). Informational, for silent-spin detection.
    miss_admitted_count:
        Miss clusters admitted via the ``miss_recurrence`` gate this run
        (M12 M2) AND accepted by the store (gate17 claude nit 8: counted
        only after ``store.upsert`` actually lands the row; in dry-run,
        counted on classification since no store interaction happens).
        These become stable-visible candidates with
        ``source="miss_recurrence"`` despite ``gold_rate == 0.0``.
    miss_rejected_count:
        Admitted miss candidates the store REFUSED at the stable-class
        cap (F-a: budgets are per-class now — miss candidates compete on
        ``gold_rate`` within the STABLE class, where their 0.0 still
        loses to gold rows; a full UNSTABLE bucket no longer blocks
        them). Without this field a full pool would silently swallow
        them.
    unstable_refused_count:
        Unstable (diagnosis-bucket) candidates the store refused at the
        ``MAX_PENDING_UNSTABLE`` cap this run (F-a). Surfaced so a
        churning diagnosis bucket is visible, not silent.
    stable_refused_count:
        Stable-class candidates (gold path) the store refused at the
        ``MAX_PENDING`` cap this run (gate21 pi NIT-4 — symmetric with
        ``unstable_refused_count``; previously visible only via the
        store's WARNING log). Miss-path refusals are counted separately
        in ``miss_rejected_count``.
    embedding_degraded:
        True when the pre-clustering embedding probe (one fixed-string
        ``cache.embed`` — a cache hit on repeat scans) returned None,
        meaning cosine soft-merge silently no-ops and clusters are hard
        task_id groupings only (gate17 pi BLOCK-1; design v3 M2 前置:
        degradation must be explicit in scan output, not just per-query
        warnings). The CLI lane renders the marker; this is the signal.
    miss_share_by_layer:
        Share of the miss pool per routing layer (M12 M4 item, done in
        M5 for file-ownership disjointness): ``{layer: fraction}`` over
        the same miss spans counted by ``miss_pool_size``, fractions
        summing to 1.0. The layer is read from the span's metadata
        ``layer`` field. gate18: producers (``cli/main.py`` route path,
        ``agent_runtime.handle_query``) now WRITE this field — winning
        layer on match, deepest cascade layer on miss — so new spans
        bucket by real layer; spans written before that change (and
        spans where no layer was determinable) fall into ``"unknown"``.
        Empty dict when there are no misses.
    """

    promoted_count: int = 0
    unstable_count: int = 0
    pruned_count: int = 0
    capped: bool = False
    clusters_seen: int = 0
    miss_pool_size: int = 0
    miss_admitted_count: int = 0
    miss_rejected_count: int = 0
    unstable_refused_count: int = 0
    stable_refused_count: int = 0
    # gate30 round-2 (claude NIT-2): miss candidates SKIPPED by the
    # gold/miss collision guard (a stronger gold row for the same pattern
    # already pending, by exact id or Jaccard overlap) — neither admitted
    # nor cap-rejected, so they need their own counter to stay visible in
    # scan accounting.
    miss_guard_skipped_count: int = 0
    embedding_degraded: bool = False
    miss_share_by_layer: dict[str, float] = field(default_factory=dict)


def scan_candidates(
    spans: list[dict[str, Any]],
    learner: InstinctLearner,
    store: ClusterCandidateStore,
    cache: EmbeddingCache | None = None,
    *,
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
    min_gold_rate: float = DEFAULT_MIN_GOLD_RATE,
    unstable_gold_rate: float = DEFAULT_UNSTABLE_GOLD_RATE,
    miss_cosine_threshold: float = MISS_COSINE_THRESHOLD,
    miss_min_pairs: int = MISS_RECURRENCE_MIN_PAIRS,
    miss_min_days: int = MISS_RECURRENCE_MIN_DAYS,
    behavior_threshold: float = _BEHAVIOR_JACCARD_THRESHOLD,
    dry_run: bool = False,
    include_legacy: bool = False,
) -> ScanSummary:
    """Cluster recent spans → label → populate candidate pool.

    Pipeline:

    1. ``store.prune_expired()`` (skipped in dry-run).
    2. ``cluster_queries(spans, cache)`` → list[Cluster].
    3. ``assess_gold_status(clusters, learner, min_cluster_size)`` —
       enriches each cluster with ``gold_task_ids`` / ``gold_rate``.
    4. For each cluster:
       - Skip if ``span_count < min_cluster_size``.
       - Stable candidate if ``gold_rate >= min_gold_rate``.
       - Unstable candidate if ``gold_rate < unstable_gold_rate``.
       - Otherwise (neutral zone, between the two thresholds): skip.
    4b. M12 M2 miss_recurrence admission (parallel to the gold path):
       route-miss spans (``is_route_miss_span``) are clustered separately
       at ``miss_cosine_threshold``. A miss cluster is admitted when it
       has >= ``miss_min_pairs`` distinct (task_id, natural-day) pairs
       AND covers >= ``miss_min_days`` distinct natural days
       (conjunction — gate15b). Admitted clusters bypass the gold gate:
       they become stable-visible candidates with
       ``source="miss_recurrence"`` and ``gold_rate=0.0`` recorded as-is.
       Pure-miss clusters already admitted here are NOT also filed into
       the unstable diagnosis bucket by step 4.
    5. ``label_step_frequency`` on the cluster's spans → step_freq +
       step_labels + core_steps attached to the candidate.
    6. ``store.upsert(candidate)`` (skipped in dry-run).

    On the ``min_cluster_size=3`` choice: W1 uses 5 for ``is_gold``
    (confirmed gold). W4 uses 3 because candidates are *reviewable
    suggestions*, not confirmed patterns — surfacing them earlier gives
    the human material to triage. Reviewer Q1.

    Returns ``ScanSummary``. Idempotent across rescans: upsert is
    idempotent on ``cluster_id`` and overlap-merges pending rows whose
    cluster_id drifted with membership growth (gate30,
    ``MERGE_JACCARD_THRESHOLD``), so re-scanning the same spans produces
    the same pending rows (refreshed counts, no duplicates).
    """
    from vibesop.core.observability.behavior_consistency import assess_behavior_consistency
    from vibesop.core.observability.clustering import _extract_query, cluster_queries
    from vibesop.core.observability.embedding import get_embedding_cache
    from vibesop.core.observability.gold_detection import (
        assess_gold_status,
        is_route_miss_span,
    )

    summary = ScanSummary()

    # 1) Prune TTL-expired pending rows before scanning. Dry-run leaves
    # the pool untouched so the caller can compare.
    if not dry_run:
        summary.pruned_count = store.prune_expired()

    if not spans:
        return summary

    # M3: the behavior join evaluates against the PRE-filter span list.
    # (gate24 pi#3 — an earlier note here wrongly claimed the parent route
    # "already passed the filter"; the join matches route spans in this
    # pre-filter list, filter-passing or not.) Two recorded consequences:
    # 1. pre-W5.0 tool_call spans carry no project_id and would be dropped
    #    by the age-out below; keeping them preserves per-trace evidence
    #    when their trace/parent matches a candidate.
    # 2. Legacy routes (project_id "default") never match the composite
    #    (project_id, task_id) candidate key, but their tool spans can
    #    still join via the trace_id fallback. Bidirectional effect,
    #    accepted: legacy recurrence can push n up toward consistent OR
    #    drag the mean down to divergent.
    behavior_spans = spans

    # W5.1 Task 2.3: lazy age-out for pre-W5.0 spans.
    if not include_legacy:
        spans = [s for s in spans if (s.get("project_id") or "default") != "default"]
        if not spans:
            return summary

    # gate17 pi BLOCK-1: embedding health probe before clustering. One
    # fixed-string embed — a cache hit on repeat scans, so no per-query
    # cost. None (or a backend exception) means cosine soft-merge silently
    # no-ops and every cluster below is a hard task_id grouping; that MUST
    # be explicit in scan output (design v3 M2 前置), not just per-query
    # warnings. The resolved cache is reused for both clusterings.
    resolved_cache = cache or get_embedding_cache()
    try:
        summary.embedding_degraded = resolved_cache.embed(_EMBEDDING_PROBE_TEXT) is None
    except Exception:  # backend failure modes vary (model download, OOM, ...)
        summary.embedding_degraded = True
    if summary.embedding_degraded:
        logger.warning(
            "embedding probe returned None — cosine soft-merge is degraded "
            "this scan; clusters fall back to hard task_id grouping"
        )

    # 2) Cluster recent spans.
    clusters = cluster_queries(spans, cache=resolved_cache)
    summary.clusters_seen = len(clusters)
    if not clusters:
        return summary

    # 3) Assess gold status (mutates clusters in place, populates
    # gold_task_ids + gold_rate regardless of size).
    assess_gold_status(clusters, learner, min_cluster_size=min_cluster_size)

    # 4b-pre) M12 M2 miss_recurrence path. Cluster miss-only spans at the
    # miss-specific cosine threshold (miss-vs-miss is a different
    # distribution than the gold 0.80 default — design v3 §阈值哲学) and
    # apply the recurrence gate BEFORE the gold loop so admitted pure-miss
    # clusters are not also filed into the unstable bucket.
    #
    # Degenerate content-free queries ("继续"/"可以"/"ok" — calibration
    # finding: they cosine-match EVERYTHING at 0.72–0.82) are excluded
    # BEFORE pooling; no threshold can fix a query with no information.
    miss_spans = [
        s
        for s in spans
        if is_route_miss_span(s) and not _is_low_information_query(_extract_query(s) or "")
    ]
    summary.miss_pool_size = len(miss_spans)
    summary.miss_share_by_layer = _miss_share_by_layer(miss_spans)
    admitted_miss: list[Cluster] = []
    if miss_spans:
        miss_clusters = cluster_queries(
            miss_spans,
            cache=resolved_cache,
            threshold=miss_cosine_threshold,
            include_legacy=True,  # age-out already applied above
        )
        summary.clusters_seen += len(miss_clusters)
        for mc in miss_clusters:
            pairs, days = _miss_recurrence_counts(mc, miss_spans)
            if pairs >= miss_min_pairs and days >= miss_min_days:
                admitted_miss.append(mc)
            else:
                logger.debug(
                    "miss cluster %s not admitted: %d (task_id, day) pairs "
                    "(need >=%d), %d distinct days (need >=%d)",
                    mc.cluster_id,
                    pairs,
                    miss_min_pairs,
                    days,
                    miss_min_days,
                )
    admitted_miss_keys = [frozenset(mc.task_keys) for mc in admitted_miss]

    # 4+5+6) Classify → label → upsert.
    for cluster in clusters:
        if cluster.span_count < min_cluster_size:
            continue

        if cluster.gold_rate >= min_gold_rate:
            is_unstable = False
        elif cluster.gold_rate < unstable_gold_rate:
            # M12 M2: a pure-miss cluster already admitted via the
            # miss_recurrence gate becomes a stable-visible candidate
            # below — filing it into the unstable diagnosis bucket too
            # would double-count it and hide it from list_pending().
            cluster_keys = frozenset(cluster.task_keys)
            if any(cluster_keys <= admitted for admitted in admitted_miss_keys):
                continue
            is_unstable = True
        else:
            # Neutral zone (between unstable_gold_rate and min_gold_rate)
            # — neither stable enough to suggest nor unstable enough to
            # flag. Skip silently.
            continue

        # W5.1 Task 2.1: filter spans by composite (project_id, task_id) key.
        # Pre-W5.1 used `task_id in cluster.task_ids` which collapsed the same
        # task_id across projects. Composite key is unambiguous.
        #
        # Invariant: ``cluster_queries`` always populates ``task_keys`` post-W5.1.
        # If empty, the cluster was constructed elsewhere (test fixture, manual);
        # skip with an error log rather than silently assuming "default"
        # project_id (which the lazy age-out filter has just excluded). This
        # MUST NOT be an ``assert`` — under ``python -O`` asserts are stripped,
        # the guard would vanish, and the empty ``cluster_spans`` below would
        # promote a zero-step zero-query shell candidate that renders a
        # garbage SKILL.md (review finding F2). Skip-and-log matches the
        # repo's bad-record policy (see ``_parse_lines``).
        if not cluster.task_keys:
            logger.error(
                "skipping cluster %s: empty task_keys (W5.1 invariant violated — "
                "cluster not built by cluster_queries). Manually-constructed "
                "Cluster objects must set task_keys explicitly.",
                cluster.cluster_id,
            )
            continue
        cluster_task_keys = set(cluster.task_keys)
        cluster_spans = [
            s
            for s in spans
            if (s.get("project_id") or "default", s.get("task_id")) in cluster_task_keys
        ]
        freq, labels, core_steps = label_step_frequency(
            cluster_spans, total_span_count=cluster.span_count
        )

        # M3: behavior evidence from the cluster's own spans (tool_call
        # spans are already loaded — no extra scan). Recomputed fresh
        # every rescan; upsert's whole-row refresh means the latest value
        # always wins (unlike first_seen_at's earliest-wins).
        behavior_state, behavior_score, _n_seq = assess_behavior_consistency(
            list(cluster.task_keys), behavior_spans, threshold=behavior_threshold
        )
        candidate = ClusterCandidate(
            cluster_id=cluster.cluster_id,
            task_ids=list(cluster.task_ids),
            queries=list(cluster.queries),
            span_count=cluster.span_count,
            gold_rate=cluster.gold_rate,
            gold_task_ids=list(cluster.gold_task_ids),
            first_seen_at=_earliest_span_timestamp(cluster_spans),
            step_freq=freq,
            step_labels=labels,
            core_steps=core_steps,
            is_unstable=is_unstable,
            behavior_evidence=behavior_state,
            behavior_score=behavior_score,
            project_distribution=dict(cluster.project_distribution),
        )

        if is_unstable:
            summary.unstable_count += 1
        else:
            summary.promoted_count += 1

        if dry_run:
            continue

        store.upsert(candidate)
        # F-a: surface per-class refusals. upsert silently refuses new
        # rows at the class cap under admit-only-if-better — detect the
        # refusal (row absent) and count it per class so pool churn is
        # visible in the scan output, not just in the store's WARNING log
        # (gate21 pi NIT-4: stable refusals counted symmetrically).
        landed = store.get(candidate.cluster_id) is not None
        if not landed and is_unstable:
            summary.unstable_refused_count += 1
        elif not landed:
            summary.stable_refused_count += 1
        if store.pending_count() >= MAX_PENDING:
            summary.capped = True

    # 4b-post) Upsert admitted miss_recurrence candidates. Same shape as
    # gold-path candidates; ``gold_rate`` is recorded as 0.0 as-is (miss
    # clusters carry no success signal by construction) but the row is
    # stable-visible (``is_unstable=False``) — that is the whole point of
    # the admission gate.
    for mc in admitted_miss:
        mc_keys = set(mc.task_keys)
        mc_spans = [
            s for s in miss_spans if (s.get("project_id") or "default", s.get("task_id")) in mc_keys
        ]
        freq, labels, core_steps = label_step_frequency(mc_spans, total_span_count=mc.span_count)
        behavior_state, behavior_score, _n_seq = assess_behavior_consistency(
            list(mc.task_keys), behavior_spans, threshold=behavior_threshold
        )
        candidate = ClusterCandidate(
            cluster_id=mc.cluster_id,
            task_ids=list(mc.task_ids),
            queries=list(mc.queries),
            span_count=mc.span_count,
            gold_rate=0.0,
            gold_task_ids=[],
            first_seen_at=_earliest_span_timestamp(mc_spans),
            step_freq=freq,
            step_labels=labels,
            core_steps=core_steps,
            is_unstable=False,
            source="miss_recurrence",
            behavior_evidence=behavior_state,
            behavior_score=behavior_score,
            project_distribution=dict(mc.project_distribution),
        )
        if dry_run:
            # No store interaction — count the classification itself
            # (matches promoted_count/unstable_count dry-run semantics).
            summary.miss_admitted_count += 1
            continue
        # gate17b claude nit 1: if a PENDING row with the same cluster_id
        # already exists from the gold path, do NOT let the weaker miss
        # evidence overwrite it (source gold→miss_recurrence, gold_rate→0.0,
        # both counters incremented for one row). The gold row is the
        # stronger evidence; the pattern stays reviewable either way.
        # Terminal rows (promoted/dismissed) are sticky by store contract,
        # and refreshing an existing miss_recurrence row is the intended
        # rescan path — only the gold-pending collision is guarded.
        # gate30 round-2: the check is overlap-aware AND full-set
        # (find_all_overlapping_pending), not just exact-id/best-match —
        # upsert absorbs EVERY Jaccard-overlapping same-class pending row,
        # so a best-match-only guard leaks when a miss row wins the best
        # match while a gold row gets absorbed anyway (pi M1). UNSTABLE
        # rows do NOT block via OVERLAP (claude MAJOR-1): they are the
        # weakest evidence (gold_rate below the unstable threshold) and
        # the same-class merge restriction guarantees a stable miss
        # candidate cannot absorb them — the miss row lands beside the
        # unstable diagnosis row, keeping miss patterns visible.
        blocking = [
            r
            for r in store.find_all_overlapping_pending(candidate.task_ids)
            if r.source != "miss_recurrence" and not r.is_unstable
        ]
        # Exact-id exception (pi round-2 BLOCK-1): cluster_id equality ⟹
        # identical composite-key membership ⟹ task_id sets identical ⟹
        # Jaccard 1.0 — so a NON-unstable exact row is already in
        # `blocking` and this branch is reachable ONLY for an UNSTABLE
        # exact-id row. Same-cluster identity changes the doctrine: the
        # unstable row IS this pattern's current evidence, and upsert's
        # exact-id match is a wholesale replace (gate21), so a miss
        # candidate let through here would REPLACE the diagnosis row
        # (source→miss_recurrence, gold_rate→0.0, is_unstable flipped)
        # instead of landing beside it. Block it; the pattern is already
        # visible via `vibe skill candidates --unstable`.
        exact = store.get(candidate.cluster_id)
        if (
            exact is not None
            and exact.status == "pending"
            and exact.source != "miss_recurrence"
            and all(r.cluster_id != exact.cluster_id for r in blocking)
        ):
            blocking.append(exact)
        if blocking:
            logger.info(
                "miss_recurrence candidate %s skipped: pending gold row(s) "
                "for the same pattern exist (stronger evidence wins; "
                "exact id or Jaccard-overlap match: %s)",
                candidate.cluster_id,
                [r.cluster_id for r in blocking],
            )
            summary.miss_guard_skipped_count += 1
            continue
        store.upsert(candidate)
        # gate17 claude nit 8: count only when the row actually LANDED.
        # upsert silently refuses new rows at the class cap under
        # admit-only-if-better — a gold_rate=0.0 miss candidate still
        # loses that comparison against gold rows WITHIN the stable class
        # (F-a split the budgets, so a full unstable bucket no longer
        # blocks it, but a full stable pool still can) — detect the
        # refusal (row absent) and surface it via miss_rejected_count
        # instead of lying in miss_admitted_count. An existing terminal
        # row counts as landed (the candidate IS in the pool, human
        # already decided).
        if store.get(candidate.cluster_id) is not None:
            summary.miss_admitted_count += 1
        else:
            summary.miss_rejected_count += 1
            logger.warning(
                "miss_recurrence candidate %s refused by store (stable-class "
                "pool at MAX_PENDING=%d; gold_rate=0.0 loses "
                "admit-only-if-better to gold rows). Review backlog or "
                "dismiss to make room.",
                candidate.cluster_id,
                MAX_PENDING,
            )
        if store.pending_count() >= MAX_PENDING:
            summary.capped = True

    return summary


def _earliest_span_timestamp(spans: list[dict[str, Any]]) -> datetime | None:
    """Earliest parseable span timestamp in a cluster (模式首见, M12 NIT-B).

    Feeds ``ClusterCandidate.first_seen_at`` — the discovery queue's
    "First seen" age. Same parsing tolerance as ``_miss_recurrence_counts``:
    missing/unparseable timestamps contribute nothing; tz-naive values are
    attached to UTC. An all-undated cluster yields None and the display
    layer falls back to ``created_at``.
    """
    from vibesop.core.observability._span_fields import span_timestamp

    earliest: datetime | None = None
    for span in spans:
        raw_ts = span_timestamp(span)
        if not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if earliest is None or ts < earliest:
            earliest = ts
    return earliest


def _miss_recurrence_counts(cluster: Cluster, miss_spans: list[dict[str, Any]]) -> tuple[int, int]:
    """Count distinct (task_id, natural-day) pairs and days in a miss cluster.

    The M12 M2 recurrence gate (design v3 §阈值哲学): admission requires
    ``pairs >= MISS_RECURRENCE_MIN_PAIRS`` AND ``days >=
    MISS_RECURRENCE_MIN_DAYS`` — a conjunction, not one implying the
    other (gate15b). ``task_id`` is the span's full-text-derived task key
    (same derivation as re-ask detection — no 200-char truncation
    collision). Natural days are UTC dates from the span timestamp.

    Spans with a missing/unparseable timestamp contribute NOTHING to the
    counts (conservative — an undated miss cannot prove recurrence).
    """
    from vibesop.core.observability._span_fields import span_timestamp

    member_keys = set(cluster.task_keys)
    pairs: set[tuple[str, object]] = set()
    for span in miss_spans:
        key = (span.get("project_id") or "default", span.get("task_id"))
        if key not in member_keys:
            continue
        task_id = span.get("task_id")
        raw_ts = span_timestamp(span)
        if not task_id or not raw_ts:
            continue
        try:
            ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        # Pair key is (task_id, UTC date) WITHOUT the project component:
        # the same query missed in N projects on one day counts once.
        # Conservative (never over-admits) — cross-project recurrence is
        # already signalled separately via the [XP] marker (gate17b pi).
        pairs.add((task_id, ts.date()))
    days = {day for _tid, day in pairs}
    return len(pairs), len(days)


def _miss_share_by_layer(miss_spans: list[dict[str, Any]]) -> dict[str, float]:
    """Per-layer share of the miss pool (M12 M4 item; ScanSummary field).

    Reads the span metadata ``layer`` field (dict or JSON-string
    metadata, same tolerance as ``is_route_miss_span``). Since gate18
    the route-span producers (``cli/main.py``, ``agent_runtime``) write
    ``layer`` — winning layer on match, deepest cascade layer on miss —
    so new misses bucket by the layer they fell through. Spans written
    BEFORE that change carry no such field and bucket into
    ``"unknown"`` (honest degradation for legacy data, not a bug).
    Empty pool → empty dict. Fractions sum to 1.0 (±float dust).
    """
    if not miss_spans:
        return {}
    counts: dict[str, int] = {}
    for span in miss_spans:
        meta = span.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = None
        layer = meta.get("layer") if isinstance(meta, dict) else None
        key = str(layer) if isinstance(layer, str) and layer else "unknown"
        counts[key] = counts.get(key, 0) + 1
    total = len(miss_spans)
    return {layer: count / total for layer, count in sorted(counts.items())}


def _sanitize_yaml_value(text: str, max_len: int = 80) -> str:
    """Make a string safe to interpolate into YAML frontmatter.

    Strips newlines (which break YAML parsing), truncates to ``max_len``,
    and collapses runs of internal whitespace. The result is wrapped in
    double quotes with any embedded double-quotes escaped — this makes
    colons, hashes, and other YAML metacharacters in the value safe.

    Used by ``_render_skill_md`` on raw query text before putting it in
    ``name:`` / ``description:`` fields. Without sanitization, a query
    like ``"setup: config"`` would break ``ruamel.yaml`` parsing when
    the drafted skill is later loaded by ``SkillLoader`` (grok P1).
    """
    if not text:
        return '""'
    cleaned = " ".join(str(text).split())  # collapse whitespace incl newlines
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip() + "…"
    # Escape backslashes and double quotes, then wrap in double quotes.
    # Quoting is the YAML-native way to allow colons / hashes in values.
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def sanitize_body_text(text: str, max_len: int = 200) -> str:
    """Collapse a raw query to a single display line for the SKILL.md body.

    M7 F6: raw cluster queries were embedded verbatim into the queries
    list; real queries contain ``\\n\\n`` and run to 700+ chars, which
    breaks the markdown list structure and can smuggle pseudo-instruction
    blocks into the rendered draft. Collapsing all whitespace runs to
    single spaces + truncating keeps the example readable without
    altering its wording.

    Deliberately NOT a full markdown/prompt escape: these entries are
    *examples for a human reviewer*, not executable content. Residual
    instruction-like text is inherent to showing real queries at all —
    the safeguard is human review before activation (plus the
    cross-project warning block), not character-level mangling that
    would make the examples useless.

    Public since M12 gate18 (was ``_sanitize_body_text``): the dashboard
    read-model (``dashboard/_discoveries.py``) consumes it too — renames
    must update both call sites.
    """
    cleaned = " ".join(str(text).split())
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip() + "…"
    return cleaned


# Backward-compat alias for the pre-gate18 private name.
_sanitize_body_text = sanitize_body_text


def _project_id_to_basename(project_id: str) -> str:
    """Render a project_id (absolute path) as a portable basename.

    Privacy: the SKILL.md may be shared across machines or committed to
    version control. Absolute filesystem paths leak user / org structure
    (e.g. ``/Users/jane.doe/…``); basenames don't. The pool alias (which
    ``candidates`` CLI shows) is not available here because the renderer
    runs at promote time inside ``materialize_candidate`` and shouldn't
    depend on the CLI layer to look up the pool.
    """
    try:
        return Path(project_id).name or project_id[:8]
    except (OSError, ValueError):
        return project_id[:8]


def dedupe_project_distribution(distribution: dict[str, int]) -> dict[str, int]:
    """Collapse ``{abs_path: count}`` to ``{basename: count}`` collision-free.

    Two pool members may share a basename (multiple checkouts of the same
    repo, sibling ``playground/`` dirs, etc.). Naive ``{basename: count}``
    would then emit duplicate YAML keys → ``ruamel.yaml`` raises
    ``DuplicateKeyError`` → ``SkillLoader`` returns ``None`` frontmatter
    and silently fails to load the skill (omx-code-review CRITICAL #1).

    Collisions get ``-2``, ``-3`` suffixes (the second occurrence is the
    one that needs disambiguation; the first stays bare). Counts from
    same-basename projects are NOT summed — the user can tell from the
    suffix that there are two sources.

    Grok re-review CRITICAL: the suffix algorithm must also avoid
    colliding with REAL basenames that already end in ``-N``. Example:
    ``{"/p/foo": 1, "/q/foo": 3, "/q/foo-2": 4}`` must NOT collapse to
    ``{foo: 1, foo-2: 4}`` (silently dropping the second synthetic key).
    The taken-keys set below ensures synthetic suffixes increment until
    a free slot is found.

    Also the privacy boundary: returned keys are basenames only, never
    absolute paths. Used by both ``_render_skill_md`` (YAML frontmatter
    + warning prose) and the CLI's JSON output (omx-code-review HIGH #2).
    """
    taken: set[str] = set()
    seen_count: dict[str, int] = {}
    out: dict[str, int] = {}
    for pid, count in distribution.items():
        base = _project_id_to_basename(pid)
        if base in taken:
            # Find next free synthetic key. Start at 2; if `foo-2` is
            # already taken (by a real `foo-2` path or an earlier synthetic),
            # keep incrementing.
            seen_count[base] = seen_count.get(base, 1) + 1
            candidate = f"{base}-{seen_count[base]}"
            while candidate in taken:
                seen_count[base] += 1
                candidate = f"{base}-{seen_count[base]}"
            base = candidate
        taken.add(base)
        out[base] = count
    return out


def _format_cross_project_warning(distribution: dict[str, int]) -> str:
    """Render the warning header for a heterogeneous cluster (W5.2).

    Permissive policy: all queries + steps are kept in the SKILL.md body.
    The warning is the safeguard — the user opted in via explicit
    ``--scope`` flag at promote time.

    Names source projects by basename only (no absolute paths) per the
    privacy assertion in kill criteria (brief v2 §6, tightened P-5).
    """
    if not distribution:
        return ""
    deduped = dedupe_project_distribution(distribution)
    parts = sorted(deduped.items(), key=lambda kv: kv[1], reverse=True)
    listing = ", ".join(f"`{name}` ({count} spans)" for name, count in parts)
    return (
        "\n> ⚠ **Cross-project cluster — handle with care.**\n"
        "> \n"
        "> This skill was synthesized from queries across multiple projects:\n"
        f"> {listing}. Example queries and step sequences below may encode\n"
        "> one project's workflow that doesn't apply to the other. Review\n"
        "> carefully before activating.\n"
        "> \n"
        "> Activate via: `vibe skill add <path> --scope global`\n"
    )


def _render_skill_md(
    candidate: ClusterCandidate,
    skill_id: str,
    *,
    scope: Literal["project", "global"] = "project",
) -> str:
    """Render SKILL.md content for a promoted cluster candidate.

    Template mirrors ``instinct_cmd.evolve`` (lines 370-402) — YAML
    frontmatter + Overview/When-to-Apply/Steps/Metrics sections.
    gate31: the body grew a fill-in skeleton (When-NOT-to-Apply /
    Acceptance Checklist / Anti-patterns, oneshot-web-spec methodology)
    so the human editor gets guided TODO slots instead of an empty
    shell — the review value of a skill is its acceptance bar and
    boundaries, which the trace cannot synthesize.

    The metrics block records provenance (``cluster_id``, ``gold_rate``,
    ``span_count``) so future audits can trace why this skill was
    promoted. Reviewers and humans can verify the signal that produced
    the draft.

    YAML frontmatter values are sanitized via ``_sanitize_yaml_value``
    to prevent parse failures on multi-line / colon-bearing queries
    (grok P1).

    W5.2: For cross-project clusters, ``project_distribution`` is added
    to YAML frontmatter (basenames only — absolute paths leak user /
    org structure and must never appear in the SKILL.md body) and a
    warning header is prepended after the frontmatter.

    gate32 A1: ``triggers:`` is prefilled from hygiene-filtered cluster
    queries (project scope only) so an activated skill can catch the
    pattern that produced it. This does NOT weaken M7 F3: the draft
    cannot be activated unedited (content-hash guard), so prefilled
    triggers only reach routing after human review. Global drafts get a
    TODO placeholder instead (privacy boundary, same as the queries
    block).

    M12 M5 privacy boundary (design v3 §隐私边界: 全局草稿不含示例
    query 与项目标识): for ``scope="global"`` the example-queries block
    is replaced by an omission note, ``project_distribution`` is NOT
    emitted, and the cross-project warning no longer names projects —
    even basenames are project identifiers once the draft can travel
    across machines. Project scope keeps the permissive rendering.
    """
    # M7 F3 (adjudicated design — do NOT "optimize" this back into a
    # query-derived name): ``name`` is the strongest routing-match magnet
    # (the INDEX layer grants a +0.4 containment bonus on it), so a raw
    # query here makes an unedited draft over-match the moment it is
    # injected. A neutral ``draft-<cluster>`` slug marks the draft as
    # unfinished and fails safe against accidental activation.
    # ``description`` intentionally stays provenance-only: it satisfies
    # the spec-v3 required field, acts as a neutral diluent for matching,
    # and provenance is exactly what belongs here pre-review.
    name = f"draft-{candidate.cluster_id[:8]}"
    description = _sanitize_yaml_value(
        f"Auto-drafted from cluster {candidate.cluster_id} "
        f"({candidate.span_count} spans, gold_rate={candidate.gold_rate:.0%})",
        max_len=140,
    )
    # M7 F6: queries are sanitized to single display lines (see
    # ``_sanitize_body_text``) before entering the markdown body.
    # M12 M5: global drafts carry NO example queries (privacy boundary).
    if scope == "global":
        queries_block = (
            "- (example queries omitted — global drafts never carry raw "
            "queries, per the M12 privacy boundary)"
        )
    else:
        queries_block = (
            "\n".join(f"- {_sanitize_body_text(q)}" for q in candidate.queries[:5])
            or "- (no representative queries recorded)"
        )
    # gate32 A1: prefill ``triggers:`` from the cluster's example queries
    # so an activated skill can catch the very pattern that produced it
    # (dogfood: a promoted skill scored 0.26 against its own canonical
    # query until triggers were hand-added). Three constraints, all
    # review-mandated:
    # - SAMPLES pass B4-lite hygiene (_is_low_information_query +
    #   _is_agent_prompt_shape) — the miss pool is ~64% sub-agent prompt
    #   echoes; prefilling them verbatim would auto-route future agent
    #   traffic onto the skill (pi MAJOR-1 / grok M4 / claude MAJOR-1).
    # - M7 F3 stays intact: activation still requires a human edit
    #   (draft_sha256 content-hash guard), so the indexer only ever sees
    #   reviewed triggers (pi BLOCK-2: data source = the ACTIVATED
    #   frontmatter, never raw cluster queries).
    # - M12 M5 privacy boundary: global drafts get a TODO placeholder,
    #   never raw queries (claude MAJOR-2 / grok: scope gate shared with
    #   the queries block).
    if scope == "global":
        triggers_line = (
            "# triggers: TODO after review — global drafts never prefill raw "
            "queries (M12 privacy boundary); write intent phrases by hand"
        )
    else:
        # pi impl NIT-2: sanitize at the SAME 150-char budget as the
        # hygiene shape filter — otherwise an 81–150 char sample passes
        # hygiene but gets silently truncated to 80 here, and the
        # "150 leaves margin" rationale would be false for prefilled
        # content.
        # claude impl NIT-2: filter BEFORE slicing — slicing first would
        # yield the TODO placeholder whenever the first 5 samples are all
        # hygiene-filtered even when clean samples exist deeper in the
        # list.
        clean_samples = [
            q
            for q in candidate.queries
            if not _is_low_information_query(q) and not _is_agent_prompt_shape(q)
        ]
        trigger_items = [
            _sanitize_yaml_value(q, max_len=_AGENT_PROMPT_MAX_LEN) for q in clean_samples[:5]
        ]
        if trigger_items:
            triggers_line = f"triggers: [{', '.join(trigger_items)}]"
        else:
            triggers_line = (
                "# triggers: TODO — every sample query was filtered by hygiene "
                "rules; write intent phrases by hand"
            )

    if candidate.core_steps:
        steps_block = "\n".join(
            f"{i}. {step}" for i, step in enumerate(candidate.core_steps, start=1)
        )
    else:
        # gate31: the empty case gets a guided TODO instead of a bare
        # parenthetical — the trace lacked ≥70%-frequency step names, so
        # the human editor reconstructs the procedure. gate31 pi NIT-1:
        # the pointer must match scope — global drafts omit example
        # queries (M12 privacy boundary), so pointing at them there is
        # self-contradictory guidance.
        source_hint = "the task traces" if scope == "global" else "the example queries above"
        steps_block = (
            f"1. TODO: reconstruct the procedure from {source_hint} "
            "(the cluster's spans had no step name in ≥70% of executions — "
            "the trace shows WHAT was asked, not HOW it was done)"
        )

    # W5.2: cross-project frontmatter + warning header (permissive policy).
    # M12 M5: global drafts omit project identifiers entirely — no
    # project_distribution YAML, and the warning names no projects.
    if candidate.is_cross_project and scope != "global":
        # Basenames only, collision-suffixed — never emit absolute paths
        # (privacy P-5) AND avoid duplicate YAML keys when two pool
        # members share a basename (omx-code-review CRITICAL #1).
        deduped = dedupe_project_distribution(candidate.project_distribution)
        dist_yaml_lines = "\n".join(
            f"  {name}: {count}"
            for name, count in sorted(deduped.items(), key=lambda kv: kv[1], reverse=True)
        )
        cross_project_frontmatter = f"""project_distribution:
{dist_yaml_lines}
scope_recommended: global
"""
        warning_block = _format_cross_project_warning(candidate.project_distribution)
    elif candidate.is_cross_project:
        cross_project_frontmatter = "scope_recommended: global\n"
        warning_block = (
            "\n> ⚠ **Cross-project cluster — handle with care.**\n"
            "> \n"
            "> This skill was synthesized from queries across multiple projects\n"
            "> (project names omitted: global drafts carry no project identifiers,\n"
            "> per the M12 privacy boundary). The steps below may encode one\n"
            "> project's workflow that doesn't apply to the others. Review\n"
            "> carefully before activating.\n"
        )
    else:
        cross_project_frontmatter = ""
        warning_block = ""

    # pi re-review H2: warning_block sits ABOVE ## Overview so the user
    # sees it the instant they open the SKILL.md. Trailing blank line
    # separates the last ``> ...`` quote from the heading.
    if warning_block:
        warning_block = warning_block.rstrip() + "\n\n"

    # W5.2 omx-code-review HIGH #3: footer activate path must match the
    # --scope the user actually passed. Prior version hardcoded
    # ``.vibe/skills/{id}`` regardless of scope, contradicting the stdout
    # hint for ``--scope global`` promotes within the same run.
    if scope == "global":
        activate_path = f"~/.vibe/skills/{skill_id}"
    else:
        activate_path = f".vibe/skills/{skill_id}"

    return f"""---
id: {skill_id}
name: {name}
description: {description}
{triggers_line}
tags: [auto-drafted, task-memory-loop]
intent: workflow
namespace: custom
version: 1.0.0
type: prompt
source: cluster-candidate
cluster_id: {candidate.cluster_id}
{cross_project_frontmatter}---
{warning_block}
## Overview

This skill was auto-drafted from **{candidate.span_count}** task executions
that clustered together (cluster_id: `{candidate.cluster_id}`).

- **Gold rate**: {candidate.gold_rate:.0%}
- **Gold member task_ids**: {len(candidate.gold_task_ids)} / {len(candidate.task_ids)}
- **Status**: drafted by `vibe skill promote` — NOT yet registered with
  the routing engine.

## When to Apply

Representative queries that triggered this cluster:

{queries_block}

## When NOT to Apply

<!-- gate31 skeleton: name the adjacent-but-different requests this skill
     must NOT fire on. An explicit boundary is what keeps routing precise
     after activation. Delete this section only if truly everything
     similar should route here. -->

- TODO: requests that resemble this pattern but differ in … (goal / scope / object)

## Steps

Steps below appeared in ≥70% of cluster spans (core steps). Treat as a
starting point — edit, reorder, or replace based on domain knowledge.

{steps_block}

## Acceptance Checklist

<!-- gate31 skeleton (oneshot-web-spec methodology): the review value of a
     skill is its acceptance bar written BEFORE the work, in checkable
     terms. Replace every TODO with something an observer can verify —
     numbers, exit codes, file paths — not "looks good". -->

- [ ] TODO: verifiable outcome 1 (e.g. `git status` clean, CI green)
- [ ] TODO: verifiable outcome 2

## Anti-patterns

<!-- gate31 skeleton: record how this workflow has gone WRONG before —
     soft-worded requests, skipped verification, wrong-scope edits. -->

- TODO: known failure mode 1
- TODO: known failure mode 2

## Metrics

| metric | value |
|---|---|
| span_count | {candidate.span_count} |
| gold_rate | {candidate.gold_rate:.4f} |
| gold_task_ids | {candidate.gold_task_ids} |
| core_steps | {candidate.core_steps} |
| promoted_from_cluster | {candidate.cluster_id} |

---

*Auto-drafted by `vibe skill promote`. Edit before use. To inject into
routing, copy this directory into `{activate_path.rsplit("/", 1)[0]}/` and run
`vibe skill add {activate_path}`.*


"""


@dataclass
class MaterializeResult:
    """Result of ``materialize_candidate`` (gate18 pi NIT-2).

    ``fresh`` is True only when THIS call wrote the draft — the
    existence check and the write happen inside one critical section,
    so a concurrent promote of the same cluster cannot have its bytes
    mistaken for this process's freshly generated baseline (the edit
    guard's ``draft_sha256`` relies on this).
    """

    path: Path
    fresh: bool


def materialize_candidate(
    candidate: ClusterCandidate,
    skill_id: str,
    *,
    drafts_root: Path | None = None,
    scope: Literal["project", "global"] = "project",
) -> MaterializeResult:
    """Write a SKILL.md draft for a promoted cluster candidate.

    Path: ``<drafts_root>/<skill_id>/SKILL.md`` where ``drafts_root``
    defaults to ``Path.cwd() / ".vibe" / "observability" /
    "skill_drafts"``. This path is intentionally OUTSIDE the
    ``CandidateManager._build_search_paths`` discovery roots
    (``.vibe/skills``, ``~/.config/skills``, etc.) — drafting here is
    the literal "未审不注入" guarantee. The drafted SKILL.md is invisible
    to routing until the user copies it into ``.vibe/skills/`` (or
    elsewhere on the discovery path) and runs ``vibe skill add``.

    Grok+pi P0 on W4 review: the prior implementation wrote to
    ``.vibe/skills/<id>/``, which IS in the discovery path. The
    "未审不注入" test passed only because it patched CandidateManager
    construction (which never happens during promote anyway) — the
    actual guarantee was broken: a later ``CandidateManager.get_candidates()``
    call auto-discovered the draft.

    Idempotent: if SKILL.md already exists at the target path, return
    ``fresh=False`` WITHOUT overwriting. The user may have edited the
    draft since promotion; clobbering would lose their edits.
    Re-promoting the same cluster still updates store metadata
    (reviewed_at etc.) via ``ClusterCandidateStore.promote``.

    gate18 pi NIT-2 (TOCTOU): the freshness decision is made HERE,
    inside a cross-process lock bracketing check + write — callers must
    not pre-check ``skill_path.exists()`` themselves (a pre-check races
    with a concurrent promote and could record the other process's
    bytes as the edit-guard baseline hash).

    Parameters
    ----------
    candidate:
        The promoted ``ClusterCandidate`` (status is not checked here —
        the caller is expected to have called or be about to call
        ``store.promote``).
    skill_id:
        Dotted skill ID (e.g. ``custom/screenshot-permission-popup``).
    drafts_root:
        Optional override for the drafts directory. Tests pass a
        tmp_path here; production callers leave None for cwd default.
    scope:
        ``"project"`` or ``"global"`` — used only to vary the
        activate-on-inject hint in the SKILL.md footer so it matches
        the CLI's stdout hint (omx-code-review HIGH #3). Does NOT
        affect where the draft is written (that's ``drafts_root``).

    Returns
    -------
    MaterializeResult
        ``path`` to the SKILL.md; ``fresh`` True iff this call wrote it.
    """
    root = (
        drafts_root
        if drafts_root is not None
        else (Path.cwd() / ".vibe" / "observability" / "skill_drafts")
    )
    skill_dir = root / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"

    # gate18 pi NIT-2: sibling .lock file (AtomicWriter renames the data
    # file, so locking the data path itself would not survive the swap —
    # same caveat documented in utils.file_lock).
    from vibesop.utils.file_lock import cross_process_lock

    with cross_process_lock(skill_dir / ".materialize.lock"):
        if skill_path.exists():
            logger.info(
                "skill_promote: SKILL.md already exists at %s — not overwriting",
                skill_path,
            )
            return MaterializeResult(path=skill_path, fresh=False)

        content = _render_skill_md(candidate, skill_id, scope=scope)
        # Grok re-review HIGH: use AtomicWriter (temp + rename) so a crash
        # mid-write never leaves a partial SKILL.md. SkillLoader would parse
        # garbage and silently fail to load the very promote the user just
        # confirmed. Mirrors ``ClusterCandidateStore._rewrite_all_locked``.
        from vibesop.utils.atomic_writer import write_text

        write_text(skill_path, content)
        return MaterializeResult(path=skill_path, fresh=True)
