# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-05-24 (S6) pi-skill-conflict-fix
**Session**: 修复 pi agent 启动时的技能冲突警告 (技能名非法字符 + 重复目录)
**Completed**:
- 27 个 gstack/superpowers SKILL.md name 字段 `/` → `-` (规范化为 lowercase a-z, 0-9, hyphens)
- 删除 14 个因名称冲突被跳过的重复技能目录
- 验证: 126 skills, 零冲突, 零非法字符
**Files**: 27 SKILL.md edited, 14 directories removed (~/.pi/agent/skills/)
### 2026-05-24 (S5) pi-agent-adapter
**Session**: Full Pi Coding Agent (pi) platform adapter implementation
**Completed**:
- Created PiCodingAgentAdapter with full PlatformAdapter interface (15 methods)
- 16 Jinja2 templates for Pi config (AGENTS.md, extensions, skills, prompts, docs, settings)
- 15 pi targets added to core/registry.yaml (parity with claude-code)
- TypeScript extensions for route interception (vibesop-route.ts, vibesop-track.ts)
- Fixed runtime bug: RouteResult interface matched to actual vibe route --json output
- Fixed settings.json paths to resolve correctly relative to .pi/
**Key Decisions**:
- Pi uses AGENTS.md (project root) instead of CLAUDE.md (~/.claude/)
- Pi uses TypeScript extensions instead of shell hooks for event interception
- Pi uses prompt templates (.pi/prompts/) instead of slash commands
- Project-local .pi/ directory chosen over global ~/.pi/agent/ for per-project deployment
- skills/ paths written relative to .pi/ per Pi's settings resolution rules
**Files**: 1 adapter + 16 templates + 5 modified (registry, init, renderer, hooks, registry_sync)

---

### 2026-05-24 (S4) config-dedup
**Session**: Clean up duplicate content between system-level and project-level CLAUDE.md/AGENTS.md
**Completed**:
- Removed routing/tool-env/lifecycle/quick-commands from project-level CLAUDE.md and AGENTS.md
- Updated CLAUDE.md.project.j2 template (removed tool_environment + routing sections)
- System-level ~/.claude/CLAUDE.md now sole source for tool env, routing, lifecycle, quick commands
**Key Decisions**:
- CLAUDE.md.project.j2 no longer emits tool_environment or routing — these are system-level concerns
- AGENTS.md slimmed to multi-platform index (other platforms get full config via `vibe build`)
**Files Modified**: 3 files (CLAUDE.md, AGENTS.md, CLAUDE.md.project.j2)

---

### 2026-05-24 00:40 (S3)
**Session**: Deep review + GOALS.md alignment fixes + gstack removal + engineering charter + slash-orchestrate routing fix
**Key Learnings**: Duplicate data models diverge silently; management skills need explicit routing exclusion; selective META charter adoption
**Files Modified**: 55 files
<!-- handoff:end -->
