---
id: builtin/deep-diagnosis-optimization
name: deep-diagnosis-optimization
description: >-
  Systematic codebase diagnosis → prioritized batch optimization → kimi+container
  triple verification → CI green → merge to main. A proven end-to-end workflow
  for deeply auditing a codebase, fixing issues by severity, and landing them
  with full CI green — using dynamic workflows, kimi code review, and arm64
  container e2e validation.
tags: [diagnosis, optimization, workflow, ci, verification, kimi, docker,
       诊断, 优化, 审查, 审计, 代码质量]
triggers:
  - "deep diagnosis"
  - "diagnose and optimize"
  - "audit and fix"
  - "全面诊断"
  - "深度诊断"
  - "优化项目"
  - "make CI green"
  - "CI 全绿"
  - "diagnose the codebase"
  - "/deep-diagnosis-optimization"
version: 1.0.0
allowed-tools:
  - Agent
  - Bash
  - Read
  - Write
  - Edit
  - Workflow
intent: >-
  Run a multi-phase deep diagnosis of a codebase, fix findings in prioritized
  batches, verify each fix with kimi review + container e2e, achieve fully green
  CI, and merge to main — a repeatable, battle-tested optimization workflow.
namespace: builtin
type: prompt
---

# Deep Diagnosis → Optimization → Verification → CI Green → Merge

A proven end-to-end workflow for auditing, fixing, and landing code changes with
full CI green. Developed and validated on the VibeSOP v8.0.0-dev optimization
(12 PRs, 200+ findings fixed, CI from fully-red to fully-green).

## Prerequisites

### Tooling

```bash
# Kimi code review (NOT on PATH — use full path)
KIMI=/Users/huchen/.kimi-code/bin/kimi
# Invoke: $KIMI -p "<review prompt with diff>" --output-format text

# Container e2e (OrbStack — arm64 native, NO Rosetta needed)
DOCKER="$HOME/.orbstack/bin/docker"
# Verify: orb status (must be "Running")
# If stopped: orb start (or open the OrbStack app)
# If Rosetta missing: softwareupdate --install-rosetta --agree-to-license
```

### Base Image (one-time)

Build a validation base image with all deps pre-baked (avoids repeated installs):

```dockerfile
# docker/val-base.Dockerfile
FROM --platform=linux/arm64 python:3.12-slim
# ... install system deps, node+bun (for pack e2e), uv
COPY pyproject.toml uv.lock ./
RUN uv sync --extra dev --frozen --no-install-project
WORKDIR /repo
CMD ["bash"]
```

```bash
docker build -f docker/val-base.Dockerfile -t vibesop-val-base:py3.12 .
```

Per-feature validation:
```bash
$DOCKER run --rm -v "$PWD":/repo -w /repo vibesop-val-base:py3.12 \
    uv run --frozen pytest <target> --no-header -q
```

## Phase 1 — Deep Diagnosis (Dynamic Workflow)

Fan out parallel agents to map + diagnose + cross-cut audit the codebase.

### Workflow structure

```
Map (10 agents)     → map each subsystem's purpose + smells
Diagnose (pipeline) → critical diagnosis per subsystem (map→diagnose per item)
Cross-cut (6 agents) → architecture, correctness, security, tests, ops, integration
Synthesize (1 agent) → senior-engineer professional opinion + prioritized findings
```

### Key patterns

- **Pipeline** map→diagnose per subsystem (no barrier between stages).
- **Barrier** before cross-cut (needs all diagnoses for dedup).
- **Adversarial verify** for security findings (spawn skeptics, default to refuted).
- **Schema output** for structured findings (severity, category, file:line, evidence).

### Output

A structured report with:
- Executive summary + overall grade
- Critical/high/medium findings (deduplicated, with file:line)
- Architectural assessment
- Prioritized action plan (P0/P1/P2)

## Phase 2 — Batch Optimization

Break findings into atomic batches by severity:

```
P0 (release-blocking): critical security + critical ops
P1 (important):       high correctness + governance
P2 (maintenance):     CI quality gates + tech debt
```

### Per-batch workflow

```
implement (I control the edit)
    ↓
kimi review ($KIMI -p "<diff + context + focus>" --output-format text)
    ↓
host pytest (uv run pytest <targets>)
    ↓
container e2e ($DOCKER run ... uv run --frozen pytest <targets>)
    ↓
commit (conventional commit message + Co-Authored-By trailer)
```

### kimi review value

