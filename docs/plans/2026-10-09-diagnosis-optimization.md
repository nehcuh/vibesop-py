# VibeSOP 深度诊断优化计划（2026-10-09）

- **Leader/裁决**：Kimi（预 commit APPROVE / REQUEST_CHANGES、收批、最终放行）
- **执行**：Grok、Claude Code（GLM-5.3）双泳道并行（Codex 按本计划调 CLI、跑机器验证、记录证据，不代替裁决）
- **基线**：`49901afe401a3f6fd25ba33c4854ce6329e1e44c`（HEAD，与远程 main 同）
- **输入**：`docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/REPORT.md` 终核 15 项（D01–D08 为 P1，D09–D15 为 P2）；RR06/PS06（FileTransactionalInstaller 回滚残留、WorkflowEngine squad 终态语义）为辅助债务，**不膨胀为 P1、不进批次**，仅在对应批次做 sibling 审计登记。
- **边界**：本轮只做优化开发；**不 merge、不 push 到 main、不部署、不发版**。终态交付 PR，发行/合并待用户明确授权。
- **分支/worktree**：实际分支 `codex/diagnosis-optimization`，唯一受控 worktree `/Users/huchen/.codex/worktrees/diagnosis-optimization/vibesop-py`；用户主目录改动不 stash、不切分支、不接管。

## 1. 总原则

1. 不动 `core/skills/**/SKILL.md`、`core/registry.yaml` → 不触发路由基线刷新义务（若意外触碰，必须 `uv run python scripts/eval_routing.py --hermetic --update-baseline` 并 `--check` exit 0）。
2. 不整体重写：每批只改 listed ownership 文件；sibling 审计产出登记在批次记录里，超出边界的另立项。
3. 不下调门禁：覆盖率闸 73%、basedpyright `--level error`、ruff、hermetic 基线、artifact-links 基线全部保持；新增测试只增约束。
4. 公开结果形状兼容：StepRunner 结果 dict 只增键不改旧键；overlay 读取保留 legacy 顶层键；`llm-config.json` 回归父类 `api_key_env` 约定（本就是他处已有合同）。
5. 每个修复用**真实 producer→公共 consumer** 反例验收（真实 CLI、真实 SpanWriter payload、真实 helper→merger roundtrip），不用 mock 口径替代公共入口。
6. 保留用户 main 未提交文件（`.pi/*`、`.grok/hooks/`、`Makefile`、演示 PPTX 等）与 `stash@{0}`（docs/skill-routing-explained 分支）；整理只做可恢复移动。

## 2. D→批次映射（15 项全覆盖）

以下保留批准时分工；实际实现署名与模型通道以末节执行记录和正式裁决为准。

| 批次 | 发现 | 级别 | Owner | 实现 | 交叉审 | 依赖 | 波次 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | D01, D02, D03 | P1 | Claude | Claude | Grok | — | W1 |
| B2 | D04, D05 | P1 | Grok | Grok | Claude | — | W1 |
| B3 | D06, D07, D08 | P1 | Claude | Claude | Grok | — | W2 |
| B4 | D09, D10 | P2 | Grok | Grok | Claude | — | W2 |
| B5 | D14 | P2 | Claude | Claude | Grok | B3 | W3 |
| B6 | D11, D13 | P2 | Grok | Grok | Claude | — | W3 |
| B7 | D12 | P2 | Claude | Claude | Grok | — | W4 |
| B8 | D15 | P2 | Grok | Grok | Claude | — | W4 |

两泳道文件 ownership 零交叉（见各批 paths），W1 起双模型并行；同 owner 批次串行。

## 3. 每批标准流程（不得跳过）

```
开发（owner 模型，限定 ownership 文件）
  → 完整 diff 送 Kimi 预 commit 审 → APPROVE 才可继续（REQUEST_CHANGES 必修并复审）
  → targeted host pytest + 本批新增 Docker 容器测试（冻结镜像 `vibesop-audit:20261009` @ `sha256:9fa60a217ea2215c956ff5a5e605e4b598cccfd95df6e76692e5d3a9c0893ef8`，arm64，uv run --frozen；输入为冻结 diff 应用后的干净 clone，只读挂载 /input 后复制到容器 /repo，不直接挂活跃 worktree）
  → atomic commit（conventional message + Co-Authored-By；全部批次在唯一受控 worktree 的同一分支 `codex/diagnosis-optimization` 上提交，不直接提交 main；每批可含多个 atomic commit，8 个**收批**才是约束）
  → Grok 只读复审（第二道闸：git archive HEAD 隔离复跑受影响测试，防「树绿 HEAD 红」）→ APPROVE
  → CHANGELOG.md 条目
  → Kimi 收批
```

