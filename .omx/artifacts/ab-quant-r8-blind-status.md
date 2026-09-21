# R8 盲评状态（2026-09-21）

> 预注册：`.omx/artifacts/ab-quant-r8-prereg.md`
> 工作区：`/Users/huchen/Projects/ab-quant-r8/`（仓库外）
> 本文件：**不结算**预注册的人盲评。记录本轮能执行的部分，和仍然缺的部分。

## 裁决

**盲评未结算。** 预注册的评分协议是：独立命题人写出的同一份 `TASK.md` 上，人在 **8821 / 8822** 上看运行中的两臂，五维 1–5，主假设 P5（总分差 ≥3 且 treatment 优）。本会话编排者已经知道哪边是 treatment，不能充当盲评人。LLM 评审不作放行闸（F3 / ROADMAP），也不能替代人盲评去解锁 E4。

未盲的人评（S71b，用户）仍然有效、也仍然只是人评：「技能组明显更完整」。

## 本轮实查 [executed]

双臂产物都在，不是空目录。

| | treatment | control |
|---|---|---|
| compose / Dockerfile / DONE.md | 有 | 有 |
| `app/*.py` 行数 | 1939 | 2517 |
| 面板 | `webapp.py` + `web/` | `app/web/` + `main.py` |
| 独立模块 | `tdx.py` `tushare_src.py` `ai.py` | `ingest.py`（无独立 tdx/ai 文件） |
| PROCESS.md（路由日志） | 有（RIPER 为主路径） | 无 |
| 预注册端口 | 8821 | 8822 |

这是结构观察，不是五维分数，不能写成「treatment 赢了 P5」。

## 仍然缺

1. 独立盲评人（未见过臂标签、未见过 S71b 结论）。
2. 两臂在 8821/8822 上的当场运行记录（本轮未起 docker）。
3. 填好的五维表与 P5 判定。

E4 整机流水线保持关闭，直到上面三条齐。

## 证据分级

- [executed]：工作区目录与文件清单、行数。
- [inspected]：预注册评分协议、S71b 人评记录。
- [assumed]：无。
