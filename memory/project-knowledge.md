# VibeSOP Project Knowledge

## Technical Pitfalls

### basedpyright 本地与 CI 同版本不同结果 — 判"净增"必须对基线差，不看绝对数 (2026-09-03 S66/S67)

**Issue**: 本地 `uv run basedpyright` 报 29-30 errors（含 confirmation.py 私有跨模块导入、dashboard Flask 路由被报 unused 等），而 CI Type Check 同一 commit 全绿。**版本相同**（本地=lock=CI 均 1.39.9），无参数调用方式也相同——不是版本漂移，是环境性结果分叉（平台/stub 解析差异未定位）。绝对数会误导：看到 30 errors 会以为 CI 要红。

**Solution**: 发布/提交前判类型检查净增，用 `git stash` 在 HEAD（或 origin/main）跑一遍记基线数，再对比工作树——只关心差值。同型佐证：新增 `_candidate_source_lookup` 私有函数被本地报 reportUnusedFunction（CI 不报），改公名 `candidate_source_lookup` 后回到基线持平。另外跨模块导入的符号不该用下划线私有名（私有名正是该规则只盯的目标）。

**Files**: `src/vibesop/cli/render.py`, `src/vibesop/cli/confirmation.py`（同型存量）

### session-end 三条「去读文件」命令只有一条能拿到路径 (2026-09-03 S62)

**Issue**: 路由失败后的 session-end 回退曾写成 `vibe route --slash "/session-end"`。`--slash` 只接受 `/vibe-*`，该命令 Exit(1)。改成 `vibe route "session-end"` 也不行：短查询旁路 + 守卫技能（无显式告别信号）→ `fallback-llm`、`skill_file` 空。

**Solution**: 用 `vibe skills info builtin/session-end`，它打印真实 `Source file`。不要猜 `skills/session-end/SKILL.md`。

**Files**: `_generation.py`, `kimi_cli.py`, `templates/claude-code/docs/session-lifecycle.md.j2`

### `vibe build pi` 会无条件覆盖仓库根 AGENTS.md (2026-09-03 S63)

**Issue**: 本仓根 `AGENTS.md` 是手维护的 Multi 平台索引。`PiCodingAgentAdapter.render_config` 总是用 `AGENTS.md.j2` 写 cwd `AGENTS.md`，会丢掉 do-not-guess 文案并改回 `.pi/skills/<matched-skill>`。CHANGELOG 已记过测试泄漏。

**Solution**: 刷新签入的 `.pi/` 生成物用外科补丁（对模板）。不要在本仓根对 pi 跑 `vibe build`。grok-build 默认输出 `.vibe/dist/`，不碰 `.grok/`，除非显式 `--output .grok`。

### 无人值守 `claude -p`：`--tools ""` 在 2.1.220 会直接报错；stdin 无权限模式会挂死 (2026-09-03)

**Issue**: 旧解法 `claude -p --tools ""` 现在报 `option '--tools' argument missing`。把 30KB prompt 喂 stdin 且不给权限模式时，进程零输出挂到超时（工具权限提示无人点）。

**Solution**: `claude -p --permission-mode dontAsk "<短 prompt 指向文件>"`，用 Python `subprocess.run(['claude','-p','--permission-mode','dontAsk', prompt])` 避开 PowerShell 把后续参数吞进 `--disallowedTools`。`kimi -p` 必须带 prompt 参数（stdin 不算）；不能和 `--auto`/`--yolo` 组合。

### 发现能看见的技能，注入器未必能加载 — match 必须 fail-closed (2026-09-03 S58)

**Issue**: Windows 上 `vibe route` 命中 `fuck-my-shit-mountain`（82%），agent 读不到 SKILL.md。不是路径分隔符。`SkillLoader.discover_all` rglob `*.md` 能看见 `.vibe/skills/cross-cutting/{id}.skill/SKILL.md`，候选 id 是 frontmatter 裸 id；`SkillInjector` 只猜 `{base}/{id}/SKILL.md`，且 `**/{leaf}.skill` glob 曾被挡在 `if "/" in skill_id`。Hook 已写 `VibeSOP routed` + `[ACTIVE SKILL]`。GBK SKILL.md 的 `UnicodeDecodeError` 不是 `OSError`，会被 `handle_query` 裸 except 吞掉并留下 skill_id。`has_content` 曾嗅探用户文案 `"no injectable content"`，改 notice 就静默失效。

