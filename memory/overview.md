# Overview - VibeSOP Project

**Last Updated**: 2026-08-28 (S52b — Claude Code 2.1.220 hook 形态翻转探针+修复 PR #115 merged `f6f32c6`)

---

## Goals

### Current Week (August 23-29, 2026)

1. **Claude Code 2.1.220 hook 形态修复** ✅ (Completed - Aug 28, PR #115 merged `f6f32c6`)
   - 实机探针证伪 S51 前提（宿主改 `bash -c` + 会话 CWD spawn）；生成器/rewrite/verify/e2e 四层统一 `bash <posix-abs>`；CI 11/11 job 绿；本机 `~/.claude` 已重部署
   - 教训入 project-knowledge：hook 规范形态必须对用户实际版本实机探针钉死
2. **S52 深度治理主线**（in progress）— 分支 `governance/s52-deep-clean` 已建，Phase 1 六路对抗诊断未跑
3. **Adoption 推广线：块0 打包回退 + gate46 块2 quickstart 双平台 aha** ✅ (Completed - Aug 27；块0+块2 已 push，CI 全绿)
   - 待办：GIF 录制（W5 发布 gate）；recall 演示 defer 独立 mini-gate；W1 test.pypi 发版无限期 defer
4. **Dependabot 积压 9 PR**（#102-114）— 小版本批量合；openai 3.x / anthropic 1.0 major 需单独评估
5. **grok 真实会话 probe**（hooks 已部署；等真实使用确认 span 落盘）
6. **verifier 真实数据点**（等用户）：cmspark 用新流程 promote/dismiss，看徽章分布
7. **gate42/43 后续验收**（cron 触发）：8-31 一周+T+7 / 9-7 T+14，durable one-shot 自动带检查提示词

### Previous Weeks (July 26 - August 16, 2026) — Completed

1. **Dashboard v3 Phase A/B** ✅ (July 28)；**产品演化对抗 + Sprint 1 黄金 aha** ✅ (July 31)
2. **M12 主体施工**（语义洞察、发现队列、行为门、归属迁移）——8 月上旬多 session 完成，详见 session.md 与 CHANGELOG [Unreleased]

> Deferred（持续有效）：Dashboard v3 Phase C（UI 前端）——树先于 Cytoscape；AtomicWriter sibling lock file 修 rename+inode race（Phase B+1）。

### Previous Week (July 19-25, 2026) — Completed

1. **Windows 兼容生产化** ✅ (Completed - July 19)
   - 套件 88 failed → 0 failed（本地 4282 passed）+ CI test-windows job 全绿 + ubuntu 零回归
   - 9 个真实生产 bug 修复（GBK 自毒/场景路由禁用/fd 泄漏丢状态/shlex 引号泄漏等）
   - 多 agent 动态工作流（设计→对抗→开发→评审→pi/Grok 签字），全套文档 docs/dev/windows-compat/
2. **Observability loop closure (v8.2)** ✅ (Completed - July 22-24)
   - P1 ship：SpanWrappedProvider + SpanAggregator + `vibe trace replay/metrics` CLI；Kimi 4 blocker 全处理
   - Deep diagnosis (07-24)：4 agent 诊断 + 12 P0/P1 fix（3 batch）+ pi 评审双清；4633 tests
   - Instinct loop Phase A-E (07-24)：command_args / 文件锁 / launchd / auto-promote+feedback-collect / preset+ADR-005
3. **Conversation mirror (Path-1 + Path-2)** ✅ (Completed - July 24-25)
   - Path-1：thinking/tool_calls/tool_results/model/usage/stop_reason 端到端捕获（commit d7ddfeb）
   - Path-2：sub-agent transcripts — 每个 sub-agent 独立 mirror conversation + metadata bag（commits 6f2f7f0 + 23f478e）
   - 3 轮 grok+pi review，全 must-fix 修完

### Previous Week (July 13-18, 2026) — Completed

1. **Control Panel 分拆** ✅ (Completed - July 18)
   - vibesop-py-panel 独立仓库（私有，36 提交全历史），worktree 转独立克隆
   - 主仓回归四个核心定位：脚手架 / 语义路由 / agent 优化 / 其他优化
2. **质量收口** ✅ (Completed - July 18)
   - main CI 6/6 全绿（此前 7-14 起持续红）：lint 修复 + 测试隔离 + release 管线 workflow_call
   - 供应链：pip-audit 覆盖全 extras、dependabot→uv 生态、bandit 配置单源化

### Previous Week (May 24-30, 2026) — Completed

1. **4-Phase Transformation** ✅ (Completed - May 29)
   - Phase 1: Spec v3.0 (SkillSpec Pydantic model, SpecValidator, SkillType.STANDARD)
   - Phase 2: Reference (3 base classes: FileBased/HookBased/SdkBased, shared templates)
   - Phase 3: Wire (AgentRuntime wiring, shell hook elimination 221→22 lines, HookPoint.ROUTE_INTERCEPTOR)
   - Phase 4: Conformance Suite (85 tests, dead code removal, SKILL.md template unification, Pi→SdkBasedAdapter)
2. **Audit Optimization** ✅ (Completed - May 29)
   - SKILL.md template unified across all adapters
   - Pi adapter inherits from SdkBasedAdapter (~30 lines removed)
   - Shell hook template 53→22 lines

### Previous Week (April 21-22, 2026) — Completed

1. **Lint Sweep** ✅ (Completed - April 22)
2. **Badge System MVP** ✅ (Completed - April 22)
3. **UnifiedRouter Refactoring** ✅ (Completed - April 22)
4. **v4.3 Multi-Turn Support** ✅ (Completed - April 22)
5. **v4.3 Context-Aware Routing** ✅ (Completed - April 22)
6. **Custom Matchers Plugin System** ✅ (Completed - April 22)
7. **A/B Testing Framework** ✅ (Completed - April 22)
8. **Fix Flaky Tests + v4.3.0 Release** ✅ (Completed - April 22)

### Previous Week (April 23-30, 2026) — Completed

1. **Agent Runtime Layer** ✅ (Completed - April 23)
2. **v4.4 Platform Adaptation** ✅ (Completed)
3. **Code Review Defect Fixes** ✅ (Completed - April 27)
4. **CLI `vibe build --platform=all`** ✅ (Completed)

### Previous Week (May 1-3, 2026) — Completed

1. **Test Coverage Backfill** ✅ (Completed - May 3)
2. **Documentation YAML→TOML Migration** ✅ (Completed - May 3)
3. **Agent Override Protocol Cross-Platform Sync** ✅ (Completed - May 3)

### Current Week (June 9, 2026)

1. **v7.0 Prompt Chain Generator** ✅ (Completed - June 9)
   - Classifier multi-dimensional review detection → PROMPT_CHAIN trigger
   - Dynamic Workflow Prompt Chain — 4-phase implementation
   - Quality fixes: step_type-based key points, fallback file resolution, Final Phase red team/scoring/action items
   - Final Phase conditional branching: review tasks get red team + scoring + action items; non-review tasks get functional verification checklist

2. **Routing Quality Improvements** ✅ (Completed - May 5)
   - Candidate deduplication by canonical ID
   - Management-only skill tagging (slash-* prefix exclusion from semantic matching)
   - Triage prompt v3 with office-hours/plan routing rules
   - Committed and pushed: `2380ec2`

### Previous Week (May 4-10, 2026)

1. **Vibe Coding Article Revision** ✅ (Completed - May 5)
   - Added "Core Problems + Survival Principles" overview chapter to docs/vibe-coding-article.md
   - Structured as: answers first → story second → methodology third

---

## Projects Summary

### VibeSOP (vibesop-py)
**Status**: v8.1.1+ (hook 命令规范 `bash <posix-abs>` 四层统一 PR #115；CI Windows 为 required gate)
**Description**: AI SkillOS — vibe-coding 脚手架、语义级 query→skill 路由、编程 agent（Claude Code/Grok Build/Kimi/Pi/Cursor/Zed）优化
**Coverage**: 覆盖率门禁 73%；Windows job 为 required gate（gate44）
**Key Metrics**:
- Routing accuracy: 94%
- Performance: 44 QPS (target: 40+ QPS)
- CI: Windows required + Ubuntu；release 复用 ci-gate
- Panel extension: split to nehcuh/vibesop-py-panel (2026-07-18)
- Workflow patterns: 7 (SEQUENTIAL, PARALLEL, FAN_OUT, ADVERSARIAL, LOOP_UNTIL_DRY, TOURNAMENT, PROMPT_CHAIN)
- Platforms: Claude Code, Grok Build, Kimi CLI, Pi Agent, OpenCode, Cursor (adapter exists; installer/quickstart 未接线)

**Recent Changes** (2026-08-28):
- ✅ Claude Code 2.1.220 hook 形态翻转修复：实机探针（4 形态对照）证伪 S51 config-relative 前提
- ✅ PR #115 merged：生成器/rewrite/verify/e2e 断言四层统一 `bash <posix-abs>`；CI 11/11 绿
- ✅ 本机 `~/.claude` 重部署为绝对形态；project-knowledge 08-26 旧条目标注已证伪

**Recent Changes** (2026-07-18):
- ✅ Fanout 六路诊断 → 全部问题收口：CI 转绿、release 管线修复（workflow_call）、pip-audit 全 extras 覆盖
- ✅ Control panel 分拆为独立仓库 vibesop-py-panel（36 提交全历史，worktree→独立克隆）
- ✅ 仓库清理：origin 15 个陈旧分支删除，本地/远端只剩 main
- ✅ CHANGELOG 补齐 59 个提交；dependabot→uv 生态；删除 mypy/sync-core.sh

**Recent Changes** (2026-06-09):
- ✅ Final Phase conditional branching: review tasks get red team + scoring + action items; non-review tasks get functional verification checklist
- ✅ ExecutionPlan.metadata field for passing classification context downstream
- ✅ Prompt Chain Generator quality: step_type-based key points (6 analysis subcategories), fallback file resolution for external skills
- ✅ Final Phase enhanced: red team attack surface analysis (4 dimensions), five-dimension radar scoring, P0/P1/P2 action items
- ✅ Classifier multi-dimensional review detection → PROMPT_CHAIN trigger
- ✅ 35/35 prompt_chain tests, 196/196 orchestration tests passing

**Recent Changes** (2026-06-05):
- ✅ Version bumped 5.5.0 → 6.2.0, 29 files synced
- ✅ Dynamic Workflow Engine documentation (ARCHITECTURE.md, README.md, templates)
- ✅ Platform compatibility matrix documented (native sub-agent vs serial)
- ✅ Adapter templates updated with Workflow Patterns sections
- ✅ Fixed hook template test assertions and _Skill.get() AttributeError
- ✅ Commit: b6daa4d on refactor/router-orchestrator-split
- ✅ Phase 4 complete: conformance suite (85 tests), dead code removal, README sync
- ✅ SKILL.md template unification (shared template + render_skill_md function)
- ✅ Pi adapter inherits SdkBasedAdapter (~30 lines duplicated code removed)
- ✅ Shell hook template optimized 53→22 lines
- ✅ Version bumped 5.4.6→5.5.0, pyproject.toml + CHANGELOG updated

**Recent Changes** (2026-04-27):
- ✅ 9 P0/P1 routing/feedback defects fixed (IndexError, Chinese bypass, ConfigSource, etc.)
- ✅ Context-aware optimization now works for all routing layers
- ✅ Matcher prefilter warmup re-activated
- ✅ Scope defaults corrected (project→global) for builtin skills

**Recent Changes** (2026-04-23):
- ✅ Agent Runtime layer: IntentInterceptor + SkillInjector + DecisionPresenter + PlanExecutor
- ✅ Platform adaptation: Claude Code (hooks), Kimi CLI (AGENTS.md), OpenCode (plugin template)
- ✅ E2E validation: 13 tests covering full chain + platform artifacts + cross-platform consistency

**Recent Changes** (2026-04-21):
- ✅ Code review optimization plan: P0-1/P0-2/P0-3/H1/H4/M3/M4 all complete
- ✅ 27 bare `except Exception` narrowed to specific types
- ✅ `LayerResult` unified to Pydantic BaseModel
- ✅ Duplicate `RoutingConfig` resolved (adapters → `RoutingPolicy`)
- ✅ `UnifiedRouter` supports `skill_loader` injection
- ✅ `fallback_mode`/`default_strategy` now Literal-validated
- ✅ `_edit_execution_plan` empty plan guard added
- ✅ `_handle_single_result` split from 213 lines to 6 focused functions

**Recent Changes** (2026-04-21):
- ✅ Architecture review with professional assessment
- ✅ Document version sync (PHILOSOPHY/ARCHITECTURE/ROADMAP/PROJECT_STATUS → 4.2.0)
- ✅ UnifiedRouter extracted RouterStatsMixin (-49 lines)
- ✅ pytest-xdist parallel testing (make test-fast ~39s)
- ✅ Fixed 3 pre-existing test failures
- ✅ Eliminated test warnings, fixed ruff issues
- ✅ Added TECH DEBT annotations for known issues

**Recent Changes** (2026-04-20):
- ✅ Implemented skill-level LLM configuration system
- ✅ Created `SkillConfigManager` with CRUD operations
- ✅ Added CLI commands for config management
- ✅ Integrated auto-configuration with skill install
- ✅ Fixed dataclass bug in understander.py
- ✅ Improved keyword extraction (added stop words)
- ✅ All tests passing (1000+ lines of new code, fully tested)

**Next Steps**:
- Skill 商店简化：GitHub 按需搜索替代 issues 版市场，询问式安装（全局/项目级）
- 未命中查询追踪：后台记录重复无匹配查询，定期建议搜索安装
- 任务蒸馏：重复任务总结为独立技能（instinct learning 延伸）
- Langfuse 不进核心（留 panel 层）；核心用本地结构化日志（F-06 opt-in 先例）
- 存量 backlog：文档深度治理（49 坏引用/187 版本漂移）、双 PromptChainGenerator 合并

---

### Kimi CLI Integration
**Status**: Active
**Description**: VibeSOP configuration adapter for Kimi Code CLI
**Provider**: Moonshot (Kimi)
**Recent Changes**:
- Fixed configuration fragment generation
- Corrected provider value to 'moonshot'
- Resolved vibe doctor issues

---

## Quick Reference

### Development Commands
```bash
# Type checking
uv run basedpyright

# Linting
uv run ruff check

# Testing
uv run pytest

# Test coverage
uv run pytest --cov=src/vibesop --cov-report=html

# Run specific test
uv run pytest tests/path/to/test.py
```

### Key Files
- **Router**: `src/vibesop/core/routing/unified.py`
- **Skill Loader**: `src/vibesop/core/skills/loader.py`
- **Security**: `src/vibesop/security/skill_auditor.py`
- **Tests**: `tests/integration/test_external_skill_execution.py`

### Important Paths
- **Memory**: `memory/` (session.md, project-knowledge.md, overview.md)
- **Session State**: `.vibe/state/sessions/`
- **Configuration**: `.vibe/config.yaml`
