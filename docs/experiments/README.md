# 实验执行索引

状态索引更新：**2026-09-14**。旧多专家队列已结算；固定角色委员会 v2 已进入后续运行阶段，尚未完成。以下状态来自已有报告，本次目录整理没有重跑或补算实验。

旧 360/144 不重跑、不改冻结源。早期 v2 协议中的“未启动”是设计期记录，不能作为当前状态；后续状态见 [v2 登记页](fixed-role-v2/README.md) 和 [2026-09-14 中间发现](2026-09-14-fixed-role-interim-findings.md)。

| 目录 | 角色 | 样本 | 读什么 |
|---|---|---|---|
| [multi-expert-e2e-protocol.md](multi-expert-e2e-protocol.md) | 原始设计 + 执行后差异 | — | 先读状态段 |
| [multi-expert-calibration/](multi-expert-calibration/README.md) | 非正式校准 | 75（45+30），**不是** 360 | 账本 |
| [multi-expert-formal/](multi-expert-formal/REPORT.md) | 预固定主实验 | **360/360 terminal** | **主报告（两轮合读）** |
| [multi-expert-sensitivity/](multi-expert-sensitivity/REPORT.md) | 诊断触发的探索补充 | **144 = 136 完成 + 8 中断** | 敏感性全文 |
| [fixed-role-v2/](fixed-role-v2/README.md) | 后续：固定角色委员会与人数/适配/通信/腐化/升级 | **未完成**；09-14 00:26 中间记录：241 条正式终态，另有 4 条已启动缺终态、115 条未启动；人数诊断未启动 | [中间发现](2026-09-14-fixed-role-interim-findings.md)；[设计期协议](fixed-role-committee-v2-protocol.md)与[矩阵](fixed-role-committee-v2-matrices.md)保留原文 |

旧队列入口：[multi-expert-formal/REPORT.md](multi-expert-formal/REPORT.md)。过程档案：[multi-expert-formal/report/provenance/PROCESS.md](multi-expert-formal/report/provenance/PROCESS.md)。

8 次中断是 Grok headless 600s 控制器清理，按预定规则计 0，不是模型能力失败，未补跑。旧报告结论不能直接支持新协议中的四条假设。

## 原始数据与恢复

已结算的 calibration / formal / sensitivity `runs/` 共 20,199 个文件已移至本机 `../vibesop-py-archives/2026-09-14/experiments/`。内容校验通过，原目录保留被 Git 忽略的相对符号链接，原报告和读取脚本在本机继续可用。

每个实验目录的 `evidence-manifest.json` 记录冷归档位置、文件数和完整校验清单的 SHA-256。这些大体积原始数据未提交到 Git；新机器需要一并恢复冷归档，不能把本机兼容链接当作仓库自带数据。v2 未完成运行的数据继续保留在 `.experiment/v2/`。
