# Review Brief — Instinct-Learning Loop（v1 plan + 对抗评审）

**Date:** 2026-07-23
**Plan under review:** `/Users/huchen/.claude/plans/starry-herding-stream.md`
**Adversarial review:** 已完成（FIX BEFORE EXECUTE 总判定，8 个 CONFIRMED FLAW）

## 1. 任务背景

VibeSOP 项目里 instinct 学习链路当前**只在 session-end 一次性触发**：
PostToolUse hook → `.vibe/sequences.jsonl` → session-end 跑 `vibe sequence assemble` →
候选要靠人手 `/learn-eval` 才升级。

要接通三个空缺：**积累 → 提升 → 反馈**，作为 launchd 定时任务跑。
所有 loop 都是本地文件操作，不调 LLM。

用户已拍板：
- 范围：全套闭环（assemble + promote + feedback）
- 调度器：launchd（macOS）
- 执行入口：扩展 `LoopSpec` 加 `command_args` target 类型
- 频率：assemble 15min、promote daily 04:17、feedback hourly :23
- promote 语义：直接进 `.vibe/instincts.jsonl`（带熔断器）
- feedback 语义：双向（衰减 + 增强）

## 2. 关键代码事实（已核实）

| 位置 | 事实 |
|------|------|
| `src/vibesop/core/loop/models.py:138` | `LoopSpec` 用 `ConfigDict(extra="forbid")`，line 237 `_exactly_one_target` 校验三选一 |
| `src/vibesop/core/loop/executor.py:176` | `execute_loop_tick(spec, runtime, store=None)` — store 可选，state 内部加载 |
| `src/vibesop/core/loop/executor.py:85-94` | `LoopRunner` Protocol 只有 `handle_query` — Core->Agent 反向依赖的修复点 |
| `src/vibesop/core/instinct/learner.py:160-167` | `InstinctLearner._lock = threading.RLock()` — **进程锁，非文件锁** |
| `src/vibesop/core/instinct/learner.py:204` | `set_instinct` 不调 `_save()`，只改内存；`record_outcome` (line 267) 每次都 `_save()` |
| `src/vibesop/core/instinct/learner.py:196-198` | `instincts` property 返回 dict 拷贝（公开 API） |
| `src/vibesop/core/instinct/learner.py:117` | `SequencePattern.is_candidate` 已要求 `total_count>=5` |
| `src/vibesop/core/skills/miss_counter.py:138-143` | `clear()` **删整个数据文件**（保留 salt） |
| `src/vibesop/core/skills/miss_counter.py:170` | salt 创建 mode 0o600 |
| `src/vibesop/cli/commands/loop_cmd.py:81-134` | per-loop advisory lock 只保护 `state.json`，不保护 instincts.jsonl |
| `src/vibesop/cli/commands/loop_cmd.py:171-173` | `not any([skill_id, query, workflow])` guard 未含 command |
| `src/vibesop/cli/commands/instinct_cmd.py:101-163` | 现有 `eval` 走 `SkillSuggestionCollector` 写 `.vibe/instincts/skill_candidates.jsonl`（与 auto-promote 不同文件） |
| `src/vibesop/hooks/templates/pre-session-end.sh.j2:39` | session-end 会调 `vibe instinct eval` |

## 3. 对抗评审摘要（全文见会话上下文）

总判定：**FIX BEFORE EXECUTE**。

8 个 CONFIRMED FLAW：

**A. 并发**：`.vibe/instincts.jsonl` 和 `.vibe/sequences.jsonl` 跨进程无文件锁（launchd tick + 交互 session + session-end hook 三方写）；threading.RLock 只保护进程内。建议加 `fcntl.flock`。

**B. 状态机**：plan 的 `_run_command_target(spec, store, state)` 签名错（实际签名 `execute_loop_tick(spec, runtime, store=None)`，state 内部加载）；绕开 `state.record_run`，DEAD/FAILING 转换失效；`_classify_failure` 关键词针对路由错误，对 subprocess stderr 形状不适配。

**C. Growth cap off-by-one**：`promoted > before * 0.2 + 1` — before=0 时只允 1 次，before=100 时允 21 次（应是 20）；用了 private `learner._instincts`（应该用 public `learner.instincts`）；check 在 `set_instinct` 之后。

**D. Feedback 信号擦除**：`miss.clear()` 每小时清空整个 miss_counter.json，feedback 路径第一次后就废；建议改成 watermark 或减量。Boost 启发式 `success_rate>=0.8 且 total_applications<=2` 触发一次后 total_applications=3 自限。

**E. launchd plist 缺陷**：
- `cd {project_root}` 无 `shlex.quote`，spaces in path（macOS 常见）直接挂
- `StartInterval` sleep 时不补跑 — 笔记本实际频率远低于设定
- cron→launchd 转换对 `0 0 * * 1-5` 这种带 weekday 的有 cron Sunday=0 vs launchd Sunday=1 陷阱
- 用了 deprecated 的 `launchctl load`（应 `launchctl bootstrap gui/$(id -u)`）
- `StandardOutPath` 无 rotation

**F. `MissCounter.hash_for` 隐私**：扩大 API surface；盐若被 commit 则跨用户哈希可对照。

