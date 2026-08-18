# 门禁 7b 复审包:BLOCK 修复 + 收敛 NIT

## 背景

gate7:pi BLOCK(_route_lock 竞态,300/300 复现 levenshtein 被永久静默移除)+ claude PASS_WITH_NITS。本轮修复 BLOCK + 两路共同/重要 NIT。合并后 1786 passed, 2 skipped。

## 修复清单(均含测试)

1. **BLOCK**:full_matchers 读取/交换/复原全部移入 _route_lock 临界区;并发回归测试(8 线程×10 交错,monkeypatch sleep 放大窗口,断言列表逐相等且 LEVENSHTEIN 在)
2. **OSA ≥6 字符下限**:转置折扣仅当较短 token ≥6;form/from、trail/trial、angel/angle、dairy/diary 距离 2 不过阈值;reivew/review 保留;CJK 4 字转置不享折扣(与 OSA 前基线一致,是否设 CJK 专用门限记录为产品决策)
3. **两遍制注释更正**:与代码一致(第一遍有果 levenshtein 不进 merged_matches;第二遍全量照常进 apply_optimizations)
4. **wrapped-junk 遥测短路**:unwrap 后再过一次 _is_junk_query,命中即返回 junk result,遥测整体跳过;测试断言 miss_counter/pending 零写入
5. **unwrap 正则全锚定**:DOTALL + tempered 非贪婪,病态输入(含第二个闭合标签)不解包
6. **token 判据去副本**:strategies.py 提模块级 _is_meaningful_token(Keyword/Levenshtein 共用),routing_pending.py 删本地副本改 lazy import
7. **suppress 改 hash-only**:与 dedup 对齐,空 hash 回落语义一致;is_suppressed 同步
8. **增量索引 RMW 锁**:cross_process_lock sidecar,锁内重读再合并;锁 OSError 降级 False;并发测试(2 线程 sleep 放大窗口不丢条目)
9. **global 死路径诚实化**:docstring Scope caveat + 按 scope 区分的降级提示(global → 提示 vibe skills index --scope global)

## 遗留(记录不修)

- pi NIT-e(dedup 折叠吞歧义信号,建议折为 alternatives):设计变更,下轮
- pi NIT-f(CJK 3+ 字确认语穿透闸门):接受保守,已注释?请验证是否真有注释
- pi NIT-g(闸门在 store 层):设计残留,今日无绕过路径
- claude NIT-2(闸门边界文档:调试/修 bug 被拦):token 启发式固有边界
- CJK 转置专用门限:新产品决策

## 请重点攻击

1. BLOCK 修复是否真正消除竞态(读-换-复原同临界区)?并发测试是否真钉死(突变:把读取移回锁外,测试应失败)?
2. OSA ≥6 下限的边界:恰好 6 字符异义对(如 unrest/…自己构造)是否仍可误匹配?这是可接受的残余吗?
3. wrapped-junk 二次 _is_junk_query 判断与 route() 入口守卫的重复是否有不一致场景?
4. suppress hash-only 是否过度压制(同 query 合法换新技能的场景)?
5. 增量索引锁与全量 build_index 无锁的共存——sidecar 同名吗?会不会互相等锁?

## src diff(累计,含 gate7 原改动)

diff --git a/src/vibesop/cli/commands/instinct_cmd.py b/src/vibesop/cli/commands/instinct_cmd.py
index c71f352..52d76f3 100644
--- a/src/vibesop/cli/commands/instinct_cmd.py
+++ b/src/vibesop/cli/commands/instinct_cmd.py
@@ -811,22 +811,20 @@ def feedback_collect(
     min_miss_count: int = typer.Option(
         3, "--min-miss-count", help="miss hash 被纳入衰减的次数下限"
     ),
-    boost_threshold_apps: int = typer.Option(
-        2,
-        "--boost-threshold-apps",
-        help="单 instinct 应用次数 ≤ 此值且 success_rate ≥ 0.8 时增强",
-    ),
     dry_run: bool = typer.Option(False, "--dry-run", help="只打印，不写盘"),
 ) -> None:
-    """根据 miss counter 反馈双向调整 instinct 置信度（计划 §5e）。
+    """根据 miss counter 反馈下调 instinct 置信度（计划 §5e，仅 decay 方向）。
 
     - **Decay**：高频 miss 命中的 instinct → ``record_outcome(success=False)``，
-      让 Wilson score 自动下调 confidence。
-    - **Boost**：success_rate ≥ 0.8 且应用次数少 → ``record_outcome(success=True)``，
-      加速其从候选变可靠。
+      让 Wilson score 自动下调 confidence。负信号有真实外部来源（miss counter）。
     - **Early-stop**：confidence ≥ 0.95 或 ≤ 0.1 跳过（避免无意义震荡）。
     - **Watermark**：处理过的 miss hash 写盘，下次跳过；``miss.decay_frequent``
       把 frequent count 减半（不 clear，保留 first/last）。
