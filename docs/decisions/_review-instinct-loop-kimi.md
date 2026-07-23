# Instinct-Learning Loop — Kimi External Review

**Date:** 2026-07-23
**Session:** `session_3380675b-70ae-41a0-aa68-ac6567e2b1d1` (resumable via `kimi -r`)
**Brief:** `docs/decisions/_review-instinct-loop-brief.md`
**Plan:** `/Users/huchen/.claude/plans/starry-herding-stream.md`

## 总判定：CONDITIONAL

修 A、C（含 save）、D、E.1 后放行；反对 REWRITE PLAN。

## 4.1 对抗评审质量

**真问题，必须修：**
- **A 并发**：`learner.py:188` `_save()` 只在 `threading.RLock` 下；`_load()` 只在 `__init__` 读一次（line 167），即使无写冲突也是陈旧视图。
- **C growth cap off-by-one**：`>before*0.2+1` before=0 时只允 1 次；用 private `_instincts` 而 public `learner.instincts` 在隔壁（learner.py:196）。
- **D 信号擦除**：`miss.clear()` 直接 `unlink` 数据文件（miss_counter.py:141），hourly 清空后第二 tick 看不到积累。
- **E.1 shlex.quote**：路径含空格时 `cd` 直接炸。

**过度反应：**
- **B 部分成立**：签名错误属实，但"绕开 state.record_run 状态机失效"不是独立问题——解法是**复用 `execute_loop_tick`**（executor.py:176）而非绕过，不需要新发明 Protocol 层。
- **H.1/H.2 过度**：Core 层 subprocess 已有先例（`core/prompt_chain/validator.py:110,153,187`），项目对 layering 的实际标准是"core 不 import agent 层"，而非"core 不能有 I/O 副作用"。

**对抗评审漏判：**
1. **`set_instinct` 不持久化**（learner.py:204-208 只改内存，对比 `record_outcome` line 267 每次都 `_save()`）——auto-promote 忘了调 `save()` 就白跑，这比 cap off-by-one 更致命。
2. **cron weekday 陷阱实际不存在**：`models.py:216-235` `_validate_schedule` 用自家解析器，`LoopTrigger.CRON` 是独立系统；launchd 是新增调度器，需统一定义 launchd 用 `StartCalendarInterval`。

## 4.2 修订方向

- **SubprocessLoopRunner 走 Protocol**：过度。`LoopRunner`（executor.py:85-94）语义是路由查询，subprocess 不是 query。伪清洁。**直接在 CLI 层调 subprocess + 调 `execute_loop_tick` 持久化记录**即可。
- **CommandLoopSpec 子类**：过度抽象。commit 553622d 加 `MetricCondition` 就是**平铺字段**（models.py:203-206）。子类要动 Pydantic 序列化/CLI/store 三处，收益不匹配。
- **水位标替代 clear**：正确，must-fix。

## 4.3 三个抉择

- **Q1 字段 vs 子类**：平铺字段。`extra="forbid"`（models.py:138）加字段向后兼容。子类方案被 553622d 先例否定。
- **Q2 subprocess 进 CLI 层**：但理由是工程而非教条。CLI 已有 launchd/installer 类逻辑；core/loop 保持纯调度语义。
- **Q3 反馈频率**：每小时激进。`record_outcome`（learner.py:267-273）每次整体重写 instincts.jsonl，24 次/天全量写 + 双向漂移，confidence 振荡无 early-stop。建议改 daily，decay/boost 都加"达上下限（0.95/0.1）即停"边界检查。

## 4.4 验证矩阵

| 修订项 | 判定 | 理由 |
|---|---|---|
| A 文件锁 | 必须修 | 三方写 jsonl 丢数据，flock 唯一解 |
| B 走 Protocol | 可不修 | 复用 `execute_loop_tick` 即可 |
| C cap + public API | 必须修 | 另补：`set_instinct` 后要调 `save()` |
| D 水位标 | 必须修 | clear 使 feedback 一次即废 |
| E.1 shlex.quote | 必须修 | 一行修复 |
| E.2 sleep 警告 | 可不修 | 文档说明 |
| E.3 modern launchctl | 建议修 | 顺手 |
| F hash_for 文档 | 可不修 | 文档一句即可 |
| G 7 个测试 | 建议修 | path-with-spaces / growth-cap 边界 / DEAD 转换 3 个必须，其余可选 |
| H.1 子类 | 过度 | 553622d 先例是平铺字段 |
| H.2 Runner 注入 | 过度 | 同 B |
| H.3 eval/promote 去重 | 建议修 | 双写两文件会精神分裂，v1 至少标注各自域 |
| I .bak rotation | 可不修 | v1 不需要 |

## 新问题（对抗 reviewer 未列）

1. **promote 后忘 save**：`set_instinct` 不持久化（learner.py:204 vs 267），是本次 loop 最大的 silent-failure 点。
2. **jsonl 非原子写**：需确认 `write_text` 是否 tmp+rename；若不是，A 的 flock 只防并发、不防 SIGTERM 半写——与 I 项联动。

## 最终：CONDITIONAL

修 A/C（含 save）/D/E.1，B 按"复用 execute_loop_tick"简化，G 选 3 个测试，即可执行；不必 REWRITE。