- 作者为 Claude：交叉审 = Grok（第二道闸即此人）。
- 作者为 Grok：Claude 在预 commit 阶段补交叉审（与 Kimi 审并行，blocking）；Grok 仍走第二道闸，但只核证据链完整性与流程合规，**逻辑疑点一律上报 Kimi 裁决**，不得自批自过。
- 第二道闸必须在 commit 后跑 `git archive HEAD` 隔离抽取 + 受影响测试复跑（S95 模式）。

## 4. 批次详述

### B1 — 保护用户文件与凭据（D01/D02/D03）W1，Claude

> 执行勘误（Codex，待 Kimi 完整 diff 门禁确认）：祖先目录链接、固定临时文件链接及相对项目根的真实反例已复现。允许最小扩展到 `adapters/claude_code.py`、`file_based.py`、`pi_coding_agent.py`、`kimi_cli.py` 与 Pi adapter 回归，将受信输出根传入内容渲染及 override/fallback 签名，避免只修基类而遗漏真实调用者。必须用排他创建临时文件、统一相对根和依赖前 ID 校验；不扩改无反例的宿主功能。

**问题**：frontmatter `id: ../../../outside` 令 `vibe skill add` 写出安装根（D01）；render 沿已有 skill symlink 改写中央安装正文（D02）；`vibe build opencode` 把 ambient API key 原值写入 0644 产物（D03，cursor 同型）。

**Ownership**（唯一允许改动）：
- `src/vibesop/installer/skill_installer.py` — D01 主修。`install_skill` 在 `_copy_skill_files` 前校验 `manifest.id`：**按逻辑 namespace 逐段校验**——不得整体 `validate_filename(id)` 拒绝合法斜杠（合法 pack/skill 合同如 `demo-scope/demo` 必须兼容）；逐段拒绝空段、绝对路径、`.`/`..`、反斜杠与 symlink 穿越，并用 `ensure_safe_output_path(target_dir, project_path, create_parents=True)` 做 resolved containment + 目标各级 `lstat` symlink 检查；`uninstall_skill`/`verify_skill` 的 CLI 传入 `skill_id` 同样校验（`skill_installer.py:120,135,170` 同型）。
- `src/vibesop/adapters/base.py` — D02 主修。`write_file_atomic`（:351-402）不得 resolve-first 后把 resolved.parent 当 base：以调用方显式 `base_dir`（平台输出根）为锚，或在 resolve 前对未解析路径做 `_no_symlinks_in_chain` 检查；`_render_skill_content` content-hit 分支（:532-544）在写前显式处理 `skill_dir.is_symlink()`（沿用 :561-570 pack-installed 分支的「跳过中央改写」语义）。
- `src/vibesop/adapters/opencode.py`（:166,:178）、`src/vibesop/adapters/cursor.py`（:131,:143）— D03 主修。删除 raw `os.getenv` 回退，与父类 `file_based.py:157-181` 的 `api_key_env`（只写环境变量**名**）对齐；若宿主确需原值，加独立显式 opt-in + 0600 权限合同（默认路径不许写值）。
- 测试：`tests/installer/test_skill_installer.py`、`tests/adapters/test_base.py`、`tests/adapters/test_claude_code.py`、`tests/adapters/test_opencode.py`、`tests/adapters/test_cursor.py`、`tests/adapters/test_kimi_cli.py`。

