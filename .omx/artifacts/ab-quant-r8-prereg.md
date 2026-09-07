# A/B 案例 R8 预注册：独立命题人写 TASK.md

> 2026-09-02 · 写死后再跑 builder · 事后不改题目
> 工作区：`/Users/huchen/Projects/ab-quant-r8/`
> 相对 R7 的唯一协议变更：**命题人 ≠ 编排者，且命题人不得读技能目录 / R5–R7 任务书模板**

## 为什么要这一轮

R7 的 `TASK.md` 是编排者（Grok 4.6）写的：路由未命中实现技能，但出题人读过技能清单和 R5「必须项 + 留白」模板，并故意做成技能形态。control 与 treatment 栈接近，无法分开「技能改了实现」和「题目已经把路铺好」。

R8 测的是：把题目交给**另一个模型**，只给用户原始产品描述，不给 VibeSOP / 技能 / R7 TASK。然后同一份新题目上再做两臂。

## 命题协议

| 项 | 规定 |
|---|---|
| 命题人 | Kimi Code CLI（与 builder 不同模型） |
| 输入 | 仅用户第一轮里的产品需求（rstdx 现状 + 完整量化系统诉求 + 模拟盘/CTP） |
| 禁止给命题人 | `SKILL.md`、R5/R7 `TASK.md`、预注册、CHOICES、实现说明书、VibeSOP 字样、14 条清单模板 |
| 编排者对 TASK | **不得改写需求**。只允许在文末追加「环境附录」（路径、种子、端口、无 SimNow），并标明附录不是命题人原文 |
| 种子 | 复用 R7 已落盘的真 TDX / Tushare parquet + `ctp_port.py` + pytdx + uPlot（公平条件，不是题目） |

## 双臂（与 R7 相同）

- 同一份新 `TASK.md` + 同一份 `seed/`
- treatment：每个非平凡子任务 `vibe route` 并跟 SKILL.md；技能问人 → 独立对抗代理写 `CHOICES.md`
- control：禁止 `vibe route`、禁止读任何 SKILL.md
- Builder：Grok 4.6 隔离子代理，分 cwd
- 运行时：每臂 docker compose，人评端口 **8821 treatment / 8822 control**（避开 R7 的 8811/8812）

## 评分（沿用 R7 五维 1–5）

D1 量化正确 · D2 系统完备 · D3 面板 · D4 工程 · D5 文档  
判读仍用 R7 §7。主假设仍是 P5：总分差 ≥3 且 treatment 优。  
额外记录：新 TASK 是否仍呈「14 条 checklist + 明确留白」——若否，说明 R7 的形态来自出题人而非用户原话。

## 种子哈希（拷贝后回填）

- TASK.md（命题人原文）sha256: `eb074c2750c8000358c590c32d83a89ca224ae6195b54a8f192008784cee4678`
- 环境附录 sha256: `5ce376a2ecf25d09403dc97bc6c6580125a64c4cf18725f260187e05ea11b23b`
- seed/real/bars_daily.parquet: `4bdd3f2237d777a0cc6953f6e291684100015833f909b100b00981f605c4d1ca`
