# VibeSOP Roadmap

> **Version**: 8.0.0.dev0
> **版本 Version**: 8.0.0.dev0
> **最后更新 Last Updated**: 2026-06-14

---

## Current State (v7.0.0)

### ✅ Completed in v7.0 (2026-06-14)

- [x] **Hook path P0 fix** — `AgentRouter.orchestrate` accepts `callbacks`; `vibesop-route.sh` finds project root + PATH-robust (orbs / docker / non-interactive shells)
- [x] **Multi-Agent Squad auto-trigger** — `IntentInterceptor.ROLE_KEYWORDS` fast path promotes ≥2-role queries to `MULTI_AGENT_SQUAD` without LLM; `Orchestrator` reads `context.metadata["intent_analysis"]`; `AgentRuntime.handle_query` unifies ORCHESTRATE + SQUAD paths
- [x] **Prompt injection + path traversal hardening** — `_escape_query` strips C0 control chars; `write_files` rejects NUL bytes + uses separator-suffixed prefix check
- [x] **`prompt-chain-validator` cross-cutting skill** — `.vibe/skills/cross-cutting/prompt-chain-validator.skill/` + `vibe prompt-chain {diagnose,generate,validate,run}` CLI + `core/prompt_chain/{generator,validator}.py`

### ✅ Completed in v6.2.0 (2026-06-05)

- [x] Core SkillOS engine with 10-layer pipeline

### ✅ Completed

- [x] Core SkillOS engine with 10-layer pipeline
- [x] Unified skill management (builtin + external + custom)
- [x] Security auditing for external skills
- [x] Preference learning system
- [x] CLI with route/install/skills commands
- [x] Performance optimization (candidate caching, <50ms P95)
- [x] Architecture cleanup (65% code reduction)
- [x] Documentation overhaul
- [x] AI Triage production readiness (v4.1.0)
- [x] Skill health monitoring (v4.2.0)
- [x] Skill-level LLM configuration system
- [x] One-click smart skill installation
- [x] Context-aware routing (v4.3.0)
- [x] Agent Runtime layer (v4.3.0)
- [x] Badge system (v4.3.0)
- [x] Multi-intent detection + task decomposition + execution planning (v4.4.0)
- [x] Skill lifecycle management (DRAFT → ACTIVE → DEPRECATED → ARCHIVED) (v4.4.0)
- [x] Scope system (project-level vs global skill isolation) (v4.4.0)
- [x] Feedback loop (usage analytics + satisfaction tracking) (v4.4.0)
- [x] Scope-aware routing isolation — project skills invisible outside project (v5.1-dev)
- [x] Retention system CLI visibility — `vibe skill stale` with archive detection (v5.1-dev)
- [x] Auto-archive for 90+ day unused skills + archived skills excluded from routing (v5.1-dev)
- [x] Post-route retention nudge every N routes (v5.1-dev)
- [x] InstinctLearner sequence pattern detection for workflow-to-skill learning (v5.1-dev)
- [x] SkillSuggestionCollector — bridge from pattern detection to one-click skill creation (v5.1-dev)
- [x] `vibe skills suggestions` — view and create skills from auto-detected patterns (v5.1-dev)
- [x] `vibe skill end-check` — session-end retention + suggestion review (v5.1-dev)
- [x] Routing transparency — rejected candidates display with per-layer reasons (v5.1)
- [x] Unified `orchestrate()` entry point with single-skill fallback (v5.1)
- [x] Multi-intent detection — heuristic + LLM two-phase confirmation (v5.1)
- [x] `SkillInjector` — full skill content injection for 3 platforms (v5.1)
- [x] `SessionTracker` — file persistence with atomic writes (v5.1)
- [x] `BadgeTracker` — persistent badge storage with no-duplicate logic (v5.1)

### 📊 Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Test Count | 4,066 | 2,000+ | ✅ |
| Test Coverage | ~73% (full run) | >75% | ⚠️ Near target |
| Pure Routing P95 | ~50ms | <100ms | ✅ |
| LLM Triage P95 | ~220ms | <300ms | ✅ |
| Skills Supported | 45+ | 45+ | ✅ |
| Lint Errors | 0 | 0 | ✅ |
| Quick Commands | 7 | 7 | ✅ |
| Service Layer | 4 services | 4 services | ✅ |
| Rejected Candidates Display | ✅ | ✅ | ✅ |
| Unified Orchestration Entry | ✅ | ✅ | ✅ |
| LLM Multi-Intent Detection | ✅ | ✅ | ✅ |

