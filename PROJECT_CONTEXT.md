# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-08-24 S42 [vibesop-py + cmspark] gate42 幻影 reask 治理 + CI 红灯清零 + v8.1.0 发布

**Session Summary**:
- gate42：vibe-cli 自路由 span 被误判为用户重问（cmspark 残余 reask 75% 幻影）→ bridge `_classify`/`_classify_hit` 两处 `later_same_task` 各加 `not rs.is_cli`（gate41 §6 预授权语义收窄）；三 lane 对抗完全收敛，in-flight 去重/S4 被数据证伪；三路评审+确认轮全 PASS，pi 红绿突变实验 6红2绿
- CI 红灯清零：main 自 gate37 红了一个多月——三轮修（lint 24 + ruff format 74 文件 → launchd uv 路径 hermetic mock + benchmark 重试 → p95 环境分级预算 CI 500µs/本地 100µs）
- v8.1.0 发布：PyPI + GitHub Release 落地（147 commits since v8.0.0；首轮 release 被 p95 假警阻断，tag 前移至 `18be788`）
- cmspark rebuild dry-run 验收预审全过：硬闸 A CLI 触发=0 / 硬闸 B 0.93:1/0.23:1 / sanity 72.2% / 40 条真实重问保全 / ≥60s 样本 11 条已核（最坏损失 2.3%）

**Key Decisions**:
- 定性走 gate41 §6 授权链（语义收窄），不走"代码违背 docstring"叙事——三路评审一致打回后者
- 执行顺序三段：合补丁 → 升级 live `~/.local/bin/vibe`（堵增量靠安装体不靠 checkout）→ 同一空闲窗口 rebuild --apply
- 绝对 µs 微基准在共享 runner 必假警 → 环境分级预算；`--reruns` 救不了系统性减速

**Next Steps**:
1. cmspark rebuild --apply（等 grok 空闲窗口；验收已预审，一条命令）+ T+24h 早期检查（新增 outcome CLI 触发=0）+ CHANGELOG ≥60s 抽样回填
2. gate43 候选：模板文案降级（带定价）/ Windows claude_code 路径断言 3 处 / 流程文档补"push 后盯 CI"
3. 触发器：verdict ≥30 / M3 复检 / 留存池 2026-09-19 / P0-lite 观察期

### 2026-08-22/23 S41 [vibesop-py] gate33-36：grok hooks · 队列可读性 · shadow verifier → push 2359026

**Session Summary**:
- gate33：Grok Build 平台 hooks 落地——`vibe route --hook`（stdin 事件 JSON 模式）+ PostToolUse `vibesop-tool-seq.json` 工具序列采集；adapter `src/vibesop/adapters/grok_build.py`
- gate34：路线图梳理；gate35：Discovery 队列可读性——自解释列头（评分/模式/来源/行为/为什么在）、`为什么在` 只从实存字段直译、agent-echo 打 `shape: agent-echo` 标沉底、`dismiss --shape agent-echo --yes` 批量否决（池翻转/镜像同翻/`dismiss_reason=shape-batch`/豁免 threshold_suggestion）
- gate36：promote shadow verifier——`verify_draft` 输出 PASS/WARN 徽章（无 FAIL、永不阻断、degraded 至多 WARN），verdict 存 `promote_verdicts.jsonl`（global 只存计数+query 哈希，RULESET_VERSION=gate36-r1）
- 验证：pytest 6123 passed / 14 skipped；e2e smoke 68/68 + routing 7/7；最新 push `a59eb13`（文档同步）

**Key Decisions**:
- 批量否决选择去重后的队列视图、翻转在 project+global 双 scope 都执行（只翻一边会复活）；确认文案点名 bd1bc217 先例（回声簇也曾 promote 成功）
- shadow verifier 是提示灯不是门：异常时跳过不阻断；PASS 分母排除 agent-echo 行；activate 时草稿未变复用 verdict、已变以 activate-rerun 重跑
- 看板 ✨ Discoveries tab 与 CLI 共用同一沉底规则/打标/why_here 口径

**Next Steps**:
1. 用户：grok 侧 `vibe build --platform grok-build` 部署后验证 UserPromptSubmit 注入与 PostToolUse 采集落盘
2. 观察 shadow verifier 在真实 promote 流上的徽章分布（WARN 率、degraded 占比）
3. 愿景条目命名冲突跟进：`vibe skill discover` 已被本地队列占用，社区搜索落地时改名 `vibe market search` 之类
<!-- handoff:end -->
