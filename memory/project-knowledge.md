# VibeSOP Project Knowledge

## Technical Pitfalls

### Run-level CI success swallows job-level failures under `continue-on-error` (2026-08-25)

gate44 转正计数踩坑：run 32798482327（commit 3325200）run 级 conclusion=success，但
`gh run view --json jobs` 显示 Windows 双 job 实为 failure——被 `continue-on-error: true`
吞掉。任何"连续 N 绿"计数、或观察期内判断 job 健康时，**必须查 job 级结论**：
`gh run view <id> --json jobs --jq '.jobs[] | "\(.name): \(.conclusion)"'`。
转正后（required gate）run 级才恢复可信。

### auto-config.yaml `routing.patterns` 是无消费者死配置；路由真实输入 = skill-index.json (2026-08-25)

追踪 cmspark 347 次调用时发现：understander `_generate_routing_patterns` 生成的
`.*reviewer.*` / `.*prompt.*` 等无锚正则写入 auto-config.yaml 后，**全 routing/matching
链路零消费者**（无任何 `["patterns"]` 访问；priority 也被 candidate_manager 硬编码
P0/P2）。auto-config 真正被消费的字段只有 enabled/scope/lifecycle/usage_stats。
路由层真实输入是 skill-index.json 的 query_patterns/confidence_boosters
（`routing/_layers.py`）。教训：判断某配置字段是否生效，先 grep 消费点再下结论；
同理 skill_id slug 派生自 `queries[0]`（`custom/{_slugify(queries[0])}-{cluster_id[:8]}`），
代表 query 是回声时 id 直接是回声文本。

### route_outcomes.jsonl 的 recorded_at 不能判"新增行"——用 span_ts > cutover (2026-08-25)

cmspark outcomes 文件里有两类 recorded_at 很新但 span_ts 是历史的批簇：rebuild
`--apply` 重写行（recorded_at = rebuild 时刻）、bridge 存量补录行（2026-08-25T00:48Z
一次性 2092 行，state 重置/丢失后按 span_id 去重补推导）。gate42/43 的 T+24h / 一周
检查若用 recorded_at 过滤会把存量行当新增行，验收数字完全失真。**新增行判定 =
span_ts > rebuild cutover**（本仓 cmspark cutover = 2026-08-24T09:31Z）。

### Local-Green ≠ CI-Green — macOS 开发的三类验证盲区 (2026-08-24)

**Issue**: main CI 自 gate37 起红了一个多月（7 个 gate 的 push 全部 failure），无人发现——本地 macOS 全量 pytest + orbstack e2e 的验证组合全绿，但 CI 上 Linux/Windows 三处全崩。

**Root Cause**: 本地验证掩盖三类平台差异：① **Linux 平台语义**——launchd 测试 mock 了 `_is_macos` 平台门却没 mock `shutil.which("uv")`，CI runner 的 uv 在 `/opt/hostedtoolcache`（P1-5 白名单外）必炸；② **无 tty 环境**——CI runner 无 `COLUMNS`，Rich 按 80 列折行把断言短语从中截断（`never\nsynced`）；③ **工具版本漂移**——uv.lock 升级 ruff 0.15.21 后折行风格变化，`ruff format --check` 在 HEAD 即 74 文件红。

**Solution**: 测试要 hermetic 到宿主二进制解析层（fixture 统一 mock `shutil.which`，逐测试 patch 覆盖生效）；Rich 输出断言一律空白归一化（`" ".join(output.split())`）；**流程补一条：push 后 `gh run watch` 盯 CI 变绿才算 gate 收尾**。

### Absolute-µs Microbenchmark Budgets False-Alarm on Shared CI Runners (2026-08-24)

**Issue**: `test_span_emit_overhead` 的 p95 <100µs 验收在 GitHub 共享 runner 上三连挂（131/162/163µs），`--reruns 2` 救不了——本地隔离 3 连绿，代码零变化。

**Root Cause**: 共享 runner 是系统性慢（CPU steal + 噪声邻居），不是瞬时毛刺；重试只能吸收毛刺，吸收不了"这台机器就是慢 30-60%"。绝对时间预算本质依赖测量环境。