kimi catches things parallel verifiers miss:
- Orphaned YAML keys (structural corruption invisible to parse-success checks)
- Shared-mutable-state leaks (ClassVar mutation)
- Substring-vs-exact-match bugs (`*/2` vs bare `*`)
- Unused-noqa directives (misplaced suppression)
- Parallel injection bypasses (orchestration path vs injector path)

Always pass the FULL diff + context. kimi's value is the independent perspective.

## Phase 3 — CI Green

Make all CI jobs pass. Common patterns (battle-tested):

### Dev-dep unification

```toml
# pyproject.toml — SINGLE source for dev deps
[project.optional-dependencies]
dev = [...]  # ALL dev tools here (ruff, pytest, mypy, etc.)
# DELETE [dependency-groups].dev — it diverges and breaks CI
```

CI uses `uv sync --extra dev` (not bare `uv sync`).

### pytest version bump (CVE fix)

```toml
"pytest>=9.0.3,<10.0.0",  # fixes CVE-2025-71176 (was <9.0.0)
"pytest-asyncio>=1.0.0,<2.0.0",  # 1.x required for pytest 9
```

### Coverage DataError fix

```toml
# [tool.coverage.run]
# REMOVE `parallel = true` — with branch=true it causes
# "Can't combine statement coverage data with branch data"
```

CI test command needs `--cov-branch` (aligns pytest-cov with config):
```yaml
run: uv run pytest -m "not benchmark and not slow" --cov=src/vibesop --cov-branch --cov-fail-under=73
```

### Flaky test exclusion

CI test command: `-m "not benchmark and not slow"` (matches Makefile).
Mark perf tests: `pytestmark = pytest.mark.slow` at module level.

### basedpyright exit-code fix

basedpyright exits 3 for warnings-only (unlike pyright which exits 0).
The project sets many rules to "warning" (advisory). Accept exit 3:

```yaml
run: uv run basedpyright || [ $? -eq 3 ]  # accept 0 (clean) or 3 (warnings)
```

### ruff lint sweep

```bash
ruff check --fix --unsafe-fixes .   # auto-fix safe + unsafe (review diff)
ruff format .                        # format
ruff check .                         # verify clean
```

For remaining manual errors, categorize by rule + apply per-rule playbook.
For ARG (unused interface args): inline `# noqa: ARG00x` (don't remove).
For E402 (lazy imports): inline `# noqa: E402` (intentional).

### Bandit false positives

For justified findings, add inline `# nosec BXXX  # <reason>`.
For TOML-template misidentified as SQL: add B608 to CI `--skip`.

### pip-audit CVEs

Bump affected deps:
```toml
"idna>=3.15",                      # PYSEC-2026-215
"pydantic-settings>=2.14.2,<3.0.0", # GHSA-4xgf-cpjx-pc3j
```

## Phase 4 — Merge

### PR workflow

```bash
git checkout -b fix/<description>     # branch off main
# ... implement + verify + commit ...
git push -u origin fix/<description>
gh pr create --base main --title "..." --body "..."
```

### Poll CI + merge

```bash
RUN=$(gh run list --branch <branch> --limit 1 --json databaseId --jq '.[0].databaseId')
# poll until completed
gh run view $RUN --json jobs --jq '.jobs[] | "\(.name): \(.conclusion)"'
# merge when all green
gh pr merge <PR#> --rebase --delete-branch
```

### Commit cadence

- One commit per verified fix (atomic, conventional commit message).
- End with: `Co-Authored-By: Claude <noreply@anthropic.com>`
- Commit each batch immediately after verification (don't accumulate).

## Anti-Patterns (Avoided)

- ❌ Bulk `ruff --add-noqa` (hides real issues — fix or targeted-noqa with reason).
- ❌ Silently lowering coverage gate below actual (calibrate to the marker-filtered suite).
- ❌ Skipping container e2e (host env can mask CI-specific failures).
- ❌ Skipping kimi review (it catches what parallel verifiers miss — every time).
- ❌ Using `git add -A` blindly (session artifacts like `.vibe/prompts/` leak — gitignore them).
- ❌ Force-pushing without `--force-with-lease` (safer than `--force`).

## Execution Notes

- **Branch per batch** off main (never commit directly to main).
- **kimi path**: `/Users/huchen/.kimi-code/bin/kimi` (not on PATH).
- **Docker path**: `$HOME/.orbstack/bin/docker` (not on PATH).
- **arm64 native**: use `--platform=linux/arm64` (no Rosetta needed on Apple Silicon).
- **Container freshness**: each `docker run --rm` is a fresh container (no stale state).
- **`uv run --frozen`**: uses the lock exactly; mount the repo for live-code validation.
- **Base image rebuild**: needed when `pyproject.toml`/`uv.lock` change (deps shift).