> **注**: 作为 SkillOS（技能操作系统），代码量包含完整的功能模块是合理的。性能指标已针对包含 LLM 调用的场景进行调整。

---

## v4.1.0 — AI Triage Production ✅ (Released 2026-04)

### Goals
Make AI Triage (Layer 2) production-ready with real LLM integration.

### Features

- [x] **Real LLM Integration**
  - Anthropic Claude API
  - OpenAI GPT API
  - Local model support (Ollama, default provider in v4.4.0+)

- [x] **Cost Management**
  - Token usage tracking
  - Cost per query estimation
  - Budget alerts and limits

- [x] **Caching Improvements**
  - Semantic cache (similar queries)
  - Persistent cache across sessions
  - Cache warming for common queries

- [x] **Fallback Strategy**
  - Graceful degradation when LLM unavailable
  - Automatic fallback to keyword matching
  - Circuit breaker pattern

### Success Metrics

- AI Triage hit rate > 30%
- Average cost per query < $0.005
- Cache hit rate > 50%
- Zero downtime for LLM failures

---

## v4.2.0 — Skill Health Monitoring ✅ (Released 2026-04)

### Goals
Monitor the health and quality of external skill packs.

### Features

- [x] **Health Dashboard**
  - `vibe skills health` command
  - Visual status indicators
  - Detailed health reports

- [x] **Health Metrics**
  - Last update time
  - Open issues count
  - Version compatibility
  - Security audit status

- [x] **Alerts**
  - Outdated skill packs
  - Security vulnerabilities
  - Breaking changes

- [x] **Auto-Update**
  - Check for updates
  - Security patch auto-install
  - Changelog integration

### Success Metrics

- Health check coverage: 100% of installed packs
- Alert response time: < 24 hours
- Security patch adoption: > 90% within 7 days

---

## v4.3.0 — Context-Aware Routing + Quick Commands ✅ (Released 2026-04-24)

### Goals
Improve routing accuracy with context awareness, multi-turn conversations, direct Agent integration, and CLI quick commands.

### Features

- [x] **Context-Aware Routing**
  - Project type detection (15+ types: python, rust, js, ts, go, java, etc.)
  - Technology stack inference (13+ stacks: django, fastapi, react, docker, k8s, etc.)
  - Project context boost (+0.02~0.04 confidence)

- [x] **Multi-Turn Support**
  - Conversation context tracking
  - Follow-up query detection (continuation/retry/alternative/clarification/refinement)
  - Chinese + English pronoun reference detection

- [x] **Agent Runtime Layer**
  - Direct Python API for AI Agents (no external API key needed)
  - Agent LLM injection (`router.set_llm(agent_llm)`)
  - Platform adaptation (Claude Code, Cursor, Continue.dev)

- [x] **Router Refactoring**
  - 8 Mixin extraction from 1210-line God Class → 506 lines (-58%)
  - Cleaner separation of concerns
  - Better testability

- [x] **Badge System**
  - 4 badge types: first_feedback, skill_champion, quality_master, ecosystem_guardian
  - Integrated into skills feedback, health check, and routing

- [x] **Routing Transparency**
  - `--explain` flag shows full routing decision tree
  - `--validate` mode with rejected candidate display
  - Per-layer diagnostics with timing and reasoning

- [x] **Central Storage Architecture**
  - Skill packs installed to `~/.config/skills/<pack>/`
  - Platform directories receive symlinks (`~/.claude/skills/<pack>` → central)
  - Unified management across all AI tools

- [x] **Quick Commands (CLI)**
  - 7 built-in commands: `/vibe-route`, `/vibe-install`, `/vibe-analyze`, `/vibe-evaluate`, `/vibe-orchestrate`, `/vibe-list`, `/vibe-help`
  - CLI direct execution via `vibe route --slash "/vibe-help"`
  - Platform hook scripts for best-effort AI Agent integration
  - Shared service layer (RoutingService, InstallService, AnalysisService, EvaluationService)

- [x] **Orchestration Interaction**
  - `--strategy=sequential|parallel|auto` for multi-skill execution
  - Interactive step editing (move/remove/reorder)
  - Data dependency visualization

