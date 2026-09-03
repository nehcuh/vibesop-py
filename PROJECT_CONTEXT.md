# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-09-03 S68 [vibesop-py] 科普文 v2：skill-routing-explained 重写

**Session Summary**:
- 两轮用户复审迭代：v1 补深度 + 完整实验流程（为什么设计→目的→发现→结果→反思→改进）；v2 中段去干——§3 改「考试/封卷/验药」语感，§4 重写为「借口排雷记」连续剧结构（三条选题直觉先行 → 每轮怎么选题/为什么该赢 → 结局 → 借口 → 下轮冲借口去）。
- 中心论点（用户洞察）：spec 写满时 LLM+Harness 无需技能；skill = 需求设计的泛化、spec 的补充（spec 一次一图 / skill 图集 / 老师傅手感=没画出来的施工图）；grill-me = spec 缺口探测器（事实它查/决策你拍，`disable-model-invocation` 只能人点名）。
- 7 张 mermaid；数据全部对齐 R1-R6 报告；§9 新增「泛化框架是假设非定理」诚实条目。

**Key Decisions**:
- 文章定位 = 思考分享，不是项目推广；技术报告体最多做附录
- R6 完成度差距不归因技能内容；协议偏离注脚随正文走

**Next Steps**:
1. R8 结算后回写 §9 假设条目；该文即公众号素材
2. S66/S67 对抗评审修复仍未提交（非本 session 文件，未动）

### 2026-09-03 S67 [vibesop-py] pull-20260903 评审修复闭环 + 8.2.0 发版（CI 全绿）（并行线，与 S68 提及的对抗评审线 S65-S67 同号不同文）

**Session Summary**:
- 三路评审 5 P1 / 8 P2 / 4 NIT 分四批全修（925d4ad→14f96b5，每批 kimi 门禁 + grok 只读复审双 APPROVE）；主线是识别器-生成器同构收口：demote 信号面、source_file 全穿（stub 不可路由）、doctor 部署新鲜度、真实载荷测试。
- 8.2.0 发版（967e134 + tag，已 push）：CHANGELOG 收录 8-28 以来全部；v8.3 契约 Added + instinct-learning Removed 留守 Unreleased；33 文件版本串扫荡。
- 全量 6638 passed；basedpyright 本地 29 错=环境分叉（CI 同 commit 绿），净增判据=与 origin/main 基线差。

**Key Decisions**:
- minor 依据：demo 技能 always-on（路由胜者变化）、confirmation_mode 默认 ambiguous_only、demote 计入 success=False、注入器根序中心存储优先
- 跨模块导入的符号不用下划线私有名（basedpyright reportUnusedFunction 只盯私有名）
- origin/main 的 CI Lint 曾红（7f2de48 三文件未 format），批A/B 顺带修复

**Next Steps**:
1. Dependabot 9 PR（#102-114）：非 major 批量合，openai 3.x / anthropic 1.0 单独评估
2. R5 第二轮人评 + GIF 发版 gate（等用户）
3. backlog：decomposer 未过滤池、execute_build 假成功、非 CLI 面三处 annotate 无 lookup

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
<!-- handoff:end -->
