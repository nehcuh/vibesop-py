# Report audit notes to verify after primary completion

These are provisional source-review observations, not participant outcomes. Re-check latest implementation before acting.

- report/audit360.py task_hash_drift currently uses `manifest.get("task_hashes") is not None`, which reports presence rather than drift. Must compare catalog-computed hash, frozen manifest hash and per-result task_hash; preserve primary data.
- Hidden-leak detection must not classify generic model text such as "hidden acceptance" or an invented cases.py filename as actual leaked evaluator content. Such marker hits are candidates requiring evidence. Verify provenance/data flow: fixed ToolBox exposes only visible tests, contract Q&A and workspace CLI; evaluator runs after model end. Record true issue/false positive with examples, never remove a flag merely to make audit green.
- Audit requests/response XOR, raw usage incl cache+reasoning, seq tool events and used_k, limits, parameter consistency, task metadata, all allocation multiplicities, exact frozen manifest sha256 (supervisor first12 JSON) not only360 count.
- plots need installed Chinese font explicitly (PingFang/Songti/Noto CJK), inspect renderedPNG to avoid tofu; resource axes must represent values without clipping.
- Full report: evidence trace cases must include an actual hidden-acceptance failure (if any), expected versus actual CLI output and original source/code/tool/request references; don't select all examples from first12 if that misses code-level failures.
- Task roots come from project mechanisms, not original production replay. Cite available project experience sources; disclose plan deviations: synthetic smallCLI, same author generated evaluator+runner with supervisor review, no independent blinded human maintainability review. No invented completion claims.
- Model cost estimates exclude Grok preparation/supervision, compute/engineering overhead; label exact scope.
- D vs C changes both role title and focus instructions; cannot isolate title alone. No strong-vs-weak or skill experiment here.

## Confirmed after all primary360
Independent supervisor audit: 360unique,4665calls, no usage/cache/reasoning/tool/metadata/success-contract mismatches; manifest SHA matches first12. A67/72, B65/72, C2/72, D0/72, E15/72. D all72 fail internal stage. All160 hidden-evaluated artifacts pass, but11E have ownership protocol failures. Therefore **there are no primary hidden-test implementation-failure examples**; do not invent one. Show actual rejected cross-file ownership attempts instead and distinguish raw artifact acceptance160 from strict success149.
The sole marker hit in report audit is confirmed false positive: route-nomatch-contract-v1-brief-E-r2/call-022-request.json assistant says its `_selftest.py` will not affect `hidden acceptance` running app.py. This is generic participant reasoning about task execution, not evaluator content. Preserve candidate flag + adjudication.
Viewed pass_by_arm.png: all Chinese labels are tofu boxes. Must fix font and regenerate all figures, visually inspect PNG.
Current audit360.json incorrectly says task_hash_drift:true from the presence check noted above; correct actual hash comparisons in audit layer.
Primary supervisor JSON: /Users/huchen/Projects/vibesop-py/.experiment/supervisor-final-20260913T023645Z.json. Independent D-A -0.9305555555555555, CI[-1.0,-0.8194444444444445].

## Ceiling limitation
Primary A=67/72=93.1%; on this realized battery even a perfect D can improve by only6.9pp. The preregistered+10pp adoption threshold must stay unchanged, but report this ceiling explicitly: failure to reach10pp can partly reflect insufficient task headroom, not the absence of benefits on harder tasks. All160 artifacts reaching hidden tests pass, reinforcing that this battery mainly separates completion/protocol rather than delivered-code quality. The same-task sensitivity isolates orchestration, not external generalization or blinded maintainability.

Supplement interpretation: soft-closing may leave missing independent/exchange deliver notes. Quantify missing notes and do not describe every D_soft allocation as a fully completed deliberation. The single-rule sensitivity tests continuation under the original caps, not an optimized expert team. Supervisor independent five guard checks passed; artifact /Users/huchen/Projects/vibesop-py/.experiment/sensitivity-guard-audit.json (compare engine hash if later edited).

## Final144 independent outcome/usage audit
144 unique allocations:130passed,6failed,8interrupted;136 actually completed. D_soft61/72 (7interrupted,3K exhaustion,1final truncation); A69/72 (1interrupted,2final truncation). 2404requests,2397savedresponses,7expected missing final responses due controllerkill. No unexpected audit defects. Both groups'130 hidden-evaluated artifacts allpass. D_soft-A -11.1111pp, frozen task-cluster CI[-23.6111,0]pp; interruption outcome point bounds[-12.5,-1.3889]pp, boundsare descriptive unknown-outcome analysis, notnewCI. Even all7 interruptedDsuccessful+interruptedAfailed =>D68 vsA69 onthisbattery. Report this sample bound withoutclaiming universal/statisticallycertaininferiority.
Source: /Users/huchen/Projects/vibesop-py/.experiment/supervisor-final-20260913T033401Z.json.
