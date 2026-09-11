# Docker AB：hermetic 闸 vs 容器 live `vibe route`

> 2026-09-11 · linux/arm64 · `vibesop-val-base:py3.12` · 代码 `feat/evo-wave1`
> 原始 JSON：`.omx/artifacts/ab-routing-hygiene-20260911.json`
> 预注册（跑前写死）：同一组负例/正例，比过灌率与命中率；不谈墙钟。

## 两臂

| 臂 | 是什么 |
|---|---|
| **T / hermetic** | `eval_routing.py --hermetic`：cwd/HOME pin、关 embedding/triage、宇宙钉在 builtins + benchmark-pack |
| **C / live** | 同一容器里 `vibe route --json`：真实 CLI，HOME=`/tmp/e2e-home`，无 hermetic pin |

题集：`must_not_inject` 5 + `near_miss` 14 + 正例 16（diagnosis / experiment / session / slash）。

## 结果 [executed]

| 指标 | hermetic | live |
|---|---:|---:|
| 负例过灌 | **2 / 19** | **1 / 19** |
| 正例命中 | 15 / 16 | 14 / 16 |

过灌明细：

- 两边都灌：`工地上的工人六点准时收工下班` → `builtin/session-end`（keyword 0.95）。形近退出信号，域外是工地下班。
- 仅 hermetic 灌：`herd instinct is what drives most market bubbles` → `builtin/instinct`；live 正确落到 fallback（no-match）。pin 宇宙和 live 宇宙不一样。
- 最低集五条（公众号 / 微信 / 翻译 / 天气 / 考试题）：**两臂全绿**，都不注入。

正例漏：

- 两臂都漏：`帮我深度诊断这个项目的性能瓶颈并给出优化建议` → fallback（诊断+性能混在一句，hermetic 基线里已是 known-fail）。
- live 另漏：`收工了` 未解析到 primary（JSON 抽取空）。不当成产品结论。

## 判读（观察性）

1. **日常负例已经不像 8 月那次 5/7 误注入。** 天气/翻译/写公众号在 Docker 里两臂都拒。这是 D3 `must_not_inject` 闸 + 改口之后的回归，不是「技能突然懂了闲聊」。
2. **近失仍在。** 「收工」这种触发词裸匹配没有域过滤器。用户场景：真正下班收工该命中；工地叙事不该。产品该做的是分层负例，不是把 session-end 拆掉。
3. **hermetic ≠ live。** `herd instinct` 一臂灌一臂拒。拿 hermetic 数字直接当生产数字会说错话。生产基线仍以 spans 聚合为准（本机 898 route，no-match 32.18%）。
4. **这不是「技能让编码更强」的 A/B。** 那组实验（R1–R6）已经做过：强模型打平，弱模型赢的不是 SKILL.md。本组只测路由卫生——这是技能有效性的前置条件。

## 和用户场景的对应

| 你输入 | 该发生 | 本次是否发生 |
|---|---|---|
| 今天天气怎么样 / 翻译这段英文 | no-match | 是 |
| 写公众号总结 | no-match | 是 |
| 收工了 / that's all for now | session-end | hermetic 是；短句 live 仪器未钉死 |
| 工地上的工人六点准时收工下班 | 应 no-match | **否**，两臂都灌 session-end |
| /help、/list、点名诊断（英文） | 命中对应技能 | 是 |
