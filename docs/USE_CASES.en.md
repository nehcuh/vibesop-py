# VibeSOP Use Cases Guide

> **Audience**: Developers new to VibeSOP who want to know "what does this thing actually do for me?"
> **What this is not**: Not a CLI reference (see [`user/CLI_REFERENCE.md`](user/CLI_REFERENCE.md)); not a philosophy doc (see [`PHILOSOPHY.md`](PHILOSOPHY.md))
> **What this is**: 12 concrete scenarios, each with "pain → approach → commands → expected output". Find the one matching your day and follow it.
>
> **中文版**: [USE_CASES.md](USE_CASES.md)

---

## What Problems VibeSOP Solves

If you've hit any of these, VibeSOP was built for you:

- "I know skill packs like superpowers / gstack / omx are powerful, but **I can't memorize 50+ commands**"
- "I installed skills in Claude Code, **switched to Cursor and had to reinstall everything**"
- "Team of 5, each person fumbling through the same workflows, **reinventing the same wheels**"
- "CI went red after hours, **nobody noticed until next morning** — 8 hours of broken builds"
- "I want to do 'analyze code + write tests + write docs' as **one multi-step task**, but I always skip a step"
- "I installed a bunch of skills and don't use them — **6 months later I forgot which were useful**"

VibeSOP = **SkillOS** (Skill Operating System) + **Loop Engine** (autonomous task engine). It manages the **full lifecycle** of skills in AI-assisted development: discovery → install → routing → orchestration → autonomous execution → evaluation → retention/deprecation.

---

## Five Categories at a Glance

| Category | Problem Solved | Key Command | Capability Layer |
|---|---|---|---|
| **1. Daily dev** | Can't remember commands | `vibe route "<intent>"` | L1 routing injection |
| **2. Complex tasks** | Multi-step easy to miss | `vibe route --guided "<complex>"` | L2 orchestration |
| **3. Cross-platform** | Reinstall on tool switch | `vibe install <pack>` | Cross-platform adapter |
| **4. Autonomous monitoring** | Nobody watching after hours | `vibe loop create ...` | L0 autonomous exec |
| **5. Lifecycle** | Skills pile up messy | `vibe skill stale` / `cleanup` | Lifecycle management |

---

## Category 1: Daily Development (most common)

### Case 1: Debugging a Weird Crash

**Pain**: Your Python service throws `RuntimeError: coroutine was never awaited`. You don't recognize this common asyncio pitfall. Claude Code by default analyzes from scratch — but you have `systematic-debugging` from the superpowers pack installed. The problem is **you forgot it exists and what its command is**.

**VibeSOP approach**: Just state your intent. VibeSOP routes to the right skill and injects the SKILL.md content into the agent's context.

**Commands**:
```bash
# In Claude Code, just say:
debug this RuntimeError: coroutine was never awaited in my FastAPI endpoint

# Or trigger routing explicitly from CLI:
vibe route "debug asyncio coroutine never awaited error"
```

**Expected output** (auto-injected by Claude Code hook):
```
🎯 VibeSOP routed: superpowers/systematic-debugging (94% confidence)

NEXT STEP (MANDATORY): read skills/superpowers-systematic-debugging/SKILL.md
Do NOT proceed without reading this file.

[ACTIVE SKILL: superpowers/systematic-debugging]
You MUST follow this skill's workflow. Do not skip steps.
... (full SKILL.md content) ...
```

**Why this matters**: The agent now follows systematic-debugging's 6-phase flow (reproduce → minimise → hypothesise → instrument → fix → regression-test) instead of guessing.

---

### Case 2: Writing Tests (TDD)

**Pain**: You want to write tests for a new function but **forgot how the TDD red-green loop** actually starts.

**VibeSOP approach**:

**Commands**:
```bash
# In Claude Code:
write tests for src/auth/token.py using TDD approach

# Or via CLI:
vibe route "write TDD tests for src/auth/token.py"
```

**Expected**: Routes to `superpowers/test-driven-development`. The agent will write failing test → run → implement → run-green → refactor.

---

### Case 3: Code Review (Multi-Dimensional)

**Pain**: You want AI to review your PR but **don't know which review angles exist** (security? performance? readability?).

**VibeSOP approach**: Trigger a multi-role Squad — implementer + reviewer + red-team.

**Commands**:
```bash
vibe route --guided "review PR #234 across security, performance, and readability dimensions"
```

**Expected**: VibeSOP detects "three dimensions" as a multi-role query, auto-enters MULTI_AGENT_SQUAD mode, assigns three agents one dimension each, aggregates at the end.

---

## Category 2: Complex Task Orchestration