**Solution**: 环境分级预算——`budget = 500µs if os.environ.get("CI") else 100µs`（docstring 记录实测依据）。CI 上仍抓 sync fsync/O(n²) 级灾难回归（5× 裕量），本地保留严格告警。不要为通过率直接抬全局阈值——那会同时杀死本地的回归灵敏度。

### Content-Derived Identity Hash Drifts with Membership Growth — Upsert Needs Overlap-Merge (2026-08-22)

**Issue**: 候选池（`ClusterCandidateStore`）出现同一模式的重复行——cmspark 真实池 27 条 pending 里 8 对重复（61 任务行 vs 63 任务行同内容）。

**Root Cause**: `cluster_id` = 排序后 (project_id, task_id) 复合键集合的 sha1。簇吸收新 task（miss 持续累积是常态）→ sha1 变化 → upsert 的 exact-match 判为新候选 → 追加重复行。**任何"身份 = 成员集合哈希"的设计都有这个病**：成员变，身份漂。discovery.py 早年为 dismiss 粘性列表发明 fingerprint 时已记录同款漂移，但 store 层 upsert 没跟上。

**Solution**: upsert 匹配集 = exact-id 行 ∪ 同类（is_unstable）Jaccard 严格 > 0.5 的 pending 行，整集 absorb-merge；保留最早 created_at/ttl/first_seen_at；project_distribution 求和并集。阈值用真实池标定（真重复对 0.88–0.99 vs 假重复 ≤0.41，双侧留距）；严格 `>` 使两个 3 任务簇共享 2 泛化 task（恰 0.5）不误并。

**Test fixture 连锁坑**：改了身份语义后，测试 fixture 里共享常量 `task_ids=["t1"]` 的 helper 会让所有 fixture 候选互吸成一行——改为从 cluster_id 派生。3 个测试文件中招。

**Files**: `src/vibesop/core/observability/skill_promote.py`（`_do_locked_upsert`、`MERGE_JACCARD_THRESHOLD`）

### Guard Width Must Match Mutation Width — Best-Match Guard vs Absorb-All Write (2026-08-22)

**Issue**: gate30 双路复审两轮抓到的同型洞：守卫只查"最佳重叠行"（或排除某类行），而写路径吸收"全部匹配行"——miss 证据经合并路径绕路销毁 gold 行（pi M1）；守卫排除 unstable 行后，exact-id 路径仍能整行替换 unstable 诊断行（pi BLOCK-1 / claude MAJOR-1，两路独立复现收敛到同洞）。

**Root Cause**: 守卫和写路径是分开演化的，没人维护"守卫的阻断集 ⊇ 写路径的破坏集"这个不变量。

**Solution**: 写路径的吸收集怎么定，守卫就查同一个全集（`find_all_overlapping_pending`）；例外规则（如"unstable 不算更强证据"）要写路径和守卫同步论证——exact-id 同簇 ⟹ 同成员 ⟹ J=1.0 这种恒等式可以把例外收窄到唯一可达分支。修在守卫侧还是写侧要看副作用：写侧加类条件会引入同 id 双行并存/`get()` 歧义，守卫侧干净。

### YAML Skill Loader Picks Up Non-Skill Files — `rglob` Is Too Greedy (2026-07-21)

**Issue**: `vibe` 命令运行时崩溃：`Unexpected error loading YAML skill /Users/huchen/.config/skills/omx/.github/dependabot.yml: version should be a valid string (got int 2)`。

**Root Cause**: `SkillLoader.discover_all()` 用 `rglob("*.yml")` 扫描所有 YAML 文件，包括 `.github/dependabot.yml`、CI configs 等非 skill 文件。`_load_yaml_skill()` 没有 pre-filter——只要 YAML 是 dict 就尝试解析为 `SkillSpec`，Dependabot 的 `version: 2`（int）导致 Pydantic 验证失败。

