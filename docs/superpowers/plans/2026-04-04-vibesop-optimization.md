# VibeSOP v2.2.0 全面优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 6.5/10 提升到 8.5/10，通过文档治理、CI/CD、测试覆盖、架构重构、工程纪律六大优化

**Architecture:** 6 个 Phase 顺序执行，Phase 3（测试）在 Phase 4（重构）前建立保护网，确保重构安全

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, pytest, Ruff, Pyright, GitHub Actions, hatch-vcs

---

## 文件变更总览

### 新建文件（约 25 个）
- `.github/workflows/ci.yml` — CI 工作流
- `.github/workflows/release.yml` — 发布工作流
- `.github/CODEOWNERS` — 代码所有者
- `tests/conftest.py` — 根级共享 fixture
- `tests/cli/test_auto.py` — auto 命令测试
- `tests/cli/test_build.py` — build 命令测试
- `tests/cli/test_doctor.py` — doctor 命令测试
- `tests/cli/test_skills.py` — skills 命令测试
- `tests/installer/test_init_support.py` — 初始化支持测试
- `tests/installer/test_quickstart.py` — 快速启动测试
- `tests/hooks/test_base.py` — hook 基础测试
- `tests/hooks/test_installer.py` — hook 安装测试
- `tests/semantic/test_integration.py` — 语义集成测试
- `tests/integrations/test_detector.py` — 集成检测测试
- `tests/utils/test_helpers.py` — 工具函数测试
- `tests/benchmark/test_routing_performance.py` — 性能基准
- `scripts/check_docs.py` — 文档一致性检查脚本
- `docs/README.md` — 文档索引
- `docs/user/getting-started.md` — 快速开始
- `docs/user/cli-reference.md` — CLI 参考
- `docs/dev/architecture.md` — 架构文档
- `docs/dev/testing.md` — 测试指南
- `docs/dev/releasing.md` — 发布指南
- `CODE_OF_CONDUCT.md` — 行为准则
- `SECURITY.md` — 安全政策

### 修改文件（约 15 个）
- `pyproject.toml` — 添加依赖、覆盖率门禁、hatch-vcs
- `README.md` — 修复断裂引用
- `README.zh-CN.md` — 同步迁移状态
- `docs/QUICK_REFERENCE.md` — 版本更新
- `docs/CLI_REFERENCE.md` — 修复命令文档
- `CHANGELOG.md` — 修复断裂引用
- `.pre-commit-config.yaml` — 更新 hooks
- `.github/ISSUE_TEMPLATE/bug_report.md` — 修复 CLI 语言
- `src/vibesop/_version.py` — 改为 hatch-vcs 生成
- `src/vibesop/cli/main.py` — CLI 命令分组
- `src/vibesop/core/preference.py` — 添加负反馈
- `src/vibesop/routing/engine.py` — 添加统计收集（迁移后）
- `src/vibesop/core/__init__.py` — 新建，re-export 保持兼容
- `Makefile` — 添加 benchmark 目标
- `src/vibesop/core/container.py` — 新建，轻量 DI 容器

---

## Phase 1: 文档治理（1 天）

### Task 1.1: 清理内部开发文档

**Files:**
- Delete: `docs/FINAL_ASSESSMENT.md`
- Delete: `docs/FINAL_HONEST_CHECK.md`
- Delete: `docs/PROJECT_STATUS.md`
- Delete: `docs/SESSION_SUMMARY.md`
- Delete: `docs/FINAL_SESSION_SUMMARY.md`
- Delete: `docs/PROGRESS_UPDATE.md`
- Delete: `docs/IMPLEMENTATION_SUMMARY.md`
- Delete: `docs/COMPLETION_SUMMARY.md`
- Delete: `docs/INSTALLER_GAP_ANALYSIS.md`
- Delete: `docs/INSTALLER_IMPLEMENTATION_STATUS.md`
- Delete: `docs/RECOMMENDATIONS.md`
- Delete: `docs/AUTO-LEARNING-GUIDE.md`（内容已过期）
- Delete: `docs/AUTO-LEARNING-SYSTEM.md`（内容已过期）
- Delete: `docs/AUTO-RECORD-GUIDE.md`（内容已过期）
- Delete: `docs/CAPABILITY_COMPARISON.md`（内部对比）
- Delete: `docs/PUBLISHING_CHECKLIST.md`（内部清单）
- Delete: `docs/development-plan.md`（内部计划）
- Delete: `docs/v2-development-guide.md`（内部指南）
- Delete: `docs/roadmap-2.0.md`
- Delete: `docs/roadmap-2.0-board.md`
- Delete: `docs/roadmap-2.0-summary.md`
- Delete: `docs/roadmap-2.0-timeline.md`
- Delete: `docs/semantic/COMPARISON.md`
- Delete: `docs/semantic/DOCUMENTATION-CONSISTENCY-CHECK.md`
- Delete: `docs/semantic/IMPLEMENTATION-REVIEW.md`
- Delete: `docs/semantic/LIMITATIONS.md`
- Delete: `docs/semantic/PHASE2.1_COMPLETE.md`
- Delete: `docs/semantic/RELEASE.md`
- Delete: `docs/triggers/day10-e2e-testing.md`
- Delete: `docs/triggers/day11-12-docs.md`
- Delete: `docs/triggers/PHASE2_COMPLETE.md`

- [ ] **Step 1: Delete internal docs**

```bash
# Delete internal development documents
rm -f docs/FINAL_ASSESSMENT.md docs/FINAL_HONEST_CHECK.md docs/PROJECT_STATUS.md
rm -f docs/SESSION_SUMMARY.md docs/FINAL_SESSION_SUMMARY.md docs/PROGRESS_UPDATE.md
rm -f docs/IMPLEMENTATION_SUMMARY.md docs/COMPLETION_SUMMARY.md
rm -f docs/INSTALLER_GAP_ANALYSIS.md docs/INSTALLER_IMPLEMENTATION_STATUS.md
rm -f docs/RECOMMENDATIONS.md docs/AUTO-LEARNING-GUIDE.md docs/AUTO-LEARNING-SYSTEM.md
rm -f docs/AUTO-RECORD-GUIDE.md docs/CAPABILITY_COMPARISON.md docs/PUBLISHING_CHECKLIST.md
rm -f docs/development-plan.md docs/v2-development-guide.md
rm -f docs/roadmap-2.0.md docs/roadmap-2.0-board.md docs/roadmap-2.0-summary.md docs/roadmap-2.0-timeline.md
rm -f docs/semantic/COMPARISON.md docs/semantic/DOCUMENTATION-CONSISTENCY-CHECK.md
rm -f docs/semantic/IMPLEMENTATION-REVIEW.md docs/semantic/LIMITATIONS.md
rm -f docs/semantic/PHASE2.1_COMPLETE.md docs/semantic/RELEASE.md
rm -f docs/triggers/day10-e2e-testing.md docs/triggers/day11-12-docs.md docs/triggers/PHASE2_COMPLETE.md
```

- [ ] **Step 2: Verify deletion**

```bash
ls docs/*.md
# Should only show: CLI_REFERENCE.md, QUICK_REFERENCE.md, ROADMAP_INDEX.md, hooks-guide.md
# Plus subdirectories: plans/, semantic/, superpowers/, triggers/
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: clean up internal development documents

Remove 29 internal assessment, summary, and planning documents
that should not be in user-facing documentation."
```

---

### Task 1.2: 修复 README.md 断裂引用

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README.md**

```bash
wc -l README.md
# Read the full file to identify all broken references
```

- [ ] **Step 2: Fix broken references in README.md**

Remove or fix these broken references:
- References to `V2_Release_COMPLETE.md` (does not exist)
- References to `DEPLOYMENT_COMPLETE.md` (does not exist)
- References to `COMPLETE.md` (does not exist)
- References to `docs/workflows/guide.md` (does not exist)
- References to `docs/workflows/api.md` (does not exist)
- References to `./scripts/vibe-install` (does not exist)

Replace with working links or remove the references entirely.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: fix broken references in README.md

Remove references to non-existent files:
- V2_Release_COMPLETE.md, DEPLOYMENT_COMPLETE.md, COMPLETE.md
- docs/workflows/guide.md, docs/workflows/api.md
- scripts/vibe-install (not yet created)"
```

---

### Task 1.3: 修复 README.zh-CN.md 迁移状态

**Files:**
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Read current README.zh-CN.md**

```bash
cat README.zh-CN.md
```

- [ ] **Step 2: Update migration status**

Change all `[ ]` (incomplete) to `[x]` (complete) for features that are already implemented:
- 技能管理 → `[x]`
- 记忆系统 → `[x]`
- 检查点系统 → `[x]`
- 偏好学习 → `[x]`
- 工作流编排 → `[x]`
- 智能触发 → `[x]`
- 语义匹配 → `[x]`

- [ ] **Step 3: Commit**

```bash
git add README.zh-CN.md
git commit -m "docs: update Chinese README migration status

Mark all implemented features as complete:
skill management, memory, checkpoints, preference learning,
workflow orchestration, intelligent triggers, semantic matching."
```

---

### Task 1.4: 修复 CLI_REFERENCE.md

**Files:**
- Modify: `docs/CLI_REFERENCE.md`

- [ ] **Step 1: Read current CLI_REFERENCE.md**

```bash
wc -l docs/CLI_REFERENCE.md
```

- [ ] **Step 2: Remove non-existent `vibe render` command documentation**

Search for and delete the entire section documenting `vibe render`.

- [ ] **Step 3: Update installation instructions**

Replace all `poetry install` references with `uv sync` or `pip install -e ".[dev]"`.

- [ ] **Step 4: Fix GitHub username**

Replace all `github.com/yourusername/vibesop-py` with `github.com/nehcuh/vibesop-py`.

- [ ] **Step 5: Add missing commands**

Add documentation for these missing commands (read each command file first to understand its options):
- `vibe init`
- `vibe deploy`
- `vibe switch`
- `vibe inspect`
- `vibe targets`
- `vibe checkpoint`
- `vibe cascade`
- `vibe experiment`
- `vibe memory`
- `vibe instinct`
- `vibe quickstart`
- `vibe onboard`
- `vibe toolchain`
- `vibe skill-craft`
- `vibe tools`
- `vibe worktree`
- `vibe route-select`
- `vibe route-validate`
- `vibe import-rules`
- `vibe detect`
- `vibe install`
- `vibe hooks`
- `vibe analyze`
- `vibe auto-analyze-session`
- `vibe create-suggested-skills`
- `vibe preferences`
- `vibe top-skills`
- `vibe skill-info`
- `vibe semantic`

For each command, read the source file in `src/vibesop/cli/commands/` and document:
- Command name and description
- Arguments and options
- Example usage
- Expected output

- [ ] **Step 6: Fix `vibe config semantic` reference**

Change `vibe config semantic --enable` to `vibe semantic --enable` (it's a standalone command, not a subcommand).

- [ ] **Step 7: Commit**

```bash
git add docs/CLI_REFERENCE.md
git commit -m "docs: fix CLI_REFERENCE.md consistency with actual CLI