### Case 4: Architecture Analysis + Test Generation + Documentation (End-to-End)

**Pain**: You inherited an old project. You need to **simultaneously** do three things: understand architecture, add tests, update docs. Doing them sequentially is error-prone, and each step needs a different skill.

**VibeSOP approach**: One sentence triggers a 3-step orchestration plan.

**Commands**:
```bash
vibe route --guided "analyze src/payment/ module architecture, add unit tests, update README"
```

**Expected output**:
```
🔀 VibeSOP detected multiple intents. Execution plan injected.

Plan:
  Step 1: superpowers/architect → analyze src/payment/ structure
  Step 2: superpowers/test-driven-development → cover gaps
  Step 3: mattpocock/write-docs → update README

Strategy: sequential (each step's output feeds the next)
```

The agent walks through the plan; each step's context carries the previous step's output.

---

### Case 5: Cross-Skill Workflow (Cross-Cutting)

**Pain**: Every new feature ships through "PR → code review → security audit → deploy". **Manually chaining 4 skills** is easy to forget.

**VibeSOP approach**: Define once, invoke repeatedly.

**Commands**:
```bash
# Define once (team shares via git)
vibe workflows create release-pipeline \
  --steps "create-pr, code-review, security-audit, deploy"

# Each new feature, one sentence triggers the full pipeline
vibe route "run release-pipeline workflow for feature/payment-v2"
```

The workflow definition lives in `.vibe/skills/cross-cutting/release-pipeline/SKILL.md`, git-tracked, team-shared.

---

## Category 3: Cross-Platform Skill Management

### Case 6: Multi-Agent Workflow (Claude Code + Cursor + Kimi CLI)

**Pain**: You use Claude Code at work, Cursor at home, Kimi CLI for cross-language tasks. Each tool's skills directory differs:
- Claude Code: `~/.claude/skills/`
- Cursor: `~/.config/cursor/skills/`
- Kimi CLI: `~/.kimi-code/skills/`

Manually maintaining 3 copies is a nightmare.

**VibeSOP approach**: Central storage + symlinks.

**Commands**:
```bash
# Install once, auto-distribute to all platforms
vibe install superpowers

# Specify which platforms receive
vibe config set platforms.install_targets '["claude-code", "cursor", "kimi-cli"]'

# Verify
vibe verify
```

**Result**:
```
~/.config/skills/superpowers/         ← central storage (actual files)
~/.claude/skills/superpowers          ← symlink
~/.config/cursor/skills/superpowers   ← symlink
~/.kimi-code/skills/superpowers       ← symlink
```

Any agent can route to the same skill content.

---

### Case 7: Team-Shared Skill Configuration

**Pain**: Team of 5, each installing superpowers, gstack, omx on their own machine. New hires spend an hour configuring.

**VibeSOP approach**: Commit `.vibe/` to git.

**Commands**:
```bash
# After team lead configures:
git add .vibe/config.toml .vibe/skills/cross-cutting/
git commit -m "feat: team skill baseline"

# New hire after cloning:
vibe install --auto      # one-click install of team-selected packs
vibe verify              # verify environment
```

5 minutes from zero to productive for new hires.

---

## Category 4: Autonomous Monitoring (v8.0 Loop System)

### Case 8: CI Failure Auto-Diagnosis (Classic)

**Pain**: You leave work, your PR triggers CI, CI goes red at 2am. **Next morning at 9am you discover it** — 7 hours of broken state.

**VibeSOP approach**: Create a loop that checks CI every 30 minutes; on failure, uses the systematic-debugging skill to diagnose and create an issue.

**Commands**:
```bash
# Create the loop
vibe loop create ci-watcher \
  --skill systematic-debugging \
  --schedule "*/30 * * * *" \
  --desc "Check CI status every 30 min; diagnose on failure"

# Configure external scheduler (macOS launchd example — see docs/loop-setup-guide.md)
launchctl load ~/Library/LaunchAgents/com.vibesop.looptick.plist

# Check status
vibe loop show ci-watcher
```

**Expected**: Within 30 minutes of CI going red, the loop fires, systematic-debugging auto-analyzes the failure log, results land in `~/.vibe/loops/ci-watcher/state.json`. Morning glance tells you what broke overnight.

---

### Case 9: Daily PR Status Digest

**Pain**: Every morning you open GitHub to check 10+ open PRs (CI status, review progress, conflicts). **Repetitive grind**.

**VibeSOP approach**: Auto-run once a day at 9am, output to Slack or file.

