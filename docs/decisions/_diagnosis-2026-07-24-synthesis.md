# Deep Diagnosis 2026-07-24 — Synthesis

**来源**：4 个并行 agent（architecture / security / observability / instinct-loop）+ bandit + pip-audit + coverage

**自动扫描 baseline**：
- pytest: 4601 passed, 14 skipped (75.52% coverage, gate 73%)
- basedpyright: 0 errors, 4 pre-existing warnings
- ruff: 1 pre-existing ARG002 (context_mixin.py:128)
- pip-audit: 无 CVE ✓
- bandit: 13 High + 1 Medium + 45 Low

---

## P0（release-blocking — 立即修）

### P0-1 — `feedback-collect` hash 不匹配，decay 分支几乎永不命中（instinct agent）

`cli/commands/instinct_cmd.py:624` 调 `miss.hash_for(ins.pattern)` 用**原始 pattern**（可能大写、原样空白）。
但 `MissCounter.record()` (miss_counter.py:77) hash 的是 `query.split()` 折叠 + `.lower()` 后的串。
两路 hash 永远不一致 → feedback-collect 实际只跑 boost，decay 死代码。

**影响**：刚装到 launchd 的 `instinct-feedback` preset 04:37 跑了等于没跑，phase D 的核心闭环失效。

**修法**：`hash_for(" ".join(ins.pattern.split()).lower())`，或在 instinct 存储时记录原始 normalized pattern。

### P0-2 — `core/loop + instinct + observability` 全部新模块绕过 `vibesop.core.exceptions`（architecture agent）

新代码 ~17 处 `raise ValueError/RuntimeError`，CLI 无法据此区分"用户配错"和"内部 bug"。
涉及文件：loop/{store,models,executor,scheduler}.py、instinct/learner.py。

**修法**：换用 `VibeSOPError` 子类（`ConfigurationError` / `LoopSpecError` / `StorageError`）。

### P0-3 — `span_writer.py` Windows 分支完全无锁（architecture agent）

`fcntl` 不可用时退化到裸 `open("a") + write`，多进程并发会撕裂 JSONL 行。Phase B 的 instinct learner flock 也有同样问题。

**修法**：Windows 用 `msvcrt.locking` 或 `filelock` 库；至少 retry-on-IOError。

### P0-4 — `prompt_chain/validator.py:181` lima 分支 shell 拼接模式（security agent）

`cmd = f"export KEY={shlex.quote(...)} && {cmd}"` 当前硬编码，但模式易在后续扩展中引入注入。
**优先级争议**：目前不可利用，agent 标 P0 偏重。实际可降为 P1。

---

## P1（ship 前修）

### P1-1 — `launchd.py:83` Weekday 0=Sunday 与 launchd 不兼容（instinct agent）

launchd `StartCalendarInterval.Weekday` 接受 1=Monday..7=Sunday，不接受 0。
cron `0 0 * * 0`（每周日）会写出 `Weekday=[0]` → launchd 拒绝/忽略 → tick 永不触发。

**修法**：转换 `0 → 7`。

### P1-2 — `aggregator.py:374-378` tz-naive datetime 被 except 吞（observability agent）

`datetime.fromisoformat(started_at.replace("Z", "+00:00"))` 对 tz-naive 字符串返回 tz-naive datetime，
与 tz-aware cutoff 比较抛 TypeError → 被 except 吞 → 无条件 include。

**修法**：tz-naive 时 assume UTC 或显式拒绝。

### P1-3 — `aggregator.py:312-323` attribution last-writer-wins（observability agent）

同一 trace 多个 task-span（workflow 子任务）时后写的覆盖 root skill_id → 该 trace 下所有 llm/tool span 错关联。

**修法**：改 first-writer-wins，或要求 root span 显式标记。

### P1-4 — `loop/launchd.py:188 + loop_cmd.py:911` Path.cwd() 未校验（security agent）