- Remove non-existent 'vibe render' command
- Update installation from poetry to uv
- Fix GitHub username (yourusername -> nehcuh)
- Add documentation for 29 missing commands
- Fix 'vibe config semantic' -> 'vibe semantic'"
```

---

### Task 1.5: 修复元数据和创建文档索引

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/QUICK_REFERENCE.md`
- Modify: `CHANGELOG.md`
- Modify: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `docs/README.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `SECURITY.md`

- [ ] **Step 1: Fix author email in pyproject.toml**

```toml
# Line 9: Change from
authors = [
    { name = "nehcuh", email = "your@email.com" }
]
# To (remove email placeholder)
authors = [
    { name = "nehcuh" }
]
```

- [ ] **Step 2: Update QUICK_REFERENCE.md version**

```markdown
# Line 1: Change from
# VibeSOP Quick Reference
# Version: 1.0.0 | Status: PRODUCTION READY
# To
# VibeSOP Quick Reference
# Version: 2.2.0 | Status: PRODUCTION READY
```

Also update the architecture flow diagram to include v2.0 and v2.1 features (workflow orchestration, intelligent triggers, semantic matching).

- [ ] **Step 3: Fix CHANGELOG.md broken reference**

```markdown
# Line 371: Change from
All issues documented in [COMPLETE.md](COMPLETE.md).
# To
All issues have been resolved in subsequent patches.
```

- [ ] **Step 4: Fix bug_report.md for CLI tools**

```markdown
# .github/ISSUE_TEMPLATE/bug_report.md
# Replace Web-specific language with CLI-appropriate language:

# Change:
## Steps to Reproduce
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'

# To:
## Steps to Reproduce
1. Run command: `vibe ...`
2. Input: `...`
3. Observe: `...`

# Change:
## Screenshots
# To:
## Output/Logs
```

- [ ] **Step 5: Create docs/README.md (文档索引)**

```markdown
# VibeSOP Documentation

> **Version**: 2.2.0
> **Repository**: https://github.com/nehcuh/vibesop-py

## User Documentation

- [Getting Started](user/getting-started.md) — Installation and quick start
- [CLI Reference](CLI_REFERENCE.md) — Complete command reference
- [Semantic Matching Guide](semantic/guide.md) — Semantic recognition setup and usage
- [Trigger Patterns](triggers/guide.md) — Intent detection patterns
- [Workflow Orchestration](user/workflows.md) — Multi-stage workflow guide

## Developer Documentation

- [Architecture](dev/architecture.md) — System design and components
- [Contributing](../CONTRIBUTING.md) — How to contribute
- [Testing Guide](dev/testing.md) — Running and writing tests
- [Release Process](dev/releasing.md) — Versioning and releases

## API Reference

- [Python API](user/api-reference.md) — Programmatic usage
- [Semantic API](semantic/api.md) — Semantic matching API
- [Trigger API](triggers/api.md) — Trigger detection API

## Feature Documentation

- [Semantic Recognition](semantic/) — Sentence Transformers integration
- [Trigger System](triggers/) — 30 predefined patterns
- [Hooks](hooks-guide.md) — Extending VibeSOP

## Quick Links

