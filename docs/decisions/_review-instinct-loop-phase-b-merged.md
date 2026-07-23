# Phase B Milestone — Merged Kimi + Pi Review

**Date:** 2026-07-23
**Brief:** `docs/decisions/_review-instinct-loop-phase-b-brief.md`
**Phase B diff:** 675 lines (`git diff HEAD` after Phase A merged at `fdafbcb`)
**Verification:** 4484 passed / 13 skipped, ruff clean, basedpyright 0 errors
**Adversarial pre-review:** FIX BEFORE EXECUTE → 3 flaws fixed (#1 CRITICAL, #3 HIGH) + 1 documented (#2 HIGH)

## Merged verdict

| | kimi | pi | Consensus |
|---|---|---|---|
| **总判定** | CONDITIONAL (1 P1) | SHIP TO PHASE C (0 P0/P1, 3 P2) | ✅ **通过（P1 已修）** |
| Q1 clear-epoch | 正确（仅 instincts 路径）| 正确 | ✅ |
| Q2 FLAW #2 defer | 可接受 | 可接受 | ✅ defer |
| Q3 锁降级 | 可接受 | 可接受 | ✅ |
| Q4 epoch 检查重复 | v1 可接受，建议 helper | 可接受，P2 | ✅ defer |
| Q5 .bak 单步 | 够用 | 够用 | ✅ |
| Q6 同进程测试 | 够用（P2 建议补 subprocess） | 够用 | ✅ defer |

## Kimi P1（必修，已修）

**sequences.jsonl 双锁漏洞**：`_save()`/`clear()` 持 `instincts.jsonl.lock`，`record_sequence()` 持 `sequences.jsonl.lock` —— 两把不同的 flock 文件互不阻塞。后果：
- (a) 跨进程 `_save` 与 `record_sequence` 仍可竞态 `sequences.jsonl`，FLAW #3 修复不彻底
- (b) `record_sequence` 的 epoch 检查与 `clear()` 的 bump 不在同一锁下串行，sequences 的复活窗口仍在（FLAW #1 残留）

**修法**：`record_sequence` 改用 `_cross_process_lock(self.storage_path)`，全店共用一把锁。+ 新增回归测试 `test_record_sequence_clear_does_not_resurrect_sequences`。

## Pi P2 nits（部分采纳）

| # | Pi 建议 | 处理 |
|---|---------|------|
| 1 | `record_sequence` 缺 sequences.jsonl 的 `.bak` | ✅ 已采纳（与 kimi P1 一并修，加 `_backup_locked(seq_path)`） |
| 2 | 抽 `_ensure_fresh_epoch_locked()` helper | defer 到 Phase C（kimi Q4 也建议，但双方都不阻塞）|
| 3 | `_bump_clear_epoch_locked` warning 已有 | N/A（pi 自评 OK）|

## Kimi P2 建议（未采纳，记入 Phase C/E）

- 补 subprocess 级并发测试（两个真进程并发 `record_outcome`/`record_sequence`）→ Phase C launchd E2E 顺带覆盖
- `_save` 每次无条件 backup sequences.jsonl → 无害，保留
- `clear()` 遗留 `.lock` 文件 → 同意 cosmetic

## Phase B 落地（基于评审）

| 改动 | 来源 | 状态 |
|------|------|------|
| `_cross_process_lock` context manager (fcntl.flock sibling .lock) | plan v2 §3 | ✅ |
| `_backup_locked` .bak rotation | plan v2 §3 (pi 建议) | ✅ |
| `_merge_disk_into_memory_locked` / `_merge_disk_sequences_into_memory_locked` | plan v2 §3 | ✅ |
| `_save` 双锁 + .bak + merge | plan v2 §3 | ✅ |
| `clear()` 删文件 + bump epoch + 跳过 merge | 对抗 FLAW #1 | ✅ |
| Clear-epoch 生成计数器 (`.vibe/clear_epoch`) | 对抗 FLAW #1 | ✅ |
| `record_sequence` 加锁 + merge + epoch 检查 | 对抗 FLAW #3 | ✅ |
| `record_sequence` 改用 storage_path 锁 + seq .bak | kimi P1 + pi P2 #1 | ✅ |
| `_load()` 不再短路 sequences 加载 | 对抗 review 顺手发现 | ✅ |
| `decay_frequent` 减半 + 返回 pre-decay 列表 | plan v2 §4 | ✅ |
| `hash_for` 公开包装 | plan v2 §4 | ✅ |
| `.gitignore` 加 `.vibe/*.lock`、`.vibe/sequences.jsonl*` | 配套 | ✅ |
| 8 个 `TestInstinctLearnerCrossProcessLock` 测试 | 对抗 + kimi | ✅ |
| 4 个 miss_counter 测试 | plan v2 §4 | ✅ |
| 1 个 unicode command_args 测试 | pi Phase A defer | ✅ |

## Phase C 待办（来自本次评审）

- [ ] launchd plist 生成（`core/loop/launchd.py`）
- [ ] `vibe loop install-launchd` / `uninstall-launchd` CLI
- [ ] `vibe loop delete` 清 plist（pi plan v2 新增）
- [ ] plist quoting 用 `shlex.quote`（plan v2 §5c E.1 必修）
- [ ] modern launchctl `bootstrap`/`bootout`（plan v2 §5c E.3 必修）
- [ ] （可选）抽 `_ensure_fresh_epoch_locked()` helper（pi P2 #2 + kimi Q4）
- [ ] （可选）subprocess 并发测试（kimi P2）

## Phase B 资产

- `src/vibesop/core/instinct/learner.py` — flock + .bak + epoch + merge + record_sequence 统一锁
- `src/vibesop/core/skills/miss_counter.py` — decay_frequent + hash_for
- `tests/core/test_instinct_learner.py` — 8 个 `TestInstinctLearnerCrossProcessLock` 测试
- `tests/core/skills/test_miss_counter.py` — 4 个新测试
- `tests/core/loop/test_executor.py` — 1 个 unicode command_args 测试
- `.gitignore` — `.vibe/*.lock`、`.vibe/sequences.jsonl*`
- `docs/decisions/_review-instinct-loop-phase-b-brief.md` — 评审 brief
- `docs/decisions/_review-instinct-loop-phase-b-merged.md` — 本文（merged verdict）

## Review sessions

- kimi: `session_20ed1e4a-bf3e-4321-be58-cc8d8df21afe` (resumable via `kimi -r`)
- pi: 通过 `pi -p` 一次性评审（无 session id）
