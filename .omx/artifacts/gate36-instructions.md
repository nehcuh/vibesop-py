# Gate36 双路复审任务书

你是独立高级评审，复审 VibeSOP 项目 gate36 阶段二的实施（promote shadow verifier)。项目根：/Users/huchen/Projects/vibesop-py。

## 设计规格
`.omx/artifacts/gate34-synthesis.md` §3 阶段二 + §6 修订 A/B/D/J/K + §6.1 全部细化是定稿规格（评审修订是规范的一部分）。先读它，再读随附 gate36.diff。

## 评审要点
1. **规格符合性**逐条对照：
   - trigger 侧不得调用 guarded-only 的 `explicit_guarded_skill_match`；生产 containment 语义（lowercase+剥撇号、无空白折叠、无长度下限、first-hit-wins）泛化包装且 `has_explicit_guard_signal` 原行为不变；
   - PASS 分母排除 `_has_agent_prompt_prefix` 回声行，lint 与 shadow 同口径；任一线 embedding unavailable → 至多 WARN(degraded) 永不 PASS；无 FAIL 级、激活永不阻断、无 --force；
   - verdict schema：当前文件字节哈希（非 ClusterCandidate.draft_sha256 基线）+ ruleset_version + 分线结果；store 双锁+坏行跳过+200 条/90 天容量；global scope 只存计数+query 哈希不存原文；文本过 sanitize_body_text；
   - activate 重跑：draft 未变复用、变了重跑、降级重跑不遮蔽完整 verdict；
   - 看板 verdicts 段按 scope 过滤明细、stale 比对、CLI/看板 lockstep；
   - 修订 K：空 core_steps 簇保持 TODO 不编造；e2e 新增 promote 降级 smoke 且现有 65 条不动。
2. **不变量**:gate30 upsert、intake 零过滤、双 embedding 分离、triage_service 原函数行为、存储层风格。
3. **代码质量**：正确性 bug、并发/边界（空 catalog、模型加载失败、sticky failure 单例的测试隔离风险）、测试说服力、新 e2e smoke 的正确性。
4. **多平台/安全漏项**。

## 输出格式（严格遵守）
```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```
只读核查（grep/read），不要修改任何文件。
