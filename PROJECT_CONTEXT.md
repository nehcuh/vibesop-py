# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-09-03 S58 [vibesop-py] 匹配无内容 fail-closed + 对外叙事复审收口

**Session Summary**:
- 根因：SkillLoader rglob 看见 `.vibe/skills/cross-cutting/{id}.skill/SKILL.md`，注入器按裸 id 重猜路径；`fuck-my-shit-mountain` 是仓库跟踪包。不是 Windows `/` 分隔符。
- 闸门：source_file 缺失不可路由；inject 全 id glob；空内容/GBK/unsafe 不再 `VibeSOP routed` + `[ACTIVE SKILL]`。清 pack + skill-index + skill-routing.yaml。
- 三路对抗 2 APPROVE / 1 COMMENT（project/skills 已吸收）；Kimi+Claude 双路 APPROVE。定向 143 passed。
- 对外叙事同步吸收 S57 对抗复审：88% 非 fail_under；R7 仅笔记；R8 未完成不结算。

**Key Decisions**:
- 不变量是 match ⇔ 可注入 SKILL.md 正文，闸在 inject 时刻
- fallback-llm / orchestrate 跳过 inject（gate40 结果契约）
- `.omx/artifacts` 仍不入库

**Next Steps**:
1. 注入优先 `candidate.source_file`（glob 兜底）仍是债
2. 人机 `vibe route` 仍不 inject
3. 需要的话再开 `source_file` 主路径

### 2026-08-30 S54 [vibesop-py + cmspark] 侧边栏任务面板 → 跨项目纠正 → 编排事件契约 → 技能治理（已全部推送）

**Session Summary**:
- cmspark 侧边栏"任务拆解清单"：4 路对抗推演 + claude/grok 双路复审（9 必改）→ v1.1；用户纠正归属后，cmspark 侧发现 Issue #256 在途 → spec 补强 §5 + Wave 1 实现（RunProgress 默认收起+sticky，855/855）→ 合 main 推送（`9d45b7c2`）
- vibesop-py 编排事件契约保留：events.py（PlanEventLog 单调 seq + replay）+ commands.py（retry/skip 幂等 + 依赖级联）；四路评审后清死钩子 on_plan_event、修 H1 级联 skip 抹终态等 11 项 → 4 commits
- 技能治理：18 预置技能审计零删除；registry_sync 键 bug + slash-analyze 补建 + Pi 模板 .pi/ 前缀；instinct-learning 并入 instinct（双路终审抓出绿灯假象：834 恰好不含 matching）→ slash-* 家族级模糊层排除 → 全量 6563 passed → 推至 `e682861`
- 本机残留清理：instinct-learning 中央库/claude/grok/opencode 副本 + 全局索引条目（备份 ~/.vibe/skill-index.json.bak）

**Key Decisions**:
- vibesop-py 定位纯后端给外部 agent；外产品 UI 需求不入仓（文档归档 docs/archive/）
- 计数语义：静态计划 x/N，动态计划分项计数；SW 永不做状态真源（Agent 后端事件日志才是）
- LEVENSHTEIN_EXCLUDED 不再逐事故扩列——slash-* 家族级前缀排除（_is_slash_wrapper）
- 分支纪律：只删已合并分支；cmspark 两个 fix 分支含未合并提交（用户确认后删）

**Next Steps**:
1. cmspark #256 Wave 2（FocusBand 24px 扫视行）另票；#256 可更新 Wave 1 已落地
2. tortoise-centipede 分支被 Warp worktree 占用，需用户在 Warp 侧处理
3. examples/datasets/silm-log.zip（18MB 未跟踪）归属待确认；.omx/artifacts/ 是否入库/ignore 待定
4. executor.py:182 "bug" 是误报（同名不同类 WorkflowEngine），已实证关闭
<!-- handoff:end -->