**Solution**: 不变量是 **match ⇔ 可注入 SKILL.md 正文**，闸在 inject 时刻而不是「两套路径学碰巧对齐」。① 候选 `source_file` 缺失/不可读则不可路由。② 注入对所有 id glob `**/{leaf}.skill/SKILL.md`，`candidate_dirs` 必须是发现根的超集（含 `project/skills`、`~/.kimi/skills`、`~/.config/opencode/skills`）。③ `_load_skill_content` 捕获 `(OSError, UnicodeError)`。④ `InjectionResult.content_missing` 标志，不靠 notice 文案。⑤ 空内容 demote 为 no-match；unsafe 走 `notice_only` 信封，禁止 wrap MUST follow。删跟踪包还要清 `.vibe/skill-index.json` 与 `skill-routing.yaml`，否则语义索引仍会召回幽灵 id。

**Files**: `skill_injector.py`, `agent_runtime.py`, `candidate_manager.py`

### 绿灯假象：子代理汇报的测试通过数必须核对覆盖范围 (2026-08-30 S54)

**Issue**: instinct 合并后执行方汇报 "834 passed"，但 claude+grok 双路终审独立发现 `tests/core/matching/test_strategies.py` 的排除集钉死测试必红——834 的覆盖范围（benchmark/integration/skills/hooks/routing）恰好不含 `tests/core/matching`。对抗验证员另发现执行顺序问题：基线重生成后又改了 SKILL.md，最终状态下 `--check` 实际 exit 3 STALE。

**Solution**: 验收子代理工作时，（a）测试数字必须附目录/标记口径并与改动面交叉比对——改动 `src/vibesop/core/matching/` 就必须看到 matching 目录的结果；（b）有指纹/基线类门禁时，最后跑一次 `--check` 确认的是**最终**工作区状态；（c）双路外部评审（claude+grok）对这种"覆盖范围错位"检出率很高，值得作为重交付的固定收尾。

### 改任何 SKILL.md 必须重刷路由基线 — 两个 commit 漏刷导致 HEAD STALE (2026-08-30 S54)

