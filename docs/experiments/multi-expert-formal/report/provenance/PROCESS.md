# 过程档案：准备 → 校准 75 → 主 360 → 纠偏 → 补充 144 → 交付

本目录只归档**非密钥**的监督与过程文件。Grok 流式 thought / stderr **不复制**，本机路径见文末索引。冻结实验源码与原始 `result.json` 不在这里改写。

## 时间线

1. **协议与准备**  
   设计稿 [`../../../multi-expert-e2e-protocol.md`](../../../multi-expert-e2e-protocol.md)（执行后状态已更新，原文设计意图保留）。任务从项目失败机制构造，不是生产回放。`beliefs.md`、`supervision.md` 记录当时假设与监督约定。

2. **校准 75**（非正式，**不是** 360 样本）  
   - 45 次旧执行器：`docs/experiments/multi-expert-calibration/runs/`  
   - 30 次新执行器非正式：`runs/20260913T015759Z`（K=40）、`runs/20260913T020657Z`（K=80）  
   账本：[`../../../multi-expert-calibration/README.md`](../../../multi-expert-calibration/README.md)。三批留存，不合并胜率。`calibration-supervisor-audit.json`。

3. **主 360 预固定**  
   freeze 后写入不可变 manifest `runs/20260913T023645Z`（360 行）。先 12 后 resume 348。360/360 terminal。  
   监督终审：`supervisor-final-20260913T023645Z.json`（360 唯一，4665 调用，D−A −93.06pp）。  
   快照报告：[`../../REPORT.primary360.md`](../../REPORT.primary360.md)。

4. **展示层纠偏**（不改冻结源、不改原始结果）  
   审计层 task_hash 比较、泄漏候选裁定、中文字体、资源轴。见 `phase4-supervision-notes.md`。

5. **敏感性触发与 144**  
   决策预先写在 `sensitivity-decision.md`（主实验 D 失败至少一半为内部 stage_cap；实测 72/72）。  
   守卫：`sensitivity-guard-audit.json`（五条离线检查通过）。启动审计：`sensitivity-start-audit.json`。  
   指令：`grok-phase4-sensitivity.md`。run `20260913T033401Z`。

6. **控制器中断与恢复**  
   2026-09-13T03:46:53Z Grok headless 600s 超时杀后台 runner。123 已终态保留，8 个 running 标 interrupted 且不重跑，13 个未开始项 resume。  
   `sensitivity-infrastructure-interruption.json`、`grok-phase4-recovery.md`。  
   终态：144 = 136 执行完 + 8 中断。监督：`supervisor-final-20260913T033401Z.json`。

7. **终稿交付**  
   指令：`grok-phase5-delivery.md`、`final-editorial-review.md`。主 `REPORT.md` 改为连贯中文文章。本 PROCESS 与 provenance 归档。不增加模型实验。

## 独立审计 JSON（本目录）

| 文件 | 内容 |
|---|---|
| `supervisor-final-20260913T023645Z.json` | 主 360 |
| `supervisor-final-20260913T033401Z.json` | 敏感性 144 |
| `sensitivity-start-audit.json` | 144 启动前 freeze/pack |
| `sensitivity-guard-audit.json` | 软结束守卫（无 live 模型） |
| `calibration-supervisor-audit.json` | 校准 |
| `formal-first12-supervisor-audit.json` | first12 |
| `supervisor-progress.jsonl` | 监督进度 |
| `supervisor_audit.py` | 监督审计脚本 |

## Grok 流式日志（本机，未复制）

根目录：`/Users/huchen/Projects/vibesop-py/.experiment/`

| 阶段 | 指令 md（已归档） | thought jsonl（本机） | stderr（本机） |
|---|---|---|---|
| phase1 | `grok-phase1.md` | `grok-phase1.jsonl` | `grok-phase1.stderr` |
| correction1 | `grok-correction1.md` | `grok-correction1.jsonl` | `grok-correction1.stderr` |
| phase2 | `grok-phase2-start.md` | `grok-phase2.jsonl` | `grok-phase2.stderr` |
| phase3 | `grok-phase3-complete.md` | `grok-phase3.jsonl` | `grok-phase3.stderr` |
| phase4 144 | `grok-phase4-sensitivity.md` | `grok-phase4.jsonl` | `grok-phase4.stderr` |
| phase4 恢复 | `grok-phase4-recovery.md` | `grok-phase4-recovery.jsonl`；另有 `grok-recovery-fresh.jsonl` | `grok-phase4-recovery.stderr`；`grok-recovery-fresh.stderr` |
| phase5 交付 | `grok-phase5-delivery.md` | `grok-phase5.jsonl` | `grok-phase5.stderr` |

**超时证据**：`grok-phase4.stderr` 在 `2026-09-13T03:46:53.948409Z`：`headless: background wait timed out, exiting pending_bg=2 timeout_secs=600`；随后 `killing background work still pending`。

## 最后验证（交付轮）

- 主 360：360 unique，passed 149 / failed 211，与 `supervisor-final-20260913T023645Z.json` 一致。
- 敏感性 144：passed 130 / failed 6 / interrupted 8；136+8=144。ITT −11.11pp，CI [−23.61, 0]。7 个开放 HTTP。与 `supervisor-final-20260913T033401Z.json` 一致。
- 主 `REPORT.md` 按 `final-editorial-review.md` 八条改写：连贯结构、天花板、中断计量、不把 CI 上界=0 说成已证实更差、A 整合列 N/A、案例非 JSON 截断、Mermaid+嵌图、建议限定证据。
- 未改冻结 prereg / harness 源 / 原始结果。未 merge、未 push。
- 展示层勘误（额度：独立 2400/人、交流 800/人；费用 n 为实验运行/分配而非 API 次数；同批 A/D_soft 已知费用对比）。不重跑实验。
- 勘误同步后与主仓 `docs/experiments/` 目录 hash 一致（排除 `__pycache__` / `.pyc`）：`multi-expert-formal` 13263 文件，`multi-expert-sensitivity` 6677 文件。commit `365988ce`。
