# Phase A Milestone — Merged Kimi + Pi Review

**Date:** 2026-07-23
**Brief:** `docs/decisions/_review-instinct-loop-phase-a-brief.md`
**Phase A diff:** `git diff src/vibesop/core/loop/{models,executor}.py`（320 行）
**Verification:** 164 passed / 1 skipped, ruff clean, basedpyright 0 errors

## Merged verdict

| | kimi | pi | Consensus |
|---|---|---|---|
| **总判定** | SHIP TO PHASE B | SHIP TO PHASE B | ✅ **通过** |
| Q1 状态机集成 | 正确 | 正确 | ✅ |
| Q2 分类不对称 | 合理 + 1 P2 nit | 合理 | ✅ |
| Q3 错误累积 | (a) keep as-is | (a) keep as-is | ✅ |
| Q4 core/loop subprocess | 接受（先例 validator.py:6）| 接受 | ✅ |
| Q5 测试缺口 | 并发/unicode 补在 Phase B | 同意 | ✅ defer |
| Q6 verdict | SHIP | SHIP | ✅ |

## Kimi 评审细节

- 状态机集成精确：循环外持久化 + try/except 包裹 save_state 都对路
- **P2 nit（已修）**：`_COMMAND_PERMANENT_KEYWORDS` 含 `"no such file or directory"`，但设计 rationale 列举的 TRANSIENT 场景（".venv 锁、文件竞争"）恰以此字符串表现。已收窄：从 keyword 表移除，OSError 分支（prefix 缺失）单独覆盖。

## Pi 评审细节

- 分类不对称两表分开合理（routing 用语法/配置错误集，command 用用法/权限集）
- 建议 Phase B 加 `attempt_history: list[FailureInfo]` 字段，`error` 只保留最后一次（避免膨胀）
- 建议 Phase B 补 unicode command_args 测试

## Phase A 落地（基于评审）

| 改动 | 来源 | 状态 |
|------|------|------|
| `_COMMAND_PERMANENT_KEYWORDS` 移除 "no such file or directory" | kimi P2 nit | ✅ 已修 |
| 新增 `test_classify_command_failure_keyword_coverage` 表征测试 | kimi P2 nit | ✅ 已加 |
| `failure: FailureInfo \| None = None` 防御初始化 | 对抗 review §1 | ✅ 已加 |
| VIBESOP_RUN_PREFIX 改用 `shlex.split` | 对抗 review §15 | ✅ 已修 |
| 重试 `attempt_errors` 累积 + final 拼接 | 对抗 review §2 | ✅ 已加 |
| 5 个新测试（retry/env/prefix/truncation）| 对抗 review §9 | ✅ 已加 |
| `timeout_s` docstring caveats（≥30s） | 对抗 review §11 | ✅ 已加 |
| `max_retries` docstring 警告 tick 上限 | 对抗 review §13 | ✅ 已加 |

## Phase B 待办（来自本次评审）

- [ ] `InstinctLearner` 加 `fcntl.flock` + `.bak` rotation
- [ ] `MissCounter` 加 `decay_frequent` + `hash_for`
- [ ] unicode command_args 测试
- [ ] （可选）`LoopRunRecord.attempt_history` 字段（pi 建议）

## Phase A 资产

- `src/vibesop/core/loop/models.py` — command_args + timeout_s 字段 + 4-way xor
- `src/vibesop/core/loop/executor.py` — `_classify_command_failure`、`_run_command_target`、execute_loop_tick 分支
- `tests/core/loop/test_models.py` — 6 个新测试
- `tests/core/loop/test_executor.py` — 12 个新测试（含 P2 nit 表征测试）
- `docs/decisions/_review-instinct-loop-phase-a-brief.md` — 本次评审 brief
- `docs/decisions/_review-instinct-loop-phase-a-merged.md` — 本文（merged verdict）

## Review sessions

- kimi: `session_6ab85f2f-61fe-4b24-95b9-fb2a0f247350` (resumable via `kimi -r`)
- pi: 通过 `pi -p` 一次性评审（无 session id）
