# Instinct-Learning Loop — Pi External Review

**Date:** 2026-07-23
**Brief:** `docs/decisions/_review-instinct-loop-brief.md`
**Plan:** `/Users/huchen/.claude/plans/starry-herding-stream.md`

## 总判定：CONDITIONAL — 修 5 项后放行

对抗 reviewer 的 FIX BEFORE EXECUTE 判对了一半——核心并发/数据擦除是真问题，但架构方面的担忧过度。

## 4.1 对抗评审质量

### 真问题（必须修）

| Flaw | 证据 | 判定 |
|------|------|------|
| **A 并发** | `learner.py:160-167` `threading.RLock()` 进程内锁；`loop_cmd.py:81-134` advisory lock 只护 `state.json`。三方写 `instincts.jsonl`/`sequences.jsonl` 全无文件锁。`_save()` 全量覆写（learner.py:196-198），并发下丢数据。 | **MUST-FIX** |
| **C Growth cap off-by-one** | `promoted > before * 0.2 + 1`，before=100 允 21 次（应 20）。用 `learner._instincts`（private，line 160），应用 public `learner.instincts`（line 196-198）。 | **MUST-FIX** |
| **D 反馈信号擦除** | `miss.clear()`（miss_counter.py:138-143）删整个文件。feedback-collect 每小时跑，第一次后 `miss_counter.json` 为空。**逻辑 bug，非风格问题**。 | **MUST-FIX** |
| **E.1 plist 无 shlex.quote** | `f"cd {project_root}"` 遇空格直接挂。 | **MUST-FIX** |
| **E.3 deprecated launchctl** | 用 `launchctl load`（deprecated），应 `launchctl bootstrap gui/$(id -u)`。 | **MUST-FIX** |

### 过度反应 / 误判

| Flaw | 反驳 |
|------|------|
| **B 状态机签名错** | 伪代码 `_run_command_target(spec, store, state)` vs 实际 `execute_loop_tick(spec, runtime, store=None)`（executor.py:176）。但这是 plan **伪代码不精确**，意图是对的重用 `state.record_run`。**文档问题，非设计缺陷**。 |
| **H.1 sum type 双职责** | `LoopSpec` 已 3-way 互斥（models.py:237），加 `command_args` 作第 4 选遵循现有模式。`MetricCondition` 也是字段方式。架构洁癖。 |
| **H.2 Subprocess 破坏 layering** | `core/prompt_chain/validator.py:6` 已经 `import subprocess`。LoopRunner Protocol（executor.py:85）是为打破 Core→Agent 反向依赖，不是禁止 subprocess。 |
| **H.3 eval vs auto-promote 去重** | 写不同文件（`skill_candidates.jsonl` vs `instincts.jsonl`），走不同下游。**设计选择，不是缺陷**。 |

### 对抗评审漏掉的结构性问题

1. **`_classify_failure` 不适配 subprocess stderr**（executor.py:85-94）：关键词集为路由错误设计（"timeout"/"connection"/"rate limit"/"not found"）。subprocess 返回的 stderr 形状完全不同——`uv run` 失败输出不含这些词 → 绝大多数 command 失败归为 PERMANENT → 快速进 DEAD。plan 没提适配方案。

2. **plan 伪代码未体现 `record_run` / `save_state`**：plan 文字说"复用"，伪代码没写。若照伪代码实现，DEAD/FAILING 状态机对 command target 彻底不工作。**关键落差**。

3. **`vibe loop delete` 不清 plist**：创建了 `install-launchd` 却没有对称的清理逻辑，stale plist 会累积并持续触发。

4. **`get_reliable_instincts()` 当前不存在**：feedback-collect 伪代码调用此方法。**[pi 误判 — 此方法实存于 learner.py:316，已核实]**

## 4.2 修订方向

| 建议 | 判断 |
|------|------|
| SubprocessLoopRunner 走 Protocol | **矫枉过正**。直接调 `subprocess` 20 行解决，用 Protocol + injection 要加 2 个新类型 + 调用方改造。`validator.py` 已有先例。 |
| CommandLoopSpec 子类 | **矫枉过正**。字段方案改 3→4 way 互斥校验，Pydantic 模型无需 discriminated unions。 |
| 不用 miss.clear()，用水位标 | **must-fix**。否则 feedback 路径一天后就是僵尸。 |

## 4.3 三个抉择

- **Q1**：选字段。`MetricCondition` 也是字段方式（commit 553622d）。子类要改 Pydantic discriminated union + store 序列化 + CLI 解析，无收益。
- **Q2**：接受 core 层 subprocess。`validator.py:6` 已有先例。LoopRunner Protocol 语义是"注入 Agent runtime 打破反向依赖"，不是"禁止 core 层 I/O"。
- **Q3**：每小时太激进。一天 24 次写 → 并发窗口扩大 24 倍。confidence 漂移有界（boost 单次 +1、cap at 2 applications），频率越高边际收益越低。**建议改 daily**。

## 4.4 验证矩阵

| 修订项 | 判定 | 理由 |
|--------|------|------|
| A 并发文件锁 | **必须修** | 加 `fcntl.flock` |
| B 重构走 Protocol | **可不修** | 现有 plan 路线可行 |
| C Growth cap 修 | **必须修** | 边界错 + private API |
| D 水位标 | **必须修** | `clear()` 让 feedback 一次后永久失效，逻辑 bug |
| E.1 shlex.quote | **必须修** | crash bug |
| E.2 sleep 警告 | 建议修 | 文档说明 |
| E.3 modern launchctl | **必须修** | 用 deprecated API 是技术债，首次实现就做对 |
| F hash_for 文档 | 建议修 | salt 已 0o600（line 170）；加 `.gitignore` 提示 |
| G 7 个测试 | 建议修 | path-with-spaces / shell-injection / growth-cap 边界 / DEAD 转换 4 个必须 |
| H.1 子类 | 可不修 | 字段方案符合现有模式 |
| H.2 Runner 注入 | 可不修 | `validator.py` 已有先例 |
| H.3 eval/promote 去重 | 可不修 | 不同文件不同下游，加文档说明即可 |
| I bak rotation | 建议修 | 运维安全，不阻塞 |

## 4.5 最终发布条件

**CONDITIONAL**：修 5 项后放行——

1. **A** — `InstinctLearner._save()`、`record_sequence()`、`record_outcome()` 加 `fcntl.flock`
2. **C** — growth cap 公式修正 + 改用 `learner.instincts`
3. **D** — `feedback-collect` 不用 `miss.clear()`，改用水位标
4. **E.1** — plist 中 `project_root` 过 `shlex.quote`
5. **E.3** — 用 `launchctl bootstrap/bootout` 替代 `load/unload`

外加 **plan 修正**：`_run_command_target` 伪代码补全 `state.record_run()` + `store.save_state()`，以及 `_classify_failure` 对 subprocess stderr 的适配方案（建议：所有非零 exit code 默认 TRANSIENT，command target 失败多为环境问题）。

反馈频率建议从 hourly 降为 daily，但**非阻塞条件**。