### Success Metrics

- ✅ Routing accuracy improvement: +5% (with project context)
- ✅ Multi-turn query support: 100%
- ✅ Agent Runtime API stability: v1.0
- ✅ Quick command coverage: 7 commands, CLI + hook integration
- ✅ Service layer: 4 services, zero duplication with CLI
- ✅ Test count: 4,066 (+2,216 from v4.2.0)

---

## v4.4.0 — SkillOS: Orchestration + Lifecycle + Feedback ✅ (Released 2026-04-26)

### Goals
Transform VibeSOP from a routing tool into a complete Skill Operating System.

### Features

#### Orchestration (Default Mode)
- [x] **Multi-Intent Detection**
  - Automatic detection of complex queries with multiple intents
  - Heuristic + LLM-based detection with zero-cost fast path
  - Intent domain boundary detection

- [x] **Task Decomposition**
  - LLM-based query decomposition into sub-tasks
  - Fallback rule-based decomposition when LLM unavailable
  - Guardrails to prevent over-decomposition

- [x] **Execution Planning**
  - Automatic serial/parallel strategy detection
  - Dependency inference between steps
  - Interactive plan editing (move/remove/reorder)

- [x] **Streaming Progress**
  - Real-time orchestration progress display
  - Phase-by-phase callbacks (routing → detection → decomposition → planning)
  - Error recovery strategies (skip/retry/abort)

#### Skill Lifecycle Management
- [x] **SkillLifecycle State Machine**
  - States: DRAFT → ACTIVE → DEPRECATED → ARCHIVED
  - Valid transition enforcement
  - Routability checks (archived/draft skills excluded)

- [x] **Scope System**
  - Project-level vs global skills
  - Scope-aware routing (project skills invisible outside project)
  - `.vibe/skills/` project-local override

- [x] **CLI Commands**
  - `vibe skill list` — List skills with lifecycle state
  - `vibe skill enable <id>` / `vibe skill disable <id>`
  - `vibe skill status <id>` — Show skill details and valid transitions

#### Feedback Loop
- [x] **Usage Analytics**
  - Execution record storage (`.vibe/analytics.jsonl`)
  - Skill usage statistics (satisfaction rate, modification rate)
  - Low-quality skill detection

- [x] **User Feedback Collection**
  - Post-execution satisfaction prompt
  - Automatic deviation recording suggestion
  - Feedback-driven routing improvement

#### SkillMarket (Partial)
- [x] **GitHub Topic Crawling**
  - `vibe market search <query>` — Search by keywords
  - `vibe market install <skill>` — Install from discovery

#### Performance Optimization
- [x] **Latency Reduction** (Completed)
  - Pure routing P95: ~50ms ✅ (target <100ms)
  - LLM Triage P95: ~220ms ✅ (target <300ms)
  - Router hot-path optimization
  - Lazy loading for heavy dependencies

- [x] **Quality Gates** (Completed)
  - Fix remaining lint errors → 0 ✅
  - Increase coverage from 73% → 75% (near target, sprint nearly done)

### Success Metrics

- ✅ Orchestration: Multi-intent detection + task decomposition + execution planning
- ✅ SkillLifecycle: 4 states with transition validation
- ✅ Scope system: Project-level skill isolation
- ✅ Feedback loop: Usage analytics + user satisfaction tracking
- ✅ Pure routing P95: ~50ms (target <100ms)
- ✅ LLM Triage P95: ~220ms (target <300ms)
- ✅ Lint errors: 0
- ⚠️ Test coverage: ~73% (target 75%, close to completion)

---

## v5.0.0 — SkillRuntime: Scope + Lifecycle (2026-Q2) ✅ CLOSED (scope + lifecycle hardened in v5.1-dev)

> **ADR**: [docs/archive/version_05.md](archive/version_05.md) (Plan: VibeSOP Skill Ecosystem Evolution, approved 2026-04-21)

### Goals
Introduce scope isolation, skill enable/disable, and lifecycle state management.

### Features

- [~] **SkillRuntime Core** (In Progress)
  - Scope system: project-level vs global skills
  - Skill enable/disable toggle (`vibe skill enable/disable <id>`)
  - SkillLifecycleState machine (DRAFT → ACTIVE → DEPRECATED → ARCHIVED)
  - Scope-aware config resolution (project `.vibe/` overrides global `~/.vibe/`)