**Solution**: 两处防御式修复
1. `_load_yaml_skill()` 添加 pre-filter：`"id" not in data and "name" not in data` → 直接跳过
2. `build_spec()` 的 `version` 字段加 `str()` 强制转换，即使有漏网的非 skill YAML 也不会崩溃

**Files**: `src/vibesop/core/skills/loader.py:359-361`, `src/vibesop/core/skills/parser.py:189`

### UTF-8 BOM Silently Breaks TOML Parsing — `encoding="utf-8"` Is Not Enough (2026-07-20)

**Issue**: `~/.vibe/config.toml` 开头有 UTF-8 BOM（`EF BB BF`），`tomllib.loads()` 报 `Invalid statement (at line 1, column 1)`，路由回退到默认配置，LLM provider 失效。

**Root Cause**: Python 的 `Path.write_text(content, encoding="utf-8")` 不写 BOM，但 Windows 编辑器（Notepad）、某些 PowerShell 重定向会自动加 BOM。`read_text_with_fallback()` 正确解码了 BOM 文件（`.decode("utf-8")` 保留 `\ufeff` 在字符串中），但 `tomllib` 不接受以 `\ufeff` 开头的文本。

**Solution**: 在 `load_toml_with_fallback()` 和 `read_text_with_fallback()` 中统一剥离 BOM：
```python
def _strip_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text
```
这是跨平台部署的经典坑——文件生成时走 `encoding="utf-8"`（无 BOM），但用户在任何 Windows 编辑器打开保存后就会引入 BOM。

**Files**: `src/vibesop/utils/encoding.py`

### `sys.stdin.isatty()` Is Unreliable on Windows with PTY — `NoConsoleScreenBufferError` (2026-07-20)

**Issue**: Grok Build 给 shell 进程分配了 PTY（`sys.stdin.isatty()` → `True`），但 `prompt_toolkit` 在 Windows 上需要真实控制台屏幕缓冲区（`Win32Output`），PTY 环境下抛 `NoConsoleScreenBufferError`，`vibe route` 的 `questionary.select()` 直接崩溃。

**Root Cause**: `_needs_confirmation()` 用 `sys.stdin.isatty()` 判断是否跳过交互提示，但 PTY（伪终端）也满足 `isatty()`。真正的检测应该是"能否创建 `Win32Output`"，而这只能在调用时才知道。

**Solution**: 用 `try/except Exception` 包裹所有 `questionary` 调用，异常时 fallback 到默认值：
```python
def _safe_questionary_select(message, choices, default="confirm"):
    try:
        return questionary.select(message, choices=choices).ask()
    except Exception:
        logger.warning("Interactive prompt unavailable (no console); auto-selecting %r.", default)
        return default
```
`NoConsoleScreenBufferError` 是 `prompt_toolkit` 内部实现细节的普通 `Exception` 子类，不能精确 `except`（跨版本可能变），所以用 broad catch。

**Files**: `src/vibesop/cli/confirmation.py`, `src/vibesop/cli/main.py`

### Routing Eval Baseline: CN Queries Miss Builtin Management Skills (2026-07-19)

See project-knowledge.md history for details.

### Analytics default-off surprises users
- `_analytics_enabled()` in `unified.py:840` returns `False` by default (opt-in). All `vibe route` calls silently skip `analytics.jsonl` writing unless `[analytics] enabled = true` is in config
- `vibe status` dashboard shows "No routing activity" / "Routing analytics not yet available" even though user has been routing — no error, no hint to enable
- `vibe init` now generates `config.toml` with `analytics.enabled = true`, but old projects (pre-config-template) have no config file → analytics silently disabled despite user expectation

### GitHub Actions pinned SHAs silently break when GC'd (2026-07-21)
- `softprops/action-gh-release@3bb12739...` stopped resolving — GitHub garbage-collected the commit
- `pypa/gh-action-pypi-publish@ec4db0b4...` also at risk
- **Fix**: use version tags (`@v2`, `@release/v1`) for non-security-critical actions; avoid pinned SHAs
- Only security-critical actions (publish, attestation) should pin SHAs; general-purpose actions (checkout, setup-uv) are safe with `@v4`

