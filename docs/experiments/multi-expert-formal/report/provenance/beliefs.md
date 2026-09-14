# Experiment beliefs

B1: Prior calibration is not a valid organizational comparison: tools, context and usable budgets differ. Predict initial fidelity gate fails despite offline runner checks passing.
B2: Expert role labels may have limited incremental value; this is a prediction, not a predetermined result.
B3: Coordination overhead will be measurable; validity requires recording all attempts and shared resource ceilings.
B4: Three repeats within one task are not independent tasks; inference must cluster by base task.
B5: A per-call 6000-token cap made A poorer than multi-agent on usable budget; removing it while keeping a shared T/I/K ceiling is required for a valid D-A comparison.
B6: Identical tool sets (read/write, visible Docker tests/CLI, fixed Q&A) plus preserved histories are necessary; without them C/D/E cannot iterate and any ranking is a harness artifact.
B7: Twelve formal tasks must be distinct mechanisms (4 routing / 4 config-entry / 4 split-quant), not calibration clones or data permutations, or the sample is invalid.
B8: Brief specs plus a shared Q&A bank can equalize knowable norms; hidden preferences that are not in Q&A must not be scored against the brief arm.
B9: Objective readiness is a count of protocol gates (tasks, isolation, budget, logging, pre-acceptance, preregistration), not participant win rate.
B10: Informal tool-loop calibration (3 new tasks x 5 arms x 1) is required to freeze T/I/K; old 45 runs stay read-only and out of the 360.

## Iteration 1 prediction (before code)

Hypothesis: B5+B6+B7+B9. Building the formal harness, 12-task catalog, shared Q&A, reference/mutant pre-acceptance, and `verify_experiment.py` will raise compound from 0 to a majority of protocol gates, but informal live calibration and frozen T/I/K will still be incomplete in this iteration.

Predicted rubric (gate pass=1):
- catalog_12x2xQA: 1
- independence_review: 1
- reference_and_mutant_sensitivity: 1
- visible_hidden_split: 1
- real_cli_entry: 1
- identical_tools: 1
- budget_precheck_full_T_for_A: 1
- history_and_CD_independence: 1
- E_ownership_serial_deps: 1
- docker_isolation: 1
- metering_and_logging: 1
- truncation_policy: 1
- preregistration_DA_cluster_10pp: 1
- calibration_excluded_from_360: 1
- formal_360_not_started: 1
- model_alias_documented: 1
- informal_live_calibration_frozen_TIK: 0
- ready_for_review_complete: 0

Predicted compound: 16 / 18. Predicted verdict after eval: keep if compound > 0.

## Iteration 1 revised prediction (supervisor notes; still before first commit)

Supervisor corrections are pre-freeze validity, not outcome edits. Additional beliefs:

B11: Unique monotonic call_id owned by the run recorder is required; per-Loop counters will overwrite C/D/E artifacts.
B12: Requests must be persisted before the HTTP call; otherwise API failures have no request body.
B13: Stage quotas must be reserved per assigned member; a shared exchange/worker pool lets the first speaker starve the rest.
B14: Truncated tool_calls cannot be replayed without matching tool results.
B15: E overlap is a pre-registered failure, not a logged footnote on a passing run. Integrator keeps the planner history.
B16: Brief arms need a metered `contract` question that returns the full normative spec; otherwise information-parity fails (T3 id grammar is the example).
B17: T9 must be real volume-weighted VWAP or be renamed; T6 echo/sum is a control, not a cross-layer task; T4 depends_on is emission order, not sorted.

Revised predicted gates: previous 16 plus harness_call_id_and_usage_sum, request_before_http, per_member_stage_quota, truncation_tool_calls, e_dag_and_overlap_fail, contract_qa, t9_real_vwap, t6_cross_layer — still 0 on live informal calibration and READY until those run.

Predicted compound after this commit's evaluator: majority of protocol gates, live calibration still 0. Verdict: keep if compound > 0.

## Iteration 1 actual (after first commit eval)

Actual compound: 22 / 25. Hard fail: `config-home-isolation-v1/domain_mutant` (target still `init` after renaming persist case) and `cal-harness-route-v1/domain_mutant` (prefix mutant did not change `maybe`). Offline harness protocol gates all passed. Live calibration 0. Verdict: keep (compound > 0) and patch mutants.

## Iteration 2 prediction

B18: Renaming T7's first hidden case requires updating the mutant target; a prefix-ok mutant needs an `okay` negative case. After that, reference_and_mutant_sensitivity passes. Live calibration still 0.

Predicted compound: 23 / 25 (mutant gate 1, live+READY still 0).

