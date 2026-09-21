# 落地计划：把研究结论变成产品能力（设计先行）

> 源：S88 调研 + `.omx/artifacts/skill-distillation-review-20260921.md`
> 日期：2026-09-21 · 基线：`f57f7faa` · 编排：grok（本 tmux pane 0）
> 状态：**Wave 1 派工**（先产品设计，再开发）

## 0. 一句话

评审方法论（F4/F5/F6/F10 的 decision-source）已经是技能和 CI。本轮把 **F1 / F2 / F9** 的可操作面做成产品：少注入写满的任务、把消费分账记下来、晋升草稿必须带前提与反例。全部 report-only，零新门禁。

## 1. 本轮不做

- R8 盲评结算、E4 整机流水线（等人评数据）
- gate43 T+21 生产复测（要 cmspark 活体 spans；本轮只把 t7/t14 入库）
- 恢复「每次都注入」
- 用未验证启发式当注入硬闸
- 把 LLM 评审或新度量当 merge gate
- 自动合 main、force-push、`git add -A`
- 改 R3/R4 预注册判据
- 改 `src/vibesop/core/routing/benchmark.py` 的 `HERMETIC_POSTURE` / 指纹 / 吸收守卫
- 三路同时改 `memory/project-knowledge.md`（F 系 warm 层由 grok 在合入后写）

## 2. 硬边界（所有 lane）

- 只用 `uv`，不用 pip。
- 工人只在自己的 worktree + feature branch 上提交。
- **Phase 1 未写出设计文档并自检之前，禁止改 `src/`。**
- 新信号一律 report-only 或 WARN；promote 继续「灯不是闸」。
- 验收贴命令和退出码，不写「已验证」。
- 完成必须有 handback。

## 3. 波次

```
Wave 1（本轮，三路并行，各自先设计再开发）
  F1     claude   spec 缺口 → 注入策略 / task-briefing
  F2     pi       消费分账：选中 / 读到 / 适用 / 执行 / 验收
  F9+F10 kimi     promote 四要素模板 + gate43 测量入库 + workflow 悬空

Wave 1.5（grok）
  读三份设计 → 合入 worktree → 主工作区验证 → F 系写入 project-knowledge
```

## 4. 文件所有权（禁止跨 lane 写）

| Lane | 可写 | 只读 |
|---|---|---|
| F1 claude | `core/skills/task-briefing/`（新建）；`core/registry.yaml` **只增** F1 技能条目；`src/vibesop/agent/runtime/skill_injector.py`；`src/vibesop/agent/runtime/agent_runtime.py`（仅注入注释/字段）；对应测试；本 lane 设计/handback | 路由匹配器、hermetic、promote |
| F2 pi | `src/vibesop/core/observability/` 下新建消费模块；接线 `tool_call_bridge.py` / `route_observe.py`（最小）；CLI 子命令；对应测试；本 lane 设计/handback | skill_injector 主体、promote 模板、registry.yaml |
| F9 kimi | `src/vibesop/core/observability/skill_promote.py` 的 SKILL.md 渲染；`promote_verifier.py`（只加 WARN 项）；`core/skills/skill-craft/SKILL.md` 模板段；`core/skills/adversarial-panel/SKILL.md` 第 3 步（workflow 名）；tracked `.grok/workflows/` **或** 改技能不再依赖未跟踪 workflow；`git add -f` gate43-t7/t14；`scripts/check_artifact_links.py` 仅当守卫需要；对应测试；本 lane 设计/handback | skill_injector、registry.yaml、F1/F2 新模块 |

本轮 handback 命名改为 `distill-lane-<id>-handback.md`（例如
`.omx/artifacts/distill-lane-f1-handback.md`）。

设计文档写在**本 worktree**：

`docs/specs/2026-09-21-distill-<id>-design.md`

## 5. Staffing

| Agent | tmux | worktree | branch |
|---|---|---|---|
| grok | session 0 pane 0 | 主仓 `/Users/huchen/Projects/vibesop-py` | main（ahead 2，不在本波改 src） |
| claude | session 0 pane 1 | `/Users/huchen/Projects/vibesop-distill-claude` | `feat/distill-f1` |
| pi | session 0 pane 3 | `/Users/huchen/Projects/vibesop-distill-pi` | `feat/distill-f2` |
| kimi | session 0 pane 2 | `/Users/huchen/Projects/vibesop-distill-kimi` | `feat/distill-f9` |

## 6. 每 lane 完成定义

1. `Status: DONE | PARTIAL | BLOCKED`
2. 设计文档路径（Phase 1）
3. 改动文件清单
4. **命令 + 退出码**
5. 「我无法验证的部分」
6. 建议 grok 写入 `memory/project-knowledge.md` 的 F 条目草稿（5–10 行）
7. 对 hermetic / CI / 既有 promote「灯不是闸」的影响说明

没有设计文档 + handback + 退出码，一律不算完成。

## 7. 产品原则（设计时不可推翻）

1. **可信靠测量，收口靠机制。** 新能力必须能被测试钉住，不能只写进 SKILL.md。
2. **过滤自动化，不过滤人审。** promote 缺四要素 → WARN，永不阻断 activate。
3. **消费证据优先于评分。** F2 的分账是「技能有没有进上下文」的前置判据，不是新的成功率分数。
4. **精确命中既非必要也非充分**（E23）。F1 不得把「没注入」或「注入了」直接写成效用。
5. **确定性层才配门禁。** 本轮零新 required CI job；现有 `routing-eval` 保持 `human`。
