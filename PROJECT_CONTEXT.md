# Project Context

## Session Handoff

<!-- handoff:start -->
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

### 2026-08-22 S40 [vibesop-py + cmspark] 候选池 id 漂移去重（gate30）→ push f76dd61

**Session Summary**:
- M12（语义洞察→技能发现）全收官后的触发器检查发现真 bug：`cluster_id` 随簇增长漂移 → upsert 重复追加（cmspark 池 8 对重复）
- 修复：upsert 同类 Jaccard>0.5 absorb-merge + 守卫全集化；三轮 claude+pi 复审收敛（2 轮真洞全修）
- 验证：5964 passed / e2e 65/65+7/7；push `f76dd61`；cmspark 重扫池自愈（26 行，重复归零）

**Key Decisions**:
- 池层模式身份 = project-agnostic task 词汇集（跨项目同模式 = 一个候选）；W5.1 复合键只管 span 归因
- 守卫阻断集 ⊇ 写路径破坏集；exact-id 例外仅对 unstable 行可达（同 id ⟹ 同成员）
- 候选 ID 会漂移：`5bd44eee`→`64d301b8`，`6a6d554f` 并入 `af55cfff`

**Next Steps**:
1. 用户：cmspark `vibe skill discover` 处理 5 条 stable 候选；bd1bc217 草稿 `--activate`
2. 新开 kimi 会话激活 hooks（M3 行为证据前提）；3 个 dead loop 可 reset 复活
3. 数据触发：簇攒 ≥2 条工具序列 trace → M3 阈值复检；留存池 2026-09-19 前复挖再 purge
<!-- handoff:end -->
