# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-09-07 S70 [vibesop-py] CLI help/man 三入口 + -h 全树支持（已 push CI 全绿）

**Session Summary**:
- 用户反馈 CLI 不支持 help/-h 不方便。Ship：`vibe -h`/`--help`/`vibe help [COMMAND...]` 三入口 + `vibe man [COMMAND...]` 手册查询（`--roff` 输出真 roff 可喂系统 man，Linux `man -l -` / macOS 存 .1 文件）。
- 实现要点：root Typer `context_settings={"help_option_names": ["-h","--help"]}` 全树继承；已占用 -h 的命令（dashboard=--host、skills feedback=--helpful）自动退化仅 --help，零破坏。
- 3 commits 已 push（`987cf95` feat + `7cf81fc` chore skill-index 刷新 + `67d14c4` docs memory）；CI 10/10 job 绿 + Quickstart E2E 绿 + CodeQL 3/3 绿；全量 6801 passed。

**Key Decisions**:
- Typer≥0.26 运行时是 vendored `typer._click` 层，命令/参数对象**不是** click 子类——反射命令树一律 duck typing（get_command/list_commands/param_type_name），兼容老版本真 click
- `vibe help` 未知命令给 difflib 相似建议（git 风格）；man 终端渲染优先于 roff（Windows 无 man）

**Next Steps**:
1. 本机 dogfood：`uv tool install --reinstall --force .` 后重验 help/man（CLI surface 变化，按 dogfood checklist）
2. Dependabot 9 PR（#102-114）非 major 批量合；openai 3.x / anthropic 1.0 单独评估
3. R5 第二轮人评 + GIF 发版 gate（等用户）

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
<!-- handoff:end -->