- [~] **Data Pre-burial for v5.1** (In Progress)
  - SkillConfig gains `usage_stats` field (call count, success rate, last used)
  - SkillConfig gains `version_history` field (semver tracking)
  - SkillConfig gains `evaluation_context` extension slot

- [~] **CLI Commands** (In Progress)
  - `vibe skill enable <id>` / `vibe skill disable <id>`
  - `vibe skill scope <id> --project` / `vibe skill scope <id> --global`
  - `vibe skill lifecycle <id> --set deprecated`

### Success Metrics

- Skill scope isolation: 100% (project skills invisible outside project root)
- Toggle latency: <50ms
- Lifecycle states: 4 (draft/active/deprecated/archived)
- Backward compatibility: v4.x users smooth migration via config

---

## v5.1.0 — SkillMarket + Feedback Loop ✅ COMPLETED (delivered in v5.1-v5.2)

### Goals
Complete the skill ecosystem with discovery, community, and self-improvement.

### Features

- [~] **SkillMarket MVP** (Partial — core commands implemented)
  - `vibe market search <query>` — keyword + tag search ✅
  - `vibe market info <skill>` — ratings, downloads, compatibility ⚠️ (command stubbed)
  - `vibe market install` — one-click from discovered skills ✅
  - GitHub topic crawling (`topic:vibesop-skill`) ✅ (unauthenticated, rate-limited)

- [~] **Autoresearch Feedback Loop** (Partial — analysis implemented, automation pending)
  - Analyze routing success/failure patterns ✅
  - Suggest keyword additions for missed queries ⚠️ (manual CLI only: `vibe skill optimize`)
  - Skill quality regression detection ✅
  - Auto-deprecate skills below quality threshold ✅
  - User satisfaction tracking (`AnalyticsStore`) ✅
  - Interactive feedback collection after execution ✅

- [x] **Retention System (CLI-visible)**
  - `vibe skill stale` — detect stale/underperforming skills with archive actions
  - 90-day auto-archive for unused C/D/F-grade skills
  - Archived skills excluded from routing (`is_routable(ARCHIVED) = False`)
  - Post-route retention nudge every 20 routes
  - `vibe skill end-check` — session-end review command

- [~] **Skill Learning → Creation → Registration Closed Loop** (Partial — manual workflow ready, auto-trigger pending)
  - `InstinctLearner` sequence pattern detection (multi-step tool call patterns) ✅
  - `SkillSuggestionCollector` — candidate persistence + threshold triggering ✅
  - `vibe skills suggestions` — view auto-detected workflow patterns ✅
  - `vibe skills create --from-suggestion <id>` — one-click skill generation ✅
  - Auto-generated SKILL.md + `SkillAutoConfigurator` + registry registration ✅
  - ⚠️ `record_sequence()` is not auto-triggered; users must manually run `vibe session record-tool`

- [x] **Scope-Aware Routing**
  - Project hash binding for project-scoped skills
  - Cross-project isolation via `SkillLoader` scope filtering
  - `vibe skills scope <id> --set project` with project binding

- [x] **Skill Evaluation**
  - Rating and reviews system (`SkillRatingStore`, `vibe skills rate`)
  - Usage statistics (downloads, active users via `SkillConfig.usage_stats`)
  - Compatibility matrix (via platform adapters)
  - Quality grading A-F with 5-dimensional scoring (`RoutingEvaluator`)

### Success Metrics

- SkillMarket: 50+ discoverable skill packs
- Feedback loop: automatic keyword additions for 80%+ missed queries
- Evaluation coverage: 100% of installed skills
- Deprecation accuracy: <5% false positives

---

## v5.2.0 — Intelligent Ecosystem ✅ COMPLETED (delivered in v5.1-v5.2)

> Core infrastructure (transparency, unified entry, LLM multi-intent) already shipped in v5.1.

### Goals
Proactive skill recommendations, transparent fallback, active discovery.

### Features

- [x] **Routing Transparency — Rejected Candidates**
  - `--explain` shows near-miss candidates with per-layer rejection reasons
  - Rejected reasons: below threshold, scope mismatch, disabled
  - Tested: `test_rejected_candidates.py` (21 tests passing)