## Iteration 2 actual

Compound 23/25 after T7 mutant returned a wrong JSON root (cwd writes under read-only /work were infrastructure failures, not contract mismatches). Remaining red gates are live informal calibration and READY, which require model calls rather than more harness edits.

## Iteration 3 prediction

B19: First informal batch (K=40) showed C/D/E hitting the tool cap while A passed with K≤14. Raising the shared K to 80 (A may still use all 80) is required so committee K-starvation is not an organizational result. T=24000 and I=200000 had headroom. Predict second informal batch has fewer K-exhaustions; compound 24/25 if freeze recorded; READY after freeze.

## Iteration 3 actual

K=80 still bound 2/15 and one E hit I_precheck. Frozen shared ceilings T=24000 I=400000 K=120 (A may use all). Two informal batches retained, not 360. verify_experiment.py 25/25 [executed]. READY_FOR_REVIEW.md written. Formal 0/360. Stop for supervisor. No organizational ranking.

## Iteration 4 prediction (supervisor operational freeze)

B20: An immutable 360-row manifest plus --max-new/--resume that never reruns terminal or interrupted allocations is required before any formal call.
B21: Concurrency 8 with independent client/ledger/workspace/recorder will not mix logs if dest paths are unique; this is execution, not a speed claim.
B22: A path-preserving freeze pack (harness+tasks+QA+evaluator+resources+prereg+analysis) excluding logs/runs/STATUS/READY, with no resource fallback, is required for resume integrity.
B23: Cluster bootstrap (12 task means, 20000, seed 20260913, failures=0) must be toy-checked before formal results exist.

Predicted new gates all pass; catalog/mutant hashes reused without a full Docker rerun. Compound ≥ previous 25 plus resume/freeze/analysis gates. Then start first 12 of the same 360 manifest.

## Iteration 4 actual

verify_experiment.py 34/34 [executed]. Docker self-check reused (catalog hashes unchanged). Offline: 360-row manifest, --max-new 12, interrupted not rerun, 8-way isolation, freeze pack excludes runs/STATUS, analysis toy, no resource fallback. Formal 0/360 at eval time. Keep. Authorized to start first 12 of one immutable 360 manifest.

## Iteration 5 prediction (resume 348 + full report)

B24: Completing the frozen 360 under the same T/I/K and hard stage caps will show C/D hidden-eval entry rates far below A/B because independent-0 10% T (2400) often exhausts; D−A will therefore largely reflect this envelope, not “experts are worse.” Predict main interval does not support +10pp adoption; likely unresolved or rules-out-minimum-gain, possibly crossing 0. Do not change freeze sources. Report docker tag-vs-digest caveat. Ownership/path violations counted in success definition.

Predicted: 360 terminal; confirmatory D−A from frozen analysis.py only; presentation plots outside freeze.

## Iteration 5 actual

360/360 terminal [executed]: A 67/72, B 65/72, C 2/72, D 0/72, E 15/72. Frozen D−A −93.1pp, 95% CI [−100.0, −81.9] pp, `support_worse` on this hard-stage envelope. C/D hidden-eval entry 2.8%/0% — stage caps dominate. Freeze unchanged. REPORT.md + audit360.json written. Not a claim that experts are worse in general.

## Iteration 6 prediction (exploratory 144 D_soft)

Trigger met: 72/72 D failures are internal stage_budget_exhausted (independent-*). B25: Soft-closing only independent/exchange stage exhaustion, then continuing D's original sequence, will raise D_soft hidden-eval entry vs primary D; D_soft−A on a new interleaved A cohort may still miss +10pp because integrate/I/ownership remain hard. Do not pool with 360. Primary freeze untouched.

Do not treat K=40 failures as instrumentation illusions. Do not generalize to heterogeneous expert teams or whole-repo engineering.

Workflow: Grok implements and executes in isolated worktree. Supervisor reviews direction, preregistration and important results. All formal participant outcomes retained regardless of quality.

## Supervisor direction note (before any formal outcomes)

Review the newly drafted task catalog before claiming independence/complexity. `match-vwap-window-v1` currently defines an arithmetic mean without volumes: call it a rolling mean, not VWAP, or specify real volume weighting consistently. `config-adapter-vs-entry-v1` currently echo/sum is a useful small control but too trivial to stand in for coupled cross-layer engineering; ensure the task battery has meaningful integration difficulty and label small controls explicitly. T7 home-isolation needs persistent state across fresh CLI/container invocations without violating its no-workdir-data rule; reference pre-acceptance should prove this works. These are task-design validity checks, not outcome-based edits. Address before READY_FOR_REVIEW.

