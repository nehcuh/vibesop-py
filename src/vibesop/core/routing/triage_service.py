"""AI Triage service for routing layer 2."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from vibesop.core.matching import KeywordMatcher, MatcherConfig
from vibesop.core.models import RoutingLayer, SkillRoute
from vibesop.core.routing._protocols import LLMFactory, PromptBuilder
from vibesop.core.routing.candidate_manager import with_source_file
from vibesop.core.routing.circuit_breaker import TriageCircuitBreaker
from vibesop.core.routing.layers import LayerResult
from vibesop.core.routing.triage_cache import TriageCache
from vibesop.core.routing.triage_recall import DEFAULT_MIN_SIMILARITY, EmbeddingRecall

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from vibesop.core.config import RoutingConfig
    from vibesop.core.optimization import CandidatePrefilter
    from vibesop.core.routing.cache import CacheManager
    from vibesop.core.routing.cost_tracker import TriageCostTracker

logger = logging.getLogger(__name__)

# Decay applied to a stale (last-good) cached confidence so it never competes
# with a fresh LLM result at full weight.
LAST_GOOD_CONFIDENCE_DECAY = 0.7

# Tokens the model may use to decline a match ("no skill fits this prompt").
_NONE_TOKENS = frozenset({"none", "null", "n/a", "no-match", "nomatch", "no_match"})


def _resolve_vibe_dir(cache_dir: str | Path) -> Path:
    """Locate the .vibe dir from a cache dir.

    Standard layout is ``<root>/.vibe/cache``, where the .vibe dir is the
    parent. When cache_dir is already the .vibe dir itself (custom setups),
    use it as-is instead of blindly walking up one level.
    """
    path = Path(cache_dir)
    return path.parent if path.name == "cache" else path


def query_matches_triggers(query: str, triggers: Iterable[Any]) -> str | None:
    """Production trigger-containment semantics (gate36 修订 B extraction).

    The exact matching rule ``TriageService.has_explicit_guard_signal``
    applies to a guarded skill's declared triggers, generalized to ANY
    trigger list (e.g. a promoted draft's own triggers — the guarded-only
    ``explicit_guarded_skill_match`` can never fire on a draft id, so the
    shadow verifier wraps THIS rule instead):

    - ``query.lower()`` with apostrophes (``'`` / ``’``) stripped;
    - NO whitespace folding (``"foo  bar"`` does NOT contain ``"foo bar"``);
    - NO minimum trigger length (a 1-char trigger can match);
    - first-hit-wins in trigger list order.

    Returns the first matching trigger (original form), or ``None``.
    Deliberately NOT the ``p0_shadow`` rule from
    ``scripts/replay_routing_baseline.py`` (that one folds whitespace,
    keeps apostrophes, and imposes a ≥6-char containment floor — a
    signal-existence probe, not production semantics).
    """
    normalized_query = query.lower().replace("'", "").replace("’", "")
    for trigger in triggers:
        trigger_norm = str(trigger).lower().replace("'", "").replace("’", "")
        if trigger_norm and trigger_norm in normalized_query:
            return str(trigger)
    return None


class TriageService:
    """AI Triage layer for skill routing."""

    def __init__(
        self,
        config: RoutingConfig,
        cost_tracker: TriageCostTracker,
        prefilter: CandidatePrefilter,
        cache_manager: CacheManager,
        get_skill_source: Callable[..., str],
        llm_factory: LLMFactory | None = None,
        prompt_builder: PromptBuilder | None = None,
        triage_cache: TriageCache | None = None,
        embedding_recall: EmbeddingRecall | None = None,
    ) -> None:
        self._config = config
        self._cost_tracker = cost_tracker
        self._prefilter = prefilter
        # Consecutive unstructured-reply drops (reset on any structured
        # reply); drives the "provider format incompatible" warning.
        self._unstructured_drops = 0
        # Retained for backward compatibility and to locate the .vibe dir
        # below; triage results are no longer cached via CacheManager (the
        # persistent TriageCache is the single triage cache).
        self._cache_manager = cache_manager
        self._get_skill_source = get_skill_source
        self._llm_factory = llm_factory
        self._prompt_builder = prompt_builder
        self._llm: Any | None = None
        # Persistent cross-process cache (.vibe/triage_cache.json) — the only
        # cache backing triage results. Its dir is derived from the in-memory
        # cache's dir (.vibe/cache -> .vibe); disabled when no real cache dir
        # is available (e.g. mocked in tests).
        if triage_cache is not None:
            self._triage_cache = triage_cache
        else:
            cache_dir = getattr(cache_manager, "cache_dir", None)
            self._triage_cache = (
                TriageCache(_resolve_vibe_dir(cache_dir))
                if isinstance(cache_dir, (str, Path))
                else None
            )
        # Embedding recall for the candidate prefilter, persisted alongside
        # the triage cache (.vibe/skill_embeddings.json). None when no real
        # cache dir is available; the prefilter then uses KeywordMatcher.
        if embedding_recall is not None:
            self._embedding_recall = embedding_recall
            # Injected recall: its configured floor is authoritative — the
            # config sync in prefilter_ai_triage_candidates skips it.
            self._owns_embedding_recall = False
        else:
            cache_dir = getattr(cache_manager, "cache_dir", None)
            self._embedding_recall = (
                EmbeddingRecall(
                    _resolve_vibe_dir(cache_dir),
                    min_similarity=self._recall_min_similarity(),
                )
                if isinstance(cache_dir, (str, Path))
                else None
            )
            self._owns_embedding_recall = self._embedding_recall is not None
        self._last_recall_method: str | None = None
        self._circuit_breaker = TriageCircuitBreaker(
            enabled=getattr(config, "ai_triage_circuit_breaker_enabled", True),
            failure_threshold=getattr(config, "ai_triage_circuit_breaker_failure_threshold", 3),
            latency_threshold_ms=getattr(
                config, "ai_triage_circuit_breaker_latency_threshold_ms", 500.0
            ),
            cooldown_seconds=getattr(config, "ai_triage_circuit_breaker_cooldown_seconds", 60),
        )

    @property
    def config(self) -> RoutingConfig:
        """Current routing configuration used by this service."""
        return self._config

    @config.setter
    def config(self, value: RoutingConfig) -> None:
        self._config = value

    def try_ai_triage(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        context: Any | None = None,
    ) -> LayerResult | None:
        if not self._config.enable_ai_triage:
            return None

        # Build augmented query with memory context (before the cache lookup
        # so the persisted key matches what would be sent to the LLM).
        augmented_query = query
        if (
            context
            and context.recent_queries
            and (
                len(query) < 20
                or any(p in query.lower() for p in ("还是", "再", "继续", "也", "另外", "还有"))
            )
        ):
            augmented_query = (
                "Conversation:\n"
                + "\n".join(f"- {q}" for q in context.recent_queries[-3:])
                + f"\nCurrent request: {query}"
            )

        # Persistent cross-process cache: fresh entries skip the LLM entirely;
        # stale ones (expired TTL / changed candidates) are kept as last-good.
        # A fresh hit costs nothing (no recall, no LLM call), so it runs
        # before the LLM-availability check, the prefilter, and the
        # budget/circuit gates below — those only guard the LLM call path.
        # Serving a fresh hit with no LLM configured is safe: the entry was
        # itself an LLM routing decision, the candidates hash proves the
        # decision context is unchanged, and the session-end guard below is
        # re-validated on every hit. (Note: VIBE_AI_TRIAGE_ENABLED=0 only
        # gates the LLM client, so fresh hits are still served under it; the
        # config-level enable_ai_triage switch above remains the full
        # kill switch.) The hash covers the FULL candidate set (not the
        # prefiltered window), which is what makes lookup possible before
        # prefiltering; a changed set demotes the entry to stale, and
        # _last_good_route then re-validates the skill still exists.
        stale_entry: dict[str, Any] | None = None
        candidate_lookup: dict[str, dict[str, Any]] = {
            c["id"]: c for c in candidates if c.get("id")
        }
        if self._triage_cache is not None:
            fresh_entry, stale_entry = self._triage_cache.lookup(
                augmented_query, candidates, self._cache_ttl_hours()
            )
            if fresh_entry is not None:
                if not fresh_entry.get("skill_id"):
                    # Negative hit: this exact query (under this candidate
                    # set) was already triaged to no-match within the
                    # negative TTL — skip the LLM call entirely.
                    logger.debug("Persistent triage negative hit; skipping LLM call")
                    return None
                try:
                    skill_id = str(fresh_entry["skill_id"])
                    # Session-end guard, same criterion as the LLM path below:
                    # the entry passed the guard when stored, but skill
                    # triggers may have changed since — re-validate
                    # defensively. A guarded hit is treated as a miss and
                    # triage continues down to the gated LLM path.
                    if self.is_session_end_skill(
                        skill_id
                    ) and not self.is_explicit_session_end_signal(query, candidates):
                        logger.debug(
                            "Persistent triage hit '%s' ignored: query lacks an explicit session-end signal",
                            skill_id,
                        )
                    else:
                        route = SkillRoute(
                            skill_id=skill_id,
                            confidence=float(fresh_entry["confidence"]),
                            layer=RoutingLayer.AI_TRIAGE,
                            source=str(fresh_entry.get("source", "")),
                            description=str(fresh_entry.get("description", "")),
                            metadata=with_source_file(
                                {
                                    "ai_triage": True,
                                    "persistent_cache": True,
                                    # Cache hit: nothing was sent to the LLM (the
                                    # prefilter below was skipped), so there is no
                                    # real model or parse mode — fixed placeholders
                                    # keep the metadata keys identical to the LLM
                                    # path ("cache" marks the provenance).
                                    "structured": False,
                                    "model": "cache",
                                    "candidates_sent": 0,
                                    "recall_method": None,
                                },
                                candidate_lookup.get(skill_id) or {},
                            ),
                        )
                        return LayerResult(match=route, layer=RoutingLayer.AI_TRIAGE)
                except (KeyError, TypeError, ValueError) as e:
                    logger.debug("Failed to deserialize persistent triage entry: %s", e)

        # LLM availability gate: checked AFTER the persistent-cache lookup so
        # a fresh hit is still served when no LLM is configured; a miss (or a
        # stale-only entry) falls through to here and short-circuits exactly
        # as before — no last-good fallback, since a deliberately LLM-less
        # layer should not extend decayed stale results either.
        if self._llm is None:
            self._llm = self.init_llm_client()

        if self._llm is None or not self._llm.configured():
            return None

        # Budget enforcement. Cheap check, runs before the (expensive)
        # prefilter below: a closed gate must not pay the recall cost.
        budget = getattr(self._config, "ai_triage_budget_monthly", 5.0)
        if budget > 0:
            monthly_cost = self._cost_tracker.get_monthly_cost()
            if monthly_cost >= budget:
                # The trip below logs the single warning for this path (with
                # the cost figures in the reason); no separate log here, and
                # the 90% warning only covers the not-yet-exhausted band.
                self._circuit_breaker.trip(
                    f"budget exhausted ({monthly_cost:.4f}/{budget:.4f} USD)"
                )
                # Last-good fallback: the budget gate only guards the LLM call;
                # a stale persistent entry may still be usable while the LLM
                # path is closed. Aliveness is checked against the full
                # candidate set (is the skill still installed), not the
                # prefiltered window.
                last_good = self._last_good_route(stale_entry, candidates)
                if last_good is not None:
                    return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)
                return None
            if monthly_cost >= budget * 0.9:
                logger.warning(f"AI triage budget at {monthly_cost:.4f}/{budget:.4f} USD (90%+)")

        # Circuit breaker: fast-fail if recent calls have been slow or failing.
        # Also cheap, so it too precedes the prefilter.
        if not self._circuit_breaker.can_execute():
            logger.debug("AI triage skipped: circuit breaker is open")
            # Last-good fallback: exactly when the LLM keeps failing, a stale
            # persistent entry is the only usable triage signal left.
            last_good = self._last_good_route(stale_entry, candidates)
            if last_good is not None:
                return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)
            return None

        # Cost control: pre-filter candidates (embedding recall, keyword
        # fallback) before sending to LLM. Only reached on a cache miss with
        # both gates open — a fresh hit or a closed gate never pays the
        # recall cost.
        max_skills = self._config.ai_triage_max_skills
        triage_candidates = self.prefilter_ai_triage_candidates(query, candidates, max_skills)
        if not triage_candidates:
            # Embedding recall found nothing above the similarity floor
            # (junk query) — skip the LLM call entirely. Only reachable when
            # the candidate count exceeds ai_triage_max_skills; smaller sets
            # bypass the floor (see prefilter_ai_triage_candidates).
            logger.debug("AI triage skipped: prefilter found no relevant candidates")
            return None

        def _skill_summary(c: dict[str, Any]) -> str:
            text = c.get("intent", c.get("description", "N/A"))
            triggers = c.get("triggers", [])
            if triggers:
                return f"- {c['id']}: {text} [triggers: {', '.join(triggers)}]"
            return f"- {c['id']}: {text}"

        skills_summary = "\n".join(_skill_summary(c) for c in triage_candidates)

        prompt = self.build_ai_triage_prompt(augmented_query, skills_summary)

        start_time = time.perf_counter()
        try:
            response = self._call_llm(prompt)
            latency_ms = (time.perf_counter() - start_time) * 1000

            parsed = self.parse_ai_triage_response(response.content)
            skill_id = parsed.get("skill_id")
            parsed_confidence = parsed.get("confidence")

            # Record cost if enabled
            log_calls = getattr(self._config, "ai_triage_log_calls", True)
            if log_calls:
                input_tokens = getattr(response, "input_tokens", None)
                output_tokens = getattr(response, "output_tokens", None)
                tokens_used = getattr(response, "tokens_used", None)
                if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
                    # Fallback to tokens_used if split counts aren't available
                    if isinstance(tokens_used, int):
                        input_tokens = tokens_used
                        output_tokens = 0
                    else:
                        input_tokens = 0
                        output_tokens = 0
                self._cost_tracker.record(
                    model=getattr(response, "model", "unknown"),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    query=query,
                    selected_skill=skill_id,
                )

            # Record success for circuit breaker
            self._circuit_breaker.record_success(latency_ms)
            self._circuit_breaker.maybe_trip_on_latency()

            if not parsed.get("structured"):
                # Unstructured replies (bare token / regex-scraped) carry no
                # usable confidence signal, and the hook path has no
                # confirmation gate — stamping them with a fixed high
                # confidence silently injected skills into non-coding
                # prompts (routing-precision audit 2026-08-29: 5/7
                # negatives misrouted at a hardcoded 82%). Demote to
                # no-match and let the remaining layers decide.
                self._unstructured_drops += 1
                if self._unstructured_drops % 10 == 0:
                    # Distinct from a proper NONE decline: a provider that
                    # systematically replies unstructured silently paralyzes
                    # this layer while looking "successful" to the breaker.
                    logger.warning(
                        "AI triage dropped %d consecutive unstructured replies — "
                        "provider output format is incompatible with the parser",
                        self._unstructured_drops,
                    )
                logger.debug(
                    "AI triage reply was unstructured; dropping weak signal (query hash hidden)"
                )
                if self._triage_cache is not None:
                    self._store_negative(augmented_query, candidates)
                return None

            if skill_id:
                candidate = next((c for c in triage_candidates if c["id"] == skill_id), None)
                if candidate is None:
                    candidate = next(
                        (c for c in triage_candidates if c["id"].lower() == skill_id.lower()), None
                    )
                if candidate:
                    # Guard session-end: LLMs frequently misclassify problem
                    # reports, confusion, or negative statements as session-end
                    # signals. Only allow session-end when the query explicitly
                    # matches one of the skill's declared triggers. Checked
                    # against the FULL candidate set (same as the fresh-cache
                    # path above), not the prefiltered window, so the criterion
                    # is identical on both paths.
                    if self.is_session_end_skill(
                        skill_id
                    ) and not self.is_explicit_session_end_signal(query, candidates):
                        logger.debug(
                            "AI triage selected '%s' but query lacks an explicit session-end signal; ignoring",
                            skill_id,
                        )
                        # Still a structured reply — reset the drop counter
                        # (same rule as the match and NONE paths below).
                        self._unstructured_drops = 0
                        return None

                    source = self._get_skill_source(skill_id, candidate.get("namespace", "builtin"))
                    # Structured-only path: trust the model's bounded
                    # self-reported confidence, else default to 0.88.
                    confidence = 0.88
                    if (
                        isinstance(parsed_confidence, (int, float))
                        and not isinstance(parsed_confidence, bool)
                        and 0.0 <= float(parsed_confidence) <= 1.0
                    ):
                        confidence = float(parsed_confidence)
                    result = SkillRoute(
                        skill_id=skill_id,
                        confidence=confidence,
                        layer=RoutingLayer.AI_TRIAGE,
                        source=source,
                        description=str(candidate.get("description", "")),
                        metadata=with_source_file(
                            {
                                "ai_triage": True,
                                "structured": parsed.get("structured", False),
                                "model": getattr(response, "model", "unknown"),
                                "candidates_sent": len(triage_candidates),
                                "recall_method": self._last_recall_method,
                            },
                            candidate,
                        ),
                    )
                    if self._triage_cache is not None:
                        # Hash the full candidate set so a later lookup can
                        # run before the prefilter (see lookup above).
                        self._triage_cache.store(augmented_query, candidates, result.to_dict())
                    self._unstructured_drops = 0
                    return LayerResult(match=result, layer=RoutingLayer.AI_TRIAGE)

            # Structured reply with no usable skill (explicit null / NONE
            # verdict): a definitive no-match — cache it negatively so
            # repeat queries skip the LLM call.
            if parsed.get("structured"):
                if self._triage_cache is not None:
                    self._store_negative(augmented_query, candidates)
                self._unstructured_drops = 0
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(f"AI triage failed, falling through to next layer: {e}")
            self._circuit_breaker.record_failure(latency_ms, reason=str(e))
            # Last-good fallback: LLM failed but a stale persistent entry
            # (expired TTL / changed candidates) may still be usable.
            last_good = self._last_good_route(stale_entry, candidates)
            if last_good is not None:
                return LayerResult(match=last_good, layer=RoutingLayer.AI_TRIAGE)

        return None

    def prefilter_ai_triage_candidates(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        max_skills: int,
    ) -> list[dict[str, Any]]:
        """Pre-filter candidates for AI Triage, embedding recall first.

        Excludes management-only skills (slash-*) from semantic matching.
        Instead of sending all candidates to the LLM (wasteful), we rank
        them by embedding similarity and only send the top N. Any recall
        failure falls back to KeywordMatcher ranking, identical to the
        previous behavior. An EMPTY recall result is different from a
        failure: recall ran and every candidate scored below the similarity
        floor, so nothing is semantically relevant — return [] (the caller
        skips the LLM call) rather than backfilling the window with
        arbitrary candidates.

        Scope note: recall (and therefore the similarity floor + abstain)
        only runs when the eligible count exceeds ``max_skills`` — at or
        below the window every candidate is forwarded as-is. That is
        deliberate: for small candidate sets the floor would mostly reject
        terse/CJK queries whose embedding similarity to English skill
        descriptions is systematically low, and the LLM disambiguates
        cheaply when the window already fits.
        """
        eligible = [c for c in candidates if not c.get("management_only")]
        self._last_recall_method = None
        if self._embedding_recall is not None and self._owns_embedding_recall:
            # Sync the floor per call (not per candidate) so swapping
            # self.config after construction takes effect; an injected recall
            # keeps its own configured floor.
            self._embedding_recall.min_similarity = self._recall_min_similarity()
        if len(eligible) <= max_skills:
            return eligible

        recall_ids = (
            self._embedding_recall.recall(query, eligible, max_skills)
            if self._embedding_recall is not None
            else None
        )
        if recall_ids is not None:
            matched_ids = set(recall_ids)
            self._last_recall_method = "embedding"
        else:
            matcher_config = MatcherConfig(
                min_confidence=0.0,
                use_cache=False,
            )
            matcher = KeywordMatcher(matcher_config)
            matches = matcher.match(query, eligible, top_k=max_skills)
            matched_ids = {m.skill_id for m in matches}
            self._last_recall_method = "keyword"

        # Preserve original order for matched candidates, then backfill if needed
        prefiltered = [c for c in eligible if c["id"] in matched_ids]
        if not prefiltered and recall_ids is not None:
            # Embedding recall is healthy but found nothing above the floor:
            # abstain instead of sending arbitrary candidates to the LLM.
            return []
        if len(prefiltered) < max_skills:
            remaining = [c for c in eligible if c["id"] not in matched_ids]
            prefiltered.extend(remaining[: max_skills - len(prefiltered)])

        return prefiltered[:max_skills]

    def is_session_end_skill(self, skill_id: str) -> bool:
        """Return True if the selected skill is the session-end skill."""
        return skill_id in {"session-end", "builtin/session-end"}

    # --- Guarded skills ---------------------------------------------------
    #
    # Some skills must only win on explicit user intent, never on fuzzy
    # evidence (keyword substring bonuses, TF-IDF, token overlap, embedding
    # similarity):
    # - session-end: high side effects (wrap-up, commit, memory writes);
    #   guarded by is_explicit_session_end_signal at the triage layers.
    # - riper-workflow: its own contract ("Use ONLY when the user explicitly
    #   requests the RIPER ... workflow. Not for generic analysis, planning,
    #   or review tasks") — yet generic "workflow"/"design" queries matched
    #   it via keyword substring bonuses ("workflow" ⊂ "riper-workflow") and
    #   embedding similarity. Extra tokens let the skill's distinctive name
    #   fragment count as explicit intent even when no full trigger phrase
    #   appears verbatim (e.g. "用 RIPER 流程来做这个功能").
    #
    # SCOPE (deliberate): the guard covers only FUZZY layers — the matcher
    # pipeline (keyword/tfidf/levenshtein, enforced in
    # UnifiedRouter._try_layers) and the semantic index layer (token overlap
    # + embedding fallback, enforced in _layers.py). The EXPLICIT layer
    # (@skill syntax) and the SCENARIO layer are exempt BY DESIGN: both
    # encode user-declared intent — an explicit mention by the user, or an
    # explicit binding written by the user/project into registry.yaml /
    # .vibe/skill-routing.yaml (e.g. this repo's vibesop_dev pattern binds
    # 「改进路由」 to riper-workflow). Overriding such declared bindings
    # would make project routing configuration untrustworthy; fuzzy layers,
    # by contrast, only ever produce *inferred* matches, which is exactly
    # where the guard belongs.
    _GUARDED_SKILL_EXTRA_TOKENS: ClassVar[dict[str, tuple[str, ...]]] = {
        "riper-workflow": ("riper",),
    }
    _GUARDED_SKILL_FALLBACK_TRIGGERS: ClassVar[dict[str, list[str]]] = {
        "riper-workflow": [
            # Mirrors core/skills/riper-workflow/SKILL.md frontmatter triggers;
            # used only when no riper candidate (hence no declared triggers)
            # is present. A test pins this list against the real SKILL.md.
            "use riper",
            "riper workflow",
            "riper 工作流",
            "5 phase workflow",
            "五阶段工作流",
            "structured workflow",
        ],
    }

    def guarded_skill_name(self, skill_id: str) -> str | None:
        """Return the short name if the skill requires explicit intent, else None."""
        short = skill_id.rsplit("/", maxsplit=1)[-1].lower()
        if self.is_session_end_skill(skill_id):
            return "session-end"
        if short in self._GUARDED_SKILL_EXTRA_TOKENS:
            return short
        return None

    def has_explicit_guard_signal(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        skill_id: str,
    ) -> bool:
        """Check whether the query carries explicit intent for a guarded skill.

        Returns True for non-guarded skills (no guard to satisfy). For guarded
        skills, explicit intent means a declared trigger phrase appears in the
        query (verbatim substring, apostrophe-normalized) or one of the skill's
        extra always-explicit tokens does. Session-end delegates to the
        long-standing is_explicit_session_end_signal semantics.
        """
        short = self.guarded_skill_name(skill_id)
        if short is None:
            return True
        if short == "session-end":
            return self.is_explicit_session_end_signal(query, candidates)

        candidate: dict[str, Any] | None = None
        for c in candidates:
            if str(c.get("id", "")).rsplit("/", maxsplit=1)[-1].lower() == short:
                candidate = c
                break

        triggers: list[Any] = []
        if candidate is not None:
            raw = candidate.get("triggers", [])
            triggers = list(raw) if isinstance(raw, list) else []
        if not triggers:
            triggers = list(self._GUARDED_SKILL_FALLBACK_TRIGGERS.get(short, []))

        # gate36 修订 B: the containment loop is extracted into
        # ``query_matches_triggers`` (same semantics, same order) so the
        # promote shadow verifier can reuse the production rule.
        if query_matches_triggers(query, triggers) is not None:
            return True

        normalized_query = query.lower().replace("'", "").replace("’", "")
        return any(tok in normalized_query for tok in self._GUARDED_SKILL_EXTRA_TOKENS[short])

    def explicit_guarded_skill_match(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the guarded skill whose explicit signal appears in the query.

        Complement to has_explicit_guard_signal (a GATE on fuzzy matches):
        this is the promotion direction — when the user literally names a
        guarded skill (declared trigger phrase or always-explicit token,
        case-insensitive via the same normalization), the skill should win
        outright instead of hoping a fuzzy layer scores it first. Its
        contract suppresses exactly the generic vocabulary those layers key
        on, so without this path an explicit 「用 RIPER 流程…」 can fall all
        the way to fallback-llm. Session-end is excluded: it has its own
        fast path (UnifiedRouter._try_session_end_layer) with stricter
        trigger semantics.
        """
        for c in candidates:
            skill_id = str(c.get("id", ""))
            short = self.guarded_skill_name(skill_id)
            if short is None or short == "session-end":
                continue
            if self.has_explicit_guard_signal(query, candidates, skill_id):
                return c
        return None

    def is_explicit_session_end_signal(
        self,
        query: str,
        candidates: list[dict[str, Any]],
    ) -> bool:
        """Check whether the query contains an explicit session-end signal.

        The session-end skill is intentionally high-impact (wrap-up, commit,
        memory writes).  We therefore require an exact match against its
        declared triggers rather than relying on the LLM's loose semantic
        interpretation of "done" or "problem".
        """
        # Find the session-end candidate and its declared triggers.
        session_end_candidate: dict[str, Any] | None = None
        for c in candidates:
            if self.is_session_end_skill(c.get("id", "")):
                session_end_candidate = c
                break

        if session_end_candidate is None:
            # No session-end candidate in this triage batch -> cannot be a
            # legitimate session-end selection.
            return False

        triggers = session_end_candidate.get("triggers", [])
        if not triggers:
            # Fall back to a conservative known-signal list if triggers are absent.
            triggers = [
                "that's all for now",
                "heading out",
                "i'm leaving",
                "i'm done",
                "gotta go",
                "我要离开了",
                "先走了",
                "拜拜",
                "今天就到这里",
                "session end",
                "/session-end",
            ]

        normalized_query = query.lower()
        # Normalize common apostrophe variants so "i'm done" and "im done" both match.
        normalized_query = normalized_query.replace("'", "").replace("’", "")

        for trigger in triggers:
            trigger_norm = str(trigger).lower().replace("'", "").replace("’", "")
            if trigger_norm in normalized_query:
                return True

        return False

    def build_ai_triage_prompt(self, query: str, skills_summary: str) -> str:
        if self._prompt_builder is not None:
            version = getattr(self._config, "ai_triage_prompt_version", "v1")
            return self._prompt_builder(query, skills_summary, version)
        # Minimal fallback (no prompt_builder injected): must carry the same
        # JSON-match / NONE-decline contract as the registry prompts — a
        # forced-match fallback reintroduces the audit's false-positive
        # channel on routers built without a prompt_builder.
        return (
            f"Query: {query}\nSkills:\n{skills_summary}\n"
            "Select the single best-matching skill and respond with ONLY a JSON "
            'object {"skill_id": "<selected-skill-id>"}. '
            "If no skill matches the request (general questions, explanations, "
            "translation, chat, summaries, advice, or review-only content — "
            "reviewing/critiquing documents, designs, or plans without changing "
            "code), respond with exactly: NONE"
        )

    def init_llm_client(self) -> Any | None:
        if os.getenv("VIBE_AI_TRIAGE_ENABLED", "").lower() in ("0", "false", "no"):
            return None
        if self._llm_factory is None:
            logger.debug("No LLM factory injected — AI triage unavailable")
            return None
        try:
            provider = self._llm_factory()
            if provider is not None and provider.configured():
                return provider
            return None
        except (OSError, ValueError, RuntimeError) as e:
            logger.debug(f"LLM factory invocation failed: {e}")
            return None

    def parse_ai_triage_response(self, response: str) -> dict[str, Any]:
        """Parse AI Triage response with structured JSON priority + regex fallback.

        Returns a dict with:
            - skill_id: str | None
            - confidence: float | None
            - structured: bool (whether JSON was successfully parsed)
        """
        import json
        import re

        result: dict[str, Any] = {"skill_id": None, "confidence": None, "structured": False}

        # Try JSON first
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Strip markdown code fences
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        if cleaned.startswith("{"):
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    raw_id = data.get("skill_id")
                    if isinstance(raw_id, str) and raw_id.strip().lower() in _NONE_TOKENS:
                        raw_id = None
                    result["skill_id"] = raw_id if isinstance(raw_id, str) else None
                    result["confidence"] = data.get("confidence")
                    result["structured"] = True
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

        # Regex fallback
        if match := re.search(r"```(?:json)?\s*([\w/-]+)```", response):
            token = match.group(1).strip()
            if token.lower() not in _NONE_TOKENS:
                result["skill_id"] = token
            return result
        _MARKDOWN_FENCE_KEYWORDS = {"json", "yaml", "yml", "python", "py", "text", "markdown", "md"}
        if match := re.search(r"^[\w/-]{3,}$", response.strip(), re.MULTILINE):
            candidate = match.group(0).strip()
            if candidate.lower() in _NONE_TOKENS:
                return result
            if candidate.lower() not in _MARKDOWN_FENCE_KEYWORDS:
                result["skill_id"] = candidate
                return result

        return result

    def _cache_ttl_hours(self) -> float:
        """Persistent-cache TTL in hours (default 72); tolerant of mocks."""
        ttl = getattr(self._config, "triage_cache_ttl_hours", 72)
        return float(ttl) if isinstance(ttl, (int, float)) else 72.0

    def _store_negative(self, query: str, candidates: list[dict[str, Any]]) -> None:
        """Persist a definitive no-match so repeat queries skip the LLM call
        (negatives dominate hook traffic; TTL is capped in TriageCache)."""
        if self._triage_cache is None:
            return
        self._triage_cache.store(
            query,
            candidates,
            {
                "skill_id": None,
                "confidence": 0.0,
                "source": "",
                "description": "",
            },
        )

    def _recall_min_similarity(self) -> float:
        """Embedding-recall similarity floor; tolerant of mocks/bad config."""
        value = getattr(self._config, "ai_triage_recall_min_similarity", None)
        return float(value) if isinstance(value, (int, float)) else DEFAULT_MIN_SIMILARITY

    def _call_llm(self, prompt: str) -> Any:
        """Call the LLM with a hard timeout (config: ai_triage_timeout_seconds).

        Provider clients carry their own hardcoded transport timeouts (~30s);
        this caps the whole triage call lower for interactive routing. The
        worker thread is a daemon so a timed-out call never blocks CLI exit.
        """
        timeout_s = getattr(self._config, "ai_triage_timeout_seconds", 15.0)
        if not isinstance(timeout_s, (int, float)):
            timeout_s = 15.0
        outcome: dict[str, Any] = {}

        def _run() -> None:
            try:
                outcome["response"] = self._llm.call(
                    prompt=prompt,
                    max_tokens=self._config.ai_triage_max_tokens,
                    temperature=0.0,
                )
            except Exception as e:  # surfaced on the caller thread below
                outcome["error"] = e

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(float(timeout_s))
        if worker.is_alive():
            # The daemon worker is left running: the provider call may still
            # complete (and be billed) after we time out here, but that cost
            # is never recorded by the cost tracker.
            raise TimeoutError(f"AI triage LLM call exceeded {timeout_s}s")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["response"]

    @staticmethod
    def _skill_in_candidates(skill_id: str, candidates: list[dict[str, Any]]) -> bool:
        """Case-tolerant membership check against the candidate id set."""
        if any(c.get("id") == skill_id for c in candidates):
            return True
        lowered = skill_id.lower()
        return any(str(c.get("id", "")).lower() == lowered for c in candidates)

    def _last_good_route(
        self,
        stale_entry: dict[str, Any] | None,
        candidates: list[dict[str, Any]],
    ) -> SkillRoute | None:
        """Build a last-good route from a stale persistent entry.

        Only used when the LLM path is unavailable (call failed, circuit
        open, or budget exhausted); the stale skill must still exist in the
        full current candidate set — i.e. still installed — not merely in the
        prefiltered top-N window (a removed skill is never resurrected).

        The recorded confidence is decayed (×LAST_GOOD_CONFIDENCE_DECAY) so a
        stale result never competes with a fresh LLM result at full weight;
        the original value is kept in metadata as
        ``last_good_original_confidence``. The decayed
        confidence may fall below the router's min_confidence and be rejected
        downstream (unified.py) — that is intentional: a stale result should
        not auto-execute. The ``last_good`` metadata flag lets downstream
        consumers distinguish it from a fresh result.
        """
        if not stale_entry or not stale_entry.get("skill_id"):
            return None
        try:
            skill_id = str(stale_entry["skill_id"])
            if not self._skill_in_candidates(skill_id, candidates):
                return None
            original_confidence = float(stale_entry["confidence"])
            return SkillRoute(
                skill_id=skill_id,
                confidence=original_confidence * LAST_GOOD_CONFIDENCE_DECAY,
                layer=RoutingLayer.AI_TRIAGE,
                source=str(stale_entry.get("source", "")),
                description=str(stale_entry.get("description", "")),
                metadata=with_source_file(
                    {
                        "ai_triage": True,
                        "last_good": True,
                        "last_good_original_confidence": original_confidence,
                        # Last-good: nothing was sent to the LLM (the gates
                        # closed or the call failed before a new prompt).
                        "candidates_sent": 0,
                        # No recall fed this route: it replays a stale cache
                        # entry, so reporting self._last_recall_method here would
                        # leak the previous request's value (or, on the
                        # LLM-failure path, a recall whose result was discarded)
                        # in long-lived processes. Fixed None, same convention as
                        # the fresh-cache path above.
                        "recall_method": None,
                    },
                    next(
                        (c for c in candidates if str(c.get("id", "")).lower() == skill_id.lower()),
                        {},
                    ),
                ),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.debug("Failed to build last-good route: %s", e)
            return None
