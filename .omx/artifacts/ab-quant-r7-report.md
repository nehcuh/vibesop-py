# A/B R7 报告：rstdx → 量化驾驶舱（真实行情）

> 2026-09-02 · 编排：Grok · 预注册：`ab-quant-r7-prereg.md`（build 前写死；行情禁令已按用户当场改为 **必须真 TDX/Tushare**）
> 工作区：`/Users/huchen/Projects/ab-quant-r7/`

## 人评入口（容器在跑）

| 臂 | 端口 | 是谁 |
|---|---|---|
| **http://localhost:8811** | treatment（VibeSOP 技能） | 标题「QUANT · 独立研究员驾驶舱」 |
| **http://localhost:8812** | control（裸实现） | 标题「ABX · 通达信量化驾驶舱」 |

建议盲评：先不要看上表。默认标的都是 **600519 茅台日线**。真实行情，不是 GBM。

## 运行事实 [executed]

| | treatment | control |
|---|---|---|
| Builder 墙钟 | **1668s** | **1454s**（T/C = 1.15×） |
| 技能消费 | 4 次 `vibe route`：prototype（拒跟）、writing-plans、TDD、design-an-interface/frontend-design | 禁止读 SKILL.md |
| 冷库 | DuckDB + 真 TDX parquet | parquet 真 TDX |
| 日线 | 8 标的 × ~799 根，2023-05-19→2026-09-01，启动后 pytdx 增量 | 同左，control 已并入 2026-09-02 |
| 钉 | `600000` 2026-09-01 O9.13 H9.36 L9.10 **C9.35** V102,669,616 | 同 OHLC（但 `PINNED_CLOSE` 会强制写 9.35） |
| 隐藏 API | `/` `/api/health` `/api/bars` `/api/equity` `/api/backtest` `/api/replay/start` `/api/paper/order` **全 200** | **全 200** |
| 茅台 DualMA 回测 | 终值约 65.3 万（-34.7%） | 约 62.5 万（-37.5%） |
| 测试 | 6 个文件（声明 20 passed） | **零** |
| 文档 | README + api/architecture/usage | 一份很完整的 README |

数据源 [executed]：本机旧 Tushare token 失效；TDX HQ `180.153.18.170:7709` 可用。种子用 rstdx 真拉（按请求重连）。Linux 容器改走 vendored pytdx 增量刷新。rstdx 源码曾因 `query/api.rs` 私有模块编不过，本地改了一处 import（未提交 rstdx）。

## 预注册判定

| 预测 | 结果 |
|---|---|
| P1 T≥1.3× 墙钟 | ✗ 1.15× |
| P2 D1 T 胜 ≥1 | 评委分裂（见下） |
| P3 D3 T 胜 ≥1 | 静态/API 层打平，留给你人评 |
| P4 T 有测试 | ✓ |
| P5 总分差 ≥3 且 T 优 | **Grok 深评不成立**（16.5 vs 17.0）；Kimi 认为成立（20 vs 15） |

机制三验：treatment 路由命中且读了 SKILL.md（PROCESS.md）→ **本轮有效**。

## 评分（不改预注册表，评委分开写）

### 1) 编排者 API 冒烟

双臂隐藏路径全过，真实行情钉 9.35 两边 HTTP 一致。**产物层：都能演示。**

### 2) Grok 独立深评（curl + 读代码，不知「技能」叙事）

| 维 | T (8811) | C (8812) |
|---|---:|---:|
| D1 | 3.0 | 3.5 |
| D2 | 3.5 | 4.0 |
| D3 | 3.0 | 3.5 |
| D4 | 3.5 | 2.5 |
| D5 | 3.5 | 3.5 |
| **合计** | **16.5** | **17.0** |

关键缺陷（评分前未修，遵守预注册 §7.4）：

- T：`tests/test_engine.py` 在 SIGNAL **同一根** `hist[-1]` 上撮合（测试路径 lookahead）；replay 主路径不走 matcher。
- C：`PINNED_CLOSE` 把评测日收盘写死 9.35；无测试；5min 增量 volume 可能 ×100。

### 3) Kimi 外部评（CLI `-p` 不能带工具；基于钉死事实）

| 维 | T | C |
|---|---:|---:|
| D1 | 3.0 | 2.0 |
| D2 | 4.5 | 4.0 |
| D3 | 4.0 | 4.0 |
| D4 | 4.0 | 2.0 |
| D5 | 4.5 | 3.0 |
| **合计** | **20.0** | **15.0** |

Kimi 把 C 的 pin 当「应试造假」、把 T 的测试 lookahead 当「可修的验证错误」，因此 T 明显更像可交付。

### 合成（编排者）

技能形态任务上，**过程层差异再次出现**（计划、TDD、三份文档、DuckDB），**API 完成度双臂打平**。深评分数方向取决于评委更恨「测试写错不变量」还是「为隐藏测试钉死收盘价」。P5 的 ≥3 且 T 优 **没有在 grok 深评上成立**；记入零增益序列时必须注明「kimi 反向、差 5 分」。人评 D3 仍开放。

## 对抗选择（仅 T 看到）

架构：DuckDB + FastAPI/Jinja/uPlot + 单进程队列 + 进程内 paper CTP。  
产品：A 股研究员、单页 Bloomberg、默认 600519、红涨绿跌。  
怀疑论 CUT 采纳（禁 Postgres/React/vn.py/.so）；其「TDX=vipdoc 文件」否决。

## 交付物位置

- 预注册：`.omx/artifacts/ab-quant-r7-prereg.md`
- 任务书：`/Users/huchen/Projects/ab-quant-r7/TASK.md`
- 真实行情：`seed/real/*.parquet`
- T：`/Users/huchen/Projects/ab-quant-r7/treatment/`（PROCESS.md、docs/）
- C：`/Users/huchen/Projects/ab-quant-r7/control/`
- Kimi 原文：`/Users/huchen/Projects/ab-quant-r7/eval/kimi-blind-out.md`

停容器：`docker compose -p r7t down` 与 `-p r7c down`。人评结束前请留着。
