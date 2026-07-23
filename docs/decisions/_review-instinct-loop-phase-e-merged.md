# Phase E merged verdict — presets + docs + ADR

**评审来源**：pi（kimi quota 仍 exhausted）

**范围**：`--preset` shortcut、`docs/loop-setup-guide.md` §3.3-3.5、`docs/adr/005-loop-command-target.md`

---

## P2（本轮修）

### P-P2-1 — Preset 错误信息暴露实现细节（pi A）

**问题**：`vibe loop create my-custom-loop --preset` 报"未知 preset 'my-custom-loop'"——把 name lookup 失败的实现细节直接抛给用户。用户直觉是"name 是 loop 名、--preset 是开关"，不应该要求 name 等于某个 preset key。

**修复**：`_resolve_preset` 区分两种情况：
- **名字看起来像 preset 拼错**（含 `instinct-` 或以 `-assemble/-promote/-feedback` 结尾）→ 报"未知 preset"并列出可选项。
- **名字明显是用户自定义**（其他情况）→ 报"'{name}' 不是预设名。请去掉 --preset 改用 --command，或换成预设名之一：..."。
- 新增 2 个回归测试覆盖两条路径。

### P-P2-2 — ADR-005 中"~50 sites"夸大（pi D）

**问题**：ADR 论证 flat field 优于 discriminated union 时引用"breaks every existing `spec.skill_id` access (~50 sites)"。实际 grep 只有 15 处（executor 11 + loop_cmd 4）。

**修复**：
- 把 ADR 里的"~50 sites"改为准确的"15 sites: ~11 in `executor.py`, ~4 in `loop_cmd.py`"。
- 同步修订"4-way xor 安全性"段落——pi 指出 `@model_validator(mode="after")` 在构造时触发，只有 `model_construct()` 能绕过（这是显式 API，不是漏洞）；`save_spec` 不重复验证但接受的 spec 必然已通过构造时验证；`load_spec` 会再次 validate，所以被篡改的磁盘 JSON 仍能被拦下。论证骨架不变，措辞更精确。

---

## Nit（本轮处理）

### P-Nit-1 — `--preset` + `--command` 同时给 → warning + exit 0（pi B）

**保持现状**。Pi 也认同：help text 已说明 preset 会自动填，读过文档的用户不会误传；复制粘贴遗留 `--command` 时 exit 0 更友好。warning 已经显式提示用户自己的 `--command` 被忽略。

### P-Nit-2 — `_LOOP_PRESETS` 硬编码（pi C）

**记入 ROADMAP**：`docs/ROADMAP.md` Backlog → Nice to Have 加一条 TODO，说明等第一个真实用户提需求时再做用户自定义 presets（`~/.vibe/loop-presets.yaml` merge system presets，约 20 行代码）。当前 YAGNI。

---

## 验证

```
273 passed, 1 skipped in 0.93s (Phase C+D+E CLI + core/loop)
ruff: 0 errors
basedpyright: 0 errors (4 pre-existing warnings about _Schedulable, 不在 Phase E 范围)
```

手测：
- 3 个 preset（assemble/promote/feedback）→ 正确 schedule + command_args ✓
- 拼错 preset（`instinct-asemble`）→ "未知 preset" + 列出可选项 ✓
- 自定义 name + `--preset`（`my-custom-loop`）→ "不是预设名，去掉 --preset" ✓
- `vibe loop install-launchd instinct-assemble --dry-run` → 生成 plist 含 `StartInterval=900` ✓

---

## Phase A-E 完成清单

| Phase | Scope | Commit |
|-------|-------|--------|
| A | LoopSpec.command_args + executor branch | `fdafbcb` |
| B | instinct learner file lock + decay_frequent/hash_for | `953df2b` |
| C | launchd plist generation + install/uninstall CLI | `b14c24c` |
| D | instinct auto-promote + feedback-collect CLI | `3be214d` |
| E | `--preset` shortcut + docs/loop-setup-guide §3.3-3.5 + ADR-005 | （本次） |

**总测试数**：273（Phase C+D+E 新增 ~50 tests）
**ADR-005**：记录"flat field 优于 discriminated union"的设计决策与 4-way xor validator 的安全边界。

**Defer 到后续迭代**（来自 Phase C P2 残留）：
- launchd `ProcessType`（Background / Adaptive）
- 日志轮转（out.log 无限增长）
- Tick throttling / coalescing
- `--command` deny-list（shlex + 4-way xor 已是双保险，pi A 没要求）
- dry-run 输出对称化（early-stop 也打印）

**待用户决策**：
- 24h 真机验证（用户要求 skip）
- `instinct-assemble` 等 preset 装到 launchd 后的实际命中率