+
+    正向（boost）分支已拆除：正信号的唯一合法来源是显式人确认
+    （CLI feedback、pending accept、replay 确认），自动
+    ``record_outcome(success=True)`` 会毒化 Wilson confidence
+    （与 unified.py 的既有设计哲学一致）。
     """
     from vibesop.core.instinct.learner import InstinctLearner
     from vibesop.core.skills.miss_counter import MissCounter
@@ -840,19 +838,13 @@ def feedback_collect(
 
     learner = InstinctLearner(_get_storage_path())
     decayed = 0
-    boosted = 0
     skipped_early_stop = 0
     decayed_hashes: set[str] = set()
-    # Iterate ALL instincts, not just reliable ones. Plan v2 §5e originally
-    # specified ``get_reliable_instincts()`` but combined with the default
-    # ``boost_threshold_apps=2`` it made the boost branch unreachable:
-    # reliable requires ``total_applications >= 3`` while boost requires
-    # ``<= 2``. The plan's intent was "boost under-utilized instincts to
-    # surface them faster" — that's only possible if we look outside the
-    # already-reliable set. Early-stop at confidence ≤ 0.1 protects against
-    # boosting dying instincts; early-stop at ≥ 0.95 prevents saturation;
-    # ``total_applications >= 1`` skips never-applied instincts (pi P2-B)
-    # so a freshly-imported or theory-only instinct can't get a free boost.
+    # Iterate ALL instincts, not just reliable ones (``get_reliable_instincts``
+    # requires ``total_applications >= 3``): an under-utilized instinct that
+    # keeps accumulating frequent misses should decay too, not get a free
+    # pass just because it hasn't been applied often. Early-stop guards both
+    # ends of the confidence range.
     all_instincts = sorted(
         learner.instincts.values(), key=lambda i: i.confidence, reverse=True
     )
@@ -871,33 +863,19 @@ def feedback_collect(
             decayed += 1
             decayed_hashes.add(h)
             _add_watermark(processed_watermark, h)
-        elif (
-            ins.total_applications >= 1
-            and ins.success_rate >= 0.8
-            and ins.total_applications <= boost_threshold_apps
-        ):
-            if dry_run:
-                console.print(f"[dim]would boost:[/dim] {ins.pattern} (n={ins.total_applications})")
-            else:
-                learner.record_outcome(ins.id, success=True)
-            boosted += 1
-
-    if not dry_run:
-        if decayed:
-            # Scope the miss-counter decay to hashes feedback-collect actually
-            # touched — without this filter, ``decay_frequent`` halves every
-            # cluster at ≥ min_miss_count, erasing signal for instincts that
-            # were early-stopped or already in the watermark (pi Phase D P2-D).
-            miss.decay_frequent(min_miss_count, hashes=decayed_hashes)
-        if decayed or boosted:
-            learner.save()
-        if decayed:
-            _save_watermark(processed_watermark)
+
+    if not dry_run and decayed:
+        # Scope the miss-counter decay to hashes feedback-collect actually
+        # touched — without this filter, ``decay_frequent`` halves every
+        # cluster at ≥ min_miss_count, erasing signal for instincts that
+        # were early-stopped or already in the watermark (pi Phase D P2-D).
+        miss.decay_frequent(min_miss_count, hashes=decayed_hashes)
+        learner.save()
+        _save_watermark(processed_watermark)
 
     console.print(
         f"[bold]Feedback collected[/bold]: "
         f"[red]{decayed} decayed[/red], "
-        f"[green]{boosted} boosted[/green], "
         f"[dim]{skipped_early_stop} early-stop skipped[/dim]"
     )
     if dry_run:
diff --git a/src/vibesop/cli/commands/skill_commands.py b/src/vibesop/cli/commands/skill_commands.py
index d62042f..b4418d5 100644
--- a/src/vibesop/cli/commands/skill_commands.py
+++ b/src/vibesop/cli/commands/skill_commands.py
@@ -530,12 +530,23 @@ def add(
         _manual_configure_skill(metadata, scope)
 
     console.print("\n[dim]Phase 6: Verifying...[/dim]")
-    _verify_and_sync(metadata.id, scope)
+    indexed = _verify_and_sync(metadata.id, scope)
 
     console.print("\n[bold green]✨ Installation complete![/bold green]")
+    if indexed:
+        ready_line = f"[bold]{metadata.name}[/bold] is now ready to use!"
+    else:
+        # Honest fallback (M7): without the semantic index entry the skill
+        # is invisible to the SEMANTIC_INDEX routing layer — don't claim
+        # "ready to use" until `vibe skills index` has run.
+        ready_line = (
+            f"[bold]{metadata.name}[/bold] is installed.\n"
+            f"[yellow]Run [cyan]vibe skills index[/cyan] before it can be "
+            f"semantically routed.[/yellow]"
+        )
     console.print(
         Panel(
-            f"[bold]{metadata.name}[/bold] is now ready to use!\n\n"
+            f"{ready_line}\n\n"
             f"[dim]Test it with:[/dim]\n"
             f'  [cyan]vibe route "{metadata.trigger_when or "test query"}"[/cyan]\n\n'
             f"[dim]View details:[/dim]\n"
@@ -983,7 +994,15 @@ def _extract_keywords(text: str) -> list[str]:
     return [word for word, _ in counter.most_common(5)]
 
 
-def _verify_and_sync(skill_id: str, _scope: str) -> None:
+def _verify_and_sync(skill_id: str, scope: str) -> bool:
+    """Smoke-test routing, then incrementally index the newly added skill.
+
+    Returns True when the skill's profile was merged into the semantic
+    index (SEMANTIC_INDEX layer); False when indexing was skipped or
+    failed (no LLM configured, analysis failed) — the caller must then
+    say ``vibe skills index`` is still required instead of claiming the
+    skill is "ready to use" (M7 skill add activation breakpoint).
+    """
     from vibesop.core.routing.unified import UnifiedRouter
 
     router = UnifiedRouter(project_root=Path())
@@ -1004,8 +1023,120 @@ def _verify_and_sync(skill_id: str, _scope: str) -> None:
     if not matched:
         console.print("[yellow]⚠ Routing test: No direct match (this is OK)[/yellow]")
 
+    indexed = _index_newly_added_skill(skill_id, scope)
+
     console.print("[dim]Syncing to platform...[/dim]")
     console.print("[green]✓ Synced[/green]")
+    return indexed
+
+
+def _index_newly_added_skill(skill_id: str, scope: str) -> bool:
+    """Incrementally index ONE newly installed skill into the semantic index.
+
+    Analyzes just the new skill (one LLM call + one embedding) and merges
+    its profile into the matching index layer — project index for project
+    installs, global index otherwise. A full ``build_index`` is
+    deliberately avoided: it would re-walk every discovered skill and
+    re-write whole layers, far too slow for an install path.
+
+    Scope caveat (gate7 pi NIT-b): incremental indexing currently only
+    takes effect for PROJECT-scope installs. ``vibe skill add --global``
+    installs to ``~/.vibe/.vibe/skills/<id>``, which is outside
+    ``SkillLoader``'s search paths, so global installs always degrade to
+    "not yet discoverable" — run ``vibe skills index --scope global``
+    after a global install. Unifying the global install path is a Tier2
+    item; this function's contract is honesty, not coverage.
+
+    Uses SkillIndexer's single-skill building blocks — no public
+    single-skill API exists and the indexer is outside this change's
+    edit scope. Best-effort: degrades to False (never raises) when no
+    LLM is configured or analysis fails, so installation itself never
+    fails because the optional index step couldn't run.
+    """
+    try:
+        from vibesop.core.llm_config import LLMConfigResolver
+        from vibesop.core.skills.indexer import SkillIndexer
+        from vibesop.core.skills.loader import SkillLoader
+        from vibesop.llm.factory import create_provider
+        from vibesop.utils.file_lock import cross_process_lock
+
+        cfg = LLMConfigResolver().get_llm_for_understanding()
+        if not cfg or not cfg.provider:
+            console.print(
+                "[dim]No LLM configured — skipping semantic indexing "
+                "(run `vibe skills index` later)[/dim]"
+            )
+            return False
+
+        indexer = SkillIndexer(
+            project_root=Path(),
+            llm_factory=lambda: create_provider(
+                provider=cfg.provider,
+                api_key=cfg.api_key,
+                base_url=cfg.api_base,
+            ),
+        )
+        llm = indexer._get_llm()
+        if llm is None:
+            return False
+
+        loaded = SkillLoader(project_root=Path()).get_skill(skill_id)
+        if loaded is None:
+            if scope == "global":
+                # See docstring: global installs land outside SkillLoader's
+                # search paths (Tier2 known issue) — this is the expected
+                # path for --global, not a transient failure.
+                console.print(
+                    f"[yellow]⚠ Incremental indexing is project-scope only — "
+                    f"run `vibe skills index --scope global` to make "
+                    f"'{skill_id}' semantically routable.[/yellow]"
+                )
+            else:
+                console.print(
+                    f"[dim]Skill '{skill_id}' not yet discoverable — "
+                    "skipping semantic indexing "
+                    "(run `vibe skills index` later)[/dim]"
+                )
+            return False
+
+        console.print("[dim]Indexing new skill (incremental, single skill)...[/dim]")
+        profile = indexer._analyze_skill(loaded, llm)
+        if profile is None:
+            return False
+        indexer._compute_embeddings({skill_id: profile})
+
+        layer = "project" if scope == "project" else "global"
+        index_path = (
+            indexer.project_index_path if layer == "project" else indexer.global_index_path
+        )
+        # gate7 claude NIT-1: the load→merge→save read-modify-write runs
+        # under a cross-process sidecar lock (same standard slice B set
+        # for routing_pending). Without it, two concurrent `skill add`
+        # runs (or add racing `skills index`) silently drop entries.
+        # The index is RE-READ inside the lock — merging into a dict read
+        # before acquiring it would defeat the lock entirely.
+        lock_path = Path(f"{index_path}.lock")
+        try:
+            with cross_process_lock(lock_path):
+                existing = indexer._load_single_index(index_path)
+                existing[skill_id] = profile
+                indexer._save_index(existing, scope=layer)
+        except OSError as e:  # lock file unavailable / IO error → degrade
+            logger.debug("Incremental indexing lock/IO failed for %s: %s", skill_id, e)
+            console.print(
+                "[yellow]⚠ Semantic indexing failed — "
+                "run `vibe skills index` to enable semantic routing[/yellow]"
+            )
+            return False
+        console.print(f"[green]✓ Indexed into {layer} semantic index[/green]")
+        return True
+    except Exception as e:  # indexing is best-effort; never fail the install
+        logger.debug("Incremental indexing failed for %s: %s", skill_id, e)
+        console.print(
+            "[yellow]⚠ Semantic indexing failed — "
+            "run `vibe skills index` to enable semantic routing[/yellow]"
+        )
+        return False
 
 
 @app.command(name="cleanup", help="Interactively review and clean up low-quality or stale skills")
@@ -1518,6 +1649,22 @@ def promote_cmd(  # pyright: ignore[reportUnusedFunction]
             f"  [dim]activate:[/dim] copy to .vibe/skills/{skill_id}/ and run "
             f"`vibe skill add .vibe/skills/{skill_id}`"
         )
+    # M7: `vibe skill add` now incrementally indexes the installed skill,
+    # so no separate full rebuild is needed when an LLM is configured.
+    console.print(
+        "  [dim]index:[/dim] `vibe skill add` indexes the skill incrementally "
+        "(needs a configured LLM); otherwise run `vibe skills index`"
+    )
+    console.print("  [dim]review checklist before activating:[/dim]")
+    console.print(
+        "    [dim]1. rewrite name/description into intent keywords "
+        "(the draft name is a placeholder)[/dim]"
+    )
+    console.print(
+        "    [dim]2. confirm the example queries are a single workflow — "
+        "split the draft if they aren't[/dim]"
+    )
+    console.print("    [dim]3. spell out when this skill should NOT be used[/dim]")
 
 
 @app.command(name="dismiss")
diff --git a/src/vibesop/core/instinct/routing_pending.py b/src/vibesop/core/instinct/routing_pending.py
index 8137c72..84bc8db 100644
--- a/src/vibesop/core/instinct/routing_pending.py
+++ b/src/vibesop/core/instinct/routing_pending.py
@@ -7,9 +7,19 @@ and explicit user corrections waiting for accept/dismiss.
 Design constraints (pi H1 + evolution final):
 - Human-readable Chinese reasons
 - ≤3 new pending items per calendar day (rate limit)
-- Dedup: same query_hash + skill_id while still pending → no re-add
+- Dedup: same query_hash while still pending → no re-add (M7: the same
+  garbage query routed to 2 skills must not consume 2 of the 3 daily slots;
+  the daily cap likewise counts distinct query_hash, not rows)
+- Low-information queries (<2 meaningful tokens — "可以", "✓", "/review")
+  are NOT enqueued; they degrade into MissCounter records so a genuine
+  false positive still surfaces as a frequent miss (M7 dogfood: the review
+  queue died of alert fatigue, 7/7 items were low-info junk)
 - Dismiss suppresses re-enqueue for 24h
 - Accept/dismiss write back via InstinctLearner + PreferenceLearner (callers)
+- Writes are serialized cross-process: every ``vibe route`` builds a fresh
+  store instance, so ``try_enqueue``/``_resolve`` re-read the file under a
+  ``cross_process_lock`` sidecar lock before rewriting it (RMW — locking
+  only the write would still lose updates from stale in-memory items)
 """
 
 from __future__ import annotations
@@ -24,6 +34,7 @@ from pathlib import Path
 from typing import Any, Literal
 
 from vibesop.utils.atomic_writer import write_text
+from vibesop.utils.file_lock import cross_process_lock
 
 logger = logging.getLogger(__name__)
 
@@ -31,6 +42,7 @@ __all__ = [
     "RoutingPendingItem",
     "RoutingPendingStore",
     "default_pending_path",
+    "is_low_information_query",
 ]
 
 PendingKind = Literal["low_confidence", "no_match", "user_correction"]
@@ -55,6 +67,28 @@ def _day_key(dt: datetime | None = None) -> str:
     return (dt or _now()).date().isoformat()
 
 
