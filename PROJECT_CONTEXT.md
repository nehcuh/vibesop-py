# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-09-03 S64 [vibesop-py] fail-closed skill_file 栈已推 origin/main

**Session Summary**:
- 头：`c67c82a`。match ⇔ 可注入 SKILL.md；编排/模板/hook/Pi 扩展/OpenCode 插件跟 `skill_file`，找不到则不要猜 `skills/<id>/SKILL.md`。
- 双路：模板层 Kimi REQUEST CHANGES（session-end `--slash` 死命令，已吸收）/ Claude APPROVE；剩余目录层 Kimi COMMENT / Claude APPROVE，已吸收 runtime 失败 hint + Pi/OpenCode。
- Pi `.pi/skills/` 生成树前缀保留。未跑 `vibe build pi`。`.omx/` 仍不入库。

**Key Decisions**:
- session-end 回退用 `vibe skills info builtin/session-end`，不用 `--slash "/session-end"` 也不用 `vibe route "session-end"`
- 刷新本仓 `.pi/` 用外科补丁，不用全量 `vibe build pi`

**Next Steps**:
1. 存量 `~/.claude` / PATH 上的旧 `vibe` 需本机 `vibe build` / `uv tool install`
2. Dependabot / R5 人评 / GIF 发版 gate 未动

### 2026-09-03 S58 [vibesop-py] 匹配无内容 fail-closed + 对外叙事复审收口

**Session Summary**:
- 根因：SkillLoader rglob 看见 `.vibe/skills/cross-cutting/{id}.skill/SKILL.md`，注入器按裸 id 重猜路径；`fuck-my-shit-mountain` 是仓库跟踪包。不是 Windows `/` 分隔符。
- 闸门：source_file 缺失不可路由；inject 全 id glob；空内容/GBK/unsafe 不再 `VibeSOP routed` + `[ACTIVE SKILL]`。
- 三路对抗 2 APPROVE / 1 COMMENT；Kimi+Claude 双路 APPROVE。对外叙事：88% 非 fail_under；R8 未完成不结算。

**Key Decisions**:
- 不变量是 match ⇔ 可注入 SKILL.md 正文，闸在 inject 时刻
- fallback-llm / orchestrate 跳过 inject
- `.omx/artifacts` 仍不入库
<!-- handoff:end -->