### Windows `Path.read_text()` encoding is locale-dependent, NOT UTF-8 (2026-07-21)
- Python's `Path.read_text()` defaults to `locale.getpreferredencoding()` — CP1252 on Windows
- Writing UTF-8 and reading without explicit encoding → UnicodeDecodeError on emoji/Chinese
- **Fix**: always use `target.read_text(encoding="utf-8")` in cross-platform tests and code
- `write_text(content, encoding="utf-8")` + `read_text(encoding="utf-8")` is the safe pair

### Windows `os.open(O_CREAT | O_EXCL)` lock files persist after close (2026-07-21)
- POSIX `fcntl.flock` auto-releases on fd close; Windows `O_EXCL` file stays on disk
- Blocking acquire with retry loop times out because stale lock file never gets deleted
- **Fix**: delete lock file after close (`os.fdopen` handle → close → `Path.unlink()`)
- Wrap in `_release_tick_lock()` helper that unlinks on Windows, no-op on POSIX

### Bootstrap→build gap on community skill packs
- `bootstrap.sh`/`bootstrap.ps1` suggest `vibe build` as next step, but `vibe build` only generates config — it does not trigger `vibe install --auto` for community packs (superpowers, omx, mattpocock)
- Only the deprecated `scripts/vibe-install` script called `_auto_install` after installation
- Fix: add `uv run vibe install --auto` to bootstrap scripts after `uv sync`

### Adversarial review workflow
- Adversarial agent (before execution) catches wrong fix approaches and missing items
- Kimi (external LLM) catches bugs parallel verifiers miss (e.g., Python list[-1] semantics, uncaught exception propagation)
- OrbStack e2e catches host-specific failures that pytest alone doesn't catch
- Each layer catches different error classes — three-layer review is the pattern

### Skill creation patterns
- Use `adversarial-optimization` skill as template for new workflow skills
- Keep SKILL.md lean: frontmatter → prerequisites → phases → anti-patterns
- Single-skill fallback from multi-intent routing is useful for validation

### Codebase-specific pitfalls
- `_shared.py` was 740 lines — split into `_content.py` (skill lifecycle) + `_generation.py` (config/doc output)
- GrokBuildAdapter CANNOT inherit HookBasedAdapter — fundamentally different hook mechanisms (JSON vs shell scripts)
- f-strings are simpler than Jinja2 for inline TOML generation (proportional simplicity)
- Python dicts are better than YAML files for internal routing rules (no I/O, no enum deserialization)

### Cross-process RMW: `list_all()` MUST run INSIDE `fcntl.flock`, not before (2026-07-28)

**Issue**: `ReflectionStore._locked_update_status` 在 Phase A 写出来后通过所有测试，但 Phase B 第一次让 dashboard 走写路径时立即被 grok+pi 同时抓到 P0 race。Race timeline（pre-fix）：

```
1. dashboard: list_all() reads N rows           ← no lock held
2. CLI:       flock → append row N+1 → funlock
3. dashboard: flock → rewrite with N rows       ← row N+1 LOST
4. dashboard: funlock
```

**Root Cause**: 直觉上 "append 走锁，update 走锁" 已经够了 — 但 update 是 read-modify-write，read 部分如果不在锁内，read 和 modify 之间穿插的 appender 会被随后的 rewrite 静默吃掉。AtomicWriter 的 tmp+rename 让这个 bug 更隐蔽：crash 不留痕迹，文件就是少一行。