**Issue**: `tests/benchmark/routing_baseline.json` 的 fingerprint 覆盖 registry/dataset/**每个 SKILL.md 的内容哈希**。两个只改技能文档的 commit 没刷基线，HEAD 处于 STALE；后续合并重生成时才发现夹带了历史欠账。

**Solution**: 流程纪律：凡 diff 触及 `core/skills/**/SKILL.md` 或 `core/registry.yaml`，commit 前跑 `uv run python scripts/eval_routing.py --hermetic --update-baseline`（--check exit 0 才算完）。另注意执行顺序：先改完全部技能文件，最后一次性刷基线。

### 删除内置技能的完整影响面 = 仓库 + 本机安装残留 (2026-08-30 S54)

**Issue**: 删 `core/skills/instinct-learning/` 后 `vibe skills list` 仍列出它——来源是四处本机残留：中央库 `~/.config/skills/<name>`、平台部署副本（`~/.claude/skills/builtin-<name>` 注意命名空间扁平前缀、`~/.grok/skills/`、`~/.config/opencode/skills/`）、全局语义索引 `~/.vibe/skill-index.json` 的条目。`list_skills()` 合并中央库 + 各平台目录（Windows 无 symlink 权限时是带 `.vibe-copy-source` 标记的实体拷贝）。

**Solution**: 删内置技能清单：仓库侧（目录/registry/routing_eval/baseline/交叉引用/文档）+ 本机侧（中央库目录、所有 PLATFORM_SKILLS_DIRS 副本——注意 `builtin-` 前缀变体、索引条目剔除）。`vibe skills index` 重建需 LLM provider，无 key 时只能手动剔条目（先备份）。

### `claude -p` 大 prompt 无声挂死 — 挂点不是 prompt 大小而是工具权限阻断；`--tools ""` 立解 (2026-08-30)

**Issue**: 用 `claude -p --output-format text < prompt.md`（stdin 传入 13KB+ 评审 prompt）做外部复审时，进程零输出挂死直到超时（20–30 分钟，5 路并行与单路串行同现）；同 CLI 小 prompt 秒回。Git Bash 下 `$(<file)` 传参另有 `Argument list too long`（~54KB 即触发），须走 stdin。

**Root Cause** [executed，对照实验]：挂点不是 prompt 大小也不是限流（429 会显式报错退出）——`-p` 模式默认挂全套工具，模型一旦决定调工具（评审 diff 时几乎必然想去 Read/Grep 仓库）就撞上无人值守的权限提示，永久阻塞。加 `--tools ""` 禁掉全部工具后同一 prompt 正常出评审。

**Solution**: 无人值守调 `claude -p` 做纯文本评审/咨询时，永远带 `--tools ""`；大 prompt 走 stdin 重定向而非命令行参数；并发 >2 路会撞账号 429（`API Error: Request rejected (429)`），失败重跑即可。

### vibe 工具链会在会话中静默再生成 AGENTS.md — 评审/提交前必须 `git status` 复查 (2026-08-30)

**Issue**: 会话期间 AGENTS.md 被反复改写（`Platform: Multi` → `Pi Coding Agent` 整体再生成、Generated 日期清空、丢末尾换行），mtime 与子代理跑 `vibe`/`uv run` 的时间重合；`git status` 显示 ` M AGENTS.md`，与手头任务完全无关。

**Solution**: 这是项目自身 CLI 的再生成行为，不是编辑器改动。任何 diff 评审/commit 分组前把 AGENTS.md 列入显式排除清单，或 `git checkout -- AGENTS.md` 还原；多路并行子代理场景下它会被多次再生，收尾时再还原一次。

### 弱模型 agentic 实验三坑：截断即错误 / 思考循环 / 处理静默丢失 (2026-08-29, R6)

**Issue**: R6 弱模型 A/B（27B via oMLX）连续 3 次 treatment 尝试零产物死亡，表面全是"模型不行"，实为三个可修的基础设施问题。

**Root Causes & Solutions** [executed]:
1. **推理服务器把"超 max_tokens 截断"当错误上报**（error_kind=max_tokens_truncation）→ grok 按错误整体终止 rc=1。解法：max_completion_tokens 提到 32768。坑在"截断"与"错误"的语义合并——传统 API 截断只截不炸。
2. **弱模型单轮思考循环**：一次观测 45 分钟、11006 个 reasoning 事件、零工具调用，直到撞帽。解法：runner 加 `--reasoning-effort low --no-plan`（11006→15 事件）。事件计数 ≠ token 数，死亡判据要看 stderr 的 promptUsage。
3. **路由 LLM 静默丢失**：factory ollama 分支不透传 config model → 回退硬编码默认名 → 服务器上不存在 → 52ms 404 → 无声降级无 LLM 模式。**A/B 表面一切正常，公平性已被破坏**。解法：OLLAMA_MODEL env 显式指定 + span 日志验证模型名与延迟。这是"有效性三验"存在的全部意义。
4. 附带：oMLX 内存守卫会中止超长上下文 prefill（8.1M 累计输入 tokens 处）；grok 会话取证时 events.jsonl **不存工具参数**，参数在 chat_history.jsonl 的 `tool_calls[].arguments`（JSON 字符串）。

### Claude Code hook command 的「安全形态」随宿主版本翻转 — 规范必须靠实机探针钉死 (2026-08-28)

**Issue**: 08-26/27 两轮修复钉死的规范形态（先 quoted POSIX、后 config-relative `hooks/<name>.sh`）在 Claude Code **自动升级到 2.1.220** 后全部失效，用户每条 prompt 报 `bash: hooks/vibesop-route.sh: No such file or directory`（127）。当时基于「宿主把非绝对 command path-join 到 `~/.claude\`」的修复前提，在新宿主上不存在了。

**Root Cause** [executed，4 形态对照探针,`claude -p` + `--settings` + 分文件落日志]：2.1.220 宿主 spawn hooks 改为 `bash -c <command>` 且 **工作目录 = 会话启动 CWD**。相对形态按 CWD 解析（全局/项目级 settings 都一样，`~/.claude` 里那份脚本从不执行）；老版本宿主行为在版本间无公告地变了。形态矩阵：相对 ❌ / 不带引号绝对（无空格）✅ / 带引号绝对 ✅ / `bash <posix-abs>` ✅（唯一新旧宿主双稳形态）。

**Solution**: ① 唯一跨版本稳形态 = `bash <posix-abs-path>`（不带引号）——生成器、rewrite、verify、e2e 断言四层统一到它（PR #115）。② **规范形态不能靠文档或上一轮修复的记忆，必须对用户实际版本做实机探针**；verify 的「Git-Bash-safe」绿灯语义要跟版本走。③ 验证 hook 修复必须在「外部 CWD」真实点火 `claude -p`，且探针脚本要分文件落日志才能区分哪份配置被执行——S51 的 verify（字符串形状检查）+ 可解析目录内 smoke 恰好盖不住这个盲区。④ 宿主自动升级 = 无公告的行为变更源；hook 类集成要有 canary（e2e 形态断言收紧后 Windows lane 红灯即是回归信号）。

**Files**: `adapters/claude_code.py` (`bash_hook_command`/`_rewrite_legacy_hook_entry`)、`cli/commands/verify.py` (`_vibesop_command_unsafe_reason`)、`.github/workflows/quickstart-e2e.yml` (shape assertion)、PR #115 (merged f6f32c6)

### CI Lint = `ruff check .` + `ruff format --check .` — 本地只跑 `ruff check src/ tests/` 是不同构验证 (2026-08-27)

**Issue**: push 后 CI Lint 两轮红。R1：修复文件只 lint 了 src 没 lint tests（UP017 `timezone.utc` 应为 `UTC` 别名）。R2：CI 还有第二条 `ruff format --check .`，本地惯例命令 `ruff check` 不覆盖 format 漂移——8 文件漂移（含块 0 存量 2 个，块 0 push 时 CI run 33052791115 实为 failure 被漏看）。

**Solution**: push 前本地验证必须与 CI 同构：`uv run ruff check . && uv run ruff format --check .`。push 后必须以 `gh run list`/`gh run view --json jobs` 核对每一轮结论——"已 push"不等于"CI 绿"（gate44 教训的 format 版）。

### 钉死绝对时间戳的测试是时间炸弹 — 相对 now 生成 fixture 时间 (2026-08-27)

**Issue**: `test_recall_cli` fixture 钉死 `2026-07-28T12:00Z`，recall 默认 `days=30` 窗口，2026-08-27 滑出 cutoff，2 个 with-matches 测试开始失败——写于 07-29、绿了一个月后无预警爆炸。

**Solution**: 时间窗内 fixture 一律 `now - timedelta` 相对生成；排查特征：本地隔离单测通过率与时刻相关、全量套件时好时坏。

### `ExternalSkillLoader.EXTERNAL_PATHS` is import-time-bound to real `Path.home()` — env HOME patch silently no-ops (2026-08-27)

**Issue**: 测试隔离 HOME 时 patch `os.environ["HOME"]` + `monkeypatch.setattr(Path, "home", ...)` 都不够——`EXTERNAL_PATHS` 是 ClassVar，import 时就用真 `Path.home()` 求值完毕。后果是测试**静默空转**成无 pack 重跑（fixture pack 根本没进池），双态测试假绿。gate46 R7 双态测试踩坑，靠"非空调转守卫"（断言 `superpowers/*`、`omx/*` 确实在 candidate pool 里）才暴露。

**Solution**: 隔离必须 patch 类变量本身：`monkeypatch.setattr(ExternalSkillLoader, "EXTERNAL_PATHS", [scratch/".claude"/"skills"])`。且任何依赖"fixture 数据在池里"的测试都应加非空调转守卫——隔离 bug 的失败模式是静默减配，不是显式报错。

**Files**: `tests/core/routing/test_demo_skills.py` (`_isolate_home` + `_router_with_packs` 守卫)

### `shlex.split(posix=False)` honors quotes but KEEPS them — token-shape intuitions fail (2026-08-27)

**Issue**: 解析 settings.json hook command 时，"引号会切成 3 token" 和 "shlex 会剥引号" 两个直觉全错。`posix=False` 认 `'`/`"`（含空格路径仍是 1 token）但**引号字符保留在 token 里**——win32 规范形态 `"C:/Users/First Last/.../x.sh"` 恰好 1 个带引号 token，basename 提取会带尾引号 miss 白名单。

**Solution**: 按失败方向选宽严。宽松口径（服务 verify）用 `split()` + `strip("'\"")` 过剥引号 + `.lower()`——fail-safe，只会多扫不会漏扫。严格口径（服务 rewrite）`shlex posix=False` + `unwrap_token` 只剥成对双引号，任何不确定返回 None = 不动用户配置。

### Hook-command 识别器与生成器口径不同构 = 全部评审 BLOCKER 的共同根源 (2026-08-27)

**Issue**: pull-20260827 修复 4 轮双路评审的每个 BLOCKER（win32 规范 1-token / 含空格用户名 / 平台门位置 / token 化假 basename）都是同一疾病：识别器（classify/parse/verify）与生成器出口（win32 引号 1-token、非 win32 `bash <posix>`）不同构。

**Solution**: 动 hook 命令解析时，生成器出口与识别器逐形态核对；win32 规范形态、含空格用户名、大写盘符变体是必测形态。宽松 classify 服务 verify（漏扫 = 绿灯掩盖），strict parse 服务 rewrite（误判 = 破坏用户配置）。共享模块 `utils/hook_commands.py` 是单一事实源。

### Wrapping `Git/bin/bash.exe` does not fix Claude Code Windows hooks (2026-08-26)

**Issue**: UserPromptSubmit 报 `bash: C:UsersHuChen.claudehooks/vibesop-route.sh: No such file`（反斜杠被吃）。`efcd0cf` 改成 `"C:/Program Files/Git/bin/bash.exe" "C:/.../x.sh"` 后**仍然 127**：`C:/Program: No such file`。

**Root Cause**: Claude Code 把 `command` 交给 Git Bash `bash -c`。宿主已经提供 bash。
1. 反斜杠：`bash C:\Users\...` → MSYS 当转义吃掉。
2. 包一层 `C:/Program Files/Git/bin/bash.exe`：`-c` 按空格拆词 → `C:/Program`。
3. 若宿主对 `.sh` 再 prepend `bash `，`bash bash script` → cannot execute binary file。
脚本本身 `bash /c/Users/.../x.sh` 能跑；settings.json 里的 command 字符串才是故障面。文件存在 / chmod 检查覆盖不到。

**Solution**: Windows 只写带引号 POSIX 路径：`"C:/Users/.../hooks/vibesop-route.sh"`。Unix 保持 `bash <posix>`。`vibe verify claude-code` 拒绝 `\` 和 `bash.exe` / `Program Files`。烟雾测试必须是 `bash -c <settings.json 里那一整段 command>` + stdin JSON，不是直接 `bash script.sh`。
**[2026-08-28 已证伪]**: quoted 形态只在当时宿主版本可跑;2.1.220 起唯一稳形态是无引号 `bash <posix-abs>`,见上方 08-28 条目。本条的反斜杠/bash.exe 包装分析仍有效。

### Route hook defaulted to Microsoft Store `python3` despite `uv` (2026-08-26)

**Issue**: POSIX command 修好后 UserPromptSubmit 报
`Python was not found; ... Microsoft Store`。用户环境有 `uv` 和 `vibe.exe`。

**Root Cause**:
1. 模板默认 `_VIBESOP_PYTHON=python3`。Windows 上这是 `WindowsApps` 占位符。
2. uv-tool 回退只查 Unix 布局 `$HOME/.local/share/uv/tools/vibesop/bin/python`。
   Windows 实际是 `%APPDATA%\uv\tools\vibesop\Scripts\python.exe`（`uv tool dir`）。
3. 无 vibesop 项目根时 `uv run python` 会在随机 cwd 拉临时环境，可能卡住。

**Solution**: 先 `uv run`（仅当找到 vibesop 项目根），再扫 `uv tool dir` /
XDG / `%APPDATA%` 的 `bin/python` 与 `Scripts/python.exe`，跳过
`WindowsApps`。都没有则 `echo '{}'` fail-open，绝不调商店 stub。
烟雾：从 `/tmp` 跑已部署的 `vibesop-route.sh`。

**Files**: `adapters/templates/shared/vibesop-route.sh.j2`

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

### 实验复盘类科普文的叙事模式：「借口排雷记」+ 选题直觉先行 (2026-09-03 S68)

**Context**: skill-routing-explained.md 两轮用户复审反馈：v1「深度/专业度不够」；v2「中段实验叙事太干，读者容易绕丢/划走」。定位澄清：文章是思考分享，不是项目推广。

**Pattern**:
1. 每轮实验先交代「怎么选的题、为什么当时觉得技能该赢」——三条选题直觉明说，并预告它们会被逐个教育；
2. 「借口排雷记」主线：每轮结局出来 → 顺手给「技能为什么没显灵」找个借口 → 下一轮专门冲着这个借口去。读者全程只需跟一条线；
3. 拟人化配角承担 dry 事实：监考老师发小抄（路由）/ 开考前封卷（预注册）/ 考完验药（有效性三验）/ 差点开香槟→收回冰箱（R6 翻面）；
4. 旅程图（R1→R6 借口链 mermaid）代替结果总表给全景，数据只进叙事正文；
5. 每节结尾留钩子，把读者推进下一节的中心论点（「技能是 spec 的泛化」）。

**How to apply**: 下次写 R8 / 三臂设计等实验复盘直接复用此结构；技术报告体（总表+要点罗列）最多做附录，不做正文。

### Spawn-`vibe` hooks inherit PATH the hard way (2026-08-26)

Bash hook templates already prepend `$HOME/.local/bin`. Any **new** hook that is not bash (Grok JSON `command`, Pi/OpenCode `execSync("vibe ...")`) does **not** get that prefix. Lift the lesson: either bake an absolute `vibe` path at render time, or `vibe verify` must check `shutil.which("vibe")`, plus a stdin hook smoke on the real host. Docker e2e having `vibe` on PATH is not this check.

### Smoke the host's exact hook argv, not a cousin invocation (2026-08-26)

Adapter 写出 `command` 之后，用**宿主会用的那一种 spawn** 复现：Claude Code = Git Bash `bash -c <command 字符串>`。`bash script.sh`、PowerShell 直接跑、或包一层自发现的 `bash.exe`，都可能绿而宿主红。verify 要读 settings.json 的 command 文本（禁 `\`、禁 `Program Files/Git/bin/bash.exe`），不要只查 hook 文件在不在。Python 发现要在**无 vibesop 项目根**的 cwd（`/tmp`）再跑一遍，否则 `uv run` 从仓库里绿、宿主目录红。

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

### Platform Registry Drift + Host-Native False Positives (2026-08-26)

**Issue**: Grok quickstart/build looked installed but hooks could not run. Same class hits other platforms.

**Root Cause** (not "forgot grok"):
1. Platform identity is copied into 6+ registries (`SUPPORTED_PLATFORMS`, installer, renderer, `HOOK_DEFINITIONS`, `verify.PLATFORM_CONFIGS`, CLI help). They drift; tests assert `len >= 2` not set-equality.
2. `_is_configured` is "any of these filenames exist" — host-native `config.toml` (Kimi, Grok) and `settings.json` (Pi) count as VibeSOP. Stock install → skip deploy.
3. Docker e2e is Linux + `vibe` on PATH + empty tmp dirs. It cannot see Windows PATH, Git-Bash vs JSON-hook, or a real `~/.kimi-code/config.toml`.
4. Shell hooks already prepend `$HOME/.local/bin` (Unix). Grok/Pi/OpenCode-plugin call bare `vibe` and inherited none of that lesson.

**Invariant to test**: `installer == renderer == verify == HOOK_DEFINITIONS == SUPPORTED_PLATFORMS`. `_is_configured(platform)` must require a VibeSOP marker, not the host's own config file. One smoke: `vibe build X -o <tmpdir>` then `shutil.which("vibe")` + hook subprocess.

**Files**: `installer.py`, `verify.py`, `hooks/points.py`, `builder/renderer.py`, `adapters/grok_build.py`

### Docker e2e Green ≠ Windows Quickstart (2026-08-26)

**Issue**: Project claimed container e2e coverage, but `vibe quickstart` on Windows (1) had no grok-build option, (2) dumped ruamel ScannerError tracebacks for datayes `agents/openai.yaml`, (3) printed "No hooks available" after a successful install, (4) WARNING-logged missing `sentence-transformers`.

**Root Cause**:
1. Quickstart hardcoded 4 platforms while installer/adapters already had grok-build.
2. SkillLoader `rglob("*.yaml")` treated nested pack agent YAML as skills; `logger.warning(..., exc_info=True)` dumped through logging lastResort.
3. Wizard called `installer.install()` twice; second hit `_is_configured` (which also didn't recognize grok `rules/routing.md`) and reported empty hooks.
4. Optional `semantic` extra's ImportError was logged at WARNING.

**Solution**: Derive wizard platforms from installer; skip `agents/` YAML + YAMLError at debug; report hooks from the first install (including adapter JSON files); ImportError → debug.

**Files**: `quickstart_runner.py`, `quickstart.py`, `installer.py`, `loader.py`, `indexer.py`

### Dogfood Checklist: Reinstall CLI + Rebuild Platform Hooks

After shipping vibe features that change CLI surface or hooks: (1) `uv tool install --reinstall --force .` from vibesop-py; (2) `vibe build claude-code -o <project>/.claude` and `vibe build grok-build -o <project>/.grok` (+ user homes if used); (3) restart agents; (4) verify in dogfood project (`cmspark`) with `vibe instinct stats/pending`. Version string may still lag pyproject until `uv tool install --reinstall --force --no-cache .` — trust command surface, not the banner.