+def is_low_information_query(query: str) -> bool:
+    """True when *query* carries too little signal to be worth human review.
+
+    Token-based, not char-based: a character wall would kill legitimate short
+    forms, while the token rule only blocks queries with fewer than 2
+    *meaningful* tokens ("可以" → 1 CJK token, "✓" → 0, "/review" → 1).
+    Multi-token queries like "review my code" pass — their review-queue
+    noise is a matcher-side problem, handled elsewhere.
+
+    The meaningful-token criterion is the shared module-level
+    ``_is_meaningful_token`` from ``core/matching/strategies.py`` (CJK >=2
+    chars, Latin >=3) — imported lazily alongside the tokenizer, mirroring
+    ``instinct/learner.py``; matching never imports instinct, so there is
+    no import cycle.
+    """
+    from vibesop.core.matching.strategies import _is_meaningful_token
+    from vibesop.core.matching.tokenizers import tokenize
+
+    meaningful = sum(1 for t in tokenize(query) if _is_meaningful_token(t))
+    return meaningful < 2
+
+
 @dataclass
 class RoutingPendingItem:
     """One route-quality item awaiting human accept/dismiss."""
@@ -103,10 +137,20 @@ class RoutingPendingItem:
 class RoutingPendingStore:
     """Append-friendly JSONL store for routing pending items."""
 
-    def __init__(self, path: Path | str | None = None) -> None:
+    def __init__(
+        self,
+        path: Path | str | None = None,
+        *,
+        miss_counter: Any | None = None,
+    ) -> None:
         self._path = Path(path) if path else default_pending_path()
+        self._lock_path = self._path.with_name(self._path.name + ".lock")
         self._lock = threading.Lock()
         self._items: list[RoutingPendingItem] = []
+        # MissCounter for gate-blocked low-info queries. Injectable for
+        # tests; otherwise lazily derived from the default store layout.
+        self._miss_counter = miss_counter
+        self._miss_counter_probed = miss_counter is not None
         self._load()
 
     @property
@@ -155,20 +199,69 @@ class RoutingPendingStore:
 
     def count_created_today(self) -> int:
         """How many items were *created* today (any status) — rate limit basis."""
-        today = _day_key()
         with self._lock:
-            n = 0
-            for item in self._items:
-                try:
-                    created = datetime.fromisoformat(item.created_at)
-                    if _day_key(created) == today:
-                        n += 1
-                except ValueError:
-                    continue
-            return n
+            return self._created_today_locked()
+
+    def _created_today_locked(self) -> int:
+        """Daily-cap count. Caller must hold ``self._lock``.
+
+        Counted by distinct query_hash (M7): one garbage query routed to N
+        skills costs 1 daily slot, not N. Legacy rows with an empty
+        query_hash count individually so historical files keep working.
+        """
+        today = _day_key()
+        hashes: set[str] = set()
+        legacy_rows = 0
+        for item in self._items:
+            try:
+                created = datetime.fromisoformat(item.created_at)
+            except ValueError:
+                continue
+            if _day_key(created) != today:
+                continue
+            if item.query_hash:
+                hashes.add(item.query_hash)
+            else:
+                legacy_rows += 1
+        return len(hashes) + legacy_rows
+
+    def _get_miss_counter(self) -> Any | None:
+        """Lazy MissCounter for gate-blocked low-info queries.
+
+        Derived from the default layout (``<root>/.vibe/instincts/...`` →
+        ``MissCounter(<root>)`` writes ``<root>/.vibe/miss_counter.json``).
+        Returns None for non-standard store paths — the gate still blocks,
+        just without a degradation record.
+        """
+        if self._miss_counter_probed:
+            return self._miss_counter
+        self._miss_counter_probed = True
+        if self._path.parent.name != "instincts" or self._path.parent.parent.name != ".vibe":
+            return None
+        try:
+            from vibesop.core.skills.miss_counter import MissCounter
+
+            self._miss_counter = MissCounter(self._path.parent.parent.parent)
+        except Exception as exc:  # telemetry must never break routing
+            logger.debug("miss counter unavailable for low-info gate: %s", exc)
+        return self._miss_counter
+
+    def _record_low_info_miss(self, query: str) -> None:
+        counter = self._get_miss_counter()
+        if counter is None:
+            return
+        try:
+            counter.record(query)
+        except Exception as exc:  # telemetry must never break routing
+            logger.debug("failed to record low-info query miss: %s", exc)
 
     def is_suppressed(self, query_hash: str, skill_id: str | None) -> bool:
-        """True if a dismiss for same key happened within suppress window."""
+        """True if a dismiss for same query_hash happened within the window.
+
+        Keyed by query_hash only, aligned with the dedup key (M7): a
+        dismissed query re-routed through a different skill_id stays
+        suppressed. Empty legacy hashes fall back to (hash, skill_id).
+        """
         cutoff = _now() - timedelta(hours=_DISMISS_SUPPRESS_HOURS)
         with self._lock:
             for item in self._items:
@@ -176,7 +269,7 @@ class RoutingPendingStore:
                     continue
                 if item.query_hash != query_hash:
                     continue
-                if (item.skill_id or None) != (skill_id or None):
+                if not query_hash and (item.skill_id or None) != (skill_id or None):
                     continue
                 try:
                     resolved = (
@@ -213,64 +306,105 @@ class RoutingPendingStore:
         reason_zh: str,
         query_hash: str,
     ) -> RoutingPendingItem | None:
-        """Enqueue if rate limit / dedup / suppress allow. Returns item or None."""
+        """Enqueue if rate limit / dedup / suppress allow. Returns item or None.
+
+        Low-information queries (<2 meaningful tokens) are not enqueued;
+        they degrade into a MissCounter record so a genuine false positive
+        still surfaces as a frequent miss. The read-modify-write cycle runs
+        under both the threading lock and a cross-process sidecar lock, and
+        the file is re-read inside the lock — every ``vibe route`` builds a
+        fresh store instance, so in-memory ``_items`` may be stale.
+        """
+        if is_low_information_query(query):
+            logger.debug("routing pending: skip low-information query %r", query[:80])
+            # no_match queries are already counted by the router's always-on
+            # miss telemetry (UnifiedRouter._record_route_miss fires on the
+            # same event just before enqueue) — recording again would
+            # double-count a single user query. low_confidence / correction
+            # kinds are not covered there, so record the degradation here.
+            if kind != "no_match":
+                self._record_low_info_miss(query)
+            return None
         with self._lock:
-            # Rate limit (created today, any status)
-            today = _day_key()
-            created_today = 0
-            for item in self._items:
-                try:
-                    if _day_key(datetime.fromisoformat(item.created_at)) == today:
-                        created_today += 1
-                except ValueError:
-                    continue
-            if created_today >= _MAX_NEW_PER_DAY:
-                logger.debug("routing pending daily cap reached (%d)", _MAX_NEW_PER_DAY)
+            try:
+                with cross_process_lock(self._lock_path):
+                    self._load()
+                    return self._try_enqueue_locked(
+                        query=query,
+                        skill_id=skill_id,
+                        confidence=confidence,
+                        kind=kind,
+                        reason_zh=reason_zh,
+                        query_hash=query_hash,
+                    )
+            except OSError as exc:
+                logger.warning("routing pending enqueue skipped (lock failed: %s)", exc)
                 return None
 
-            # Dedup open
-            for item in self._items:
-                if (
-                    item.status == "pending"
-                    and item.query_hash == query_hash
-                    and (item.skill_id or None) == (skill_id or None)
-                ):
-                    return None
+    def _try_enqueue_locked(
+        self,
+        *,
+        query: str,
+        skill_id: str | None,
+        confidence: float,
+        kind: PendingKind,
+        reason_zh: str,
+        query_hash: str,
+    ) -> RoutingPendingItem | None:
+        """Caller must hold ``self._lock`` and the cross-process lock."""
+        # Rate limit (created today, any status, distinct query_hash)
+        if self._created_today_locked() >= _MAX_NEW_PER_DAY:
+            logger.debug("routing pending daily cap reached (%d)", _MAX_NEW_PER_DAY)
+            return None
 
-            # Suppress after dismiss
-            cutoff = _now() - timedelta(hours=_DISMISS_SUPPRESS_HOURS)
-            for item in self._items:
-                if item.status != "dismissed":
-                    continue
-                if item.query_hash != query_hash:
-                    continue
-                if (item.skill_id or None) != (skill_id or None):
-                    continue
-                try:
-                    resolved = (
-                        datetime.fromisoformat(item.resolved_at)
-                        if item.resolved_at
-                        else datetime.fromisoformat(item.created_at)
-                    )
-                    if resolved.tzinfo is None:
-                        resolved = resolved.replace(tzinfo=UTC)
-                    if resolved >= cutoff:
-                        return None
-                except ValueError:
-                    continue
+        # Dedup open — keyed by query_hash only (M7): the same query routed
+        # to a different skill must not enqueue a second row. Empty legacy
+        # hashes fall back to (hash, skill_id) so a hash-less historical row
+        # cannot block every future enqueue.
+        for item in self._items:
+            if item.status != "pending" or item.query_hash != query_hash:
+                continue
+            if query_hash or (item.skill_id or None) == (skill_id or None):
+                return None
 