## Supervisor information-parity correction (before formal runs)

The drafted brief+QA bank does not yet reconstruct the full contract. Example T3: full spec requires unique IDs matching [a-z][a-z0-9-]{0,31}, but brief and its four answers do not give that grammar/uniqueness; several other tasks omit input/output schema fields. Do not penalize brief arms for unqueryable rules. Provide a common published `contract` clarification returning the complete normative contract (available to every arm, metered) or prove complete coverage with explicit schema answers. If using contract retrieval, state that spec comparison measures retrieval/clarification behavior and overhead as well as initial completeness. Also reconcile T4 Q&A “stable sorted order ... as emitted” with spec and hidden tests: choose and state exact dependency ordering before freeze. No task outcomes have been observed yet; these are pre-freeze validity corrections.

## Supervisor scope guard

The current catalog is mainly compact single-CLI synthetic tasks. This can be an end-to-end controlled benchmark (requirement -> files -> CLI), but not evidence about whole-repository engineering. At READY, explicitly justify where cross-layer tasks require a shared interface/regression across multiple components, and where splittable tasks require actual integration. Strengthen trivial echo/sum as already noted, or clearly narrow the experiment/report scope to small controlled tasks and do not claim general multi-expert efficacy. All 12 should not be minor validation variations of three algorithms. Preserve small controls, include meaningful coupling, and document the distribution before observing formal results.

## Supervisor preregistration clarification (before freeze)

preregistration.md currently gives only one interval branch (“below +10 and above 0 -> undetermined”), which does not preserve the approved protocol's interpretation. Freeze the exact 95% interval method and resampling unit/seed/repetitions before formal calls. Retain original rules: lower bound > +10pp supports the engineering adoption threshold on this battery; upper bound < +10pp rules out that minimum gain at this interval level (does not prove equivalence); upper bound < 0 supports worse performance; intervals crossing decision thresholds are unresolved. An interval entirely between 0 and +10pp supports a small positive effect but not the chosen minimum gain, not a blanket absence of knowledge. Keep direction and engineering-worth statements separate. Main D-A only confirmatory; all other comparisons exploratory. This is a clarification of the already approved protocol, not a result-driven amendment.

## Supervisor operational requirements for the formal run

Before 360 allocation, add resumability that skips only finished allocations in an immutable manifest; retain interrupted attempts and any uncertain billed calls (never silently rerun/select best). Current runner is fully serial with no resume path. Use a modest fixed worker pool if calibrated safe (e.g. 4, record and freeze concurrency); randomize allocation independently of arm, isolate each workspace/client/ledger. This is execution efficiency, not a wall-clock speed claim. Do not mutate the already running informal batch.

Freeze all executable sources + task/QA/reference/hidden-evaluator/schema/resource/prereg files, preserving relative paths and contents, not only five basename copies. Exclude growing logs/results/STATUS/READY from executable source hashing: the current broad ROOT.rglob includes the active log and transient verification files. Verify frozen hashes before starting/resuming formal calls and refuse changed contracts. Missing/invalid resource config must error, not silently use defaults. Save the analysis plan and exact confidence interval procedure before formal results; analysis scripts may only implement that frozen plan.

## Supervisor live-calibration gate

At the current K=40, observed C/D calibration attempts abort during independent analysis or before final integration. This batch is useful resource calibration, but cannot certify that each arm's full live API/tool/integration path works. Before READY, each arm must have at least one live run that reaches final external evaluation (not necessarily passes every code test), with reconciled logs. If raising K is required, raise it identically for all arms and repeat the whole calibration allocation; keep the K=40 batch. Do not choose the winning architecture from these calibration outcomes. Resource choice should give a documented common operating envelope, and formal conclusions remain conditional on that envelope.

## Supervisor interpretation note

Keep K=40 results as genuine resource consumption/failure observations under that particular common envelope. Do not label every budget failure an instrumentation “illusion”: log overwrites and contradictory phase exits were implementation defects, whereas a declared global K limit can legitimately expose coordination overhead. Raising K for all arms is a documented pre-formal calibration choice to exercise all live paths. Report both facts without inferring intrinsic model/committee inferiority or erasing the cost observation.

### Supervisor report scope note
Input precheck uses UTF-8 bytes as conservative upper-bound tokens, not a tokenizer; report this operational stopping rule and I_precheck separately from actual reported input budget exhaustion. E requires exactly two file-disjoint workers even for compact CLI tasks: conclusions concern this explicit split protocol on this task set, not arbitrary adaptive delegation. Do not change these accepted task/arm mechanics from formal outcomes.