**新增测试（真实入口反例）**：
- D01：临时源 frontmatter `id: ../../../outside`，真实 `SkillInstaller.install_skill`（无 force）→ 断言拒绝、根外目录不存在；合法 namespace id（如 `demo-scope/demo`）仍成功。
- D02：平台输出目录预置 `skills/demo -> <central>/demo` symlink + 可命中内容，真实 `ClaudeCodeAdapter.render_config` → 中央 SKILL.md 内容不变、无 ownership marker 穿透；第二次 render 幂等。
- D03：env 设哑 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`，真实 `vibe build opencode --output <tmp>` → `llm-config.json` 只含 `api_key_env` 名、不含值；`stat` 权限 ≤ 0600 或不含敏感键。

**Docker 测试**：容器内跑上述 targeted pytest（symlink 语义在 Linux 下复验）。

**Sibling 审计**（登记，不越界扩改）：`SkillStorage.get_skill_path`（`storage.py:158`，中央库 id 无防御）、`write_file_atomic` 全部 ~15 处 `base_dir=None` 调用点（列出清单，仅当同批测试暴露问题才修）、其余 5 个 adapter 的 `render_config` skill_dir 创建点。

**兼容性**：audit 通过/失败语义不变（D01 修在安装器校验，不改 `skill_auditor`）；marker 机制不变；默认产物使用 `api_key_env`；OpenCode/Cursor 的原值 `api_key` 字段改为环境引用，这是明确的安全行为变更。

**回滚**：`git revert <batch-commit>`；无 force-push（如需 `--force-with-lease`）。

**Exit criteria**：Kimi APPROVE ×2（预 commit + 收批）＋ 上述反例测试 host/container 双绿 ＋ `tests/security/`、`tests/conformance/test_platform_adapters.py` 不回归 ＋ atomic commit ＋ Grok 第二道闸 APPROVE ＋ CHANGELOG。

### B2 — 路由缓存真实性（D04/D05）W1，Grok

> 执行勘误（Codex，待 Kimi 随完整 diff 门禁确认）：独立预审 R1–R3 复现配置 mtime cache 与内容指纹分裂、合法 Markdown/默认搜索根遗漏、project_hash 作用域投影遗漏。B2 允许额外在 `src/vibesop/core/skills/config_manager.py` 增加最小的公共缓存失效接口，并避免热调用重复解析未改动 YAML。所有正式收批门禁保持。

**问题**：disable 后热实例与新实例（磁盘缓存 `candidates_v2.json`）仍视为可路由（D04）；SKILL.md 修改/显式 reload 后仍返回旧 metadata，且新 fingerprint 下回写旧 metadata（D05）。

**Ownership**：
- `src/vibesop/core/routing/candidate_manager.py` — 主修。fingerprint（`_compute_paths_hash` :74-88）纳入 `auto-config.yaml`（enabled/scope/lifecycle）、`registry.yaml`、YAML 技能文件（`*.yaml/*.yml`）及 SKILL.md 内容哈希（不只 mtime）；`reload()`/`_cached_reload_locked` 清理 loader `_skill_cache`（对齐 `SkillManager.reload_skills` 模式）；禁止在新 fingerprint 下回写旧 metadata（重算后再 `_save_to_disk_cache`）。
- `src/vibesop/core/skills/loader.py` — 暴露受控刷新接口供 CandidateManager 调用（不破坏现有 `clear_cache`/`force_reload` 公开语义）。
- `src/vibesop/core/skills/external_loader.py`、`src/vibesop/core/routing/_layers.py`（`_index_layer_cache`/`_index_profile_tokens` :611-624）— sibling 审计：reload 时同步失效；超出最小改的登记另立项。
- `src/vibesop/core/config/manager.py`（`load_registry` 缓存 :871-874）— 仅审计登记。
- 测试：`tests/unit/core/routing/test_candidate_manager.py`、`tests/core/skills/test_loader.py`、`tests/core/routing/test_skill_governance.py`、`tests/unit/core/routing/test_matcher_rewarm.py`、`tests/core/routing/test_demo_skills.py`。

**新增测试（真实反例）**：
- D04：真实 `SkillConfigManager.update_skill_config(enabled=False)` → 同实例 `route()` 与新实例 `route()`（走磁盘缓存）均排除该技能；scope/archive 更新同理；**不手戳任何私有缓存**（现有 `test_skill_governance.py:50-52` 的 cache surgery 在修复后应删除——它现在是 workaround）。
- D05：临时真实 SKILL.md 改 description（mtime+内容变化）→ 自动刷新与显式 `reload()` 都返回新 metadata；删除/新增技能同理；断言磁盘缓存新 fingerprint 下不是旧 metadata。
- 不变量回归：`!disabled-skill` 仍不可路由（`test_skill_governance.py:56-57` 语义保持）；`disable_model_invocation` 技能仍可被 EXPLICIT 层点名（fail-closed 8.3.1 A-5 不变）。

**Docker 测试**：容器内冷实例（磁盘缓存命中路径）复验 D04/D05。

**兼容性**：fingerprint 变更导致旧磁盘缓存自然失效（设计内）；`reload_candidates()` 公开语义不缩；product 语义明确：自动路由与人工强选都服从 enabled（与报告一致，不新增 force 旁路）。

**回滚**：revert；注意回滚后旧磁盘缓存与新代码的兼容由版本号 schema v3→bump 处理（`_disk_cache_path` schema 升级需一并考虑）。

**Exit criteria**：同标准流程 ＋ hermetic 路由评测 `--check` 不回归（本批不触碰 SKILL.md/registry 源文件，基线不应 STALE；若 fingerprint 逻辑导致 hermetic 口径变化，先报 Kimi 再动）。

### B3 — 统一执行结果与协作入口（D06/D07/D08）W2，Claude

**问题**：fail_fast 在全成功并行批后无条件 break，下游 pending（D06）；dynamic 桥硬编码 failed=0、丢 final_status（D07）；squad 桥绕开 WorkflowEngine handoff/review 门，blocked 标 completed（D08）。

**Ownership**：
- `src/vibesop/agent/step_runner.py` — 主修。三条 lane（squad :325 / dynamic :384 / static :397-579）统一产出 `StepOutcome`（status ∈ success/failed/blocked/skipped + output + error），共享终态汇总 `PlanOutcome`（completed/failed/skipped/blocked 计数 + plan_id + final_status）；结果 dict **只增键**；D06：break 仅在真实失败路径（对齐 serial 分支 :445-446 语义）；D07：dynamic 返回真实计数与 `final_status`；D08：`is_squad` 判定移入 dynamic 检查之后（engine 的 `is_dynamic` 先判），squad plan 委托 `WorkflowEngine.run_async`（engine 已有 handoff/review/revision，`workflow_engine.py:984-1170`），**不新增平行字符串判断**。
- `src/vibesop/core/orchestration/workflow_engine.py` — `_run_agent_squad` 硬编码 `plan.status = COMPLETED`（:1006）修正：blocked 评审 verdict 必须体现在共享 outcome（RR06 终态语义债务在此登记，不在本批扩改）。
- `src/vibesop/agent/execution_protocol.py` — 作为公开结果面与 StepOutcome 对齐（薄适配，不第三套词表）。
- `src/vibesop/agent/parallel_scheduler.py`、`src/vibesop/agent/__init__.py:403,419` — sibling 审计：结果形状对齐或登记。
- 测试：`tests/agent/test_step_runner.py`、`tests/core/orchestration/test_workflow_engine.py`、`tests/core/skills/test_workflow_engine_enhanced.py`。

**新增测试（真实公共 runner 反例）**：
- D06：PlanBuilder 生成 A∥B 无依赖 + C 依赖两者，`fail_fast=True`，A/B 成功 → **C 执行**，completed=3/failed=0。
- D07：LOOP_UNTIL_DRY executor 抛异常 → 公开结果 failed≥1、final_status 交付、与底层 engine 状态一致。
- D08：PlanBuilder RED_TEAM/DEBATE（含 `agent_squad_id` 与 `metadata["agent_squad"]`）走公共 runner，reviewer 返回 `blocked: no evidence` → 结果体现 blocked、非 completed；handoff context 存在；执行顺序为协作顺序非角色字母序。
- 矩阵：OK / exception / failed sentinel / blocked sentinel / dependency failure / cancel 各过每个公开入口。

**Docker 测试**：容器内复跑上述 tests/agent + orchestration targeted。

**兼容性**：dynamic 旧 `results` **字典形状必须保留**（keyed by step/plan 标识）——只增加统计/终态字段（真实计数、`final_status` 等），**不得改 dict 为 list**，也不得假称形状兼容；结果 dict 旧键（completed/failed/skipped/results/plan_id/dynamic/pattern）保留；D08 底层 WorkflowEngine 的「运行完成」与「review 通过」终态术语债务已排除（RR06 登记、不在本批扩改语义），公共 runner 只需正确保留并传播 failed/blocked 等真实 outcome/review verdict；全仓 grep `dynamic` 结果消费点（cli/dashboard）并在批次记录中列明适配。

**回滚**：revert。

**Exit criteria**：同标准流程 ＋ 结果形状消费点审计清单入批次记录 ＋ 全部新旧测试 host/container 绿。

### B4 — 构建合同（D09/D10）W2，Grok

**问题**：create_overlay 写顶层 security/routing、merger 只读 `policies.*`，threshold .9→.6 静默（D09）；sandbox build `/work:ro` 正常 BUILD.sh 必失败，输出退化为字符串，安装主链仍 success（D10）。

**Ownership**：
- `src/vibesop/builder/overlay.py` — D09 主修。`create_overlay` 写 canonical `policies.security`/`policies.routing`；`validate_overlay` 收紧（不再同时 bless 两形）；`_dict_to_manifest` 保留 legacy 顶层键读取（向后兼容），但 helper→merger roundtrip 必须值生效。
- `src/vibesop/builder/manifest.py` — 仅 `apply_overlay` 路径必要适配。
- `src/vibesop/installer/pack_installer.py` — D10 主修。`_run_build_in_container`（:436-495）：可写隔离副本 → 容器内构建 → 校验预期产物 → 原子写回 `target_path`（复用 AtomicWriter 模式）；`_run_post_install`/`install_pack` 传播 required build 失败 → `(False, ...)` 或异常，禁止 `return True` 吞失败；**不得**挂载用户根目录或 Docker socket。
- 测试：`tests/builder/test_overlay.py`、`tests/builder/test_manifest.py`、`tests/installer/test_pack_install_order.py`、`tests/installer/test_pack_installer.py`。

**新增测试（真实 producer→consumer）**：
- D09：真实 `create_overlay(routing={confidence_threshold:0.9})` → YAML → `OverlayMerger.merge` → Manifest 的 `policies.routing.confidence_threshold == 0.9`；legacy 顶层键文件仍能 merge（兼容）；非合法 policy 值被 validate 拒绝。
- D10：真实 arm64 Docker（可用 fake-runtime 单测 + 一次真容器 e2e）：模板 pack 的 BUILD.sh 生成文件 → 产物落盘 `target_path`、内容一致；required build 非零退出 → `install_pack` 返回失败、不写 pack-lock、不做 symlink。

**Docker 测试**：真容器 BUILD.sh e2e（报告证据链同姿势，host 调真实 Docker）。

**Sibling 审计**：`adapters/models.py:241` 的 `validate_overlay`（同名异义，登记）；`_run_build_local`（:541-588，opt-in 路径失败传播同查）。

**兼容性**：overlay 文件读取向后兼容；安装返回值从「恒 True」变「可 False」是缺陷修复本身——调用点（cli install 命令）需在同批内核对报错路径。

**回滚**：revert。

**Exit criteria**：同标准流程 ＋ roundtrip 值断言（非仅 YAML 可解析）＋ 真容器 e2e 绿。

### B5 — 并行真实性（D14）W3，Claude，depends_on [B3]

**问题**：并行批内同步 callable 在 async coroutine 里直接调用，无 await/thread dispatch，实际串行（两 .2s 任务≈.4s）。

**Ownership**：
- `src/vibesop/agent/step_runner.py` — 仅 `exec_step`（:449-483）：同步 executor 走 `asyncio.to_thread(step_executor, s, ctx)`（repo 认可姿势，tracer.py:157-163 先例；contextvars 必须传播），coroutinefunction 保持 await。semaphore 语义不变。
- 测试：`tests/agent/test_step_runner.py`。

**新增测试**：barrier/concurrency counter 证明两个 blocking callable 真实重叠（事件计数 ≥2 并发）；**禁止墙钟阈值断言**（报告明令）。同步 callable 公开 API 兼容（docstring :300 语义不变）。

**Docker 测试**：容器内复跑（线程调度语义复验）。

**Exit criteria**：同标准流程 ＋ B3 已收批。

### B6 — 经验证据完整性（D11/D13）W3，Grok

**问题**：stale snapshot 全量保存覆盖他实例已落盘反馈（同 id 也丢，1→0）（D11）；action 改变继承旧 action 成功证据，1 次新成功即跨 .6 门槛（D13）。

**Ownership**：
- `src/vibesop/core/instinct/learner.py` — 主修。D11：`_save`/`_merge_disk_into_memory_locked`（:318-353）按 FLAW #2 docstring 方向改为**锁内读最新盘态、按 id 应用 delta**（disk + (memory − loaded)），同 id 计数合并不丢；D13：action 变更分支（:552-557）证据绑定 pattern+action——改 action 时重置 success/failure 计数（或引入 evidence revision 字段，取最小改：重置计数 + 保留 id 行），`is_reliable` 语义不变。
- 测试：`tests/core/test_instinct_learner.py`、`tests/unit/core/routing/test_instinct_feedback_loop.py`。

**新增测试（真实双实例反例）**：
- D11：A/B 两实例同载 query A → A 记成功反馈 → B 记 query B 新增 → 磁盘 A 的 success 仍为 1（且 B 不丢）。
- D13：pattern 从 action A（3 成功）改 action B → 计数归零、confidence .5、is_reliable=False；一次新成功后不立即可靠。

**Sibling 审计**：全部 writer（`cli/main.py:358`、`tool_sequences.py:214`、`context_mixin.py:110`、`instinct_cmd.py`、`data_cmd.py:131`）走同一 `_save` 即自动受益，登记确认即可；`routing_pending` 队列（另一 store）不混。

**兼容性**：`.vibe/instincts.jsonl` 行格式不变（同 schema）；`update()`/`record_outcome_for_query()` 公开语义不变。

**回滚**：revert。

**Exit criteria**：同标准流程 ＋ 双实例测试 host/container 绿。

### B7 — 观测回放合同（D12）W4，Claude

**问题**：SpanWriter 把 metadata 编为 JSON string，recall `_extract_skill_id` 只认 dict → 真实磁盘 span 的 skill_id=None，用户接受回放后无 outcome、后续路由无历史偏好。

**Ownership**：
- `src/vibesop/core/observability/recall.py` — 主修。`_extract_skill_id`（:377-411）接受 JSON-string metadata，解析逻辑对齐 `skill_health.py:78-83` 的 string-or-dict 容忍模式；优先抽共用 helper（放 `core/observability/`，若引入则 `dashboard/server.py:353` 同型隐患一并修，仍在本批 ownership 内）。
- 测试：`tests/core/observability/test_recall.py`。

**新增测试（真实 producer→公共 consumer）**：真实 `SpanWriter` 写 span（metadata 含 `skill_id`）→ `query_recent` → `recall_similar` → `RecallResult.skill_id` 正确 → 用户接受回放的 consumer 返回非 None、增加 outcome。现有 dict-literal 测试保留。

**Docker 测试**：容器内复跑（真实文件格式复验）。

**Sibling 审计**：`dashboard/server.py:353`、`route_observe.py`、`skill_consumption.py:171` 等 metadata 消费点登记（只修 server.py:353 若 helper 化）。

**兼容性**：span 磁盘格式不改（producer 不动），只改 reader 容忍度；已存在的 dict 形态 span 仍可读。

**回滚**：revert。

**Exit criteria**：同标准流程 ＋ writer→reader→consumer 全链测试绿。

### B8 — 验证 oracle（D15）W4，Grok

**问题**：T4 断言无条件要求 `last_good_fired AND scenario_fallback`，只在 `last_good×.7 < min_confidence` 时联合可满足；真实模型 .88×.7=.616≥.6 时误报失败。

**Ownership**：
- `scripts/e2e_llm_routing.py` — 主修。T4 断言（:315-336）改为从子进程实际记录的 `last_good_original_confidence × LAST_GOOD_CONFIDENCE_DECAY` 与配置 `min_confidence` 计算期望分支，两条下游路径（被接受→无 scenario_fallback / 被拒→scenario_fallback）按算术确定性接受其一；修正 :318-321 过期注释。**不改生产衰减语义**（`triage_service.py`/`unified.py` 不动）。
- 测试：`tests/unit/core/routing/test_triage_service.py`、`tests/core/routing/test_scenario_demotion.py`。

**新增测试（确定性，不依赖真实模型）**：stale 条目 confidence .9×.7=.63≥.6 → last-good 被接受且无 `scenario_fallback`（`unified.py:759` 接受分支）；.8×.7=.56<.6 → 拒绝且 `scenario_fallback=True`。补 `LAST_GOOD_CONFIDENCE_DECAY` 边界算术断言。

**Docker 测试**：脚本本体是手动 docker e2e（非 CI 门），容器内跑一次 T0–T5 记录结果作证据（有 DEEPSEEK key 时；无 key 则记 skip 并跑确定性单测替代）。

**兼容性**：不降低门禁、不改 `min_confidence` 默认；脚本未接入 CI，修复只影响手动验证口径。

**回滚**：revert。

**Exit criteria**：同标准流程 ＋ 确定性分支测试绿。

## 5. 依赖与优先级

- 优先级：W1=B1∥B2（P1 安全/路由）→ W2=B3∥B4（P1 执行/P2 构建）→ W3=B5∥B6 → W4=B7∥B8。唯一硬依赖：B5→B3（统一结果模型后再动并发；同文件 step_runner.py）。
- B3 与 B5 同 owner 同文件，严格串行；其余同 owner 批次也串行，异 owner 按波次并行。

## 6. 终轮验证（全部批次收批后，Codex 执行、Kimi 放行）

1. `uv run ruff check . && uv run ruff format --check .`
2. `uv run basedpyright --level error` exit 0 才绿（基线错误数已为 0、已有诊断记录，**无需 stash 算净增**；标准口径即本命令 exit 0）
3. host 全量：`uv run pytest -m "not benchmark and not slow"`（口径同 CI/Makefile）
4. Docker arm64 全量（冻结镜像 `vibesop-audit:20261009` @ `sha256:9fa60a217ea2215c956ff5a5e605e4b598cccfd95df6e76692e5d3a9c0893ef8`）：输入为冻结 diff 应用后的干净 clone，只读挂载 `/input` 后复制到容器 `/repo` 再跑——**不得直接挂载活跃 worktree/repo**（避免污染宿主）；容器内 `uv run --frozen pytest -m "not benchmark and not slow"`
5. Node 24 专项套件（Pi extension / process boundary / generation hook / tool-seq / layering），冻结镜像 `vibesop-next-val:node24`；宿主真实 Docker 构建验证**不挂 Docker socket** 进不可信 build 容器
6. hermetic 路由评测 `uv run python scripts/eval_routing.py --hermetic --check`（基线不得 STALE）
7. wheel 冷安装 + 两平台 quickstart（源码目录外 `uv tool install`）
8. hooks 形态 canary（`bash <posix-abs>` 断言）+ artifact-links baseline guard
9. CHANGELOG 汇总条目；证据目录更新（见 §7）
10. 分支 `codex/diagnosis-optimization` push + `gh pr create`——**仅形成 PR，不 merge**；CI 观察以 job 级结论为准（`gh run view --json jobs`，防 continue-on-error 吞失败）

## 7. 仓库整理方案（开发收尾阶段执行）

1. **Inventory**：以 `docs/maintenance/cleanup-inventory-2026-10-09.json` 登记全 docs/ 与根目录散文件，三分类：`current`（活跃文档/入口）、`historical`（archive/decisions/旧评审）、`runtime`（.vibe、缓存、观测账本——不进 Git 整理面）。
2. **本轮证据**：按 `docs/maintenance/README.md` 当前维护约定，冻结诊断最终归档至 **`docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/`**（冻结诊断已迁移；后续开发与验收状态仍以执行记录为准）。保留 REPORT.md、历史 manifest、探针脚本、独立意见与小日志（≤100KB 级）在 Git（原日志以 `.log.txt`、原探针以 `.py.txt` 保留字节；完整映射见归档 `locations.json`）；约 4.9MB 原始 coverage JSON/XML 等大文件**冷归档至仓库旁** `/Users/huchen/Projects/vibesop-py-archives/2026-10-09/`，以 checksum + 文件位置映射 + 恢复说明保全；**不在仓内 `evidence/cold` 制造既不跟踪又不说明的空引用**，不改冻结报告历史事实；运行日志/精确 diff 完整保全；开发收据进对应有索引的小摘要目录；移动记录写 `docs/maintenance/cleanup-migration-2026-10-09.md`。
3. **禁区**：不动用户 main 未提交文件（`.pi/*`、`.grok/hooks/`、`Makefile`、演示 PPTX）；不动 `stash@{0}`；不清 docs/research 未完成研究；不动 `.vibe/` 运行时数据（除校验用临时 project_root，S95 教训）。
4. **入口更新**：`docs/INDEX.md` 与 `docs/README.md` 增补 reviews/2026-10-09 与 plans/2026-10-09 条目；`docs/maintenance/README.md` 增补本轮恢复入口（证据索引、cold 归档 checksum 校验命令、回滚指引）。
5. **验证**：`git status` 干净面核对 + SHA256SUMS 复验 + docs 链接抽查。

## 8. 回滚与授权边界

- 单批回滚 = revert 该批 atomic commit；整轮回滚 = 关闭 PR + 删分支（未 merge 即无损）。
- 禁止：force-push（必须时 `--force-with-lease`）、直推 main、merge、发版、部署、调外部模型（Grok/Claude 由 Codex 按分工调 CLI）。
- 发行与 merge 需用户另行明确授权；本计划交付物 = 8 个收批（每批可含多个 atomic commit，不承诺恰 8 个 commit）+ PR + 整理后的仓库。

## 9. 后续路线（待立项，本轮未开发）

本轮 8 批之后的价值/架构/创新方向，仅作路线登记，**不假称已开发**：

1. **跨宿主执行/验收合同一致性**：统一各宿主平台（Pi/Claude/Grok/Kimi）技能渲染、hooks 与验收口径的合同测试。
2. **可测量的采纳/节时/误注入与接管成本**：建立路由采纳率、节时、误注入率与人工接管成本的度量埋点与报表。
3. **真实 host-task E2E**：以真实宿主任务（非合成用例）做端到端验收。
4. **证据与文档可恢复性**：证据冷归档、checksum 与恢复演练制度化。

**进入条件**：以诊断基线/用户场景/确定性验收定义各方向立项门槛；PMF 与算法新颖性保持**未验证、待验证**；不承诺无依据的数字提升，不把本轮开发扩大到未知产品功能。

## 10. 计划裁决

本计划已获 Kimi **PLAN_APPROVE**（2026-10-09，B1=Claude/B2=Grok 派工已执行）；本次经调度器核实后修订（实际分支/worktree、D01 逐段校验、D07 形状保留、basedpyright 口径、冻结镜像与容器输入、冷归档路径、后续路线），输出 **PLAN_AMEND_APPROVE**。批次 B1–B8 **仍待验收**：按 W1→W4 推进，每批收批以 Kimi APPROVE 为准。


## 2026-10-09 Windows 与模型通道补充（执行中）

用户明确选择现有 Claude Code 的 GLM-5.3 后端；已以真实 CLI init/modelUsage 与工具往返核验客户端配置，Kimi MODEL_LANE_IDENTITY_APPROVE 生效。不得将此通道记成 Anthropic 模型。

Kimi WINDOWS_VERIFICATION_SCOPE_APPROVE 批准 W1：原生 Windows CI 仅追加 -ra/JUnit/已有 pin 的报告上传，Quickstart 仅打印 Git Bash 版本与部署 hook 行尾字节计数；五个 B1 测试文件补 copy fallback 资格，保留真实 symlink 安全反例与能力局限。B6-A 在既有 learner 测试文件补生产锁 LOCK_HELD/CONTENDED/RELEASE 双子进程握手。所有测试、过滤、重跑、coverage 和 gates 保留。两补充批次待实施/门禁，不代表 Windows 通过。

原生验收必须绑定最终新 HEAD：Windows Python3.12、3.13 全量 + Windows wheel Quickstart 三 job 必绿；skip 不算通过，原始基线逐 caseID 未取得，比较状态 unavailable。Docker Desktop/Linux containers 在 Windows 宿主上尚未验证，不能据此判为不支持。


## 当前执行结果与后续路线

B1–B8 与 Windows 补充 W1 已取得实际 Kimi 收批批准；逐批源提交、精确补丁与正式裁决见[优化验收记录](../reviews/2026-10-09-optimization/README.md)。B1/B3/B7 由 Kimi 临时代写；B5/W1 由用户授权的 Claude Code（GLM-5.3）实现。原计划中的 Claude 是客户端泳道名称，未声称原生 Anthropic 模型参与。

全量 Linux Docker 7,829 passed／26 skipped、macOS 7,839 passed／16 skipped，覆盖率 80.95%；hermetic 基线 0 新失败、6 个已知失败保留。最终容器使用 Node24 冻结镜像及只含依赖缓存的派生镜像，输入仍是精确冻结源码的只读快照；没有挂载 Docker socket、用户 home 或鉴权。新 HEAD 原生 Windows 两版本、wheel quickstart 与具体案例仍待 CI 确认。DeepSeek 实测 6/7 的 T4 负缓存前提失败保持可见，线上正缓存分支不作通过声明。

本轮之后先做真实宿主任务验收与跨平台合同一致性，再增加误注入、人工接管、耗时和成本观测，以真实用户任务验证价值；已有状态桥、async 范围、旧写者与 prune／clear 边界、构建索引内存和内容哈希成本按正式报告逐项另立可验证目标。产品需求匹配、量化收益和算法创新性尚待实证。合并、部署与发版不在本轮授权范围。