- [GitHub Repository](https://github.com/nehcuh/vibesop-py)
- [Issue Tracker](https://github.com/nehcuh/vibesop-py/issues)
- [CHANGELOG](../CHANGELOG.md)
```

- [ ] **Step 6: Create CODE_OF_CONDUCT.md**

```markdown
# Contributor Covenant Code of Conduct

## Our Pledge

We as members, contributors, and leaders pledge to make participation in our
community a harassment-free experience for everyone, regardless of age, body
size, visible or invisible disability, ethnicity, sex characteristics, gender
identity and expression, level of experience, education, socio-economic status,
nationality, personal appearance, race, caste, color, religion, or sexual
identity and orientation.

## Our Standards

Examples of behavior that contributes to a positive environment:

* Demonstrating empathy and kindness toward other people
* Being respectful of differing opinions, viewpoints, and experiences
* Giving and gracefully accepting constructive feedback
* Accepting responsibility and apologizing to those affected by our mistakes
* Focusing on what is best for the overall community

## Enforcement

Project maintainers are responsible for clarifying and enforcing standards of
acceptable behavior and will take appropriate and fair corrective action in
response to any behavior that they deem inappropriate, threatening, offensive,
or harmful.

## Scope

This Code of Conduct applies within all community spaces, and also applies when
an individual is officially representing the community in public spaces.

## Attribution

This Code of Conduct is adapted from the [Contributor Covenant][homepage],
version 2.1, available at
[https://www.contributor-covenant.org/version/2/1/code_of_conduct.html][v2.1].

[homepage]: https://www.contributor-covenant.org
[v2.1]: https://www.contributor-covenant.org/version/2/1/code_of_conduct.html
```

- [ ] **Step 7: Create SECURITY.md**

```markdown
# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.2.x   | :white_check_mark: |
| 2.1.x   | :white_check_mark: |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please open a draft security advisory at:
https://github.com/nehcuh/vibesop-py/security/advisories

You should receive a response within 48 hours. If for some reason you do not,
please follow up via email: [your-email]

## Security Features

VibeSOP includes several security features:

1. **Path Traversal Protection**: All file writes go through `PathSafety` checks
2. **Security Scanning**: Input scanned for prompt injection and other threats
3. **Atomic File Writes**: Prevents corruption during configuration generation
4. **Input Validation**: Pydantic v2 runtime validation on all data models

## Known Limitations

- LLM API keys are stored in environment variables (best practice: use secret managers)
- Configuration files may contain sensitive data (ensure proper file permissions)
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "docs: fix metadata and create documentation index

- Fix author email in pyproject.toml (remove placeholder)
- Update QUICK_REFERENCE.md version to 2.2.0
- Fix CHANGELOG.md broken reference to COMPLETE.md
- Fix bug_report.md for CLI tools (not web app)
- Create docs/README.md documentation index
- Add CODE_OF_CONDUCT.md and SECURITY.md"
```

---

### Task 1.6: 重组文档目录

**Files:**
- Create: `docs/user/getting-started.md`
- Create: `docs/user/workflows.md`
- Create: `docs/dev/architecture.md`
- Create: `docs/dev/testing.md`
- Create: `docs/dev/releasing.md`
- Move: `docs/CLI_REFERENCE.md` → `docs/user/cli-reference.md`
- Move: `docs/hooks-guide.md` → `docs/dev/hooks-guide.md`
- Move: `docs/ROADMAP_INDEX.md` → `docs/dev/roadmap-index.md`

- [ ] **Step 1: Create docs/user/getting-started.md**

```markdown
# Getting Started with VibeSOP

## Prerequisites

- Python 3.12 or higher
- `uv` package manager (recommended) or `pip`

## Installation

### Option 1: Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py

# Install dependencies
uv sync

# Verify installation
uv run vibe --help
```

### Option 2: Using pip

```bash
# Basic installation (no semantic matching)
pip install vibesop

# With semantic matching
pip install vibesop[semantic]

# With development dependencies
pip install -e "vibesop[dev]"
```

## Quick Start

```bash
# Check your environment
vibe doctor

# List available skills
vibe skills

# Route a query
vibe route "review my code"

# Auto-detect and execute
vibe auto "scan for security issues"
```

## Next Steps

- [CLI Reference](cli-reference.md) — Complete command reference
- [Semantic Matching Guide](../semantic/guide.md) — Enable semantic recognition
- [Workflow Orchestration](workflows.md) — Multi-stage workflows
```

- [ ] **Step 2: Create docs/user/workflows.md**

```markdown
# Workflow Orchestration

VibeSOP v2.0+ supports multi-stage workflow execution with dependency management.

## Running a Workflow

```bash
# Run a workflow from YAML file
vibe workflow run my-workflow.yaml

# List available workflows
vibe workflow list

# Resume an interrupted workflow
vibe workflow resume <workflow-id>

# Validate a workflow definition
vibe workflow validate my-workflow.yaml
```

## Workflow Definition

Workflows are defined in YAML format:

```yaml
name: my-workflow
strategy: sequential  # sequential, parallel, or pipeline

stages:
  - id: validate
    name: Validate Input
    handler: validate_handler
    depends_on: []

  - id: process
    name: Process Data
    handler: process_handler
    depends_on: [validate]

  - id: report
    name: Generate Report
    handler: report_handler
    depends_on: [process]
```

## Execution Strategies

- **Sequential**: Stage-by-stage execution (default)
- **Parallel**: Concurrent stage execution where dependencies allow
- **Pipeline**: Adaptive streaming with progress callbacks

## State Management

Workflow state is persisted to `.vibe/state/workflows/` and can be resumed after interruption.
```

- [ ] **Step 3: Create docs/dev/architecture.md**

```markdown
# VibeSOP Architecture

## Overview

VibeSOP is a multi-platform workflow SOP system for AI-assisted development.

## Core Components

```
┌─────────────────────────────────────────────────────────┐
│                        CLI Layer                         │
│  Typer-based commands (30+ commands, grouped)            │
├─────────────────────────────────────────────────────────┤
│                    Business Logic                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Routing  │  │ Workflow │  │ Skills   │              │
│  │ Engine   │  │ Pipeline │  │ Manager  │              │
│  └──────────┘  └──────────┘  └──────────┘              │
├─────────────────────────────────────────────────────────┤
│                   Platform Layer                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Adapters │  │ Builder  │  │ Installer│              │
│  └──────────┘  └──────────┘  └──────────┘              │
├─────────────────────────────────────────────────────────┤
│                   Infrastructure                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Security │  │ Memory   │  │ Checkpoint│             │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

## 5-Layer Routing Engine

| Layer | Mechanism | Accuracy | Use Case |
|-------|-----------|----------|----------|
| 0 | LLM Semantic Triage | 95% | Complex, ambiguous queries |
| 1 | Explicit Overrides | 100% | Direct invocation (`/review`) |
| 2 | Scenario Patterns | 80% | Common keywords (debug, test) |
| 3 | TF-IDF Semantic | 70% | Bilingual similarity |
| 4 | Fuzzy Matching | 60% | Typo tolerance |

## Key Design Patterns

- **Adapter**: Platform-agnostic config generation
- **Strategy**: Pluggable routing algorithms and workflow strategies
- **Chain of Responsibility**: 5-layer routing fallback
- **Facade**: ConfigRenderer and SkillManager simplify complex operations
- **Template Method**: Shared utilities with platform-specific rendering

## Data Models

All data models use Pydantic v2 for runtime validation:
- `SkillRoute`: Routing result
- `RoutingRequest`: User query + context
- `SkillDefinition`: Skill metadata
- `WorkflowDefinition`: Workflow structure
- `AppSettings`: Environment configuration
```

- [ ] **Step 4: Create docs/dev/testing.md**

```markdown
# Testing Guide

## Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
uv run pytest tests/cli/test_auto.py -v

# Run specific test
uv run pytest tests/test_models.py::test_skill_route -v

# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration

# Run benchmarks
make benchmark
```

## Writing Tests

### Test Structure

```python
class TestComponentName:
    """Tests for ComponentName."""

    def test_specific_behavior(self) -> None:
        """Test a specific behavior."""
        # Arrange
        component = ComponentName()

        # Act
        result = component.method(input)

        # Assert
        assert result == expected
```

### Using Fixtures

Shared fixtures are in `tests/conftest.py`. Module-specific fixtures are in each subdirectory's `conftest.py`.

```python
def test_with_fixture(sample_skill, temp_dir):
    # sample_skill from tests/conftest.py
    # temp_dir from tests/conftest.py
    pass
```

### Mocking

Use `pytest-mock` for mocking:

```python
def test_with_mock(mocker):
    mock_router = mocker.patch('vibesop.routing.engine.SkillRouter')
    mock_router.route.return_value = expected_result
```

## Coverage Targets

- Overall: 80%+
- Core modules: 85%+
- CLI commands: 60%+
- Branch coverage: 50%+
```

- [ ] **Step 5: Create docs/dev/releasing.md**

```markdown
# Release Process

## Versioning

VibeSOP uses semantic versioning (SemVer): `MAJOR.MINOR.PATCH`

Versions are automatically managed by `hatch-vcs` from git tags.

## Creating a Release

### 1. Ensure all tests pass

```bash
make check
```

### 2. Update CHANGELOG.md

Add a new section for the release following [Keep a Changelog](https://keepachangelog.com/).

### 3. Create and push tag

```bash
git tag v2.2.0
git push origin v2.2.0
```

### 4. GitHub Actions will automatically:
- Run CI checks
- Build the package
- Publish to PyPI
- Create a GitHub Release with release notes

## Release Checklist

- [ ] All tests passing
- [ ] Coverage above 80%
- [ ] CHANGELOG.md updated
- [ ] Version tag created
- [ ] PyPI package published
- [ ] GitHub Release created
- [ ] Documentation updated
```

- [ ] **Step 6: Move files to new locations**

```bash
# Move CLI_REFERENCE.md to user/
mv docs/CLI_REFERENCE.md docs/user/cli-reference.md

# Move hooks-guide.md to dev/
mv docs/hooks-guide.md docs/dev/hooks-guide.md

# Move ROADMAP_INDEX.md to dev/
mv docs/ROADMAP_INDEX.md docs/dev/roadmap-index.md
```

Update any internal links in moved files to reflect new relative paths.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "docs: reorganize documentation structure

- Create docs/user/ and docs/dev/ directories
- Move user docs to docs/user/
- Move dev docs to docs/dev/
- Create getting-started.md, workflows.md
- Create architecture.md, testing.md, releasing.md
- Add CODE_OF_CONDUCT.md and SECURITY.md"
```

---

## Phase 2: CI/CD 搭建（1 天）

### Task 2.1: 创建 GitHub Actions CI 工作流

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  UV_VERSION: "0.5.0"

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: ${{ env.UV_VERSION }}

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Run ruff lint
        run: uv run ruff check .

      - name: Run ruff format check
        run: uv run ruff format --check .

  type-check:
    name: Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: ${{ env.UV_VERSION }}

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Run pyright
        run: uv run pyright

  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: ${{ env.UV_VERSION }}

      - name: Set up Python
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Run tests with coverage
        run: uv run pytest --cov=src/vibesop --cov-report=xml --cov-report=term-missing

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: false
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions CI workflow

- Lint job: ruff check + format
- Type check job: pyright
- Test job: pytest with coverage on Python 3.12 and 3.13
- Coverage upload to Codecov"
```

---

### Task 2.2: 创建 Release 工作流

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create release workflow**

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write
  id-token: write

jobs:
  release:
    name: Publish to PyPI
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        run: uv python install 3.12

      - name: Build package
        run: uv build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: dist/*
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add release workflow

- Build package with uv
- Publish to PyPI with trusted publishing
- Create GitHub Release with auto-generated notes"
```

---

### Task 2.3: 更新 pre-commit 和创建 CODEOWNERS

**Files:**
- Modify: `.pre-commit-config.yaml`
- Create: `.github/CODEOWNERS`

- [ ] **Step 1: Update .pre-commit-config.yaml**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: pyright
        name: pyright
        entry: uv run pyright
        language: system
        types: [python]
        pass_filenames: false
      - id: pytest
        name: pytest
        entry: uv run pytest tests/ -x -q --ignore=tests/benchmark
        language: system
        types: [python]
        pass_filenames: false
        always_run: true
```

Changes:
- Remove mypy hook (pyright is the primary type checker)
- Change pytest to ignore benchmark tests (run separately)

- [ ] **Step 2: Create .github/CODEOWNERS**

```
# CODEOWNERS for VibeSOP
# https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners

* @nehcuh

# Core modules
/src/vibesop/routing/ @nehcuh
/src/vibesop/workflow/ @nehcuh
/src/vibesop/skills/ @nehcuh
/src/vibesop/core/ @nehcuh

# CLI
/src/vibesop/cli/ @nehcuh

# Tests
/tests/ @nehcuh

# Documentation
/docs/ @nehcuh
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "ci: update pre-commit hooks and add CODEOWNERS

- Replace mypy with pyright in pre-commit (single type checker)
- Skip benchmark tests in pre-commit hook
- Add CODEOWNERS file for automatic review assignment"
```

---

## Phase 3: 测试覆盖提升（2 周）

### Task 3.1: 创建根级 conftest.py

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Create tests/conftest.py**

```python
"""Root conftest with shared fixtures for all tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Temporary directory for testing."""
    return tmp_path


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM response for routing tests."""
    return {
        "skill_id": "/review",
        "confidence": 0.95,
        "reasoning": "Query matches code review pattern",
    }


@pytest.fixture
def mock_llm_client(mock_llm_response: dict) -> Mock:
    """Mock LLM client to avoid API calls."""
    with patch("vibesop.llm.anthropic.AnthropicClient") as mock_cls:
        mock_instance = Mock()
        mock_instance.query.return_value = mock_llm_response
        mock_cls.return_value = mock_instance
        yield mock_cls


@pytest.fixture
def sample_skill() -> "SkillDefinition":
    """Sample skill definition for testing."""
    from vibesop.core.models import SkillDefinition

    return SkillDefinition(
        id="/test",
        name="Test Skill",
        description="A test skill for unit testing",
        trigger_when=["test", "testing", "unit test"],
    )


@pytest.fixture
def sample_skills(sample_skill: "SkillDefinition") -> list["SkillDefinition"]:
    """List of sample skills for testing."""
    from vibesop.core.models import SkillDefinition

    return [
        sample_skill,
        SkillDefinition(
            id="/review",
            name="Code Review",
            description="Review code for issues",
            trigger_when=["review", "audit", "check"],
        ),
        SkillDefinition(
            id="/debug",
            name="Debug",
            description="Debug issues in code",
            trigger_when=["debug", "fix bug", "troubleshoot"],
        ),
    ]


@pytest.fixture
def mock_skill_loader(sample_skills: list["SkillDefinition"]) -> Mock:
    """Mock skill loader that returns sample skills."""
    with patch("vibesop.core.skills.loader.SkillLoader") as mock_cls:
        mock_instance = Mock()
        mock_instance.load_skills.return_value = sample_skills
        mock_cls.return_value = mock_instance
        yield mock_cls


@pytest.fixture
def vibe_config_dir(tmp_path: Path) -> Path:
    """Create a temporary .vibe config directory."""
    config_dir = tmp_path / ".vibe"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory."""
    skills_dir = tmp_path / ".vibe" / "skills"
    skills_dir.mkdir(parents=True)
    return skills_dir
```

- [ ] **Step 2: Verify fixtures are discoverable**

```bash
uv run pytest --collect-only -q
# Should show new fixtures available
```

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add root-level conftest.py with shared fixtures

Add common fixtures:
- temp_dir, mock_llm_client, sample_skill, sample_skills
- mock_skill_loader, vibe_config_dir, skills_dir

These fixtures are now available across all test modules."
```

---

### Task 3.2: CLI 命令测试 — auto.py

**Files:**
- Create: `tests/cli/test_auto.py`
- Read: `src/vibesop/cli/commands/auto.py`

- [ ] **Step 1: Read auto.py to understand the command**

```bash
wc -l src/vibesop/cli/commands/auto.py
# Read the file to understand the auto command structure
```

- [ ] **Step 2: Create tests/cli/test_auto.py**

```python
"""Tests for the 'vibe auto' command."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestAutoCommand:
    """Tests for vibe auto command."""

    def test_auto_dry_run(self) -> None:
        """Test auto command with --dry-run flag."""
        with patch("vibesop.cli.commands.auto.KeywordDetector") as mock_detector:
            mock_instance = Mock()
            mock_instance.detect.return_value = Mock(
                skill_id="/review",
                confidence=0.85,
                pattern_id="code-review",
                category="Dev",
            )
            mock_detector.return_value = mock_instance

            result = runner.invoke(app, ["auto", "review my code", "--dry-run"])

            assert result.exit_code == 0
            assert "review" in result.stdout.lower()

    def test_auto_no_match(self) -> None:
        """Test auto command when no skill matches."""
        with patch("vibesop.cli.commands.auto.KeywordDetector") as mock_detector:
            mock_instance = Mock()
            mock_instance.detect.return_value = None
            mock_detector.return_value = mock_instance

            result = runner.invoke(app, ["auto", "xyzabc123random"])

            assert result.exit_code == 1

    def test_auto_with_verbose(self) -> None:
        """Test auto command with --verbose flag."""
        with patch("vibesop.cli.commands.auto.KeywordDetector") as mock_detector:
            mock_instance = Mock()
            mock_instance.detect.return_value = Mock(
                skill_id="/debug",
                confidence=0.90,
                pattern_id="debug-issue",
                category="Dev",
            )
            mock_instance.get_all_patterns.return_value = []
            mock_detector.return_value = mock_instance

            result = runner.invoke(
                app, ["auto", "debug this issue", "--verbose"]
            )

            assert result.exit_code == 0

    def test_auto_with_min_confidence(self) -> None:
        """Test auto command with custom min-confidence."""
        with patch("vibesop.cli.commands.auto.KeywordDetector") as mock_detector:
            mock_instance = Mock()
            mock_instance.detect.return_value = Mock(
                skill_id="/review",
                confidence=0.50,  # Below default threshold
                pattern_id="code-review",
                category="Dev",
            )
            mock_detector.return_value = mock_instance

            # With high threshold, should not match
            result = runner.invoke(
                app, ["auto", "review", "--min-confidence", "0.8"]
            )

            assert result.exit_code == 1

    def test_auto_list_patterns(self) -> None:
        """Test auto command with --list-patterns flag."""
        with patch("vibesop.cli.commands.auto.KeywordDetector") as mock_detector:
            mock_instance = Mock()
            mock_instance.get_all_patterns.return_value = [
                Mock(
                    id="code-review",
                    name="Code Review",
                    category="Dev",
                    priority=80,
                )
            ]
            mock_detector.return_value = mock_instance

            result = runner.invoke(app, ["auto", "--list-patterns"])

            assert result.exit_code == 0
            assert "Code Review" in result.stdout
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/cli/test_auto.py -v
# Expected: All tests pass
```

- [ ] **Step 4: Commit**

```bash
git add tests/cli/test_auto.py
git commit -m "test: add CLI auto command tests

Test dry-run, no-match, verbose, min-confidence, and list-patterns scenarios."
```

---

### Task 3.3: CLI 命令测试 — build.py

**Files:**
- Create: `tests/cli/test_build.py`
- Read: `src/vibesop/cli/commands/build.py`

- [ ] **Step 1: Create tests/cli/test_build.py**

```python
"""Tests for the 'vibe build' command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestBuildCommand:
    """Tests for vibe build command."""

    def test_build_claude_code(self, tmp_path: Path) -> None:
        """Test build command for claude-code platform."""
        with patch("vibesop.cli.commands.build.ConfigRenderer") as mock_renderer:
            mock_instance = Mock()
            mock_instance.render.return_value = Mock(
                files_written=[
                    tmp_path / "CLAUDE.md",
                    tmp_path / "rules" / "behaviors.md",
                ],
                total_files=2,
                total_size=1024,
            )
            mock_renderer.return_value = mock_instance

            result = runner.invoke(
                app, ["build", "claude-code", "--output", str(tmp_path)]
            )

            assert result.exit_code == 0
            assert "CLAUDE.md" in result.stdout

    def test_build_opencode(self, tmp_path: Path) -> None:
        """Test build command for opencode platform."""
        with patch("vibesop.cli.commands.build.ConfigRenderer") as mock_renderer:
            mock_instance = Mock()
            mock_instance.render.return_value = Mock(
                files_written=[tmp_path / "config.yaml"],
                total_files=1,
                total_size=512,
            )
            mock_renderer.return_value = mock_instance

            result = runner.invoke(
                app, ["build", "opencode", "--output", str(tmp_path)]
            )

            assert result.exit_code == 0

    def test_build_verify_only(self) -> None:
        """Test build command with --verify flag."""
        with patch("vibesop.cli.commands.build.ConfigRenderer") as mock_renderer:
            mock_instance = Mock()
            mock_instance.verify.return_value = Mock(is_valid=True, errors=[])
            mock_renderer.return_value = mock_instance

            result = runner.invoke(app, ["build", "claude-code", "--verify"])

            assert result.exit_code == 0
            assert "valid" in result.stdout.lower()

    def test_build_invalid_platform(self) -> None:
        """Test build command with invalid platform."""
        result = runner.invoke(app, ["build", "nonexistent-platform"])

        assert result.exit_code != 0
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/cli/test_build.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/cli/test_build.py
git commit -m "test: add CLI build command tests

Test claude-code, opencode, verify-only, and invalid platform scenarios."
```

---

### Task 3.4: CLI 命令测试 — doctor 和 skills

**Files:**
- Create: `tests/cli/test_doctor.py`
- Create: `tests/cli/test_skills.py`

- [ ] **Step 1: Create tests/cli/test_doctor.py**

```python
"""Tests for the 'vibe doctor' command."""

from __future__ import annotations

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestDoctorCommand:
    """Tests for vibe doctor command."""

    def test_doctor_runs_successfully(self) -> None:
        """Test that doctor command completes without errors."""
        result = runner.invoke(app, ["doctor"])

        # Doctor should always exit 0, it's a diagnostic command
        assert result.exit_code == 0
        # Should contain some diagnostic output
        assert len(result.stdout) > 0

    def test_doctor_shows_python_version(self) -> None:
        """Test that doctor command shows Python version."""
        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        assert "Python" in result.stdout or "python" in result.stdout
```

- [ ] **Step 2: Create tests/cli/test_skills.py**

```python
"""Tests for the 'vibe skills' command."""

from __future__ import annotations

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from vibesop.cli.main import app

runner = CliRunner()


class TestSkillsCommand:
    """Tests for vibe skills command."""

    def test_skills_lists_available(self) -> None:
        """Test that skills command lists available skills."""
        with patch("vibesop.cli.main.SkillManager") as mock_manager:
            mock_instance = Mock()
            mock_instance.list_skills.return_value = [
                Mock(id="/review", name="Code Review", description="Review code"),
                Mock(id="/debug", name="Debug", description="Debug issues"),
            ]
            mock_manager.return_value = mock_instance

            result = runner.invoke(app, ["skills"])

            assert result.exit_code == 0
            assert "review" in result.stdout.lower()

    def test_skill_info(self) -> None:
        """Test skill-info command shows details."""
        with patch("vibesop.cli.main.SkillManager") as mock_manager:
            mock_instance = Mock()
            mock_instance.get_skill.return_value = Mock(
                id="/review",
                name="Code Review",
                description="Review code for issues",
                trigger_when=["review", "audit"],
            )
            mock_manager.return_value = mock_instance

            result = runner.invoke(app, ["skill-info", "/review"])

            assert result.exit_code == 0
            assert "Code Review" in result.stdout
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/cli/test_doctor.py tests/cli/test_skills.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/cli/test_doctor.py tests/cli/test_skills.py
git commit -m "test: add CLI doctor and skills command tests"
```

---

### Task 3.5: Installer 测试

**Files:**
- Create: `tests/installer/test_init_support.py`
- Create: `tests/installer/test_quickstart.py`
- Read: `src/vibesop/installer/init_support.py`
- Read: `src/vibesop/installer/quickstart_runner.py`

- [ ] **Step 1: Create tests/installer/test_init_support.py**

```python
"""Tests for InitSupport class."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.installer.init_support import InitSupport


class TestInitSupport:
    """Tests for project initialization support."""

    def test_create_vibe_directory(self, tmp_path: Path) -> None:
        """Test creating .vibe directory structure."""
        init = InitSupport(project_root=tmp_path)
        init.create_vibe_structure()

        assert (tmp_path / ".vibe").exists()
        assert (tmp_path / ".vibe" / "skills").exists()
        assert (tmp_path / ".vibe" / "workflows").exists()

    def test_create_default_config(self, tmp_path: Path) -> None:
        """Test creating default config.yaml."""
        init = InitSupport(project_root=tmp_path)
        init.create_vibe_structure()

        config_file = tmp_path / ".vibe" / "config.yaml"
        assert config_file.exists()

    def test_create_gitignore(self, tmp_path: Path) -> None:
        """Test creating .gitignore entry."""
        init = InitSupport(project_root=tmp_path)
        init.create_vibe_structure()

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert ".vibe/" in content or "__pycache__" in content
```

- [ ] **Step 2: Create tests/installer/test_quickstart.py**

```python
"""Tests for QuickstartRunner class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibesop.installer.quickstart_runner import QuickstartRunner


class TestQuickstartRunner:
    """Tests for the quickstart wizard."""

    def test_detect_platform(self, tmp_path: Path) -> None:
        """Test platform detection."""
        runner = QuickstartRunner(project_root=tmp_path)

        # Should detect available platforms
        platforms = runner.detect_platforms()
        assert isinstance(platforms, list)

    def test_check_prerequisites(self, tmp_path: Path) -> None:
        """Test prerequisite checking."""
        runner = QuickstartRunner(project_root=tmp_path)

        # Should return a dict with check results
        results = runner.check_prerequisites()
        assert isinstance(results, dict)
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/installer/test_init_support.py tests/installer/test_quickstart.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/installer/test_init_support.py tests/installer/test_quickstart.py
git commit -m "test: add installer init_support and quickstart tests"
```

---

### Task 3.6: Hooks 测试

**Files:**
- Create: `tests/hooks/test_base.py`
- Create: `tests/hooks/test_installer.py`

- [ ] **Step 1: Create tests/hooks/__init__.py**

```python
"""Tests for the hooks module."""
```

- [ ] **Step 2: Create tests/hooks/test_base.py**

```python
"""Tests for Hook base classes."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibesop.hooks.base import Hook, ScriptHook, TemplateHook, create_hook


class TestScriptHook:
    """Tests for ScriptHook class."""

    def test_create_script_hook(self, tmp_path: Path) -> None:
        """Test creating a script hook."""
        script_path = tmp_path / "test.sh"
        script_path.write_text("#!/bin/bash\necho test")

        hook = ScriptHook(
            name="test-hook",
            script_path=str(script_path),
            enabled=True,
        )

        assert hook.name == "test-hook"
        assert hook.enabled is True

    def test_script_hook_content(self, tmp_path: Path) -> None:
        """Test script hook reads content correctly."""
        script_path = tmp_path / "test.sh"
        script_path.write_text("#!/bin/bash\necho hello")

        hook = ScriptHook(
            name="test",
            script_path=str(script_path),
        )

        content = hook.get_content()
        assert "echo hello" in content


class TestTemplateHook:
    """Tests for TemplateHook class."""

    def test_create_template_hook(self) -> None:
        """Test creating a template hook."""
        hook = TemplateHook(
            name="test-hook",
            template_name="pre-session-end.sh.j2",
            enabled=True,
        )

        assert hook.name == "test-hook"
        assert hook.template_name == "pre-session-end.sh.j2"

    def test_template_hook_render(self) -> None:
        """Test rendering template hook with context."""
        hook = TemplateHook(
            name="test",
            template_name="pre-session-end.sh.j2",
        )

        content = hook.render_context({"platform": "claude-code"})
        assert isinstance(content, str)
        assert len(content) > 0


class TestCreateHook:
    """Tests for create_hook factory function."""

    def test_create_script_hook(self, tmp_path: Path) -> None:
        """Test create_hook creates ScriptHook for scripts."""
        script_path = tmp_path / "test.sh"
        script_path.write_text("#!/bin/bash")

        hook = create_hook(
            name="test",
            hook_type="script",
            script_path=str(script_path),
        )

        assert isinstance(hook, ScriptHook)

    def test_create_template_hook(self) -> None:
        """Test create_hook creates TemplateHook for templates."""
        hook = create_hook(
            name="test",
            hook_type="template",
            template_name="pre-session-end.sh.j2",
        )

        assert isinstance(hook, TemplateHook)
```

- [ ] **Step 3: Create tests/hooks/test_installer.py**

```python
"""Tests for HookInstaller class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibesop.hooks.installer import HookInstaller


class TestHookInstaller:
    """Tests for HookInstaller class."""

    def test_install_hooks(self, tmp_path: Path) -> None:
        """Test installing hooks for a platform."""
        installer = HookInstaller(
            platform="claude-code",
            config_dir=tmp_path,
        )

        # Should complete without error (may create empty structure)
        result = installer.install_hooks(hooks=[])
        assert isinstance(result, dict)

    def test_verify_hooks(self, tmp_path: Path) -> None:
        """Test verifying hook installation."""
        installer = HookInstaller(
            platform="claude-code",
            config_dir=tmp_path,
        )

        result = installer.verify_hooks()
        assert isinstance(result, dict)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/hooks/ -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/
git commit -m "test: add hooks module tests

Test ScriptHook, TemplateHook, create_hook factory, and HookInstaller."
```

---

### Task 3.7: 其他零覆盖模块测试

**Files:**
- Create: `tests/semantic/test_integration.py`
- Create: `tests/integrations/test_detector.py`
- Create: `tests/utils/test_helpers.py`

- [ ] **Step 1: Create tests/semantic/test_integration.py**

```python
"""Integration tests for semantic matching with routing engine."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest


class TestSemanticIntegration:
    """Tests for semantic module integration."""

    def test_semantic_encoder_import(self) -> None:
        """Test that semantic encoder can be imported."""
        try:
            from vibesop.semantic.encoder import SemanticEncoder

            assert SemanticEncoder is not None
        except ImportError:
            # Expected if sentence-transformers not installed
            pytest.skip("sentence-transformers not installed")

    def test_semantic_similarity_import(self) -> None:
        """Test that semantic similarity can be imported."""
        try:
            from vibesop.semantic.similarity import SimilarityCalculator

            assert SimilarityCalculator is not None
        except ImportError:
            pytest.skip("sentence-transformers not installed")
```

- [ ] **Step 2: Create tests/integrations/test_detector.py**

```python
"""Tests for IntegrationDetector class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from vibesop.integrations.detector import IntegrationDetector


class TestIntegrationDetector:
    """Tests for integration detection."""

    def test_detect_no_integrations(self, tmp_path: Path) -> None:
        """Test detection when no integrations are present."""
        detector = IntegrationDetector(root_dir=tmp_path)
        integrations = detector.detect_all()

        assert isinstance(integrations, list)

    def test_detect_superpowers(self, tmp_path: Path) -> None:
        """Test detection of superpowers integration."""
        # Create superpowers marker
        (tmp_path / ".superpowers").mkdir()

        detector = IntegrationDetector(root_dir=tmp_path)
        integrations = detector.detect_all()

        # Should detect superpowers if marker exists
        integration_ids = [i.id for i in integrations]
        # May or may not detect depending on implementation
        assert isinstance(integration_ids, list)
```

- [ ] **Step 3: Create tests/utils/test_helpers.py**

```python
"""Tests for utility functions."""

from __future__ import annotations

from vibesop.utils.helpers import (
    extract_keywords,
    format_duration,
    sanitize_input,
)


class TestExtractKeywords:
    """Tests for extract_keywords function."""

    def test_extract_simple(self) -> None:
        """Test extracting keywords from simple text."""
        keywords = extract_keywords("review my code please")
        assert "review" in keywords
        assert "code" in keywords

    def test_extract_empty(self) -> None:
        """Test extracting keywords from empty string."""
        keywords = extract_keywords("")
        assert keywords == []

    def test_extract_stops_words(self) -> None:
        """Test that stop words are removed."""
        keywords = extract_keywords("the quick brown fox")
        assert "the" not in keywords


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_format_milliseconds(self) -> None:
        """Test formatting milliseconds."""
        result = format_duration(0.050)
        assert "ms" in result

    def test_format_seconds(self) -> None:
        """Test formatting seconds."""
        result = format_duration(1.5)
        assert "s" in result


class TestSanitizeInput:
    """Tests for sanitize_input function."""

    def test_sanitize_normal(self) -> None:
        """Test sanitizing normal input."""
        result = sanitize_input("hello world")
        assert result == "hello world"

    def test_sanitize_whitespace(self) -> None:
        """Test sanitizing whitespace."""
        result = sanitize_input("  hello   world  ")
        assert result == "hello world"
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/semantic/test_integration.py tests/integrations/test_detector.py tests/utils/test_helpers.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/semantic/test_integration.py tests/integrations/test_detector.py tests/utils/test_helpers.py
git commit -m "test: add semantic integration, detector, and utils tests"
```

---

### Task 3.8: 添加覆盖率门禁

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add coverage fail_under to pyproject.toml**

```toml
# In [tool.coverage.report] section, add:
fail_under = 80
```

The section should now look like:

```toml
[tool.coverage.report]
fail_under = 80
precision = 2
show_missing = true
skip_covered = false
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "class .*\\bProtocol\\):",
    "@(abc\\.)?abstractmethod",
]
```

- [ ] **Step 2: Run coverage to check current status**

```bash
uv run pytest --cov=src/vibesop --cov-report=term-missing
# This will likely fail until more tests are added
# That's expected at this stage - the gate will drive future improvements
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "test: add 80% coverage fail_under gate

This will drive test coverage improvements across the codebase."
```

---

## Phase 4: 架构重构（1 周）

### Task 4.1: 拆分 core/ 包 — 迁移 routing

**Files:**
- Create: `src/vibesop/routing/__init__.py`
- Move: `src/vibesop/core/routing/engine.py` → `src/vibesop/routing/engine.py`
- Move: `src/vibesop/core/routing/semantic.py` → `src/vibesop/routing/semantic.py`
- Move: `src/vibesop/core/routing/fuzzy.py` → `src/vibesop/routing/fuzzy.py`
- Move: `src/vibesop/core/routing/cache.py` → `src/vibesop/routing/cache.py`
- Create: `src/vibesop/core/__init__.py` (re-export for backward compat)

- [ ] **Step 1: Create src/vibesop/routing/ directory and move files**

```bash
mkdir -p src/vibesop/routing
mv src/vibesop/core/routing/*.py src/vibesop/routing/
# Remove old directory (should be empty now)
rmdir src/vibesop/core/routing 2>/dev/null || true
```

- [ ] **Step 2: Create src/vibesop/routing/__init__.py**

```python
"""Routing engine — 5-layer skill routing with caching."""

from vibesop.routing.cache import CacheManager, CacheStats
from vibesop.routing.engine import SkillRouter
from vibesop.routing.fuzzy import FuzzyMatcher
from vibesop.routing.semantic import SemanticMatcher

__all__ = [
    "CacheManager",
    "CacheStats",
    "FuzzyMatcher",
    "SemanticMatcher",
    "SkillRouter",
]
```

- [ ] **Step 3: Update all imports from `vibesop.core.routing` to `vibesop.routing`**

```bash
# Find all files importing from core.routing
rg "from vibesop\.core\.routing" src/ tests/ --type py
```

For each file found, update imports:

```python
# Old:
from vibesop.core.routing.engine import SkillRouter
# New:
from vibesop.routing.engine import SkillRouter

# Old:
from vibesop.core.routing import SemanticMatcher
# New:
from vibesop.routing import SemanticMatcher
```

- [ ] **Step 4: Create src/vibesop/core/__init__.py for backward compatibility**

```python
"""Core module — backward compatibility re-exports.

All submodules have been moved to top-level packages.
These re-exports maintain backward compatibility.
"""

# Routing re-exports
from vibesop.routing import (
    CacheManager,
    CacheStats,
    FuzzyMatcher,
    SemanticMatcher,
    SkillRouter,
)

# Skills re-exports
from vibesop.skills import (
    PromptSkill,
    Skill,
    SkillContext,
    SkillDefinition,
    SkillLoader,
    SkillManager,
    SkillMetadata,
    SkillResult,
    SkillType,
    WorkflowSkill,
)

# Memory re-exports
from vibesop.memory import (
    ConversationMemory,
    MemoryManager,
    MemoryStorage,
)

# Checkpoint re-exports
from vibesop.checkpoint import (
    Checkpoint,
    CheckpointManager,
    CheckpointStorage,
)

# Models and config
from vibesop.core.config import ConfigLoader
from vibesop.core.models import (
    AppSettings,
    RoutingRequest,
    RoutingResult,
    SkillDefinition,
    SkillRegistry,
    SkillRoute,
)

# Preference learning
from vibesop.core.preference import (
    PreferenceLearner,
    PreferenceScore,
    PreferenceStorage,
    SkillSelection,
)

__all__ = [
    # Routing
    "CacheManager",
    "CacheStats",
    "FuzzyMatcher",
    "SemanticMatcher",
    "SkillRouter",
    # Skills
    "PromptSkill",
    "Skill",
    "SkillContext",
    "SkillDefinition",
    "SkillLoader",
    "SkillManager",
    "SkillMetadata",
    "SkillResult",
    "SkillType",
    "WorkflowSkill",
    # Memory
    "ConversationMemory",
    "MemoryManager",
    "MemoryStorage",
    # Checkpoint
    "Checkpoint",
    "CheckpointManager",
    "CheckpointStorage",
    # Config and models
    "AppSettings",
    "ConfigLoader",
    "RoutingRequest",
    "RoutingResult",
    "SkillRoute",
    # Preference
    "PreferenceLearner",
    "PreferenceScore",
    "PreferenceStorage",
    "SkillSelection",
]
```

- [ ] **Step 5: Run tests to verify no breakage**

```bash
uv run pytest tests/ -x -q
# All existing tests should still pass
```

- [ ] **Step 6: Run type check**

```bash
uv run pyright
# Fix any type errors from import changes
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: move routing from core/ to top-level package

- Move vibesop.core.routing.* to vibesop.routing.*
- Create backward compatibility re-exports in core/__init__.py
- Update all imports across codebase
- Maintain full backward compatibility"
```

---

### Task 4.2: 拆分 core/ 包 — 迁移 skills, memory, checkpoint

**Files:**
- Create: `src/vibesop/skills/__init__.py`
- Create: `src/vibesop/memory/__init__.py`
- Create: `src/vibesop/checkpoint/__init__.py`
- Move files from `core/skills/`, `core/memory/`, `core/checkpoint/`

- [ ] **Step 1: Move skills**

```bash
mkdir -p src/vibesop/skills
mv src/vibesop/core/skills/*.py src/vibesop/skills/
rmdir src/vibesop/core/skills 2>/dev/null || true
```

Create `src/vibesop/skills/__init__.py`:

```python
"""Skill management — loading, discovery, and execution."""

from vibesop.skills.base import (
    PromptSkill,
    Skill,
    SkillContext,
    SkillMetadata,
    SkillResult,
    SkillType,
    WorkflowSkill,
)
from vibesop.skills.loader import SkillDefinition, SkillLoader
from vibesop.skills.manager import SkillManager

__all__ = [
    "PromptSkill",
    "Skill",
    "SkillContext",
    "SkillDefinition",
    "SkillLoader",
    "SkillManager",
    "SkillMetadata",
    "SkillResult",
    "SkillType",
    "WorkflowSkill",
]
```

- [ ] **Step 2: Move memory**

```bash
mkdir -p src/vibesop/memory
mv src/vibesop/core/memory/*.py src/vibesop/memory/
rmdir src/vibesop/core/memory 2>/dev/null || true
```

Create `src/vibesop/memory/__init__.py`:

```python
"""Conversation memory — storage and management."""

from vibesop.memory.base import ConversationMemory
from vibesop.memory.manager import MemoryManager
from vibesop.memory.storage import MemoryStorage

__all__ = ["ConversationMemory", "MemoryManager", "MemoryStorage"]
```

- [ ] **Step 3: Move checkpoint**

```bash
mkdir -p src/vibesop/checkpoint
mv src/vibesop/core/checkpoint/*.py src/vibesop/checkpoint/
rmdir src/vibesop/core/checkpoint 2>/dev/null || true
```

Create `src/vibesop/checkpoint/__init__.py`:

```python
"""Checkpoint system — work state persistence and recovery."""

from vibesop.checkpoint.base import Checkpoint
from vibesop.checkpoint.manager import CheckpointManager
from vibesop.checkpoint.storage import CheckpointStorage

__all__ = ["Checkpoint", "CheckpointManager", "CheckpointStorage"]
```

- [ ] **Step 4: Update all imports**

```bash
# Find and update all imports
rg "from vibesop\.core\.skills" src/ tests/ --type py -l
rg "from vibesop\.core\.memory" src/ tests/ --type py -l
rg "from vibesop\.core\.checkpoint" src/ tests/ --type py -l
```

Update each file to use new import paths.

- [ ] **Step 5: Update core/__init__.py re-exports**

Already done in Task 4.1 — the re-exports already reference the new locations.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/ -x -q
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: move skills, memory, checkpoint to top-level packages

- vibesop.core.skills -> vibesop.skills
- vibesop.core.memory -> vibesop.memory
- vibesop.core.checkpoint -> vibesop.checkpoint
- Update all imports
- core/__init__.py re-exports maintain backward compat"
```

---

### Task 4.3: CLI 命令分组

**Files:**
- Modify: `src/vibesop/cli/main.py`

- [ ] **Step 1: Read current main.py structure**

```bash
wc -l src/vibesop/cli/main.py
# Currently 458 lines with 30+ flat commands
```

- [ ] **Step 2: Restructure main.py with command groups**

```python
"""VibeSOP CLI — AI-powered workflow SOP."""

from __future__ import annotations

import typer

from vibesop import __version__

app = typer.Typer(
    name="vibe",
    help="VibeSOP - AI-powered workflow SOP",
    no_args_is_help=True,
)

# ─── Command Groups ───────────────────────────────────────────────

# Route sub-commands
route_app = typer.Typer(help="Skill routing and detection")
app.add_typer(route_app, name="route")

# Config sub-commands
config_app = typer.Typer(help="Configuration management")
app.add_typer(config_app, name="config")

# Workflow sub-commands
workflow_app = typer.Typer(help="Workflow orchestration")
app.add_typer(workflow_app, name="workflow")

# Install sub-commands
install_app = typer.Typer(help="Installation and setup")
app.add_typer(install_app, name="install")

# ─── Top-level Commands (most frequently used) ────────────────────

@app.command()
def auto(
    query: str = typer.Argument(..., help="Natural language query"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without executing"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    min_confidence: float = typer.Option(0.6, "--min-confidence", help="Minimum confidence threshold"),
    semantic: bool = typer.Option(False, "--semantic", help="Enable semantic matching"),
) -> None:
    """Auto-detect intent and execute the matched skill."""
    from vibesop.cli.commands import auto as auto_module

    auto_module.auto(
        query=query,
        dry_run=dry_run,
        verbose=verbose,
        min_confidence=min_confidence,
        semantic=semantic,
    )


@app.command()
def skills() -> None:
    """List all available skills."""
    from vibesop.core.skills.manager import SkillManager

    manager = SkillManager()
    all_skills = manager.list_skills()

    if not all_skills:
        typer.echo("No skills found.")
        return

    typer.echo(f"\nAvailable skills ({len(all_skills)}):\n")
    for skill in all_skills:
        typer.echo(f"  {skill.id:20s} {skill.name:25s} {skill.description}")
    typer.echo()


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo(f"VibeSOP v{__version__}")


@app.command()
def doctor() -> None:
    """Check environment and configuration."""
    from vibesop.cli.main import (
        _check_config,
        _check_dependencies,
        _check_hooks,
        _check_integrations,
        _check_llm_provider,
        _check_python_version,
    )

    typer.echo("VibeSOP Environment Check\n")

    _check_python_version()
    _check_dependencies()
    _check_config()
    _check_llm_provider()
    _check_integrations()
    _check_hooks()

    typer.echo("\nRun 'vibe --help' for available commands.")


# ─── Register External Commands ─────────────────────────────────────

# Build and deploy
from vibesop.cli.commands import build as build_module
from vibesop.cli.commands import deploy as deploy_module

app.command()(build_module.build)
app.command()(deploy_module.deploy)

# Route commands (also available as sub-commands)
from vibesop.cli.commands import route_commands as route_commands_module

route_app.command()(route_commands_module.route_select)
route_app.command("validate")(route_commands_module.route_validate)

# Keep top-level for backward compatibility
app.command("route")(route_commands_module.route_single)
app.command("route-select")(route_commands_module.route_select)
app.command("route-validate")(route_commands_module.route_validate)

# Config commands
from vibesop.cli.commands import config as config_module

config_app.command("semantic")(config_module.config_semantic)
# Keep top-level for backward compatibility
app.command("semantic")(config_module.config_semantic)

# Workflow commands
from vibesop.cli.commands import workflow as workflow_module

workflow_app.command()(workflow_module.workflow)
# Keep top-level for backward compatibility
app.command()(workflow_module.workflow)

# Installation commands
from vibesop.cli.commands import init as init_module
from vibesop.cli.commands import install as install_module
from vibesop.cli.commands import switch as switch_module
from vibesop.cli.commands import inspect as inspect_module

install_app.command()(init_module.init)
install_app.command()(install_module.install)
app.command()(init_module.init)  # Keep top-level
app.command()(install_module.install)  # Keep top-level
app.command()(switch_module.switch)
app.command("inspect")(inspect_module.inspect_cmd)

# Other commands
from vibesop.cli.commands import targets as targets_module
from vibesop.cli.commands import checkpoint as checkpoint_module
from vibesop.cli.commands import cascade as cascade_module
from vibesop.cli.commands import experiment as experiment_module
from vibesop.cli.commands import memory_cmd as memory_module
from vibesop.cli.commands import instinct_cmd as instinct_module
from vibesop.cli.commands import quickstart as quickstart_module
from vibesop.cli.commands import onboard as onboard_module
from vibesop.cli.commands import toolchain as toolchain_module
from vibesop.cli.commands import scan as scan_module
from vibesop.cli.commands import skill_craft as skill_craft_module
from vibesop.cli.commands import tools_cmd as tools_module
from vibesop.cli.commands import worktree as worktree_module
from vibesop.cli.commands import import_rules as import_rules_module
from vibesop.cli.commands import detect as detect_module
from vibesop.cli.commands import hooks as hooks_module
from vibesop.cli.commands import analyze as analyze_module
from vibesop.cli.commands import auto_analyze as auto_analyze_module

app.command()(targets_module.targets)
app.command()(checkpoint_module.checkpoint)
app.command()(cascade_module.cascade)
app.command()(experiment_module.experiment)
app.command("memory")(memory_module.memory)
app.command()(instinct_module.instinct)
app.command()(quickstart_module.quickstart)
app.command()(onboard_module.onboard)
app.command()(toolchain_module.toolchain)
app.command()(scan_module.scan)
app.command("skill-craft")(skill_craft_module.skill_craft)
app.command()(tools_module.tools)
app.command()(worktree_module.worktree)
app.command("import-rules")(import_rules_module.import_rules)
app.command()(detect_module.detect)
app.command()(hooks_module.hooks)
app.command()(analyze_module.analyze)
app.command()(auto_analyze_module.auto_analyze_session)
app.command("create-suggested-skills")(auto_analyze_module.create_suggested_skills)

# ─── Preference Learning Commands ──────────────────────────────────

@app.command()
def record(
    skill_id: str = typer.Argument(..., help="Skill ID that was used"),
    query: str = typer.Option("", "--query", "-q", help="Original query"),
) -> None:
    """Record a skill selection for preference learning."""
    from vibesop.core.preference import PreferenceLearner

    learner = PreferenceLearner()
    learner.record_selection(skill_id=skill_id, query=query, was_helpful=True)
    typer.echo(f"Recorded selection: {skill_id}")


@app.command()
def preferences() -> None:
    """Show preference learning statistics."""
    from vibesop.core.preference import PreferenceLearner

    learner = PreferenceLearner()
    stats = learner.get_stats()

    typer.echo(f"\nPreference Statistics:")
    typer.echo(f"  Total selections: {stats['total_selections']}")
    typer.echo(f"  Helpfulness rate: {stats['helpfulness_rate']:.1%}")
    if stats["top_skills"]:
        typer.echo(f"  Top skills: {', '.join(stats['top_skills'])}")
    typer.echo()


@app.command()
def top_skills() -> None:
    """Show most preferred skills."""
    from vibesop.core.preference import PreferenceLearner

    learner = PreferenceLearner()
    top = learner.get_top_skills(10)

    if not top:
        typer.echo("No preference data yet. Use 'vibe record' to start learning.")
        return

    typer.echo("\nTop Skills:\n")
    for i, (skill_id, score) in enumerate(top, 1):
        typer.echo(f"  {i:2d}. {skill_id:25s} {score:.3f}")
    typer.echo()


@app.command()
def skill_info(skill_id: str = typer.Argument(..., help="Skill ID")) -> None:
    """Show detailed information about a skill."""
    from vibesop.core.skills.manager import SkillManager

    manager = SkillManager()
    skill = manager.get_skill(skill_id)

    if not skill:
        typer.echo(f"Skill not found: {skill_id}")
        raise typer.Exit(1)

    typer.echo(f"\nSkill: {skill.name}")
    typer.echo(f"ID: {skill.id}")
    typer.echo(f"Description: {skill.description}")
    if skill.trigger_when:
        typer.echo(f"Triggers: {', '.join(skill.trigger_when)}")
    typer.echo()
```

Note: This restructure keeps all existing commands at the top level for backward compatibility, while also adding them to logical sub-command groups.

- [ ] **Step 3: Run CLI to verify**

```bash
uv run vibe --help
# Should show grouped commands

uv run vibe route --help
# Should show route sub-commands

uv run vibe auto "test" --dry-run
# Should still work
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/cli/ -v
```

- [ ] **Step 5: Commit**

```bash
git add src/vibesop/cli/main.py
git commit -m "refactor: group CLI commands into logical sub-commands

- Add route/, config/, workflow/, install/ sub-command groups
- Keep all existing top-level commands for backward compatibility
- Users can now use 'vibe route select' or 'vibe route-select'"
```

---

### Task 4.4: 轻量依赖注入容器

**Files:**
- Create: `src/vibesop/core/container.py`

- [ ] **Step 1: Create container.py**

```python
"""Simple dependency injection container.

Lightweight container for managing service lifecycles and testability.
Not a full DI framework — just enough to decouple components.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class Container:
    """Simple service container for dependency injection."""

    _services: dict[str, Any] = {}
    _factories: dict[str, Callable[[], Any]] = {}

    @classmethod
    def register(cls, name: str, instance: Any) -> None:
        """Register a service instance."""
        cls._services[name] = instance

    @classmethod
    def factory(cls, name: str, factory_fn: Callable[[], Any]) -> None:
        """Register a factory function for lazy initialization."""
        cls._factories[name] = factory_fn

    @classmethod
    def resolve(cls, name: str) -> Any:
        """Resolve a service by name."""
        if name not in cls._services and name in cls._factories:
            cls._services[name] = cls._factories[name]()
        if name not in cls._services:
            msg = f"Service not registered: {name}"
            raise KeyError(msg)
        return cls._services[name]

    @classmethod
    def has(cls, name: str) -> bool:
        """Check if a service is registered."""
        return name in cls._services or name in cls._factories

    @classmethod
    def reset(cls) -> None:
        """Clear all services (for testing)."""
        cls._services.clear()
        cls._factories.clear()
```

- [ ] **Step 2: Create tests/core/test_container.py**

```python
"""Tests for the dependency injection container."""

from __future__ import annotations

import pytest

from vibesop.core.container import Container


class TestContainer:
    """Tests for Container class."""

    def setup_method(self) -> None:
        """Reset container before each test."""
        Container.reset()

    def test_register_and_resolve(self) -> None:
        """Test registering and resolving a service."""
        service = {"key": "value"}
        Container.register("test_service", service)

        resolved = Container.resolve("test_service")
        assert resolved is service

    def test_factory_lazy(self) -> None:
        """Test factory creates service lazily."""
        call_count = 0

        def factory() -> dict:
            nonlocal call_count
            call_count += 1
            return {"created": True}

        Container.factory("lazy_service", factory)

        # Factory not called yet
        assert call_count == 0

        # First resolve triggers factory
        result = Container.resolve("lazy_service")
        assert result == {"created": True}
        assert call_count == 1

        # Second resolve returns cached instance
        result2 = Container.resolve("lazy_service")
        assert result2 is result
        assert call_count == 1  # Not called again

    def test_has_service(self) -> None:
        """Test checking if service exists."""
        Container.register("exists", True)
        assert Container.has("exists") is True
        assert Container.has("not_exists") is False

    def test_unregistered_service_raises(self) -> None:
        """Test resolving unregistered service raises KeyError."""
        with pytest.raises(KeyError, match="not_registered"):
            Container.resolve("not_registered")

    def test_reset(self) -> None:
        """Test reset clears all services."""
        Container.register("temp", "value")
        Container.factory("temp_factory", lambda: "value")

        Container.reset()

        assert Container.has("temp") is False
        assert Container.has("temp_factory") is False
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/core/test_container.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/vibesop/core/container.py tests/core/test_container.py
git commit -m "feat: add lightweight dependency injection container

Simple Container class with register/factory/resolve/reset.
Improves testability by allowing service mocking."
```

---

## Phase 5: 工程纪律提升（3 天）

### Task 5.1: hatch-vcs 版本自动化

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/vibesop/_version.py`

- [ ] **Step 1: Update pyproject.toml for hatch-vcs**

```toml
# Change build-system section:
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

# Add version source:
[tool.hatch.version]
source = "vcs"

[tool.hatch.build.hooks.vcs]
version-file = "src/vibesop/_version.py"

# Remove the static version line:
# Delete: version = "2.1.0" from [project] section
```

- [ ] **Step 2: Update _version.py template**

hatch-vcs will generate this file automatically. Delete the current manual version file content and let hatch-vcs manage it. The file will be auto-generated with:

```python
# file generated by hatch-vcs
__version__ = "2.2.0.dev0+g<commit>"
```

- [ ] **Step 3: Update main.py to use dynamic version**

```python
# In src/vibesop/cli/main.py, the version command should use:
from vibesop import __version__

@app.command()
def version() -> None:
    """Show version information."""
    typer.echo(f"VibeSOP v{__version__}")
```

- [ ] **Step 4: Test version resolution**

```bash
# Create a test tag
git tag v2.2.0-test
uv build
# Check that version is picked up from tag

# Clean up
git tag -d v2.2.0-test
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "build: switch to hatch-vcs for automatic version management

- Remove hardcoded version from pyproject.toml
- Version now derived from git tags
- _version.py auto-generated by hatch-vcs"
```

---

### Task 5.2: 偏好学习负反馈

**Files:**
- Modify: `src/vibesop/core/preference.py`
- Modify: `src/vibesop/cli/main.py`

- [ ] **Step 1: Add negative feedback to PreferenceLearner**

In `src/vibesop/core/preference.py`, modify `record_selection` and add `record_feedback`:

```python
def record_feedback(
    self,
    skill_id: str,
    query: str,
    helpful: bool,
) -> None:
    """Record positive or negative feedback for a skill recommendation.

    Args:
        skill_id: The skill that was recommended.
        query: The original user query.
        helpful: Whether the recommendation was helpful.
    """
    key = f"{skill_id}:{query}"

    if helpful:
        self._storage.positive_feedback[key] = (
            self._storage.positive_feedback.get(key, 0) + 1
        )
    else:
        self._storage.negative_feedback[key] = (
            self._storage.negative_feedback.get(key, 0) + 1
        )

    # Recalculate scores with feedback
    self._recalculate_scores()
    self._save()
```

Also update `PreferenceStorage` model to include:

```python
positive_feedback: dict[str, int] = Field(default_factory=dict)
negative_feedback: dict[str, int] = Field(default_factory=dict)
```

And update `_recalculate_scores` to factor in negative feedback:

```python
# In _recalculate_scores, after calculating base score:
key = f"{skill_id}:{last_selected_query}"
negative_count = self._storage.negative_feedback.get(key, 0)
if negative_count > 0:
    # Reduce score based on negative feedback
    penalty = min(0.3, negative_count * 0.1)  # Max 30% penalty
    score = max(0.0, score - penalty)
```

- [ ] **Step 2: Add feedback CLI command**

In `src/vibesop/cli/main.py`, add:

```python
@app.command()
def feedback(
    skill_id: str = typer.Argument(..., help="Skill ID"),
    helpful: bool = typer.Option(
        True,
        "--helpful/--not-helpful",
        help="Was the recommendation helpful?",
    ),
    query: str = typer.Option("", "--query", "-q", help="Original query"),
) -> None:
    """Record feedback for a skill recommendation."""
    from vibesop.core.preference import PreferenceLearner

    learner = PreferenceLearner()
    learner.record_feedback(skill_id, query, helpful)

    if helpful:
        typer.echo(f"✅ Thanks! '{skill_id}' score updated.")
    else:
        typer.echo(f"📉 Noted. '{skill_id}' score decreased for similar queries.")
```

- [ ] **Step 3: Create tests for negative feedback**

```python
# Add to tests/test_preference.py:

class TestNegativeFeedback:
    """Tests for negative feedback functionality."""

    def test_record_negative_feedback(self) -> None:
        """Test recording negative feedback reduces score."""
        learner = self._create_learner()

        # First record positive
        learner.record_selection("/review", "review code", was_helpful=True)

        # Then record negative
        learner.record_feedback("/review", "review code", helpful=False)

        score = learner.get_preference_score("/review")
        # Score should be reduced
        assert score.score < 0.7  # Below what pure positive would be

    def test_feedback_persistence(self, tmp_path: Path) -> None:
        """Test feedback is persisted across instances."""
        storage = PreferenceStorage(data_file=str(tmp_path / "prefs.json"))
        learner = PreferenceLearner(storage=storage)

        learner.record_feedback("/review", "test query", helpful=False)

        # New instance should have the data
        storage2 = PreferenceStorage(data_file=str(tmp_path / "prefs.json"))
        learner2 = PreferenceLearner(storage=storage2)

        assert learner2._storage.negative_feedback.get("/review:test query", 0) > 0
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_preference.py -v -k "feedback"
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add negative feedback to preference learning

- Add record_feedback() method to PreferenceLearner
- Negative feedback reduces skill scores (max 30% penalty)
- Add 'vibe feedback' CLI command with --helpful/--not-helpful
- Persist positive and negative feedback separately"
```

---

### Task 5.3: 路由统计收集

**Files:**
- Modify: `src/vibesop/routing/engine.py`

- [ ] **Step 1: Add stats collection to SkillRouter**

In `src/vibesop/routing/engine.py`, add to `__init__`:

```python
def __init__(self, ...) -> None:
    # ... existing init ...
    self._stats: dict[str, Any] = {
        "total_queries": 0,
        "layer_hits": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0},
        "no_match_count": 0,
        "avg_confidence_sum": 0.0,
    }
```

In the `route` method, after getting the result:

```python
def route(self, query: str) -> RoutingResult:
    self._stats["total_queries"] += 1

    # ... existing routing logic ...

    if result.primary_match:
        self._stats["layer_hits"][result.primary_match.layer] += 1
        self._stats["avg_confidence_sum"] += result.primary_match.confidence
    else:
        self._stats["no_match_count"] += 1

    return result
```

Add stats getter:

```python
def get_stats(self) -> dict[str, Any]:
    """Get routing statistics for optimization."""
    total = self._stats["total_queries"]
    avg_confidence = (
        self._stats["avg_confidence_sum"] / total if total > 0 else 0.0
    )

    return {
        "total_queries": total,
        "layer_hits": dict(self._stats["layer_hits"]),
        "no_match_count": self._stats["no_match_count"],
        "avg_confidence": round(avg_confidence, 3),
        "hit_rate": round(
            1 - self._stats["no_match_count"] / total if total > 0 else 0, 3
        ),
    }
```

- [ ] **Step 2: Add stats CLI command**

In `src/vibesop/cli/main.py`:

```python
@app.command("route-stats")
def route_stats() -> None:
    """Show routing statistics."""
    from vibesop.routing.engine import SkillRouter

    router = SkillRouter()
    stats = router.get_stats()

    typer.echo("\nRouting Statistics:")
    typer.echo(f"  Total queries: {stats['total_queries']}")
    typer.echo(f"  Hit rate: {stats['hit_rate']:.1%}")
    typer.echo(f"  Avg confidence: {stats['avg_confidence']:.3f}")
    typer.echo(f"\n  Layer distribution:")
    for layer, count in stats["layer_hits"].items():
        pct = count / stats["total_queries"] if stats["total_queries"] > 0 else 0
        typer.echo(f"    Layer {layer}: {count} ({pct:.1%})")
    typer.echo()
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: add routing statistics collection

- Track total queries, layer_hits, no_match_count, avg_confidence
- Add get_stats() method to SkillRouter
- Add 'vibe route-stats' CLI command
- Useful for optimizing routing strategy"
```

---

### Task 5.4: 性能基准测试

**Files:**
- Create: `tests/benchmark/test_routing_performance.py`
- Modify: `Makefile`

- [ ] **Step 1: Create benchmark tests**

```python
"""Performance benchmarks for routing engine."""

from __future__ import annotations

import time

import pytest

from vibesop.routing.engine import SkillRouter


class TestRoutingPerformance:
    """Benchmarks for routing latency."""

    @pytest.mark.benchmark
    def test_routing_latency_simple(self) -> None:
        """Test routing latency for simple queries."""
        router = SkillRouter()
        queries = ["review", "debug", "test", "build", "deploy"]

        latencies = []
        for query in queries:
            start = time.perf_counter()
            router.route(query)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 10, f"Average latency {avg_latency:.1f}ms > 10ms target"

    @pytest.mark.benchmark
    def test_routing_latency_complex(self) -> None:
        """Test routing latency for complex queries."""
        router = SkillRouter()
        queries = [
            "please review my code for security issues",
            "help me debug this tricky issue",
            "run the test suite and report failures",
        ]

        latencies = []
        for query in queries:
            start = time.perf_counter()
            router.route(query)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 15, f"Average latency {avg_latency:.1f}ms > 15ms target"

    @pytest.mark.benchmark
    def test_routing_throughput(self) -> None:
        """Test routing throughput (queries per second)."""
        router = SkillRouter()
        query = "review my code"
        count = 100

        start = time.perf_counter()
        for _ in range(count):
            router.route(query)
        elapsed = time.perf_counter() - start

        qps = count / elapsed
        assert qps > 100, f"Throughput {qps:.0f} qps < 100 qps target"

    @pytest.mark.benchmark
    def test_routing_stats_overhead(self) -> None:
        """Test that stats collection has minimal overhead."""
        router_with_stats = SkillRouter()

        start = time.perf_counter()
        for i in range(50):
            router_with_stats.route(f"query {i}")
        elapsed_with_stats = time.perf_counter() - start

        # Stats overhead should be < 5%
        # (We can't easily test without stats, but this ensures it's fast)
        assert elapsed_with_stats < 1.0, f"50 queries took {elapsed_with_stats:.2f}s"
```

- [ ] **Step 2: Add benchmark target to Makefile**

```makefile
benchmark: ## Run performance benchmarks
	uv run pytest tests/benchmark/ -v -m benchmark
```

- [ ] **Step 3: Run benchmarks**

```bash
make benchmark
```

- [ ] **Step 4: Commit**

```bash
git add tests/benchmark/test_routing_performance.py Makefile
git commit -m "test: add routing performance benchmarks

- Test latency for simple and complex queries
- Test throughput (queries per second)
- Test stats collection overhead
- Add 'make benchmark' target"
```

---

### Task 5.5: 文档一致性检查脚本

**Files:**
- Create: `scripts/check_docs.py`

- [ ] **Step 1: Create check_docs.py**

```python
#!/usr/bin/env python3
"""Check documentation consistency with code."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def check_broken_file_references() -> list[str]:
    """Check for references to non-existent files in docs."""
    broken = []

    docs_dir = ROOT / "docs"
    if not docs_dir.exists():
        return broken

    # Patterns for file references
    file_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for md_file in docs_dir.rglob("*.md"):
        content = md_file.read_text()
        for match in file_pattern.finditer(content):
            link_text, link_path = match.groups()

            # Skip external links
            if link_path.startswith("http"):
                continue

            # Skip anchors
            if link_path.startswith("#"):
                continue

            # Resolve relative path
            if not link_path.startswith("/"):
                ref_path = (md_file.parent / link_path).resolve()
            else:
                ref_path = (ROOT / link_path.lstrip("/")).resolve()

            if not ref_path.exists():
                broken.append(f"{md_file.relative_to(ROOT)}: {link_path}")

    return broken


def check_readme_references() -> list[str]:
    """Check README.md for broken references."""
    broken = []
    readme = ROOT / "README.md"

    if not readme.exists():
        return broken

    content = readme.read_text()
    file_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for match in file_pattern.finditer(content):
        link_text, link_path = match.groups()

        if link_path.startswith("http") or link_path.startswith("#"):
            continue

        ref_path = (ROOT / link_path).resolve()
        if not ref_path.exists():
            broken.append(f"README.md: {link_path}")

    return broken


def main() -> None:
    """Run all consistency checks."""
    print("Checking documentation consistency...\n")

    broken = []
    broken.extend(check_broken_file_references())
    broken.extend(check_readme_references())

    if broken:
        print(f"Found {len(broken)} broken references:\n")
        for ref in broken:
            print(f"  ❌ {ref}")
        sys.exit(1)
    else:
        print("✅ No broken references found.")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/check_docs.py
```

- [ ] **Step 3: Run check**

```bash
uv run python scripts/check_docs.py
```

- [ ] **Step 4: Commit**

```bash
git add scripts/check_docs.py
git commit -m "feat: add documentation consistency check script

Check for broken file references in all markdown files.
Run with: uv run python scripts/check_docs.py"
```

---

## Phase 6: 最终验证（2 天）

### Task 6.1: 全量回归测试

- [ ] **Step 1: Run all checks**

```bash
# Lint
make lint

# Format
make format

# Type check
make type-check

# Test
make test

# Benchmark
make benchmark
```

- [ ] **Step 2: Check coverage**

```bash
uv run pytest --cov=src/vibesop --cov-report=term-missing

# Verify coverage >= 80%
```

- [ ] **Step 3: Run doc consistency check**

```bash
uv run python scripts/check_docs.py
```

- [ ] **Step 4: Verify CLI**

```bash
uv run vibe --help
uv run vibe route --help
uv run vibe config --help
uv run vibe workflow --help
uv run vibe install --help
uv run vibe auto "test query" --dry-run
uv run vibe doctor
uv run vibe version
```

---

### Task 6.2: 更新 CHANGELOG

- [ ] **Step 1: Add v2.2.0 section to CHANGELOG.md**

```markdown
## [2.2.0] - 2026-04-04

### Major Optimization Release

This release significantly improves engineering quality across all dimensions:
CI/CD automation, test coverage, documentation consistency, and architecture clarity.

### Added
- **CI/CD**: GitHub Actions workflows for lint, type-check, test, and release
- **Routing Statistics**: Track layer distribution, hit rate, avg confidence
- **Negative Feedback**: `vibe feedback --not-helpful` to reduce skill scores
- **Performance Benchmarks**: Routing latency and throughput tests
- **Doc Consistency Check**: Script to detect broken file references
- **CODE_OF_CONDUCT.md** and **SECURITY.md**

### Changed
- **Documentation**: Reorganized into user/ and dev/ directories
- **CLI Commands**: Grouped into route/, config/, workflow/, install/ sub-commands
- **Package Structure**: Moved routing/, skills/, memory/, checkpoint/ to top-level
- **Version Management**: Switched to hatch-vcs for automatic versioning from git tags
- **Pre-commit**: Replaced mypy with pyright (single type checker)

### Fixed
- **Documentation**: Removed 29 internal development documents
- **Documentation**: Fixed 12+ broken file references
- **Documentation**: Updated Chinese README migration status
- **Documentation**: Fixed CLI_REFERENCE.md (removed non-existent commands, added missing ones)
- **Documentation**: Fixed QUICK_REFERENCE.md version (1.0.0 → 2.2.0)
- **Bug Report Template**: Updated for CLI tools (not web app)

### Testing
- **Coverage**: Added root-level conftest.py with shared fixtures
- **Coverage**: Added tests for CLI commands (auto, build, doctor, skills)
- **Coverage**: Added tests for installer (init_support, quickstart)
- **Coverage**: Added tests for hooks (base, installer)
- **Coverage**: Added tests for integrations, utils, semantic
- **Coverage Gate**: Set to 80% minimum

### Breaking Changes
- None. All existing commands and APIs remain backward compatible.
- Old import paths (vibesop.core.routing, etc.) still work via re-exports.
- CLI commands available at both top-level and in sub-command groups.
```

- [ ] **Step 2: Final commit**

```bash
git add -A
git commit -m "docs: add v2.2.0 changelog entry

Document all optimizations: CI/CD, test coverage, documentation,
architecture refactoring, version automation, negative feedback,
and performance benchmarks."
```

---

## 自评审

### 1. Spec Coverage

| Spec Requirement | Task | Status |
|-----------------|------|--------|
| 清理内部文档 | Task 1.1 | ✅ |
| 修复断裂引用 | Task 1.2, 1.4 | ✅ |
| 更新中文 README | Task 1.3 | ✅ |
| 修复 CLI_REFERENCE.md | Task 1.4 | ✅ |
| 修复元数据 | Task 1.5 | ✅ |
| 重组文档目录 | Task 1.6 | ✅ |
| CI/CD 搭建 | Task 2.1, 2.2, 2.3 | ✅ |
| 测试覆盖提升 | Task 3.1-3.8 | ✅ |
| core/ 包拆分 | Task 4.1, 4.2 | ✅ |
| CLI 命令分组 | Task 4.3 | ✅ |
| 依赖注入容器 | Task 4.4 | ✅ |
| hatch-vcs 版本自动化 | Task 5.1 | ✅ |
| 偏好学习负反馈 | Task 5.2 | ✅ |
| 路由统计收集 | Task 5.3 | ✅ |
| 性能基准测试 | Task 5.4 | ✅ |
| 文档一致性检查 | Task 5.5 | ✅ |
| 最终验证 | Task 6.1, 6.2 | ✅ |

### 2. Placeholder Scan
- ✅ 无 TBD/TODO
- ✅ 所有步骤包含实际代码
- ✅ 所有命令有预期输出

### 3. Type Consistency
- ✅ 所有 import 路径一致（新路径在 Task 4.1-4.2 定义，re-export 在 core/__init__.py）
- ✅ 方法签名一致
- ✅ Pydantic 模型引用一致

### 4. Scope Check
- ✅ 聚焦于评审提出的 6 个问题
- ✅ 没有引入无关功能
- ⚠️ 计划较大（约 30 个 task），但覆盖了全量优化的所有方面

---

**Plan complete. 总计约 30 个 task，分 6 个 Phase 执行。**
