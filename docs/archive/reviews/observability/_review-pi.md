# Independent Review — VibeSOP v8.2 Loop Closure Design

## Section A — Verdict

| Criterion | Score | Justification |
|-----------|-------|---------------|
| (i) Architectural soundness | **3/5** | Closed-loop topology is correct and the component decomposition (Aggregator → Analyzer → Suggestion → Instinct) is clean. But extending LoopSpec with `analyzer_id` conflates scheduling policy with computation identity — a category error that will metastasize into `validator_id`, `pipeline_id`, etc. |
| (ii) Scope discipline | **3/5** | Two analyzers is disciplined. But the instinct lifecycle surface (pending → accept → quarantine → regression watcher → auto-rollback) is an entire state machine smuggled into v8.2 under "two-step accept." That's a v8.3-sized subsystem. |
| (iii) Risk coverage | **2/5** | Three critical under-specifications: (a) 15% threshold has no measurement window, minimum n, hysteresis, or cooldown — flapping is inevitable, (b) multi-instinct blame attribution when success_rate drops is unsolved, (c) no span volume backpressure story — spans.jsonl grows unbounded. |
| (iv) Phasing realism | **2/5** | P1 ships analyzers that consume data produced in P2. Route mismatch requires per-skill confidence scores, which require router-internal spans (GAP-1, scheduled for P2). P1's analyzers will have exactly one data point per task (the outer span) and produce zero actionable output. Stakeholders will judge the feature on a system that can't yet demonstrate its value proposition. |
| (v) Acceptance testability | **3/5** | Per-skill p25 is testable with synthetic span fixtures. But the regression watcher requires a simulation harness to validate the 15% threshold under realistic variance — no test strategy mentioned. Route mismatch correctness has no oracle. |

**Composite: 2.6/5**

---

## Section B — Top 3 concerns

### 1. Phasing is inverted (Decision #3)

P1 builds analyzers without the data they analyze. GAP-1 documents that agent-internal spans don't fire; GAP-4 documents that no InsightAnalyzer exists. The design resolves GAP-4 first and GAP-1 second. This is backwards. `route_mismatch` needs per-decision confidence scores from the router. `instinct_candidate` needs routing-decision patterns. Neither exists in P1. The analyzers will run against a near-empty dataset, produce no insights, and the closed-loop demo fails on first contact with reality. **The correct ordering is: emit internal spans → validate data shape manually → build analyzers on real data → close the loop.**

### 2. LoopSpec `analyzer_id` is the wrong abstraction (Decision #1)

LoopSpec is a cron scheduler: it answers "when should I run X?" By adding `analyzer_id` as a *target type* alongside `skill_id` and `workflow_id`, you're embedding "what kind of computation is X" into the scheduling primitive. These are orthogonal concerns. An analyzer is a computation; a LoopSpec is a trigger that *may* invoke an analyzer. The correct separation:
- LoopSpec: trigger schedule + target reference (polymorphic — could be a skill, a workflow, *or* an analyzer)
- AnalyzerRegistry: what analyzers exist, what data they need, how they produce suggestions

Jamming them together means every future computation type (validator, optimizer, drift detector) needs a new LoopSpec variant. The user's mental model of `vibe loop` can still be preserved — `vibe loop add --analyzer route_mismatch --cron "0 */6 * * *"` is a LoopSpec that references an analyzer, not a LoopSpec whose type IS an analyzer.

### 3. Regression watcher is dangerously under-specified (Decision #5)

A 15% auto-quarantine threshold with no measurement window, no minimum sample size, no hysteresis, and no cooldown period. Concrete failure mode: an instinct is applied, the next 3 tasks happen to be edge cases that fail (small-n variance), success_rate drops 40%, instinct is auto-quarantined. Then the watcher sees success_rate recover (because the instinct was fine, just unlucky), re-activates the instinct, rinse and repeat. The system flaps. Worse: if two instincts are active simultaneously and success_rate drops, which one caused it? There's no attribution model — you quarantine both or pick arbitrarily.

---

## Section C — Disagreements

### Reverse Decision #1: `analyzer_id` should not be a LoopSpec target type

**Replace with**: Analyzer as a first-class registry concept. LoopSpec references analyzers by ID the same way it references skills — the target is polymorphic, but `analyzer_id` is not a *kind* of LoopSpec. 

```
# Current proposal (category error):
LoopSpec(target_type="analyzer", analyzer_id="route_mismatch", cron="...")

# Proposed:
LoopSpec(trigger=cron("0 */6 * * *"), target=AnalyzerRef("route_mismatch"))
LoopSpec(trigger=cron("0 0 * * *"),   target=SkillRef("code_review"))
```

This keeps the user-facing `vibe loop` mental model intact while keeping the type system honest.

### Reverse Decision #3: swap P1 and P2

P1 should be **span emission + SpanAggregator integration**. Ship that, let it bake, validate the data shape, let stakeholders see real spans. Then P2 builds analyzers on real data with known characteristics. P3 closes the loop. You cannot build a data-driven system before the data exists.

---

## Section D — Missing considerations

1. **Span schema versioning.** `spans.jsonl` is the system's foundational data contract. If the schema changes between P1 and P2 (adding a `router_confidence` field, say), P1 analyzers are broken with no migration path. Needs an explicit `schema_version` field and a compatibility policy.

2. **Cold-start contract.** What does `route_mismatch` report for a skill with <5 historical invocations? "Insufficient data — need N more samples" is a valid output, but it must be explicit in the suggestion format. Otherwise the analyzer produces p25=0.3 on 4 samples and the suggestion looks actionable when it's noise.

3. **Span retention and confidence drift.** Per-skill p25 requires historical data. If `spans.jsonl` is rotated after 30 days, confidence bands for infrequently-used skills collapse. Retention policy must be specified and the analyzer must emit "stale data" warnings.

4. **Multi-project semantics.** Does `spans.jsonl` aggregate globally or per-project? Per-skill p25 confidence is meaningless if aggregated across projects with different codebases and skill semantics. A `project_id` discriminator in spans is essential.

5. **Deterministic replay.** For debugging why an analyzer produced a specific suggestion, you need to replay `spans.jsonl` through the analyzer. Without this, every misclassification is a heisenbug.

6. **Instinct conflict resolution.** What happens when instinct A says "route query pattern X to skill foo" and instinct B says "route query pattern X to skill bar"? Priority? Timestamp ordering? Merge? Refuse? This must be specified before auto-apply ships.

7. **`cost_usd` aggregation** — question 7 asks whether this should be a first-class analyzer. Yes, but only if the span already captures `cost_usd` per tool call. If not, that's a span schema addition (P2 scope). As an analyzer, it's trivially rule-based (aggregate by skill, flag top-N spenders) and provides immediate stakeholder-facing value. Recommend including in P2.

---

## Section E — Overall verdict

**Re-think.** The closed-loop topology is correct, but the phasing puts the cart before the horse (analyzers before data), the LoopSpec `analyzer_id` abstraction is a category error that will accrete technical debt, and the auto-apply regression watcher is under-specified to the point of being dangerous. Fix the phasing, separate analyzer identity from scheduling, and specify the watcher's statistical contract — then ship.
