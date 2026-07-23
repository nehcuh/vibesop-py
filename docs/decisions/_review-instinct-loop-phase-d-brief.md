# Phase D 评审 brief — instinct auto-promote + feedback-collect CLI

**范围**：把 Phase A-D 的能力串成可调度闭环（`vibe loop create --command` + launchd →
每日/每 N 分钟调用 `vibe instinct auto-promote` / `feedback-collect`，全自动学习 +
衰减、不依赖 LLM）。

**改动文件**：
- `src/vibesop/cli/commands/loop_cmd.py` — 新增 `--command / -c` flag（shlex 解析）
- `src/vibesop/cli/commands/instinct_cmd.py` — 新增 `auto-promote` + `feedback-collect`
- `tests/cli/test_loop_cmd.py` — +5 tests
- `tests/cli/test_instinct_cmd.py` — 新建 18 tests
- 99 tests 全绿，ruff/basedpyright clean

---

## 评审要点（请重点审查）

### 1. `vibe loop create --command` 接入

```python
command: str = typer.Option("", "--command", "-c",
    help="vibe 子命令（shlex 解析，如 'instinct auto-promote --min-confidence 0.85')"),
...
try:
    command_args = shlex.split(command) if command else []
except ValueError as e:
    console.print(f"[red]❌ --command 解析失败: {e}[/red]")
    raise typer.Exit(1) from e
```

**问题**：`shlex.split` 对未闭合引号会抛 `ValueError`，已捕获。但对恶意输入
（如 `'; rm -rf /'`）只做 split、不做语义校验——依赖 LoopSpec.command_args 的 4-way
xor 校验（skill_id / query / workflow_id / command_args 必须且只能设置一个）。
**请审查**：这是否足以？或是否需要 deny-list（拒绝含 `&&` `||` `;` 的 command）？

### 2. auto-promote 的 growth cap

```python
before = len(learner.instincts)
allowed = max(1, int(before * growth_cap_pct / 100))
# 默认 growth_cap_pct=20 → before=0 时 allowed=1，before=10 时 allowed=2
```

**问题**：当 instinct 库为空（before=0）时，allowed=1 仍然会促进一个候选。这是
"冷启动"必要兜底，但意味着如果用户首次运行 + 有 100 个合格候选，每次只促进 1 个，
需要 100 次运行才能全部提升。**请审查**：冷启动是否应单独有 `bootstrap_mode`
（首次允许 N 个）？

### 3. _candidate_to_instinct 直接构造 Instinct（绕过 learner.learn）

```python
def _candidate_to_instinct(learner, candidate, source):
    pattern = " → ".join(candidate.steps)
    return Instinct(
        id=learner._generate_id(pattern),  # 访问私有方法
        pattern=pattern,
        action=f"Consider this sequence as a repeatable workflow: {pattern}",
        ...
    )
```

**问题**：
1. 直接调用 `learner._generate_id(pattern)`（私有方法）——这是为了拿到确定性 id
   （同样 steps → 同样 id），保证重跑覆盖而非复制。是否应把 `_generate_id` 提为 public？
2. `action` 字段是写死的模板字符串。如果后续有人查看 instinct 库会看到一堆同模板
   的 action，可读性差。是否需要让用户自定义？

### 4. feedback-collect 改了迭代范围（plan bug fix）

原 plan §5e 写的是 `for ins in learner.get_reliable_instincts()`，但
reliable 要求 `total_applications >= 3`，而 boost 要求 `<= 2`——boost 分支永远
不可达。改为：

```python
all_instincts = sorted(
    learner.instincts.values(), key=lambda i: i.confidence, reverse=True
)
```

**问题**：现在 boost 会作用于所有 confidence 在 (0.1, 0.95) 区间、n≤2、
success_rate≥0.8 的 instinct——包括只有 1 次成功 0 次失败的"未成型"instinct。
这是否会把噪声也 boost 上去？或者我们其实应该删除 boost 分支（plan 矛盾说明它
没经过仔细考虑）？