-            item = RoutingPendingItem(
-                id=f"rp-{uuid.uuid4().hex[:12]}",
-                query=query[:500],
-                skill_id=skill_id,
-                confidence=confidence,
-                kind=kind,
-                reason_zh=reason_zh,
-                query_hash=query_hash,
-            )
-            self._items.append(item)
-            self._save()
-            return item
+        # Suppress after dismiss — keyed by query_hash only, aligned with the
+        # dedup key above (M7): a dismissed query re-routed through a
+        # different skill_id must stay suppressed, otherwise the "one garbage
+        # query costs one daily slot" intent is bypassed. Empty legacy hashes
+        # fall back to (hash, skill_id), same as dedup.
+        cutoff = _now() - timedelta(hours=_DISMISS_SUPPRESS_HOURS)
+        for item in self._items:
+            if item.status != "dismissed":
+                continue
+            if item.query_hash != query_hash:
+                continue
+            if not query_hash and (item.skill_id or None) != (skill_id or None):
+                continue
+            try:
+                resolved = (
+                    datetime.fromisoformat(item.resolved_at)
+                    if item.resolved_at
+                    else datetime.fromisoformat(item.created_at)
+                )
+                if resolved.tzinfo is None:
+                    resolved = resolved.replace(tzinfo=UTC)
+                if resolved >= cutoff:
+                    return None
+            except ValueError:
+                continue
+
+        item = RoutingPendingItem(
+            id=f"rp-{uuid.uuid4().hex[:12]}",
+            query=query[:500],
+            skill_id=skill_id,
+            confidence=confidence,
+            kind=kind,
+            reason_zh=reason_zh,
+            query_hash=query_hash,
+        )
+        self._items.append(item)
+        self._save()
+        return item
 
     def accept(self, item_id: str) -> RoutingPendingItem | None:
         return self._resolve(item_id, "accepted")
@@ -282,35 +416,35 @@ class RoutingPendingStore:
         self, item_id: str, status: PendingStatus
     ) -> RoutingPendingItem | None:
         with self._lock:
-            for item in self._items:
-                if item.id != item_id:
-                    continue
-                if item.status != "pending":
+            try:
+                with cross_process_lock(self._lock_path):
+                    # Re-read under the lock: the item may have been resolved
+                    # by another process since this instance loaded.
+                    self._load()
+                    for item in self._items:
+                        if item.id != item_id:
+                            continue
+                        if item.status != "pending":
+                            return None
+                        item.status = status
+                        item.resolved_at = _now().isoformat()
+                        self._save()
+                        return item
                     return None
-                item.status = status
-                item.resolved_at = _now().isoformat()
-                self._save()
-                return item
-            return None
+            except OSError as exc:
+                logger.warning("routing pending resolve skipped (lock failed: %s)", exc)
+                return None
 
     def stats(self) -> dict[str, int]:
         with self._lock:
             pending = sum(1 for i in self._items if i.status == "pending")
             accepted = sum(1 for i in self._items if i.status == "accepted")
             dismissed = sum(1 for i in self._items if i.status == "dismissed")
-            today = _day_key()
-            created_today = 0
-            for item in self._items:
-                try:
-                    if _day_key(datetime.fromisoformat(item.created_at)) == today:
-                        created_today += 1
-                except ValueError:
-                    continue
             return {
                 "pending": pending,
                 "accepted": accepted,
                 "dismissed": dismissed,
-                "created_today": created_today,
+                "created_today": self._created_today_locked(),
                 "daily_cap": _MAX_NEW_PER_DAY,
                 "total": len(self._items),
             }
@@ -355,6 +489,10 @@ def should_enqueue_from_route(
 ) -> PendingKind | None:
     """Decide whether a route result should create a pending item.
 
+    Note: this is the route-quality half of the policy. The low-information
+    query gate runs separately (and first) inside
+    ``RoutingPendingStore.try_enqueue`` — see ``is_low_information_query``.
+
     Enqueue when:
     - no match / FALLBACK_LLM sentinel (``has_match`` false), or
     - confidence below threshold, or
diff --git a/src/vibesop/core/matching/strategies.py b/src/vibesop/core/matching/strategies.py
index 88c9fb0..6be43fc 100644
--- a/src/vibesop/core/matching/strategies.py
+++ b/src/vibesop/core/matching/strategies.py
@@ -48,6 +48,19 @@ class MatcherConfig:
     tokenizer_config: TokenizerConfig = field(default_factory=TokenizerConfig)
 
 
+def _is_meaningful_token(token: str) -> bool:
+    """Shared meaningful-token convention for scoring denominators/filters.
+
+    CJK characters are meaningful even as 2-character tokens; Latin tokens
+    need at least 3 characters. Used by KeywordMatcher (partial-match bonus)
+    and LevenshteinMatcher (coverage denominator); also imported by
+    core/instinct/routing_pending.py for its low-information query gate.
+    """
+    if any("\u4e00" <= ch <= "\u9fff" for ch in token):
+        return len(token) >= 2
+    return len(token) >= 3
+
+
 class KeywordMatcher:
     """Fast keyword-based matcher."""
 
@@ -137,13 +150,6 @@ class KeywordMatcher:
         exact_matches = query_tokens & candidate_tokens
         base_score = len(exact_matches) / len(union)
 
-        def _is_meaningful_token(token: str) -> bool:
-            # CJK characters are meaningful even as 2-character tokens;
-            # Latin tokens need at least 3 characters.
-            if any("\u4e00" <= ch <= "\u9fff" for ch in token):
-                return len(token) >= 2
-            return len(token) >= 3
-
         # Bonus for prefix/substring matches (e.g., "debug" matches "debugging")
         partial_bonus = 0.0
         for qt in query_tokens:
@@ -524,20 +530,22 @@ class LevenshteinMatcher:
             text = self._candidate_to_text(candidate)
             return self._normalized_similarity(query, text)
 
-        # Score each query token against the best-matching candidate token,
-        # but only keep high-similarity matches (typo-level)
+        # Score every meaningful query token against the best-matching
+        # candidate token. Tokens below the similarity threshold count as 0
+        # in the average — they used to be dropped from the denominator
+        # entirely, so a single matching token could inflate the score to
+        # 1.0 (e.g. "使用 review" scored 1.0 because only "review" counted).
         SIMILARITY_THRESHOLD = 0.7
-        token_scores = []
-        for qt in query_tokens:
-            if len(qt) <= 2:
-                continue  # Skip very short tokens
-            best = max(self._normalized_similarity(qt, ct) for ct in candidate_tokens)
-            if best >= SIMILARITY_THRESHOLD:
-                token_scores.append(best)
 
-        if not token_scores:
+        meaningful_tokens = [qt for qt in query_tokens if _is_meaningful_token(qt)]
+        if not meaningful_tokens:
             return 0.0
 
+        token_scores = []
+        for qt in meaningful_tokens:
+            best = max(self._normalized_similarity(qt, ct) for ct in candidate_tokens)
+            token_scores.append(best if best >= SIMILARITY_THRESHOLD else 0.0)
+
         # Also include a bonus for exact name match
         name = str(candidate.get("name", "")).lower()
         name_bonus = 0.0
@@ -574,13 +582,30 @@ class LevenshteinMatcher:
         return list(tokens)
 
     def _levenshtein_distance(self, s1: str, s2: str) -> int:
+        """Optimal string alignment distance (Levenshtein + adjacent transposition).
+
+        Transposing adjacent characters costs 1 edit instead of 2: it is the
+        most common typo class, and plain Levenshtein scored "reivew"→"review"
+        at 2/6 = 0.667 similarity — below the 0.7 token threshold, so the
+        coverage fix above would have zeroed genuine transposition typos.
+
+        The discount only applies when BOTH tokens are ≥6 chars: at 4-5 chars
+        it promoted real distinct-word pairs over the 0.7 threshold and
+        misrouted end-to-end (form/from 0.75, trail/trial 0.8, angel/angle
+        0.8, dairy/diary 0.8 — gate7 pi finding). Shorter pairs fall back to
+        plain Levenshtein, i.e. exactly the pre-OSA behavior.
+        """
         if len(s1) < len(s2):
             return self._levenshtein_distance(s2, s1)
 
         if len(s2) == 0:
             return len(s1)
 
+        # s2 is the shorter token, so this means both are ≥6 chars.
+        allow_transposition = len(s2) >= 6
+
         previous_row = list(range(len(s2) + 1))
+        prev_prev_row: list[int] | None = None
 
         for i, c1 in enumerate(s1):
             current_row = [i + 1]
@@ -590,8 +615,20 @@ class LevenshteinMatcher:
                 deletions = current_row[j] + 1
                 substitutions = previous_row[j] + (c1 != c2)
 
-                current_row.append(min(insertions, deletions, substitutions))
+                best = min(insertions, deletions, substitutions)
+                if (
+                    allow_transposition
+                    and prev_prev_row is not None
+                    and i > 0
+                    and j > 0
+                    and c1 == s2[j - 1]
+                    and s1[i - 1] == c2
+                ):
+                    best = min(best, prev_prev_row[j - 1] + 1)
+
+                current_row.append(best)
 
+            prev_prev_row = previous_row
             previous_row = current_row
 
         return previous_row[-1]
diff --git a/src/vibesop/core/observability/skill_promote.py b/src/vibesop/core/observability/skill_promote.py
index 6ef17a2..ce6babe 100644
--- a/src/vibesop/core/observability/skill_promote.py
+++ b/src/vibesop/core/observability/skill_promote.py
@@ -862,6 +862,29 @@ def _sanitize_yaml_value(text: str, max_len: int = 80) -> str:
     return f'"{escaped}"'
 
 
+def _sanitize_body_text(text: str, max_len: int = 200) -> str:
+    """Collapse a raw query to a single display line for the SKILL.md body.
+
+    M7 F6: raw cluster queries were embedded verbatim into the queries
+    list; real queries contain ``\\n\\n`` and run to 700+ chars, which
+    breaks the markdown list structure and can smuggle pseudo-instruction
+    blocks into the rendered draft. Collapsing all whitespace runs to
+    single spaces + truncating keeps the example readable without
+    altering its wording.
+
+    Deliberately NOT a full markdown/prompt escape: these entries are
+    *examples for a human reviewer*, not executable content. Residual
+    instruction-like text is inherent to showing real queries at all —
+    the safeguard is human review before activation (plus the
+    cross-project warning block), not character-level mangling that
+    would make the examples useless.
+    """
+    cleaned = " ".join(str(text).split())
+    if len(cleaned) > max_len:
+        cleaned = cleaned[:max_len].rstrip() + "…"
+    return cleaned
+
+
 def _project_id_to_basename(project_id: str) -> str:
     """Render a project_id (absolute path) as a portable basename.
 