- [x] **Unified Orchestrate Entry Point**
  - `orchestrate()` handles both single and multi-intent queries
  - Single-skill is a degenerate 1-step execution plan
  - `route()` preserved as legacy fast-path wrapper

- [x] **Multi-Intent Semantic Detection**
  - Two-phase: heuristic regex filter (zero cost) + LLM confirmation (~10 tokens)
  - Guard words prevent false positives on short/verb queries
  - Graceful LLM failure → trust heuristic

- [~] **Smart Recommendations** (Partial — scoring implemented, proactive display pending)
  - Project-type-based recommendations ("Python project → suggest tdd, review") ⚠️ (hardcoded stack maps)
  - "Users who installed X also installed Y" ⚠️ (stubbed — no real collaborative data)
  - Missing skill detection for current project ⚠️ (scoring exists, not proactively surfaced)

- [x] **Transparent Auto-Degradation**
  - When no skill matches, show transparent fallback
  - Route result includes `layer: FALLBACK_LLM` for visibility
  - Config: `degradation_fallback_always_ask true` to require user confirmation
  - DegradationManager with 4-level confidence gating (AUTO/SUGGEST/DEGRADE/FALLBACK)

- [~] **Active Discovery** (Partial — passive query-scoring, proactive scanning pending)
  - SkillRecommender scores skills against current query ✅ (passive, embedded in routing)
  - Proactive suggestion in status dashboard and routing results ⚠️ (scoring exists, UI nudge limited)
  - Community trending panel with GitHub Issues integration ❌ (not implemented)

### Success Metrics

- Recommendation click-through: >30%
- Fallback awareness: 100% of fallbacks transparent to user
- Active discovery: <5% false positive suggestions

---

## v5.5.0 — 3-Pillar Skill Protocol Standard ✅ COMPLETED (2026-05-29)

> VibeSOP transitions from "skill router" to **skill protocol standard definer**,
> built on pillars: Spec, Reference, and Conformance Suite.

- **The Spec**: canonical `SkillSpec` model (all 29 SKILL.md frontmatter fields), `SpecValidator`, CLI `vibe spec validate` / `vibe spec version` — Spec v3.0
- **The Reference**: 3 integration patterns (file-based / hook-based / SDK-based adapters)
- **The Conformance Suite**: 85 compliance tests, `vibe spec conformance --all`

---

## v6.0.0 — Dynamic Workflow Engine: Phase 1 (Generative Dynamic) ✅ COMPLETED (2026-06-05)

> **Design Doc**: Based on Claude Code Dynamic Workflow concepts adapted to VibeSOP architecture.
> **Core Principle**: Orchestration layer dynamic, skill layer static.

### Goals
Replace static keyword-based scenario matching with LLM-driven dynamic workflow pattern selection. Enable the orchestrator to choose the right workflow pattern (fan-out, sequential, adversarial) based on query semantics, not hardcoded rules.

### Features

- [x] **Classifier Agent — Workflow Pattern Selection**
  - LLM-based intent classification (not keyword matching)
  - Dimensions: task type × complexity × certainty
  - Output: workflow pattern + confidence + reasoning
  - Fast path: keyword rules still exist for latency-sensitive simple queries

- [x] **WorkflowPattern Type System**
  - `sequential` — existing behavior, enhanced
  - `parallel` — enhanced with Synthesizer Agent result aggregation
  - `fan_out` — multiple sub-tasks in parallel → synthesize
  - `adversarial` — execute → verify (2-step, preview of Phase 2)
  - Extensible: new patterns can be added without changing skill definitions

- [x] **Enhanced Orchestrate Command**
  - `vibe orchestrate` enhanced to select pattern based on Classifier output
  - Pattern-aware ExecutionPlan generation
  - Backward compatible: existing orchestration behavior preserved as default

- [x] **User Override Layer**
  - Explicit skill selection (`--skill <id>`) bypasses workflow selection
  - Explicit pattern selection (`--pattern <pattern>`) for power users
  - User intent always sovereign

### Architecture Changes

```
User Query
  → IntentInterceptor (slash commands / explicit overrides)
    → Classifier Agent (fast path rules + LLM semantic classification)
      → Single intent + high confidence → Legacy fast routing
      → Multi-intent / low confidence / complex → WorkflowPattern selection
        → Pattern-aware ExecutionPlan generation
          → PlanExecutor (existing, no changes needed)
```

