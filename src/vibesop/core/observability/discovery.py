"""M12 M2 — Unified Discovery presentation layer over the candidate pool.

设计定案（.omx/artifacts/m12-product-design.md v3）：呈现层强制合一——
用户只面对一个 Discovery 队列；routing_pending / SkillSuggestionCollector
降为信号源。本模块只做**候选池视图**：discover 队列 = ClusterCandidateStore
里 pending 候选 + 否定列表/静音/冷却状态的合成，不合并 routing_pending
（那是后续里程碑）。

组成：

1. ``evidence_score`` — 列表排序分。公式（刻意简单、可解释）::

       score = 0.45 * min(span_count / 10, 1.0)      # 簇规模，10 span 封顶
             + 0.25 * min(distinct_task_keys / 3, 1.0)  # 准入口径 ≥3 对，封顶
             + 0.30 * source_weight                    # 来源信号强度
             + (0.10 if is_cross_project else 0.0)     # [XP] 跨项目加权

   ``source_weight``: ``source == "miss_recurrence"`` 的 miss 簇取 0.8
   （复现本身是强信号）；其余取 ``gold_rate``。注意 [XP] 加权在
   source 之后：miss+XP(1.04) 会排在非 XP 的满分 gold 簇(1.00)之前
   —— 可接受（跨项目复现是最强信号），但排序分可超过 1.0。
   distinct_task_keys 用 ``len(task_ids)`` 近似——候选行不存跨日数，
   准入侧的 (task_key, 自然日) 对计数不落到 ClusterCandidate，这里只能
   用 distinct task 数作代理（诚实降级，docstring 声明）。

2. ``DiscoverySignalStore`` — 粘性否定列表 + 临时静音，存
   ``<storage_dir>/discovery_dismissals.jsonl``。每行::

       {"kind": "dismiss"|"mute", "fingerprint": ..., "cluster_id": ...,
        "reason": str|None, "created_at": iso, "expires_at": iso|null}

   dismiss 永久有效（反馈单向收紧：``dismiss_count`` 达到
   ``DISMISS_TIGHTEN_THRESHOLD`` 时 CLI 建议上调准入阈值——只建议，
   不自动改）；mute 带 ``expires_at``，到期自动恢复，不进否定语义。

3. ``DiscoveryObservationStore`` — 冷却检测，
   ``<storage_dir>/discovery_observations.json``。候选行没有
   last_growth 字段（store 刷新时只保留 created_at），本模块在每次
   列表渲染时观测 span_count：增长则刷新 last_growth_at；
   ``COOLING_DAYS``（14 天）无增长 → 冷却降档（标注「冷却中」，
   不再主动提示）。

4. ``count_skill_route_hits`` — history 闭环检查的数据源：
   ``.vibe/analytics.jsonl``（unified router 每次路由写一条
   ExecutionRecord，带 ``primary_skill``）。instinct/learner 侧没有
   按 skill 的命中计数，FeedbackCollector 只记显式反馈——analytics
   是唯一自动累计的按 skill 命中流。

坏行跳过惯例同 ClusterCandidateStore._parse_lines：一行损坏不拖垮
整个文件。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from vibesop.core.observability.skill_promote import ClusterCandidate

logger = logging.getLogger(__name__)

__all__ = [
    "COOLING_DAYS",
    "DEFAULT_MUTE_DAYS",
    "DISMISS_TIGHTEN_THRESHOLD",
    "HISTORY_HIT_THRESHOLD",
    "DiscoveryObservationStore",
    "DiscoveryRow",
    "DiscoverySignal",
    "DiscoverySignalStore",
    "behavior_evidence_label",
    "build_queue",
    "candidate_source",
    "cluster_fingerprint",
    "count_skill_route_hits",
    "evidence_score",
    "threshold_suggestion",
]

# Knob 归属（设计 §阈值哲学）：不进 RoutingConfig——observability 域，
# 模块常量 + CLI flag，未来收 DiscoveryConfig（沿用 skill_promote.py 惯例）。
DISMISS_TIGHTEN_THRESHOLD = 5  # dismiss 计数达到此值 → 建议上调准入阈值
DEFAULT_MUTE_DAYS = 14  # --mute 默认静音时长
COOLING_DAYS = 14  # 无新增成员 N 天 → 冷却降档
HISTORY_HIT_THRESHOLD = 5  # 闭环检查：提升后技能路由命中 ≥N 次

SignalKind = Literal["dismiss", "mute"]


def _now_utc() -> datetime:
    """Single source of truth for ``datetime.now(UTC)`` — patchable in tests."""
    return datetime.now(UTC)


def _normalize_query(query: str) -> str:
    """Collapse whitespace + lowercase + truncate (matches span 200-char cap)."""
    return " ".join(str(query).split()).lower()[:200]


def cluster_fingerprint(queries: list[str]) -> str:
    """Stable fingerprint for a cluster, for the sticky negative list.

    ``cluster_id``（sha1 of sorted (project_id, task_id) composite
    keys — clustering.py W5.1）会随重扫成员变化而漂移，不适合做否定
    列表的键。指纹改用排序后的归一化 query 集——
    语义内容比成员 id 稳定。已知边界：重扫后 query 集合显著变化时指纹
    也会变（dismiss 可能「漏粘」），这是保守方向的失败模式（重新出现
    在列表，可再次 dismiss），记录在案。
    """
    normalized = sorted({_normalize_query(q) for q in queries if str(q).strip()})
    digest = hashlib.sha1("\n".join(normalized).encode("utf-8")).hexdigest()
    return digest[:16]


def candidate_source(candidate: ClusterCandidate) -> str:
    """Admission source of a candidate: ``gold`` (default) or ``miss_recurrence``.

    M2 并行路已给 ClusterCandidate 加 ``source`` 字段（gold /
    miss_recurrence）。用 getattr 防御：旧存储文件缺字段时一律视为
    gold 来源，不崩溃、不丢候选。
    """
    source = getattr(candidate, "source", None)
    return source if isinstance(source, str) and source else "gold"


def behavior_evidence_label(candidate: ClusterCandidate) -> str:
    """Behavior-evidence marker: consistent / divergent / unavailable / 未采集.

    ``behavior_evidence`` 字段由 M3 行为一致性门写入；字段缺失 =
    未采集（诚实标注，不编造）。三态语义见 behavior_consistency 模块
    docstring —— divergent（够数据但不达标）是设计原文两态之外的第三
    态，因为"有数据且低于阈值"不能诚实归入 unavailable。
    """
    evidence = getattr(candidate, "behavior_evidence", None)
    if evidence in ("consistent", "divergent", "unavailable"):
        return evidence
    return "not_collected"


def evidence_score(candidate: ClusterCandidate) -> float:
    """Sort key for the Discovery queue. Formula documented in module docstring.

    Range ≈ [0, 1.10]（含 [XP] 加权）。不追求校准，只保证「簇大、
    distinct task 多、来源信号强、跨项目」的候选排在前面。
    """
    size_term = min(candidate.span_count / 10.0, 1.0)
    task_term = min(len(candidate.task_ids) / 3.0, 1.0)
    source_weight = (
        0.8
        if candidate_source(candidate) == "miss_recurrence"
        else max(0.0, min(candidate.gold_rate, 1.0))
    )
    xp_bonus = 0.10 if candidate.is_cross_project else 0.0
    return 0.45 * size_term + 0.25 * task_term + 0.30 * source_weight + xp_bonus


@dataclass
class DiscoverySignal:
    """One negative-list / mute record (one JSONL line)."""

    kind: SignalKind
    fingerprint: str
    cluster_id: str
    reason: str | None
    created_at: datetime
    expires_at: datetime | None = None  # mute only; dismiss is permanent

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "fingerprint": self.fingerprint,
            "cluster_id": self.cluster_id,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DiscoverySignal:
        kind = d.get("kind")
        if kind not in ("dismiss", "mute"):
            msg = f"kind={kind!r} is not 'dismiss' or 'mute'"
            raise ValueError(msg)
        fingerprint = d.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            msg = "fingerprint must be a non-empty string"
            raise ValueError(msg)

        def _parse_dt(raw: Any) -> datetime | None:
            if raw is None:
                return None
            parsed = datetime.fromisoformat(raw) if isinstance(raw, str) else None
            if parsed is None:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed

        created = _parse_dt(d.get("created_at"))
        if created is None:
            msg = "created_at missing or malformed"
            raise ValueError(msg)
        return cls(
            kind=kind,
            fingerprint=fingerprint,
            cluster_id=str(d.get("cluster_id") or ""),
            reason=d.get("reason") if isinstance(d.get("reason"), str) else None,
            created_at=created,
            expires_at=_parse_dt(d.get("expires_at")),
        )


class DiscoverySignalStore:
    """Sticky negative list + temporary mutes (``discovery_dismissals.jsonl``).

    Append-only JSONL; reads skip malformed/schema-invalid lines (same
    bad-line policy as ``ClusterCandidateStore._parse_lines``). Mutes
    carry ``expires_at`` and stop matching after expiry — 到期自动恢复，
    不需要显式 unmute。
    """

    FILENAME = "discovery_dismissals.jsonl"

    def __init__(self, storage_dir: Path | str) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / self.FILENAME
        self._lock = threading.Lock()

    def record_dismiss(
        self, fingerprint: str, cluster_id: str, reason: str | None = None
    ) -> DiscoverySignal:
        """Append a permanent dismissal to the negative list."""
        return self._append(
            DiscoverySignal(
                kind="dismiss",
                fingerprint=fingerprint,
                cluster_id=cluster_id,
                reason=reason,
                created_at=_now_utc(),
            )
        )

    def record_mute(
        self,
        fingerprint: str,
        cluster_id: str,
        days: int = DEFAULT_MUTE_DAYS,
        *,
        now: datetime | None = None,
    ) -> DiscoverySignal:
        """Append a temporary mute (default 14 days, auto-restores on expiry)."""
        now = now or _now_utc()
        return self._append(
            DiscoverySignal(
                kind="mute",
                fingerprint=fingerprint,
                cluster_id=cluster_id,
                reason=None,
                created_at=now,
                expires_at=now + timedelta(days=days),
            )
        )

    def _append(self, signal: DiscoverySignal) -> DiscoverySignal:
        """Append under threading.Lock + cross-process lock (repo convention).

        POSIX: ``fcntl.flock`` on the data file (same as
        ``ClusterCandidateStore._locked_upsert``). No-fcntl platforms fall
        back to ``cross_process_lock`` (msvcrt) — prior version left those
        platforms unlocked, risking torn JSONL lines (gate17 claude nit 2).
        """
        line = json.dumps(signal.to_dict(), ensure_ascii=False) + "\n"
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            try:
                import fcntl
            except ImportError:
                from vibesop.utils.file_lock import cross_process_lock

                with (
                    cross_process_lock(self._path),
                    self._path.open("a", encoding="utf-8") as f,
                ):
                    f.write(line)
                return signal
            with self._path.open("a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(line)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return signal

    def list_all(self) -> list[DiscoverySignal]:
        """Every well-formed record in file order (bad lines skipped)."""
        if not self._path.exists():
            return []
        out: list[DiscoverySignal] = []
        with self._path.open("r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    out.append(DiscoverySignal.from_dict(json.loads(line)))
                except (json.JSONDecodeError, ValueError, TypeError):
                    logger.debug(
                        "skipping malformed discovery-signal line %d in %s",
                        lineno,
                        self._path,
                    )
        return out

    def dismissed_fingerprints(self) -> set[str]:
        """Fingerprints on the sticky negative list."""
        return {s.fingerprint for s in self.list_all() if s.kind == "dismiss"}

    def active_mutes(self, now: datetime | None = None) -> dict[str, datetime]:
        """Fingerprint → expires_at for mutes still in effect at ``now``."""
        now = now or _now_utc()
        return {
            s.fingerprint: s.expires_at
            for s in self.list_all()
            if s.kind == "mute" and s.expires_at is not None and s.expires_at > now
        }

    def dismiss_count(self) -> int:
        """Total dismissals recorded — input to the one-way tightening hint."""
        return sum(1 for s in self.list_all() if s.kind == "dismiss")

    def dismissals(self) -> list[DiscoverySignal]:
        return [s for s in self.list_all() if s.kind == "dismiss"]


class DiscoveryObservationStore:
    """Growth observations for cooling detection (``discovery_observations.json``).

    The candidate row has no last-growth timestamp (store refreshes
    preserve ``created_at`` only), so cooling is derived here: each
    ``observe`` call compares the current ``span_count`` with the last
    recorded value; growth refreshes ``last_growth_at``. A candidate
    with no growth for ``COOLING_DAYS`` is cooling (降档: annotated
    「冷却中」, no proactive prompting).

    Whole-file JSON (small: bounded by the pending-pool budgets — up to
    MAX_PENDING stable + MAX_PENDING_UNSTABLE unstable entries since the
    F-a class separation, plus terminal rows are not observed). Corrupt
    file → treated as empty (same fail-open spirit as the bad-line
    policy).
    """

    FILENAME = "discovery_observations.json"

    def __init__(self, storage_dir: Path | str) -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / self.FILENAME
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.debug("corrupt discovery observations file %s — starting empty", self._path)
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, Any]) -> None:
        from vibesop.utils.atomic_writer import AtomicWriter

        with AtomicWriter().atomic_open(self._path, "w") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))

    def observe(self, fingerprint: str, span_count: int, *, now: datetime | None = None) -> bool:
        """Record one observation. Returns True iff the cluster grew.

        First sighting or ``span_count`` increase → refresh
        ``last_growth_at``. Same-or-smaller count leaves the timestamp
        alone (a rescan that shrinks the cluster must not fake activity).

        Read-modify-write runs under threading.Lock + cross-process lock
        (fcntl on POSIX, ``cross_process_lock`` fallback — same convention
        as ``ClusterCandidateStore``), so a concurrent ``discover`` in
        another process can't lose a growth refresh (gate17 claude nit 2).
        """
        now = now or _now_utc()
        with self._lock:
            try:
                import fcntl
            except ImportError:
                from vibesop.utils.file_lock import cross_process_lock

                with cross_process_lock(self._path):
                    return self._do_observe(fingerprint, span_count, now)
            with self._path.open("a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    return self._do_observe(fingerprint, span_count, now)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _do_observe(self, fingerprint: str, span_count: int, now: datetime) -> bool:
        """Caller MUST hold threading.Lock + cross-process lock."""
        data = self._load()
        entry = data.get(fingerprint)
        prev_count = entry.get("span_count", 0) if isinstance(entry, dict) else 0
        grew = entry is None or span_count > prev_count
        if grew:
            data[fingerprint] = {
                "span_count": span_count,
                # gate23 (claude#2): NOT the same clock as
                # ``ClusterCandidate.first_seen_at`` (skill_promote.py) —
                # that one is the cluster's earliest span timestamp
                # (模式首见, drives the discover "First seen" column);
                # this one is when the discovery queue first OBSERVED the
                # candidate (this entry's ``last_growth_at`` is what
                # drives cooling).
                "first_seen_at": (entry.get("first_seen_at") if isinstance(entry, dict) else None)
                or now.isoformat(),
                "last_growth_at": now.isoformat(),
            }
            self._save(data)
        return grew

    def last_growth_at(self, fingerprint: str) -> datetime | None:
        entry = self._load().get(fingerprint)
        if not isinstance(entry, dict):
            return None
        raw = entry.get("last_growth_at")
        if not isinstance(raw, str):
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed

    def is_cooling(self, fingerprint: str, *, now: datetime | None = None) -> bool:
        """True when the cluster has had no new members for ``COOLING_DAYS``."""
        last = self.last_growth_at(fingerprint)
        if last is None:
            return False  # never observed → treat as fresh, not cooling
        now = now or _now_utc()
        return now - last >= timedelta(days=COOLING_DAYS)


@dataclass
class DiscoveryRow:
    """View-model for one Discovery queue card."""

    candidate: ClusterCandidate
    fingerprint: str
    score: float
    source: str
    behavior: str  # consistent / divergent / unavailable / not_collected
    dismissed: bool = False
    muted: bool = False
    mute_expires_at: datetime | None = None
    cooling: bool = False
    age_days: int = 0


def build_queue(
    candidates: list[ClusterCandidate],
    signal_store: DiscoverySignalStore,
    observation_store: DiscoveryObservationStore,
    *,
    now: datetime | None = None,
    observe: bool = True,
    extra_dismissed: set[str] | None = None,
    extra_mutes: dict[str, datetime] | None = None,
) -> list[DiscoveryRow]:
    """Compose the unified Discovery queue from pending candidates.

    Joins each candidate with negative-list / mute / cooling state and
    sorts by ``evidence_score`` desc (tie: span_count desc, cluster_id).
    ``observe=True`` records span_count growth (drives cooling); pass
    False for read-only renders.

    ``extra_dismissed`` / ``extra_mutes`` merge a second scope's signals
    (the CLI reads project + global stores; a fingerprint dismissed in
    either scope is treated as dismissed).
    """
    now = now or _now_utc()
    dismissed = signal_store.dismissed_fingerprints() | (extra_dismissed or set())
    mutes = {**signal_store.active_mutes(now), **(extra_mutes or {})}

    rows: list[DiscoveryRow] = []
    for candidate in candidates:
        fingerprint = cluster_fingerprint(candidate.queries)
        if observe:
            observation_store.observe(fingerprint, candidate.span_count, now=now)
        rows.append(
            DiscoveryRow(
                candidate=candidate,
                fingerprint=fingerprint,
                score=evidence_score(candidate),
                source=candidate_source(candidate),
                behavior=behavior_evidence_label(candidate),
                dismissed=fingerprint in dismissed,
                muted=fingerprint in mutes,
                mute_expires_at=mutes.get(fingerprint),
                cooling=observation_store.is_cooling(fingerprint, now=now),
                # M12 NIT-B: 簇首见年龄 (pattern first-sight), not 入池年龄.
                # Legacy rows without first_seen_at fall back to created_at.
                age_days=max(0, (now - (candidate.first_seen_at or candidate.created_at)).days),
            )
        )
    rows.sort(key=lambda r: (r.score, r.candidate.span_count, r.candidate.cluster_id), reverse=True)
    return rows


def threshold_suggestion(dismiss_count: int, *, source: str | None = None) -> str | None:
    """One-way tightening hint (阈值哲学: dismiss 反馈单向收紧).

    Returns the suggestion text when the dismiss count reaches
    ``DISMISS_TIGHTEN_THRESHOLD``, else None. Suggestion only — the
    admission thresholds are never auto-changed.

    ``source`` makes the hint actionable (gate17 claude nit 3):
    ``--min-cluster-size`` / ``--min-gold-rate`` gate gold clusters only
    and do NOT affect ``miss_recurrence`` admission — for miss-sourced
    candidates the miss knobs are the right ones to raise.
    """
    if dismiss_count < DISMISS_TIGHTEN_THRESHOLD:
        return None
    knobs = (
        "`--miss-min-pairs` / `--miss-min-days` 或 `--miss-cosine-threshold`"
        "（该候选来自 miss_recurrence；--min-cluster-size/--min-gold-rate 对 miss 准入无效）"
        if source == "miss_recurrence"
        else "`vibe skill scan-candidates --min-cluster-size` / `--min-gold-rate`"
    )
    return (
        f"dismiss 计数已达 {dismiss_count}（阈值 {DISMISS_TIGHTEN_THRESHOLD}）："
        f"误报偏多，建议上调准入门槛（如 {knobs}）。只建议，不自动修改。"
    )


def count_skill_route_hits(
    skill_id: str, analytics_path: Path | str, *, since: datetime | None = None
) -> int | None:
    """Count post-promotion route hits for a skill (history 闭环检查).

    数据源结论：``analytics.jsonl`` 的 ExecutionRecord.primary_skill
    是唯一自动累计的按 skill 命中流（core/routing/unified.py 每次路由
    写入）。instinct/learner 无按 skill 命中计数；FeedbackCollector
    只记显式反馈，覆盖不全。

    ``since``（gate17 pi nit 4）：只计不早于该时间的记录（传入
    promote 的 reviewed_at 即为「提升后命中」）。记录缺 timestamp 或
    时间戳无法解析时仍计入（best-effort，保守方向是多计不是漏计；
    analytics 生产侧恒写 timestamp，实际不会触发）。

    Returns None when the analytics file does not exist (暂无数据源 —
    unified router 从未在此项目记录路由)；0 means the file exists but
    the skill has no recorded hits（未激活或激活后未被命中；若激活时
    改过 skill_id，按 promote 时记录的 id 无法关联）。

    Bad lines skipped (same policy as the other JSONL stores).
    """
    path = Path(analytics_path)
    if not path.exists():
        return None
    hits = 0
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not (isinstance(record, dict) and record.get("primary_skill") == skill_id):
                continue
            if since is not None:
                raw_ts = record.get("timestamp")
                parsed: datetime | None = None
                if isinstance(raw_ts, str):
                    try:
                        parsed = datetime.fromisoformat(raw_ts)
                    except ValueError:
                        parsed = None
                    if parsed is not None and parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                if parsed is not None and parsed < since:
                    continue  # pre-promotion hit — outside the window
            hits += 1
    return hits