`render_plist` 用 `Path.cwd()` 作为 launchd WorkingDirectory，未校验是否可信目录。
攻击者在恶意目录跑 install-launchd 会持久化该目录为 launchd job cwd。

**修法**：要求 `project_root` 是 git repo 根（含 `.git/`）或显式 `--trust-cwd`。

### P1-5 — `loop_cmd.py:898` shutil.which("uv") 无白名单（security agent）

PATH 含 `.` 或被劫持目录时，launchd 持久化恶意 `uv`。

**修法**：只接受 `/opt/homebrew/bin`、`/usr/local/bin`、`~/.local/bin` 白名单，否则警告 + 要求 `--trust-uv-path`。

### P1-6 — `loop/launchd.py:188` 硬编码 Path.home()/.vibe/loops/<name>（instinct agent）

`LoopStore` 可被 `base_dir` 覆盖，但 plist 日志路径写死默认目录 → 日志和实际状态分离。

**修法**：从 store 拿 loop_dir。

### P1-7 — `miss_counter.py:175` decay_frequent hashes=set() vs None 语义不一致（instinct agent）

`hashes=set()`（显式空集）时全部跳过 = 啥都不做；`hashes=None` 衰减全部。API 语义模糊。

**修法**：显式区分（None=全部，set()=空集 = no-op，与 set 非空 = 过滤）或文档明确。

### P1-8 — `preference.py:240-293` lockfile 错配（architecture agent）

EX 锁在 `.lock` 文件，SH 锁在数据文件本身——两把不同的锁，SH 读不阻塞 EX 写，TOCTOU 仍在。

**修法**：SH/EX 都锁 `.lock` 文件。

### P1-9 — `executor.py:264,294` 错误日志用 ' '.join(argv)（instinct agent）

args 含 unicode/换行时日志损坏。

**修法**：改 `shlex.join` 或 `repr(argv)`。

### P1-10 — `skills/workflow.py:724` eval sandbox（security agent）

`eval(code, {"__builtins__": safe_builtins}, eval_context)` 让 workflow 变量进入 eval 命名空间。
AST whitelist 是好的，但 `__class__.__bases__[0].__subclasses__()` 链可能逃逸。

**修法**：验证 AST 是否阻挡属性访问链；或改用 `ast.literal_eval` + 限制语法节点。

---

## P2（后续迭代）

- core/ 100 处 `except Exception` 滥用（swallow 失败语义）
- orchestration/ 上帝模块（workflow_engine 881 行 + 25 方法）
- core → installer / llm 反向依赖
- cost 浮点累加无 `math.fsum`
- measured token 与 cost 维度脱钩
- `trace replay` 一次性 load 全文件 → OOM 风险
- success_count 只算 "ok"，cancelled 算失败拉低 rate
- `_candidate_to_instinct` total=0 时 confidence=0.5 注入
- launchd StartInterval sleep 不补跑未警告
- bandit B701: 4 处 jinja2 autoescape=False
- bandit B324: 9 处 hashlib MD5/SHA1（多数是 non-security hash，加 `usedforsecurity=False`）
- coverage 盲区：marker_files.py 28%、external_tools.py 58%

---

## Phase 2 执行计划

按 skill workflow 每 fix 走 "implement → pi review（kimi 替代）→ host pytest → commit"。

**Batch 1（立即 — 阻塞 24h 观察）**：P0-1（feedback hash）、P1-1（launchd Weekday）、P1-7（decay hashes 语义）、P1-9（错误日志）

**Batch 2（高 ROI 安全）**：P1-4（cwd 校验）、P1-5（uv 白名单）、P1-2（tz datetime）、P1-6（loop_dir 解耦）

**Batch 3（架构）**：P0-2（exceptions 一致性）、P0-3（Windows 锁）、P1-8（preference lockfile）、P1-10（eval sandbox 验证）

**Defer 到后续**：P0-4（lima shell，目前不可利用）、P1-3（attribution，需要 schema 改动）、所有 P2