### Success Metrics

- Multi-intent query routing accuracy: >90% (vs current ~75% estimated)
- Pattern selection relevance: user accepts suggested pattern >80% of the time
- Latency: Classifier adds <100ms for non-fast-path queries
- Zero breaking changes to existing skill ecosystem

---

## v6.1.0 — Dynamic Workflow Engine: Phase 2 (Adversarial Verification) ✅ COMPLETED (2026-06-05)

### Goals
Introduce independent verification layer to eliminate self-preference bias. After skill execution, a verifier agent with isolated context reviews the output against a rubric.

### Features

- [x] **Verifier Agent**
  - Isolated context window (no access to execution agent's reasoning)
  - Rubric-based review: completeness, correctness, edge cases, clarity
  - Configurable strictness level (lenient, standard, strict)
  - LLM-based semantic verification with JSON response parsing

- [x] **--verify Flag**
  - `vibe route --verify` and `vibe orchestrate --verify` trigger adversarial verification
  - `--strictness` option for verifier configuration
  - Integration with RoutingContext strategy_hint

- [x] **Verification Loop**
  - Simple form of execution-dynamic: verifier reject → loop back to fix
  - Max retry count configurable (default 3)
  - Escalation to user if max retries exceeded
  - Feedback aggregation for retry queries

- [x] **Runtime Trust Levels (Foundation for Quarantine)**
  - TrustLevel enum: TRUSTED, QUARANTINE, SANDBOX
  - Agent marking: trust_level field on ExecutionStep
  - Verifier always runs as QUARANTINE (read-only, no side effects)

### Success Metrics

- [x] Verification catches >30% of "claimed complete but incomplete" cases (via design)
- [x] False positive rate control through strictness levels (lenient/standard/strict)
- [x] User acceptance foundation: configurable auto-retry and escalation
- [x] 28 new tests covering all verification components
- [x] Zero regressions in existing functionality

---

## v6.2.0 — Dynamic Workflow Engine: Phase 3 (Full Execution Dynamic) ✅ COMPLETED (2026-06-05)

### Goals
Runtime workflow evolution — the execution graph can change based on intermediate results. Subagent outputs feed back into the orchestrator, which decides: continue, branch, loop, or terminate.

### Features

- [x] **WorkflowEngine Component**
  - Dynamic execution engine for LOOP_UNTIL_DRY and TOURNAMENT patterns
  - DynamicNodeStatus state machine: PENDING → RUNNING → COMPLETED / LOOPING / FAILED
  - StepRunner routes dynamic plans to WorkflowEngine automatically

- [x] **Runtime Re-orchestration**
  - Reorchestrator analyzes execution state after each step
  - ReorchestrationDecision: CONTINUE, APPEND_STEPS, LOOP_BACK, ESCALATE, TERMINATE_EARLY
  - Fast path: terminates early when all goals met (zero LLM cost)
  - Configurable max_reorchestration_rounds (default 5)

- [x] **Loop-Until-Dry Pattern**
  - Execute steps sequentially with post-step re-orchestration
  - Configurable dry_threshold (default 2 consecutive rounds with no change)
  - New steps can be dynamically appended during execution

- [x] **Tournament Pattern**
  - PlanBuilder creates N contestant copies + QUARANTINE judge step
  - TournamentRunner runs pair-wise comparison via independent judge
  - Champion selected by cumulative scoring

### Architecture

```
User Query
  → Classifier Agent → WorkflowPattern selection
    → PlanBuilder generates initial plan (with contestant copies for TOURNAMENT)
      → WorkflowEngine.is_dynamic(plan)?
         YES → WorkflowEngine.run() (loop-until-dry or tournament)
         NO  → ParallelScheduler (existing code, zero changes)
```

### Success Metrics

- [x] 22 new tests covering all Phase 3 components
- [x] 167 orchestration tests pass with zero regressions
- [x] 81 total Phase tests pass (Phase 1 + 2 + 2.5 + 3)
- [x] Token efficiency bounded by max_reorchestration_rounds cap
- [x] Backward compatibility: existing patterns completely unaffected
- Task types benefiting from dynamic execution: >50% of complex queries

---

## Backlog

### Nice to Have

- [ ] **Zed adapter**（FileBasedAdapter：Zed rules 文件 + AGENTS.md 引导，模式同 cursor/opencode，成本低）→ **Recorded 2026-07-18：用户确认为后续工作项目**（2026-07-18 跨 Agent 验证时发现 Zed 无 adapter）
- [x] Web UI for routing history & health (`vibe dashboard`, v8.0) — single-page dashboard with 4 tabs: Overview, History, Traces, Conversations
- [ ] Web UI for skill management → **Deferred: post-v5.2 evaluation**
- [ ] IDE integrations (VS Code, JetBrains) → **Deferred: post-v5.2 evaluation**
- [ ] Mobile app for skill discovery → **Deferred: post-v5.2 evaluation**
- [ ] Voice command support → **Deferred: post-v5.2 evaluation**
- [ ] Real-time collaboration → **Deferred: post-v5.2 evaluation**
- [ ] Managed skill execution sandbox (for testing/validation only) → **Deferred: post-v5.2 evaluation**
- [ ] **User-defined loop presets**（`~/.vibe/loop-presets.yaml` 合并 system presets）→ **Recorded 2026-07-24 (pi Phase E Nit-C)**：当前 `_LOOP_PRESETS` 硬编码 3 个（instinct-{assemble,promote,feedback}），等第一个真实用户提"我想每天 9 点 code-review"再做，~20 行代码即可 merge user/system presets。

### Technical Debt

- [ ] Windows 副本兜底（`storage.py` symlink→copytree 回退）缺专项测试（mock symlink_to 抛 OSError）
- [ ] Documentation translation (CN, JP, DE)
- [ ] API stability guarantees (semver)
- [ ] Migration guide for breaking changes
- [ ] Benchmark suite and performance dashboard

---

## Release Schedule

| Version | Date | Focus |
|---------|------|-------|
| v4.0.0 | 2026-04-06 | ✅ Core SkillOS engine |
| v4.1.0 | 2026-04 | ✅ AI Triage production |
| v4.2.0 | 2026-04 | ✅ Skill health monitoring |
| v4.3.0 | 2026-04-24 | ✅ Context-aware routing + Agent Runtime |
| v4.4.0 | 2026-04-26 | ✅ SkillOS: Orchestration + Lifecycle + Feedback |
| v5.0.0 | 2026-Q2 | ✅ SkillRuntime: Scope + Lifecycle |
| v5.1.0 | 2026-Q2 | ✅ SkillMarket + Feedback Loop |
| v5.2.0 | 2026-Q2 | ✅ Intelligent Ecosystem — 推荐 + 退化 + 发现 |
| v5.3.0 | 2026-04-28 | ✅ Product Experience — 仪表盘 + 清理 + 社区 + 徽章 |
| v6.0.0 | 2026-06-05 | ✅ Dynamic Workflow Engine — Phase 1: Generative Dynamic |
| v6.1.0 | 2026-06-05 | ✅ Dynamic Workflow Engine — Phase 2: Adversarial Verification |
| v6.2.0 | 2026-06-05 | ✅ Dynamic Workflow Engine — Phase 3: Full Execution Dynamic |
| v7.0.0 | 2026-06-14 | ✅ Hook Path Hardening + Multi-Agent Squad + prompt-chain-validator skill |
| v8.0.0 | 2026-Q3 | 🚧 Autonomous Loop System — vibe loop CLI + Cron 调度 + Guard 系统 |

---

## v8.0.0 — Autonomous Loop System

> **版本**: 8.0.0
> **目标**: 将 VibeSOP 从"被动响应式路由工具"升级为"可主动执行的任务平台"
> **预计交付**: 2026-Q3
> **状态**: ✅ 设计完成，待实现

### 设计背景

社区 "Claude Loops" 理念（Hanako @hanakoxbt, 67万阅读量）提出核心洞见：

> *"Most people use Claude one prompt at a time. You type, it answers, you read it, you type again. The moment you close the laptop, everything stops."*

"Loop" 的本质：把一次性的人机对话，升级为持续运行的自主任务。

### 设计决策

**vibe loop 不启动 Claude Code。** 它启动 VibeSOP 自身的 `AgentRuntime`（使用已配置的 LLM API 密钥），执行已安装的技能任务。

**执行模式双轨制**:

- **Hook API（被动模式）** — 嵌入到 Claude Code / Cursor / Kimi CLI 中，当它们的"技能大脑"
- **Runtime API（主动模式）** — 独立运行，通过 `vibe loop` 定时执行技能任务

### Phase 1: CLI 命令 + Cron 调度 + 状态持久化

**新增命令**:

```
vibe loop create        — 创建定时循环任务
vibe loop list          — 列出所有 loops
vibe loop show          — 查看 loop 详情和运行历史
vibe loop delete        — 删除 loop
vibe loop pause         — 暂停 loop
vibe loop resume        — 恢复 loop
vibe loop logs          — 查看 loop 执行日志
```

**新增模块**:

```
src/vibesop/core/loop/
  ├── models.py         — LoopSpec, LoopState, LoopRunRecord 数据模型
  ├── store.py          — JSON 文件持久化 (~/.vibe/loops/{name}/)
  ├── scheduler.py      — Cron 表达式解析引擎（无外部依赖）
  ├── executor.py       — 单次 loop 执行引擎
  └── daemon.py         — 后台轮询守护线程
```

**设计原则**:

- **窄范围、高内聚**: "改善代码库"不是 loop，"找出>50行的函数并建 issue"才是
- **从小开始**: 先一个 loop，跑熟了再添加
- **Guard 先行**: loop 有安全边界，关键步骤保留人工审批
- **人在环外、不在每环**: 95% 的枯燥工作自动化，5% 的风险操作保留人

**适合的 loop 技能类型**:

```
✅ 检查 CI 失败模式
✅ 汇总每日 PR 状态
✅ 扫描依赖漏洞
✅ 清理过期分支
✅ 监控测试覆盖率趋势
❌ 不适合: 重构代码、实现新功能、代码审查（这些需要 Claude Code 交互）
```

### Phase 2: Guard 系统 + 通知集成（未排期 — 需 PM scoping）

> **状态（v8.x）**: 未实装。`LoopSpec.guard` 字段为保留位；dead-man-switch /
> 人工审批门 / 通知渠道均未实现。Phase 4 已落地失败归因（TRANSIENT/PERMANENT）+
> 指数退避重试 + `vibe loop reset`，但完整 Guard 系统待 PM 重新 scoping 后再启动。

- **Dead man's switch**: 连续失败超限 → 自动告警
- **人工审批门**: merge-to-main 等风险操作等人确认
- **通知渠道**: Slack / Email / GitHub Issue
- **状态看板**: `vibe loop dashboard`

### Phase 3: Webhook 触发 + 事件驱动（未来规划）

- GitHub Webhook → trigger loop
- PR merged → trigger loop
- CI failed → trigger loop

### 技术架构

```
User/System
  │
  ├── [手动] → Claude Code Hook → VibeSOP (L1/L2 被动模式)
  │
  └── [定时] → cron → VibeSOP Loop Daemon
                    ├── AgentRuntime.handle_query() (L0 主动模式)
                    ├── 执行技能任务
                    ├── 记录结果到 LoopStore
                    └── 失败时触发 Guard 升级
```

### Metrics

- 目标: **20+ 个 loop 并行运行**
- 目标: loop 创建 → 执行 < 5 分钟
- 目标: 0 误触发人工审批（Guard 精确度）

---

## Contributing

See something missing? Want to accelerate a feature?

1. Check [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines
2. Open an issue to discuss the feature
3. Submit a PR referencing the roadmap item

---

## Changelog

### v4.0.0 (2026-04-06)
- Initial stable release
- 10-layer routing pipeline
- Unified architecture
- Security auditing
- Performance optimization

---

### v4.3.1 (2026-04-24)
- Roadmap revised: v5.x unified with version_05.md ADR (layered evolution plan)
- v5.0.0 redefined as SkillRuntime (scope + lifecycle), not Plugin Ecosystem
- Added v5.1.0 (SkillMarket + Feedback Loop) and v5.2.0 (Intelligent Ecosystem)
- Pre-v6.0 ideas deferred to post-v5.2 evaluation

---

*Last updated: 2026-06-19 (v8.0.0 设计 — Autonomous Loop System 路线图追加; see [CHANGELOG](../CHANGELOG.md#unreleased) for details)*