### 5. watermark 容量与去重策略

```python
def _save_watermark(hashes: set[str]) -> None:
    path = _feedback_watermark_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = list(hashes)[-10000:]  # 无 timestamp，按插入顺序 FIFO 砍掉前半
    payload = {"processed_hashes": trimmed}
    path.write_text(json.dumps(payload), encoding="utf-8")
```

**问题**：
1. `list(hashes)` 顺序由 Python set 迭代顺序决定（哈希值相关，非确定）。
   FIFO 假设不成立——实际是"随机砍一半"。这是否可接受？或应改为 LRU（需要
   记录 last_seen 时间）？
2. 写入非原子（write_text 直接覆盖）——并发跑两个 feedback-collect 会丢数据。
   是否需要 atomic_write（temp + rename）？

### 6. decay 后立即 `miss.decay_frequent(min_miss_count)`

```python
if decayed:
    miss.decay_frequent(min_miss_count)  # 不 clear，减半（plan v2 §D）
```

**问题**：`decay_frequent` 把所有 frequent count 减半。但如果一次 decay 了
1 个 instinct，却有 10 个 frequent cluster，会把另外 9 个未关联 instinct 的
cluster 也减半——丢失 miss 信号。是否应该只 decay 跟被 decay 的 instinct
相关联的那些 hash？

### 7. dry-run 与非 dry-run 的副作用分离

```python
if dry_run:
    console.print(f"[dim]would decay:[/dim] {ins.pattern}")
else:
    learner.record_outcome(ins.id, success=False)
decayed += 1
processed_watermark.add(h)  # ← dry-run 也修改内存中的 watermark
```

**问题**：`processed_watermark.add(h)` 在 dry-run 时也执行，但因为
`if not dry_run: ... _save_watermark(...)` 包裹了 save，所以不会写盘。这只是
内存修改，无副作用。但语义混乱——是否应明确分两阶段（先决策，再执行）？

### 8. feedback-collect 的 dry-run 输出不对称

dry-run 模式下，decay 和 boost 都打印，但 early-stop 不打印（因为
`skipped_early_stop += 1` 后 continue，没有 dry-run print）。用户在 dry-run
时看不到哪些会被 skip。**请审查**：是否应统一？

### 9. `vibe loop create --command` 没有对应的 uninstall/test

`install-launchd` 子命令链路对 command 类型的 spec 没有专门的集成测试。
只测了 `--command` 解析和 `tick` 时的 executor 分支。**请审查**：是否需要补
一个 e2e test（create with --command → install-launchd --dry-run → 验证 plist
包含 command_args）？

### 10. 整体设计：Phase D 的"自动闭环"是否真的不需要 LLM？

plan 说"全自动学习 + 衰减、不依赖 LLM"。但 instinct 的 `pattern` 字段
（如 `plan → execute → verify`）是从 sequence 的 steps join 来的——这些 steps
本身就是用户手工标注或 LLM 在 session-end 时生成的。所以闭环只是"频率统计
+ Wilson score"，不引入新的 LLM 调用，但**底层数据仍然来自 LLM**。
**请审查**：plan 的描述是否会误导用户认为这是"无 LLM 的智能学习"？

---

## 已知 defer 项（Phase C P2 → Phase D/E 处理）

D-1: launchd plist 的 `ProcessType` 未设置（Background / Adaptive / Interactive）
D-2: 日志轮转未配置（out.log 会无限增长）
D-3: Throttling 未实现（coalescing 多次 tick）
D-4: `--command` 无 deny-list（见评审要点 1）
D-5: watermark 无 LRU（见评审要点 5）
D-6: decay_frequent 误伤（见评审要点 6）
D-7: dry-run 输出不对称（见评审要点 8）

请按 P1（blocker）/ P2（defer ok）/ Nit 分级。