**Solution**: 把 list_all 移到 flock 内（抽 `_do_locked_update` helper 整个 RMW 都在锁里）：
```python
with self._path.open("a") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    try:
        self._do_locked_update(...)  # list_all + mutate + AtomicWriter 全在里面
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

**Why hidden in Phase A**: Phase A 只有 CLI write path（append-only，没有跨 process 的 update），race window 存在但没人触发。Phase B 引入 dashboard PATCH 后 user-visible。

**Test pattern**: 用 monkeypatch instrument `fcntl.flock` + `list_all` 记录调用顺序，断言 list_all 的 index 在 LOCK_EX 和 LOCK_UN 之间。`tests/core/observability/test_reflection_store.py::test_update_status_list_all_runs_inside_cross_process_lock`。

**Known limitation**（defer Phase B+1）: AtomicWriter rename 换 inode — flock 锁的是旧 inode，rename 后新 inode 不受保护。Fix 是 sibling lock file（`reflections.jsonl.lock`），更大重构。

## Reusable Patterns

### Cross-process JSONL store pattern (append + atomic update) (2026-07-27)

任何需要跨进程并发安全读写的 JSONL 持久层（spans / reflections / 未来的 DAG 节点），用同一套 pattern：

1. **三层锁**（按开销递增）：
   - in-process `threading.Lock` 阻止同进程多线程 race
   - cross-process POSIX `fcntl.flock(LOCK_EX)` 阻止多进程 race
   - Windows 没有 `fcntl`，fallback 到 `vibesop.utils.file_lock.cross_process_lock`（dispatch 到 `msvcrt.locking`）
2. **append path**：`json.dumps(record) + "\n"` → 在锁内 `f.write(line)`；inline `fcntl` 而非走 helper（perf-critical 路径省一次 import lookup）
3. **update path**（read-modify-write 整个文件）：在 cross-process 锁内 `read → mutate one row → AtomicWriter.atomic_open(path, "w") 重写全文`；AtomicWriter 走 tmp + rename，crash 留旧文件而非 truncated mix
4. **append vs update 必须共用同一把 cross-process lock**，否则 appender 在 updater 重写中途穿插会丢
5. **list tolerates corruption**：`json.loads` 失败 / `Reflection.from_dict` 校验失败 → debug log + skip；dashboard 不应因为一行坏数据整个崩

参考实现：`src/vibesop/core/observability/span_writer.py` (SpanWriter._locked_append) + `src/vibesop/core/observability/reflection.py` (ReflectionStore.append / _locked_update_status)。

### Plan path 与 codebase 约定冲突时跟约定 (2026-07-27)

当 plan 文档写的目标路径与 codebase 已有目录约定冲突时，跟 codebase 约定（而非 plan 字面值）。例：plan 说 `src/vibesop/observability/reflection.py`（top-level），实际 observability 全在 `src/vibesop/core/observability/`（与 tracer/aggregator/span_writer/models 同居）— 选了后者避免分裂。在 commit message + PR 描述里明说 deviation 原因即可。

### 多路独立对抗评审的实证纪律 (2026-08-23, gate34-36)

- **三路评审抓到的 MAJOR 互不重叠**：同一设计稿，claude 抓到隐私边界+反馈环污染，pi 抓到 verdict 时效+口径 provenance，grok 抓到 PASS 分母与回声合法成员冲突。双路是下限；设计稿阶段三路值得。
- **裁决层修订必须回写执行层**：gate34 §6 修订后 §3 实施步骤未同步，claude round2 抓到"实施者按 §3 原文动工就会做出修订明确禁止的事"。设计文档收敛后，第一步是同步正文，不是发复审。
- **"过滤自动化，不过滤人审"**：形状谓词用于自动预填 OK，用于数据准入会掐死训练信号（bd1bc217——全系统唯一真实 promote 成功案例就来自 agent 回声簇）。准入层改动先算失败不对称性：FN=人审多看一眼，FP=永远学不到这个模式。
- **基线测量要落在痛点语料上，口径钉死**：cmspark 回声占比池子 3.0% vs 已入队卡片 42.9%——同一现象两个口径差 14 倍，"64% 回声"的旧注释就是池/卡口径混淆的产物。
- **引用他模块函数先确认适用域**：`explicit_guarded_skill_match` 是 guarded 技能专用（只认硬编码表内 id），被两路评审独立发现"照字面用会让 verifier 空转"。
- **复审运行期间不改被审文件**（gate33 教训复验）：评审撞上并发修复的中间态会误报 BLOCK。

### Plan → Adversarial → Execute → Verify
1. Write structured plan with exact diffs
2. Spawn adversarial `plan` agent to challenge the plan
3. Execute with `general-purpose` review agent watching
4. At milestones: Kimi code review + OrbStack container e2e
5. Commit atomically after verification

### Atomic refactoring rules
- Do the safe, isolated refactor first to validate test coverage
- Then tackle higher-blast-radius changes with confidence
- Always follow existing patterns (e.g., FileBasedAdapter.render_config pattern for ClaudeCodeAdapter)

### Auto-optimization design
- Don't build new classes when existing subsystems can be composed
- RoutingHealthAnalyzer + FeedbackLoop + SkillSuggestionCollector = full optimization pipeline
- CLI is the integration layer, not a new core module

## Architecture Decisions
- GrokBuildAdapter Liskov fix explicitly rejected — JSON hooks ≠ shell hooks
- understander.py → YAML deferred — data tables as Python dicts are simpler
- init_support.py → Jinja2 deferred — f-strings are better for inline template generation

## Product Positioning (2026-07-31 — vs LLM Space)

**Insight**: [deer-flow/llm-space](https://github.com/deer-flow/llm-space) productizes Agent harness Build–Trace–Debug–Eval (desktop IDE for threads/runs). It does **not** replace VibeSOP's SkillOS loop (route → remember → autonomous cron → write-back).

**One-liner**: VibeSOP is not an agent workbench — it is the skill OS that finds the right skill, remembers what worked, and keeps loops running when humans leave.

**Narrative**: Mastra/LLM Space show what the agent is doing; VibeSOP makes the agent remember what you did and runs L0 work off-loop.

**Absorb (UX only)**: run/task as first-class replay artifact; step-level cost; path vs DAG toggle; immutable history snapshots.  
**Do not absorb**: Thread/prompt editor, desktop harness shell, LangGraph export as product core.

Full write-up: `docs/decisions/2026-07-31-positioning-vs-llm-space.md`.

## Product Evolution — Adversarial Final (2026-07-31)

**Binding**: `docs/decisions/2026-07-31-product-evolution-adversarial.md`（4 路对抗终裁；覆盖 positioning 文的 Phase 排序）。

**Aha 北极星**: 「指出路由蠢 → 我 accept → 第二天更准 → 第三次回放上次。」

**完成度倒挂（工程事实）**: task-memory ~85% 已发货；METRIC 闭环 ~25% 断线；Dashboard Phase C UI ~10%。

**90 天 Spine**: Sprint1 黄金 aha（pending+accept+replay+outcome）→ Sprint2 Task 真相+Inbox 薄盘 → Sprint3 外部价值 loop+METRIC 接线 → Sprint4 memory 运营化（非重建）。

**禁**: route-auditor 当唯一默认 onboarding；Cytoscape 先于 DAG 质量；auto-write skill 热路径；观察军备当 P0。

### Levenshtein Last-Resort Inflates Confidence → Pending Never Fills (2026-07-31)

**Issue**: Sprint 1 `should_enqueue_from_route` only used `confidence < 0.5`. On cmspark, nonsense queries still matched via **LEVENSHTEIN with conf ≈ 0.9–1.0**, so routing_pending stayed empty and the aha path looked broken.

**Root Cause**: Distance-normalized last-resort matchers report high "confidence" that is not semantic trust. Conf threshold alone is the wrong gate for human review.

**Solution**: Also enqueue when primary layer ∈ `{levenshtein, custom, fallback_llm}` as `low_confidence`, with Chinese reason noting 虚高置信. Real low-conf (<0.5) and no_match unchanged.

**Files**: `src/vibesop/core/instinct/routing_pending.py`, `unified.py` `_maybe_enqueue_routing_pending`

### Dogfood Checklist: Reinstall CLI + Rebuild Platform Hooks

After shipping vibe features that change CLI surface or hooks: (1) `uv tool install --reinstall --force .` from vibesop-py; (2) `vibe build claude-code -o <project>/.claude` and `vibe build grok-build -o <project>/.grok` (+ user homes if used); (3) restart agents; (4) verify in dogfood project (`cmspark`) with `vibe instinct stats/pending`. Version string may still say 8.1.0 while code is newer — trust command surface, not the banner.