**G. 测试缺 7 个关键 case**：path-with-spaces、shell-injection（`--command 'foo; rm -rf /'`）、growth-cap 边界、DEAD 转换、跨进程写竞态、`zsh -n` 语法校验、watermark 重置。

**H. 架构味道**：`LoopSpec` 变成路由 OR shell 双职责的 sum type；`subprocess` 进 core/loop/executor.py 破坏 Core->Agent layering 修复；`auto-promote` 和 `eval` 对同一 SequencePattern 双重处理（不同文件，不同下游）。

**I. 运维风险**：无 `.vibe/instincts.jsonl.bak` rotation；feedback-collect 的 `record_outcome` 每次都 `_save()`，被 SIGTERM 杀会半持久化；DEAD loop 的 launchd 仍在跑；launchd 无 `TimeOut` key。

对抗 reviewer 建议的主要修订：
1. `_run_command_target` → 注入 `SubprocessLoopRunner` 满足 LoopRunner Protocol，subprocess 留在 CLI 层
2. Growth cap 检查移到 `set_instinct` 之前，用 `len(learner.instincts)`
3. `InstinctLearner._save` + `record_sequence` + `record_outcome` 加 fcntl.flock
4. plist 用 `shlex.quote`
5. `loop_cmd.py:171` guard 加 `command`
6. 不要 `miss.clear()`，用水位标或减量
7. 加 7 个测试
8. 文档：salt 不应 commit + StartInterval sleep 语义 + modern launchctl

## 4. 请 kimi/pi 评审的问题

请按 P1 评审格式（参考 `docs/decisions/_review-p2-pi.md` / `_review-p2-kimi.md`）回答：

### 4.1 对抗评审质量
- 8 个 CONFIRMED FLAW 里，哪些是**真问题**必须修？
- 哪些是**过度反应**或**误判**（例如对 layering 的担忧）？
- 对抗评审**漏掉**了什么结构性问题？（P1 经验：外部评审擅长抓 self-adversarial 漏的结构）

### 4.2 修订方向合理性
对抗 reviewer 建议：
1. `SubprocessLoopRunner` 走 LoopRunner Protocol（而非直调 subprocess）
2. `command_args` 改用 `CommandLoopSpec` 子类（而非平铺字段）
3. `feedback-collect` 不 clear，用水位标

请判断：
- 这些修订方向是否**矫枉过正**？例如：CommandLoopSpec 子类是不是过度抽象？
- 哪些修订是 must-fix，哪些是 nice-to-have？

### 4.3 三个最深的设计抉择

**Q1: LoopSpec 加 `command_args` 字段 vs 单独子类**
- 字段方案：现有互斥校验从 3-way 变 4-way，简单
- 子类方案：清洁的 sum type，但要改 Pydantic 模型加载/序列化、CLI 解析、store 加载
- 项目历史里 `MetricCondition` 是怎么加的？（参考 commit 553622d）同类先例？

**Q2: Subprocess 进 core 层 vs CLI 层**
- core 层：执行逻辑集中，但破坏 Core->Agent layering
- CLI 层：保 layering，但要发明 SubprocessLoopRunner + LoopRunner Protocol 改造
- 项目里 `core/prompt_chain/validator.py` 已经有 subprocess 先例 — 这是不是说明项目对 layering 没那么严格？

**Q3: 反馈信号是否应该这么积极**
- 每小时跑 feedback-collect 是否过于激进？
- 一天最多 +24 boost / 多次 decay，对 confidence 漂移影响多大？
- 是否应该改 daily，或加"达到稳定后停止调整"的 early-stop？

### 4.4 验证矩阵（kimi/pi 都答）

| 修订项 | 你的判定（必须修 / 建议修 / 可不修 / 过度） | 理由 |
|--------|------|------|
| A 并发文件锁 | ? | |
| B 重构 _run_command_target 走 Protocol | ? | |
| C Growth cap 修 off-by-one + 用 public API | ? | |
| D 不用 miss.clear()，水位标 | ? | |
| E.1 plist shlex.quote | ? | |
| E.2 StartInterval sleep 警告 | ? | |
| E.3 modern launchctl | ? | |
| F hash_for 隐私文档 | ? | |
| G 7 个新测试 | ? | |
| H.1 CommandLoopSpec 子类 | ? | |
| H.2 SubprocessLoopRunner 注入 | ? | |
| H.3 eval vs auto-promote 去重 | ? | |
| I instincts.jsonl.bak rotation | ? | |

### 4.5 总判定

对抗 reviewer 给了 **FIX BEFORE EXECUTE**。你的判定是？
- SHIP AS-IS（plan 没问题，直接做）
- FIX BEFORE EXECUTE（同意对抗 reviewer）
- REWRITE PLAN（方向都要改）
- CONDITIONAL（修哪几项就放行）

## 5. 输出要求

- 用中文写
- 引用代码时带 `file:line`
- 不超过 1500 字
- 如果对抗 reviewer 漏判了某项（flaw 说错了），明确指出
- 如果发现新问题（对抗 reviewer 没列），加在最后
- 给最终 verdict 在开头
