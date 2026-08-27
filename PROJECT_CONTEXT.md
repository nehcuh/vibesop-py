# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-08-27 S50 [vibesop-py] gate46 块2 quickstart 双平台 aha — 8 commits 待 push

**Session Summary**:
- 标准门流程全闭环：设计稿 → grok+claude-pi 双路确认（v2.1 PASS）→ 实施 → 双路实施复审（均 NEEDS_FIX）→ P1 全清/裁决 → 8 原子提交 `d47f386`→`30a4bb7`
- 交付：4 演示技能（commit-message/test-generation/code-review/systematic-debugging，双语 keyless，无 LLM/无 embedding 命中）+ quickstart 双语路由演示与注入预览（剥 frontmatter、单 banner）+ `vibe route --hook --platform` 参数化 + 双平台探针脚本 + CI quickstart-e2e（Linux+Windows 矩阵）+ docs 14→18 口径清零
- 关键修复：injector builtin 四级解析阶梯（project_root→wheel bundle→repo 推导→sys.path——修 project_root 非 vibesop 仓库时注入 not found）；`write tests` 从 tags 移入 triggers（triggers 只参与 explicit 层，防 builtin 在 pack 机器 keyword 抢 superpowers/TDD）
- 验证：6416 passed / 0 failed；wheel e2e（隔离 HOME + offline）全绿；复审裁决记录 `.omx/artifacts/gate46-impl-review-synthesis.md`

**Key Decisions**:
- 拒绝 --force→installer force=True（静默覆盖已装 hooks 是破坏性语义扩张，CI HOME 隔离已消实际风险）
- R7 双态测试带非空调转守卫：`ExternalSkillLoader.EXTERNAL_PATHS` 是 import 时绑死真 HOME 的 ClassVar，只 patch env HOME 测试会静默空转成无 pack 重跑
- grok UserPromptSubmit 信封是 Claude 形状（`PlatformType.GROK_BUILD` 映射 `_inject_claude_code`）；levenshtein 0.3-0.5 兜底层重排属存量噪音，不动模糊层排序

**Next Steps**:
1. 用户授权 push → `gh run view --json jobs` 查 job 级绿灯（quickstart-e2e Windows lane 首跑）
2. GIF 录制（W5 发布 gate；`docs/demo-recording-guide.md`，probe 输出兜底）
3. recall 演示 defer 独立 mini-gate（关键词降级文案 + 播种命令 + span schema 对齐）

### 2026-08-27 S49 [vibesop-py] pull-20260827 三路评审 → M1/M2 hook 修复闭环

**Session Summary**:
- 拉取 `f1f34de..e286e67`（v8.1.1 上游）三路评审出 M1（rebuild rewrite 破坏用户 hook 条目）/ M2（verify 误报用户 PowerShell 命令）
- fix-plan 4 轮 pi+grok 双路（双 REJECT×2 → 拆分架构 → v4 双 APPROVE）→ v4.1 实施 `utils/hook_commands.py`：宽松 classify 服务 verify、strict parse + legacy-signal 只服务 rewrite
- omx 双 lane 清 3 条一行级；push `574349c`（代码）+ `8304e9a`（CHANGELOG 回填）
- 重部署 `~/.claude` + `~/.grok`(rules+hooks)：UPS route 复活 + route hook 实测点火 exit 0 + 双平台 verify 全绿

**Key Decisions**:
- 识别器与生成器必须同构（win32 规范 1-token / 含空格用户名 / 大写盘符是必测形态）
- shlex `posix=False` 认引号但保留引号字符——宽松口径过剥 fail-safe，严格口径不确定即 None
- 双 APPROVE 后 NIT 按处方折叠不再送审（防无限轮）

**Next Steps**:
1. 8.1.2 待办：C1 白名单 canary 测试；C2 preserve-matcher substring → `command_basenames` 精确匹配
2. 等 CI run 结果（Ubuntu + Windows 矩阵验证 HIGH 修复）
3. Grok 真实会话 probe（gate42/43 cron 8-31 / 9-7）
<!-- handoff:end -->