**Commands**:
```bash
vibe loop create daily-pr-digest \
  --query "summarize today's open PRs: CI results, review progress, conflicts" \
  --schedule "0 9 * * *" \
  --desc "Daily 9am PR status digest"
```

`--query` mode goes through the full 4-stage routing cascade (unlike `--skill` which is explicit) — perfect for "I don't know which skill fits, let VibeSOP pick".

---

### Case 10: Dependency Vulnerability Scanning

**Pain**: Dependabot opened 4 PRs and you don't know **which is urgent and which can wait**.

**VibeSOP approach**:

**Commands**:
```bash
vibe loop create deps-scan \
  --query "scan project dependencies for vulnerabilities; rank dependabot PRs by severity" \
  --schedule "0 8 * * 1" \
  --desc "Every Monday 8am dependency security scan"
```

Fires every Monday 8am, outputs "PR #234 (high severity, RCE) > PR #235 (medium) > ...".

---

## Category 5: Skill Lifecycle Management

### Case 11: Cleaning Up Stale Skills

**Pain**: Six months ago you installed a bunch of skills. Now you don't know **which are still used and which can be deleted**.

**VibeSOP approach**: Auto-tracks usage frequency, grades A-F, auto-archives expired ones.

**Commands**:
```bash
# See which skills are idle
vibe skill stale

# Interactive cleanup
vibe skill cleanup

# Fully automatic (90 days unused + D/F grade → archive)
vibe skill cleanup --auto
```

**Expected output**:
```
📋 Skill Health Report:
  ✅ superpowers/systematic-debugging  Grade A  47 uses/month
  ⚠️  gstack/old-helper                  Grade D  1 use/month   (suggest archive)
  ❌ mattpocock/experimental             Grade F  90 days idle  (archived)
```

---

### Case 12: Auto-Generate Skills From Your Work Patterns

**Pain**: You notice you **repeatedly** run the same tool sequence (e.g., "git diff → analyze changes → write commit message") but never thought to固化 it as a skill.

**VibeSOP approach**: InstinctLearner auto-detects repeat patterns.

**Commands**:
```bash
# See learned "instincts"
vibe instinct status

# Promote high-confidence instincts to正式 skills
vibe instinct evolve --threshold 0.8

# Generated skills land in .vibe/skills/auto/, edit then publish
```

**Expected**: System notices you ran the same 4-step sequence 23 times in 30 days, auto-generates `auto/commit-with-context` skill. Next time you say "commit code" it routes there directly.

---

## What VibeSOP Is NOT (Boundary Clarification)

VibeSOP is **not** the following tools. Forcing it into these roles is inefficient:

| ❌ Not suited for | Why | Use instead |
|---|---|---|
| Large-scale code generation | That's the L3 layer's job | Claude Code / Cursor directly |
| Real-time chat collaboration | Not an IM tool | Slack / Discord |
| Long-running tasks (>1 hour) | Loop v1 doesn't support | CI/CD pipeline |
| GUI-required workflows | CLI only | IDE plugins |
| Modifying skill content | VibeSOP doesn't author skill content | Find the skill pack author |
| High-risk ops like DB migrations | No Guard system yet (v8.1) | Manual + human review |

---

## Recommended Adoption Path

### Day 1: Single-platform pilot
```bash
vibe install superpowers           # install 1 pack
vibe route "debug this error"      # try L1 routing
vibe route --explain               # see routing decision tree
```

### Week 1: Cross-platform rollout
```bash
vibe install gstack omx            # more packs
vibe config set platforms.install_targets '["claude-code", "cursor"]'
vibe verify                        # verify multi-platform
```

### Month 1: Orchestration + team sharing
```bash
vibe route --guided "analyze+test+document"   # L2 orchestration
vibe workflows create release-pipeline          # cross-skill workflow
git add .vibe/ && git commit                    # team sharing
```

### Month 2+: Autonomy
```bash
vibe loop create ci-watcher ...        # L0 autonomous monitoring
vibe skill stale                       # lifecycle management
vibe instinct status                   # pattern learning
```

---

## Next Steps

- **Want to install skills**: [`SKILLS_GUIDE.md`](SKILLS_GUIDE.md) details 50+ built-in skills
- **Want cross-platform**: [`QUICKSTART_USERS.md`](QUICKSTART_USERS.md) install guide
- **Want loops**: [`loop-setup-guide.md`](loop-setup-guide.md) 24-hour deployment
- **Want the philosophy**: [`PHILOSOPHY.md`](PHILOSOPHY.md) design rationale
- **Want the roadmap**: [`ROADMAP.md`](ROADMAP.md) v4.x → v8.0

Specific scenario not covered here? Open an issue; we'll add it to the next revision.
