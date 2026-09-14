# 控制器中断用量派生（已知下界）

原始 `result.json` / request / response **未改写**。本文件从已持久化 `call-*-response.json` 的 `usage` 与 `tools.jsonl` 另行派生。

- 8 个 interrupted 分配的 `result.json` **没有最终 ledger**，不能在报告里当成用量 0。
- 7 个分配缺最后一次 HTTP 响应；这些请求**可能已计费，token 未知，不能编造为 0**。
- 1 个分配的已落盘 request 均有 response（`route-priority-table-v1-brief-D_soft-r0`），但仍无 ledger、跑程未终裁，派生值仍标下界。
- 中断原因：Grok headless 后台等待 600s 超时杀进程。不是 DeepSeek API 失败，不是模型能力失败，不把 7 个 D_soft / 1 个 A 记成编排缺陷。

已知下界合计：T=28460，I=236626，cache_hit=214905，K_tools.jsonl=271，估算 USD=0.0210（非发票）。

未知：7 次已写 request、无 response 的 HTTP。

| 分配 | 组 | req | resp | 开放HTTP | 已知T | 已知I | cache | K | 估算USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `config-render-resolve-v1-brief-D_soft-r2` | D_soft | 30 | 29 | 1 | 10502 | 102204 | 93696 | 77 | 0.0079 |
| `route-lifecycle-v1-full-D_soft-r1` | D_soft | 16 | 15 | 1 | 6729 | 46367 | 41084 | 89 | 0.0050 |
| `route-priority-table-v1-brief-D_soft-r0` | D_soft | 11 | 11 | 0 | 4558 | 31490 | 28544 | 46 | 0.0033 |
| `match-vwap-window-v1-brief-D_soft-r2` | D_soft | 12 | 11 | 1 | 3838 | 31182 | 28413 | 30 | 0.0028 |
| `window-dedup-late-v1-brief-D_soft-r0` | D_soft | 6 | 5 | 1 | 1758 | 12987 | 12032 | 15 | 0.0012 |
| `route-priority-table-v1-full-A-r0` | A | 5 | 4 | 1 | 821 | 7984 | 7296 | 6 | 0.0006 |
| `route-priority-table-v1-full-D_soft-r0` | D_soft | 2 | 1 | 1 | 122 | 1427 | 1280 | 4 | 0.0001 |
| `config-render-resolve-v1-brief-D_soft-r0` | D_soft | 3 | 2 | 1 | 132 | 2985 | 2560 | 4 | 0.0002 |