@@ -975,15 +998,25 @@ def _render_skill_md(
     org structure and must never appear in the SKILL.md body) and a
     warning header is prepended after the frontmatter.
     """
-    name_raw = candidate.queries[0] if candidate.queries else "Promoted candidate"
-    name = _sanitize_yaml_value(name_raw, max_len=80)
+    # M7 F3 (adjudicated design — do NOT "optimize" this back into a
+    # query-derived name): ``name`` is the strongest routing-match magnet
+    # (the INDEX layer grants a +0.4 containment bonus on it), so a raw
+    # query here makes an unedited draft over-match the moment it is
+    # injected. A neutral ``draft-<cluster>`` slug marks the draft as
+    # unfinished and fails safe against accidental activation.
+    # ``description`` intentionally stays provenance-only: it satisfies
+    # the spec-v3 required field, acts as a neutral diluent for matching,
+    # and provenance is exactly what belongs here pre-review.
+    name = f"draft-{candidate.cluster_id[:8]}"
     description = _sanitize_yaml_value(
         f"Auto-drafted from cluster {candidate.cluster_id} "
         f"({candidate.span_count} spans, gold_rate={candidate.gold_rate:.0%})",
         max_len=140,
     )
+    # M7 F6: queries are sanitized to single display lines (see
+    # ``_sanitize_body_text``) before entering the markdown body.
     queries_block = (
-        "\n".join(f"- {q}" for q in candidate.queries[:5])
+        "\n".join(f"- {_sanitize_body_text(q)}" for q in candidate.queries[:5])
         or "- (no representative queries recorded)"
     )
     if candidate.core_steps:
diff --git a/src/vibesop/core/routing/unified.py b/src/vibesop/core/routing/unified.py
index f8189b1..5c7b026 100644
--- a/src/vibesop/core/routing/unified.py
+++ b/src/vibesop/core/routing/unified.py
@@ -8,7 +8,9 @@ match wins.
 Architecture:
     route() → [_try_explicit, _try_scenario, _try_ai_triage, _try_matchers]
                                                         ↓
-                              matcher loop: keyword → tfidf → embedding → levenshtein
+                              matcher aggregation: keyword/tfidf/embedding,
+                              max confidence wins; levenshtein is last-resort
+                              (only consulted when the others find nothing)
                                                         ↓
                               optimization: prefilter → preference_boost → conflict_resolution
 
@@ -21,6 +23,7 @@ Example:
 from __future__ import annotations
 
 import logging
+import re
 import threading
 import time
 from pathlib import Path
@@ -93,6 +96,24 @@ def _is_junk_query(query: str) -> bool:
     return any(stripped.startswith(marker) for marker in _JUNK_QUERY_MARKERS)
 
 
+# Platform hooks may wrap the user query in <user_query>...</user_query>
+# before handing it to route(). Production logs showed the wrapper reaching
+# matching verbatim, so "user"/"query" became query tokens and polluted
+# every matcher's scoring. Only a full-wrap (modulo surrounding whitespace)
+# is unwrapped; other tags and partial markup are left untouched. The inner
+# content may not itself contain a closing tag — pathological input like
+# "<user_query>fix</user_query> mid </user_query>" must NOT unwrap.
+_USER_QUERY_WRAPPER_RE = re.compile(
+    r"\A\s*<user_query>\s*((?:(?!</user_query>).)*?)\s*</user_query>\s*\Z", re.DOTALL
+)
+
+
+def _unwrap_user_query(query: str) -> str:
+    """Strip a whole-query <user_query>...</user_query> wrapper, if present."""
+    match = _USER_QUERY_WRAPPER_RE.match(query)
+    return match.group(1) if match else query
+
+
 def _junk_query_result(query: str) -> RoutingResult:
     """No-match result for harness-markup junk queries.
 
