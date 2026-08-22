Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Loading weights:   0%|          | 0/199 [00:00<?, ?it/s]Loading weights: 100%|██████████| 199/199 [00:00<00:00, 18773.85it/s]
已只读核查 §3 + §6 + §6.1，并对关键语义主张做了实码核验（triage_service.py:474-560、replay_routing_baseline.py:65/151-175、skill_promote.py:441-460、discovery.py:101-107/550、tests/conftest.py:288-296）。

## Verdict
PASS_WITH_NITS

## Findings
- [NIT] §6.1 修订 B 细化声称"原 §6 括注安反了，已按此修正"，但 §6 修订 B 括注原文未动：仍写 `explicit_guarded_skill_match`（triage_service.py:541-566）"空白折叠/撇号/≥6 字 containment/全记录 vs first-hit-wins"，把 p0_shadow 特征安到生产匹配器上。实码核验：`has_explicit_guard_signal`（triage_service.py:500-539）生产语义 = lowercase+剥撇号、**无**空白折叠、**无**长度下限（仅 `trigger_norm and`）、first-hit-wins；`p0_shadow`（replay_routing_baseline.py:65,173，`CONTAINMENT_MIN_TRIGGER=6`）= 空白折叠、不剥撇号、≥6 字下限、全记录。修正实际只落在 §3 阶段二 item 1 与 §6.1（两处语义均正确），§6 本体"已按此修正"落空——文档内自相矛盾。建议原地改正 §6 括注，或把 §6.1 措辞改为"已在 §3 阶段二 item 1 修正"。
- [NIT] §3 阶段二 item 1 新增"embedding 双线分测为**召回主口径**（修订 B 细化，§6.1）"：§6 修订 B 与 §6.1 修订 B 细化均只定义双线（recall 线 floor 0.25 / index 线 0.45 门）＋各自 fail-open，从未定义"主口径"；双线分歧时以 recall 线为准是执行层新加的裁决、无裁决层依据，与 round2 claude-MAJOR（裁决层/执行层断裂）同型。若"主口径"仅指展示顺序，建议删词或补进 §6.1。

其余全部核验通过：修订 B 细化（§3 阶段二 item 1 正确包装 `has_explicit_guard_signal` 语义、不调用 guarded-only 匹配器；"draft id 恒落空"经 `guarded_skill_name` 仅认 session-end/riper-workflow 属实）、修订 J 细化（PASS 分母排除回声、降级不发 PASS，§3 item 6 与 §6.1 一致）、修订 A 细化（`draft_sha256`=当前字节哈希、禁止与 ClusterCandidate 生成时基线对表——skill_promote.py:453-460 注释证实）、修订 E/I（shape-batch 单列、排除出 D3 dismiss 分母，§3 阶段一 item 2/3 一致）、修订 F/G（`first_seen_at` 字段名及前缀谓词口径均正确）、§3 与裁决层同步（claude-MAJOR）到位。