@@ -179,8 +200,10 @@ class UnifiedRouter(
     #   Stage 1: EXPLICIT (short-circuit on hit)
     #   Stage 2: SCENARIO + Semantic Index (best-of-N, keyword/short-query path)
     #   Stage 3: AI_TRIAGE (LLM, long-query path)
-    #   Stage 4: Matcher aggregation (keyword/tfidf/embedding/levenshtein run in
-    #            parallel, max confidence wins — not serial fallback)
+    #   Stage 4: Matcher aggregation (keyword/tfidf/embedding run together,
+    #            max confidence wins — not serial fallback; levenshtein is
+    #            last-resort and only consulted when the others produce
+    #            nothing — see _run_matcher_pipeline_levenshtein_last)
     # NO_MATCH and FALLBACK_LLM are terminal states, not matching layers.
     _LAYER_PRIORITY: ClassVar[list[RoutingLayer]] = [
         RoutingLayer.EXPLICIT,
@@ -692,9 +715,10 @@ class UnifiedRouter(
                 context,
             )
 
-        # Step 3: Matcher pipeline (shared fallback)
-        primary, alternatives, detail = _pipeline.run_matcher_pipeline(
-            self, query, candidates, context, collect_rejected=True
+        # Step 3: Matcher pipeline (shared fallback). Levenshtein runs as
+        # last resort only — see _run_matcher_pipeline_levenshtein_last.
+        primary, alternatives, detail = self._run_matcher_pipeline_levenshtein_last(
+            query, candidates, context
         )
         routing_path.append(detail.layer)
         layer_details.append(detail)
@@ -715,6 +739,53 @@ class UnifiedRouter(
 
         return None
 
+    def _run_matcher_pipeline_levenshtein_last(
+        self,
+        query: str,
+        candidates: list[dict[str, Any]],
+        context: RoutingContext | None,
+    ) -> tuple[Any | None, list[Any], Any]:
+        """Run the matcher pipeline with Levenshtein demoted to last resort.
+
+        The pipeline aggregates all matchers by max confidence, and
+        Levenshtein's fuzzy scores systematically out-scored the calibrated
+        matchers on weak evidence (production incident: "使用 review" →
+        levenshtein @1.0). ``_LAYER_PRIORITY`` already declares LEVENSHTEIN
+        the last matcher layer, so:
+
+        - First pass runs WITHOUT Levenshtein. If it hits, Levenshtein never
+          enters ``merged_matches`` / ``apply_optimizations`` at all — this
+          is where its influence is removed.
+        - On a first-pass miss, the second pass is the full, unmodified
+          pipeline: Levenshtein's results go through ``apply_optimizations``
+          exactly like any other matcher's.
+        """
+        pipeline = self._matcher_pipeline
+        # Read, swap, and restore of the matcher list must all happen in the
+        # same critical section: reading full_matchers outside the lock let a
+        # concurrent route snapshot the *reduced* list and later "restore" it
+        # as if it were the full one, permanently dropping Levenshtein.
+        primary: Any | None = None
+        alternatives: list[Any] = []
+        detail: Any = None
+        with self._route_lock:
+            full_matchers = pipeline._matchers
+            calibrated = [m for m in full_matchers if m[0] != RoutingLayer.LEVENSHTEIN]
+            if len(calibrated) != len(full_matchers):
+                pipeline._matchers = calibrated
+                try:
+                    primary, alternatives, detail = _pipeline.run_matcher_pipeline(
+                        self, query, candidates, context, collect_rejected=True
+                    )
+                finally:
+                    pipeline._matchers = full_matchers
+        if primary is not None:
+            return primary, alternatives, detail
+        # First-pass miss (or no Levenshtein configured): full pipeline.
+        return _pipeline.run_matcher_pipeline(
+            self, query, candidates, context, collect_rejected=True
+        )
+
     def _try_early_layers(
         self,
         query: str,
@@ -943,6 +1014,14 @@ class UnifiedRouter(
         # shape as fallback_mode="disabled" (minus the matcher-pipeline nearest
         # scan, which would be meaningless for markup), and skips the telemetry
         # block below so junk never lands in analytics / the miss counter.
+        if _is_junk_query(query):
+            return _junk_query_result(query)
+        # Pre-clean: unwrap platform-hook <user_query> packaging before any
+        # matching (see _USER_QUERY_WRAPPER_RE).
+        query = _unwrap_user_query(query)
+        # The unwrap can reveal harness markup that was hidden inside the
+        # wrapper — reject it here too, so the telemetry block below keeps
+        # the "junk never lands in analytics / the miss counter" invariant.
         if _is_junk_query(query):
             return _junk_query_result(query)
         result = self._single_skill_route(query, candidates, context)

## tests diff(累计)

diff --git a/tests/cli/test_instinct_cmd.py b/tests/cli/test_instinct_cmd.py
index 322d034..56cb8ec 100644
--- a/tests/cli/test_instinct_cmd.py
+++ b/tests/cli/test_instinct_cmd.py
@@ -7,7 +7,7 @@ call an LLM — purely local file operations on instincts.jsonl + miss_counter.j
 
 Covers:
     - auto-promote: candidate filtering, growth cap, dry-run, idempotency
-    - feedback-collect: decay/boost decision tree, early-stop, watermark
+    - feedback-collect: decay decision tree, early-stop, watermark
 """
 
 from __future__ import annotations
@@ -216,7 +216,7 @@ class TestFeedbackCollect:
         result = runner.invoke(app, ["feedback-collect"])
         assert result.exit_code == 0
         assert "0 decayed" in result.stdout
-        assert "0 boosted" in result.stdout
+        assert "boosted" not in result.stdout
 
     def test_dry_run_does_not_write(self, isolated_cwd, learner, miss_counter):
         _seed_reliable_instinct(learner, "do thing")
@@ -248,27 +248,28 @@ class TestFeedbackCollect:
         assert ins is not None
         assert ins.failure_count == 2  # was 1, +1 from decay
 
-    def test_boosts_high_success_few_apps(self, isolated_cwd, learner, miss_counter):
-        """success_rate ≥ 0.8 and total_applications ≤ boost_threshold_apps
-        → boost (record_outcome success=True). No frequent misses for this
-        pattern, so it doesn't decay first."""
-        # success_rate = 4/5 = 0.8, total_applications=5 — but default
-        # boost_threshold_apps=2, so we need ≤ 2 apps. Use 2/2 = 1.0.
+    def test_no_auto_boost_for_high_success_few_apps(
+        self, isolated_cwd, learner, miss_counter
+    ):
+        """Boost 分支已拆除：success_rate ≥ 0.8 且应用次数少的 instinct 不再
+        被自动 record_outcome(success=True) —— 正信号只能来自显式人确认。
+        feedback-collect 跑完后其 success_count 必须不变。"""
         _seed_reliable_instinct(
             learner, "good instinct", success_count=2, failure_count=0, confidence=0.6
         )
 
         result = runner.invoke(app, ["feedback-collect"])
         assert result.exit_code == 0
-        assert "1 boosted" in result.stdout
+        assert "boosted" not in result.stdout
+        assert "0 decayed" in result.stdout
 
         reloaded = InstinctLearner(learner.storage_path)
         ins = reloaded.instincts.get("instinct_good_instinct")
         assert ins is not None
-        assert ins.success_count == 3  # was 2, +1 from boost
+        assert ins.success_count == 2  # unchanged — no auto boost
 
     def test_early_stop_at_confidence_ceiling(self, isolated_cwd, learner, miss_counter):
-        """confidence ≥ 0.95 → skip entirely (no decay, no boost)."""
+        """confidence ≥ 0.95 → skip entirely (no decay)."""
         _seed_reliable_instinct(learner, "saturated", confidence=0.96)
         for _ in range(5):
             miss_counter.record("saturated")
diff --git a/tests/cli/test_skill_add_cmd.py b/tests/cli/test_skill_add_cmd.py
index e6b8e51..fdfd860 100644
--- a/tests/cli/test_skill_add_cmd.py
+++ b/tests/cli/test_skill_add_cmd.py
@@ -13,6 +13,227 @@ from vibesop.spec.models import SkillSpec
 runner = CliRunner()
 
 
+class TestIncrementalIndexing:
+    """M7 — `vibe skill add` Phase 6 incrementally indexes the new skill.
+
+    `_index_newly_added_skill` must be best-effort: degrade to False
+    (never raise) when no LLM is configured, and merge the single new
+    profile into the existing index layer on success.
+    """
+
+    def test_returns_false_when_no_llm_configured(self) -> None:
+        from vibesop.cli.commands.skill_commands import _index_newly_added_skill
+
+        mock_resolver = Mock()
+        mock_resolver.get_llm_for_understanding.return_value = None
+
+        with patch(
+            "vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver
+        ):
+            assert _index_newly_added_skill("test-skill", "project") is False
+
+    def test_returns_false_when_provider_missing(self) -> None:
+        from vibesop.cli.commands.skill_commands import _index_newly_added_skill
+
+        mock_cfg = Mock(provider=None)
+        mock_resolver = Mock()
+        mock_resolver.get_llm_for_understanding.return_value = mock_cfg
+
+        with patch(
+            "vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver
+        ):
+            assert _index_newly_added_skill("test-skill", "project") is False
+
+    def test_success_merges_single_profile_into_project_layer(self, tmp_path) -> None:
+        from vibesop.cli.commands.skill_commands import _index_newly_added_skill
+
+        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
+        mock_resolver = Mock()
+        mock_resolver.get_llm_for_understanding.return_value = mock_cfg
+
+        mock_profile = Mock()
+        mock_indexer = Mock()
+        mock_indexer._get_llm.return_value = Mock()  # LLM available
+        mock_indexer._analyze_skill.return_value = mock_profile
+        mock_indexer.project_index_path = tmp_path / "proj" / "skill-index.json"
+        mock_indexer.global_index_path = tmp_path / "glob" / "skill-index.json"
+        mock_indexer._load_single_index.return_value = {"existing/skill": Mock()}
+
+        mock_loader = Mock()
+        mock_loader.get_skill.return_value = Mock()  # skill discoverable
+
+        with (
+            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
+            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
+            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
+            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
+        ):
+            assert _index_newly_added_skill("test-skill", "project") is True
+
+        # Only the new skill was analyzed (incremental, not full rebuild).
+        mock_indexer._analyze_skill.assert_called_once()
+        mock_loader.get_skill.assert_called_once_with("test-skill")
+        # Merged into the project layer, preserving existing entries.
+        saved_profiles, = mock_indexer._save_index.call_args.args[:1]
+        assert "test-skill" in saved_profiles
+        assert "existing/skill" in saved_profiles
+        assert mock_indexer._save_index.call_args.kwargs["scope"] == "project"
+
+    def test_global_scope_saves_to_global_layer(self, tmp_path) -> None:
+        from vibesop.cli.commands.skill_commands import _index_newly_added_skill
+
+        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
+        mock_resolver = Mock()
+        mock_resolver.get_llm_for_understanding.return_value = mock_cfg
+
+        mock_indexer = Mock()
+        mock_indexer._get_llm.return_value = Mock()
+        mock_indexer._analyze_skill.return_value = Mock()
+        mock_indexer.project_index_path = tmp_path / "proj" / "skill-index.json"
+        mock_indexer.global_index_path = tmp_path / "glob" / "skill-index.json"
+        mock_indexer._load_single_index.return_value = {}
+
+        mock_loader = Mock()
+        mock_loader.get_skill.return_value = Mock()
+
+        with (
+            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
+            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
+            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
+            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
+        ):
+            assert _index_newly_added_skill("test-skill", "global") is True
+
+        assert mock_indexer._save_index.call_args.kwargs["scope"] == "global"
+
+    def test_returns_false_when_skill_not_discoverable(self) -> None:
+        from vibesop.cli.commands.skill_commands import _index_newly_added_skill
+
+        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
+        mock_resolver = Mock()
+        mock_resolver.get_llm_for_understanding.return_value = mock_cfg
+
+        mock_indexer = Mock()
+        mock_indexer._get_llm.return_value = Mock()
+
+        mock_loader = Mock()
+        mock_loader.get_skill.return_value = None  # not discoverable
+
+        with (
+            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
+            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
+            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
+            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
+        ):
+            assert _index_newly_added_skill("ghost-skill", "project") is False
+
+    def test_never_raises_on_unexpected_error(self) -> None:
+        from vibesop.cli.commands.skill_commands import _index_newly_added_skill
+
+        with patch(
+            "vibesop.core.llm_config.LLMConfigResolver",
+            side_effect=RuntimeError("config exploded"),
+        ):
+            assert _index_newly_added_skill("test-skill", "project") is False
+
+    def test_concurrent_indexing_loses_no_entries(self, tmp_path) -> None:
+        """gate7 claude NIT-1: the load→merge→save RMW runs under a
+        cross-process sidecar lock — two concurrent incremental indexes
+        must both land, not silently overwrite each other.
+
+        The mock store sleeps inside the read to widen the race window:
+        without the lock, both threads read the pre-merge state and the
+        second save clobbers the first entry.
+        """
+        import threading
+        import time
+
+        from vibesop.cli.commands.skill_commands import _index_newly_added_skill
+
+        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
+        mock_resolver = Mock()
+        mock_resolver.get_llm_for_understanding.return_value = mock_cfg
+
+        store: dict[str, Mock] = {}
+
+        def _load(_path):
+            time.sleep(0.05)  # widen the RMW race window
+            return dict(store)
+
+        def _save(profiles, *, scope):
+            store.clear()
+            store.update(profiles)
+
+        mock_indexer = Mock()
+        mock_indexer._get_llm.return_value = Mock()
+        mock_indexer._analyze_skill.side_effect = lambda loaded, llm: Mock()
+        mock_indexer.project_index_path = tmp_path / "proj" / "skill-index.json"
+        mock_indexer.global_index_path = tmp_path / "glob" / "skill-index.json"
+        mock_indexer._load_single_index.side_effect = _load
+        mock_indexer._save_index.side_effect = _save
+
+        mock_loader = Mock()
+        mock_loader.get_skill.return_value = Mock()
+
+        results: list[bool] = []
+        with (
+            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
+            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
+            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
+            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
+        ):
+            threads = [
+                threading.Thread(
+                    target=lambda sid: results.append(
+                        _index_newly_added_skill(sid, "project")
+                    ),
+                    args=(f"skill-{i}",),
+                )
+                for i in range(2)
+            ]
+            for t in threads:
+                t.start()
+            for t in threads:
+                t.join()
+
+        assert results == [True, True]
+        assert set(store.keys()) == {"skill-0", "skill-1"}, (
+            f"concurrent RMW lost an entry: {sorted(store.keys())}"
+        )
+
+    def test_degrades_false_when_lock_io_fails(self, tmp_path) -> None:
+        """Lock-file OSError degrades to False (never raises), same style
+        as every other failure mode in the function."""
+        from vibesop.cli.commands.skill_commands import _index_newly_added_skill
+
+        mock_cfg = Mock(provider="deepseek", api_key="k", api_base=None, model="m")
+        mock_resolver = Mock()
+        mock_resolver.get_llm_for_understanding.return_value = mock_cfg
+
+        mock_indexer = Mock()
+        mock_indexer._get_llm.return_value = Mock()
+        mock_indexer._analyze_skill.return_value = Mock()
+        mock_indexer.project_index_path = tmp_path / "proj" / "skill-index.json"
+        mock_indexer.global_index_path = tmp_path / "glob" / "skill-index.json"
+
+        mock_loader = Mock()
+        mock_loader.get_skill.return_value = Mock()
+
+        with (
+            patch("vibesop.core.llm_config.LLMConfigResolver", return_value=mock_resolver),
+            patch("vibesop.core.skills.indexer.SkillIndexer", return_value=mock_indexer),
+            patch("vibesop.core.skills.loader.SkillLoader", return_value=mock_loader),
+            patch("vibesop.llm.factory.create_provider", return_value=Mock()),
+            patch(
+                "vibesop.utils.file_lock.cross_process_lock",
+                side_effect=OSError("lock file unavailable"),
+            ),
+        ):
+            assert _index_newly_added_skill("test-skill", "project") is False
+
+        mock_indexer._save_index.assert_not_called()
+
+
 class TestSkillAddCommand:
     """Test suite for skill add command."""
 
diff --git a/tests/cli/test_skill_promote_cli.py b/tests/cli/test_skill_promote_cli.py
index 73a065c..cfd1cf9 100644
--- a/tests/cli/test_skill_promote_cli.py
+++ b/tests/cli/test_skill_promote_cli.py
@@ -500,6 +500,30 @@ class TestPromote:
         assert stored.source_skill_id is not None
         assert stored.source_skill_id.startswith("custom/")
 
+    def test_promote_prints_index_hint_and_review_checklist(
+        self, cli_runner: CliRunner, tmp_store
+    ) -> None:
+        """M7: promote stdout includes the index hint + 3-line human
+        review checklist after the activate instructions."""
+        c = ClusterCandidate(
+            cluster_id="abc123def456",
+            task_ids=["t1"],
+            queries=["topic-A one"],
+            span_count=5,
+            gold_rate=0.8,
+            gold_task_ids=["t1"],
+        )
+        tmp_store.upsert(c)
+
+        r = cli_runner.invoke(app, ["skill", "promote", "abc123def456"])
+        assert r.exit_code == 0, f"failed: {r.output}"
+        assert "incrementally" in r.output
+        assert "vibe skills index" in r.output
+        assert "review checklist before activating:" in r.output
+        assert "1. rewrite name/description into intent keywords" in r.output
+        assert "2. confirm the example queries are a single workflow" in r.output
+        assert "3. spell out when this skill should NOT be used" in r.output
+
     def test_promote_unknown_id_errors(
         self, cli_runner: CliRunner, tmp_store
     ) -> None:
diff --git a/tests/core/matching/test_strategies.py b/tests/core/matching/test_strategies.py
index 05332b9..aebac22 100644
--- a/tests/core/matching/test_strategies.py
+++ b/tests/core/matching/test_strategies.py
@@ -354,6 +354,70 @@ class TestLevenshteinMatcher:
         m = LevenshteinMatcher()
         m.warm_up([])  # Should not raise
 
+    def test_score_unmatched_tokens_count_as_zero(self):
+        """Unmatched meaningful tokens must count as 0 in the denominator.
+
+        Regression for the production incident where "使用 review" scored 1.0:
+        only "review" passed the similarity threshold, and the average was
+        taken over passing tokens only. Now "使用" (a meaningful CJK token)
+        counts as 0, so the score is ~0.5, not 1.0.
+        """
+        m = LevenshteinMatcher()
+        c = _make_candidate("kimi-gated-fix", name="kimi gated fix", keywords=["review"])
+        score = m.score("使用 review", c)
+        assert score < 0.7
+        # (1.0 for "review" + 0.0 for "使用") / 2 tokens
+        assert score == pytest.approx(0.5, abs=0.01)
+
+    def test_score_typo_still_high(self):
+        """A genuine typo (all meaningful tokens near-match) keeps a high score."""
+        m = LevenshteinMatcher()
+        c = _make_candidate(
+            "code-review", name="code review", keywords=["review", "code"]
+        )
+        score = m.score("reivew my code", c)
+        # "my" is too short to be meaningful; "reivew"≈"review", "code"=="code"
+        assert score >= 0.9
+
+    def test_score_short_tokens_excluded_from_denominator(self):
+        """Non-meaningful tokens (latin <3 chars) are skipped, not zeroed."""
+        m = LevenshteinMatcher()
+        c = _make_candidate("debug", name="debug", keywords=["debug"])
+        # "my" is not meaningful; only "debug" counts → perfect score.
+        score = m.score("my debug", c)
+        assert score >= 0.9
+
+    def test_transposition_discount_long_tokens(self):
+        """Adjacent transposition costs 1 edit for tokens ≥6 chars."""
+        m = LevenshteinMatcher()
+        assert m._levenshtein_distance("reivew", "review") == 1
+        assert m._levenshtein_distance("configuartion", "configuration") == 1
+
+    def test_transposition_discount_short_tokens_disabled(self):
+        """Below 6 chars the transposition discount is off: real distinct-word
+        pairs (form/from, trail/trial, angel/angle, dairy/diary) must stay at
+        plain-Levenshtein distance 2 so they can't cross the 0.7 threshold."""
+        m = LevenshteinMatcher()
+        assert m._levenshtein_distance("form", "from") == 2
+        assert m._levenshtein_distance("trail", "trial") == 2
+        assert m._levenshtein_distance("angel", "angle") == 2
+        assert m._levenshtein_distance("dairy", "diary") == 2
+
+    def test_short_distinct_word_pair_scores_low(self):
+        """End-to-end: "form" must not fuzzy-match a "from" skill."""
+        m = LevenshteinMatcher()
+        c = _make_candidate("from-skill", name="from", keywords=["from"])
+        assert m.score("form", c) < 0.7
+
+    def test_cjk_transposition_reverts_to_plain_levenshtein(self):
+        """"配置禁门"↔"配置门禁" (4 chars): no discount, distance 2 → sim 0.5,
+        identical to pre-OSA behavior — a CJK transposition typo at this
+        length no longer matches, same as before OSA was introduced."""
+        m = LevenshteinMatcher()
+        assert m._levenshtein_distance("配置禁门", "配置门禁") == 2
+        c = _make_candidate("gate-skill", name="gate", keywords=["配置门禁"])
+        assert m.score("配置禁门", c) < 0.7
+
 
 class TestLazyEmbeddingMatcher:
     """Test LazyEmbeddingMatcher proxy."""
diff --git a/tests/core/observability/test_skill_promote_render.py b/tests/core/observability/test_skill_promote_render.py
index 2b9b8be..c088135 100644
--- a/tests/core/observability/test_skill_promote_render.py
+++ b/tests/core/observability/test_skill_promote_render.py
@@ -19,6 +19,7 @@ from vibesop.core.observability.skill_promote import (
     _format_cross_project_warning,
     _project_id_to_basename,
     _render_skill_md,
+    _sanitize_body_text,
     dedupe_project_distribution,
 )
 
@@ -288,3 +289,71 @@ class TestRenderScopeFooter:
         for s in ("project", "global"):
             content = _render_skill_md(c, "custom/foo", scope=s)  # type: ignore[arg-type]
             assert "## Overview" in content
+
+
+class TestDraftName:
+    """M7 F3 — name is a neutral draft slug, NOT derived from queries.
+
+    Adjudicated design: ``name`` is the strongest routing-match magnet
+    (+0.4 containment bonus), so a raw query there makes an unedited
+    draft over-match once injected. ``description`` stays provenance-only
+    on purpose. These tests pin the decision so nobody "optimizes" it
+    back.
+    """
+
+    def test_name_is_draft_cluster_slug(self) -> None:
+        c = _make_candidate(cluster_id="abc123def456", queries=["do the thing"])
+        content = _render_skill_md(c, "custom/test-name")
+        frontmatter = content.split("---\n", 2)[1]
+        assert "name: draft-abc123de" in frontmatter
+        # The raw query must NOT appear in the name field.
+        name_line = next(ln for ln in frontmatter.splitlines() if ln.startswith("name:"))
+        assert "do the thing" not in name_line
+
+    def test_name_does_not_leak_query_even_when_hostile(self) -> None:
+        c = _make_candidate(queries=["setup: config\nthen deploy"])
+        content = _render_skill_md(c, "custom/test-hostile-name")
+        frontmatter = content.split("---\n", 2)[1]
+        name_line = next(ln for ln in frontmatter.splitlines() if ln.startswith("name:"))
+        assert "setup" not in name_line
+        assert "\n" not in name_line
+
+    def test_description_keeps_provenance(self) -> None:
+        c = _make_candidate(cluster_id="abc123def456", span_count=7)
+        content = _render_skill_md(c, "custom/test-desc")
+        frontmatter = content.split("---\n", 2)[1]
+        assert "Auto-drafted from cluster abc123def456" in frontmatter
+        assert "7 spans" in frontmatter
+
+
+class TestSanitizeBodyText:
+    """M7 F6 — queries embedded in the body are single-line + truncated."""
+
+    def test_collapses_newlines_and_whitespace_runs(self) -> None:
+        q = "first line\n\nsecond   paragraph\twith\ttabs"
+        assert _sanitize_body_text(q) == "first line second paragraph with tabs"
+
+    def test_truncates_long_queries_with_ellipsis(self) -> None:
+        q = "x" * 700
+        out = _sanitize_body_text(q)
+        assert out.endswith("…")
+        assert len(out) <= 201
+
+    def test_render_queries_block_is_single_line_per_query(self) -> None:
+        c = _make_candidate(queries=["line one\n\nline two", "short"])
+        content = _render_skill_md(c, "custom/test-body-sanitize")
+        assert "- line one line two" in content
+        # No raw multi-line query survives into the body.
+        assert "line one\n\nline two" not in content
+
+    def test_render_truncates_700_char_query(self) -> None:
+        long_q = "word " * 200  # 1000 chars
+        c = _make_candidate(queries=[long_q])
+        content = _render_skill_md(c, "custom/test-body-truncate")
+        body = content.split("---\n", 2)[2]
+        query_lines = [
+            ln for ln in body.splitlines() if ln.startswith("- word")
+        ]
+        assert len(query_lines) == 1
+        assert query_lines[0].endswith("…")
+        assert len(query_lines[0]) < 250
diff --git a/tests/unit/core/instinct/test_routing_pending.py b/tests/unit/core/instinct/test_routing_pending.py
index 3a83267..ba66744 100644
--- a/tests/unit/core/instinct/test_routing_pending.py
+++ b/tests/unit/core/instinct/test_routing_pending.py
@@ -74,7 +74,7 @@ def test_dismiss_suppresses_requeue(tmp_path: Path) -> None:
     store = RoutingPendingStore(path)
 
     item = store.try_enqueue(
-        query="q",
+        query="debug flaky test",
         skill_id="s1",
         confidence=0.2,
         kind="low_confidence",
@@ -85,7 +85,7 @@ def test_dismiss_suppresses_requeue(tmp_path: Path) -> None:
     store.dismiss(item.id)
 
     again = store.try_enqueue(
-        query="q",
+        query="debug flaky test",
         skill_id="s1",
         confidence=0.2,
         kind="low_confidence",
@@ -95,13 +95,38 @@ def test_dismiss_suppresses_requeue(tmp_path: Path) -> None:
     assert again is None
 
 
+def test_dismiss_suppresses_requeue_across_skills(tmp_path: Path) -> None:
+    """M7 (pi NIT-d): suppress is keyed by query_hash, same as dedup — a
+    dismissed query re-routed through a different skill_id stays suppressed."""
+    path = tmp_path / "routing_pending.jsonl"
+    store = RoutingPendingStore(path)
+
+    item = _enqueue(store, "route my query", "skill-a", "h-same")
+    assert item is not None
+    store.dismiss(item.id)
+
+    # Same query_hash, different skill → still suppressed.
+    assert _enqueue(store, "route my query", "skill-b", "h-same") is None
+    assert store.is_suppressed("h-same", "skill-b")
+
+    # Legacy rows with empty query_hash keep the (hash, skill_id) fallback:
+    # a dismiss under skill-a does not suppress a different skill.
+    legacy = _enqueue(store, "legacy query text", "skill-a", "")
+    assert legacy is not None
+    store.dismiss(legacy.id)
+    assert _enqueue(store, "legacy query text", "skill-a", "") is None
+    assert _enqueue(store, "legacy query text", "skill-b", "") is not None
+    assert store.is_suppressed("", "skill-a")
+    assert not store.is_suppressed("", "skill-b")
+
+
 def test_daily_cap(tmp_path: Path) -> None:
     path = tmp_path / "routing_pending.jsonl"
     store = RoutingPendingStore(path)
 
     for i in range(3):
         item = store.try_enqueue(
-            query=f"query {i}",
+            query=f"query topic {i}",
             skill_id=f"s{i}",
             confidence=0.1,
             kind="low_confidence",
@@ -111,7 +136,7 @@ def test_daily_cap(tmp_path: Path) -> None:
         assert item is not None
 
     overflow = store.try_enqueue(
-        query="query 3",
+        query="query topic 3",
         skill_id="s3",
         confidence=0.1,
         kind="low_confidence",
@@ -121,3 +146,144 @@ def test_daily_cap(tmp_path: Path) -> None:
     assert overflow is None
     assert store.stats()["created_today"] == 3
     assert store.stats()["daily_cap"] == 3
+
+
+def _enqueue(store: RoutingPendingStore, query: str, skill_id: str, query_hash: str):
+    return store.try_enqueue(
+        query=query,
+        skill_id=skill_id,
+        confidence=0.2,
+        kind="low_confidence",
+        reason_zh="r",
+        query_hash=query_hash,
+    )
+
+
+def test_low_info_gate_blocks_and_records_miss(tmp_path: Path) -> None:
+    # Default layout so the store can derive the MissCounter project root.
+    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
+    store = RoutingPendingStore(path)
+
+    for junk in ("可以", "✓", "/review"):
+        assert _enqueue(store, junk, "s1", f"h-{junk}") is None
+
+    assert store.list_pending() == []
+    assert store.stats()["created_today"] == 0
+    assert not path.exists()  # gate-blocked queries never touch the queue file
+
+    from vibesop.core.skills.miss_counter import MissCounter
+
+    counter = MissCounter(tmp_path)
+    for junk in ("可以", "✓", "/review"):
+        cluster = counter.count_for(junk)
+        assert cluster is not None, junk
+        assert cluster.count == 1
+
+
+def test_low_info_gate_passes_real_queries(tmp_path: Path) -> None:
+    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
+    store = RoutingPendingStore(path)
+
+    assert _enqueue(store, "review my code", "s1", "h-review") is not None
+    assert _enqueue(store, "debug this", "s2", "h-debug") is not None
+    assert len(store.list_pending()) == 2
+
+    from vibesop.core.skills.miss_counter import MissCounter
+
+    assert MissCounter(tmp_path).count_for("review my code") is None
+
+
+def test_low_info_gate_no_match_does_not_double_record(tmp_path: Path) -> None:
+    """no_match misses are already counted by UnifiedRouter._record_route_miss
+    on the same event; the gate must not count them a second time."""
+    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
+    store = RoutingPendingStore(path)
+
+    blocked = store.try_enqueue(
+        query="可以",
+        skill_id=None,
+        confidence=0.0,
+        kind="no_match",
+        reason_zh="r",
+        query_hash="h-nomatch",
+    )
+    assert blocked is None
+
+    from vibesop.core.skills.miss_counter import MissCounter
+
+    assert MissCounter(tmp_path).count_for("可以") is None
+
+
+def test_dedup_by_query_hash_across_skills(tmp_path: Path) -> None:
+    """M7: the same query routed to 2 skills must not eat 2 daily slots."""
+    path = tmp_path / "routing_pending.jsonl"
+    store = RoutingPendingStore(path)
+
+    a = _enqueue(store, "route my query", "skill-a", "h-same")
+    assert a is not None
+    # Same query_hash, different skill → deduped, no second row, no extra quota.
+    b = _enqueue(store, "route my query", "skill-b", "h-same")
+    assert b is None
+
+    pending = store.list_pending()
+    assert len(pending) == 1
+    assert store.count_created_today() == 1
+    assert store.stats()["created_today"] == 1
+
+    # Historical rows with empty query_hash still dedup by (hash, skill_id)
+    # and count individually toward the cap.
+    legacy = _enqueue(store, "legacy query text", "skill-a", "")
+    assert legacy is not None
+    assert _enqueue(store, "legacy query text", "skill-a", "") is None
+    assert _enqueue(store, "legacy query text", "skill-b", "") is not None
+    assert store.count_created_today() == 3  # 1 hash + 2 legacy rows
+
+
+def test_cross_instance_writes_do_not_lose_entries(tmp_path: Path) -> None:
+    """Two store instances (as created per `vibe route`) must not clobber
+    each other's rows even under concurrent read-modify-write."""
+    import concurrent.futures
+    import json
+
+    import vibesop.core.instinct.routing_pending as rp
+    from vibesop.core.instinct.routing_pending import _MAX_NEW_PER_DAY
+
+    path = tmp_path / ".vibe" / "instincts" / "routing_pending.jsonl"
+    store_a = RoutingPendingStore(path)
+    store_b = RoutingPendingStore(path)
+
+    n_per_store = 10
+    assert 2 * n_per_store > _MAX_NEW_PER_DAY  # prove the cap is bypassed below
+    original_cap = rp._MAX_NEW_PER_DAY
+    rp._MAX_NEW_PER_DAY = 1000
+    try:
+        def write_batch(store: RoutingPendingStore, tag: str) -> None:
+            for i in range(n_per_store):
+                item = _enqueue(store, f"{tag} query number {i}", f"s-{tag}-{i}", f"h-{tag}-{i}")
+                assert item is not None
+
+        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
+            f1 = pool.submit(write_batch, store_a, "alpha")
+            f2 = pool.submit(write_batch, store_b, "bravo")
+            f1.result()
+            f2.result()
+    finally:
+        rp._MAX_NEW_PER_DAY = original_cap
+
+    rows = [
+        json.loads(line)
+        for line in path.read_text(encoding="utf-8").splitlines()
+        if line.strip()
+    ]
+    assert len(rows) == 2 * n_per_store
+    assert len({row["id"] for row in rows}) == 2 * n_per_store
+    assert len({row["query_hash"] for row in rows}) == 2 * n_per_store
+
+    # Cross-instance resolve: an instance that never saw the enqueue must
+    # still resolve the item (re-read under the cross-process lock).
+    fresh = RoutingPendingStore(path)
+    resolved = fresh.accept(rows[0]["id"])
+    assert resolved is not None
+    assert resolved.status == "accepted"
+    reread = RoutingPendingStore(path)
+    assert reread.get(rows[0]["id"]).status == "accepted"  # type: ignore[union-attr]
