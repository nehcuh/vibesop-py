# VibeSOP v2.2.0 全面优化设计文档

> **日期**: 2026-04-04
> **状态**: 待评审
> **目标**: 从 6.5 分提升到 8.5+ 分

---

## 1. 问题概述

VibeSOP 核心设计优秀（路由引擎、适配器模式、安全机制），但工程纪律严重不足：

| 维度 | 当前评分 | 目标评分 | 差距 |
|------|---------|---------|------|
| 设计理念 | 8/10 | 8.5/10 | +0.5 |
| 架构设计 | 7.5/10 | 8.5/10 | +1.0 |
| 实现质量 | 6/10 | 8/10 | +2.0 |
| 测试覆盖 | 3/10 | 8/10 | +5.0 |
| CI/CD | 0/10 | 8/10 | +8.0 |
| 文档质量 | 4/10 | 8/10 | +4.0 |
| **综合** | **6.5/10** | **8.5/10** | **+2.0** |

---

## 2. 优化架构

### 2.1 六大优化领域

```
┌─────────────────────────────────────────────────────────┐
│                    VibeSOP v2.2.0                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ CI/CD    │  │ 测试覆盖 │  │ 文档治理 │              │
│  │ 自动化   │  │ 80%+     │  │ 一致性   │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │              │              │                   │
│  ┌────┴──────────────┴──────────────┴─────┐             │
│  │          架构重构                       │             │
│  │  core/ 拆分 + CLI 分组 + 依赖注入       │             │
│  └────┬───────────────────────────────────┘             │
│       │                                                 │
│  ┌────┴───────────────────────────────────┐             │
│  │          工程纪律提升                    │             │
│  │  版本自动化 + 偏好学习负反馈 + 性能基准  │             │
│  └─────────────────────────────────────────┘             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 依赖关系

```
Phase 1: 文档清理 (无依赖，立即可做)
    ↓
Phase 2: CI/CD 搭建 (依赖 Phase 1 的文档正确性)
    ↓
Phase 3: 测试覆盖提升 (依赖 Phase 2 的 CI 验证)
    ↓
Phase 4: 架构重构 (依赖 Phase 3 的测试保护网)
    ↓
Phase 5: 工程纪律 (依赖 Phase 4 的新架构)
    ↓
Phase 6: 最终验证 (全量回归)
```

---

## 3. 详细设计

### 3.1 Phase 1: 文档治理

**目标**: 从 4/10 提升到 8/10

#### 3.1.1 清理内部文件

删除以下非用户文档：
- `docs/FINAL_ASSESSMENT.md`
- `docs/FINAL_HONEST_CHECK.md`
- `docs/PROJECT_STATUS.md`
- `docs/SESSION_SUMMARY.md`
- `docs/FINAL_SESSION_SUMMARY.md`
- `docs/PROGRESS_UPDATE.md`
- `docs/IMPLEMENTATION_SUMMARY.md`
- `docs/COMPLETION_SUMMARY.md`
- `docs/INSTALLER_GAP_ANALYSIS.md`
- `docs/INSTALLER_IMPLEMENTATION_STATUS.md`
- `docs/RECOMMENDATIONS.md`

#### 3.1.2 文档目录重组

```
docs/
├── README.md                    # 文档索引（新建）
├── user/                        # 用户文档
│   ├── getting-started.md       # 快速开始
│   ├── cli-reference.md         # CLI 完整参考
│   ├── api-reference.md         # Python API 参考
│   ├── configuration.md         # 配置指南
│   ├── workflows.md             # 工作流指南
│   └── troubleshooting.md       # 故障排除
├── dev/                         # 开发文档
│   ├── architecture.md          # 架构设计
│   ├── contributing.md          # 贡献指南
│   ├── testing.md               # 测试指南
│   └── releasing.md             # 发布指南
└── features/                    # 特性文档（保留现有）
    ├── semantic/
    └── triggers/
```

#### 3.1.3 修复断裂引用

- README.md: 删除对不存在文件的引用（`V2_Release_COMPLETE.md`, `DEPLOYMENT_COMPLETE.md`, `COMPLETE.md`, `docs/workflows/guide.md`, `docs/workflows/api.md`）
- README.zh-CN.md: 同步迁移状态，所有已完成功能标记为 `[x]`
- CLI_REFERENCE.md: 
  - 删除 `vibe render` 命令文档
  - 补充所有缺失的 20+ 个命令
  - 更新安装方式（poetry → uv）
  - 修复 GitHub 链接（yourusername → nehcuh）
- QUICK_REFERENCE.md: 版本更新为 2.1.0 → 2.2.0
- CHANGELOG.md: 删除对 `COMPLETE.md` 的引用

#### 3.1.4 修复元数据

- `pyproject.toml`: 修复 author email（`your@email.com` → 真实邮箱或删除）
- Issue 模板: 修复 bug report 的 Web 应用语言，改为 CLI 工具适用

---

### 3.2 Phase 2: CI/CD 搭建

**目标**: 从 0/10 提升到 8/10

#### 3.2.1 GitHub Actions 工作流

创建 `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run ruff check .
      - run: uv run ruff format --check

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run pyright

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run pytest --cov=src/vibesop --cov-report=xml
      - uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

#### 3.2.2 发布工作流

创建 `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
      - uses: softprops/action-gh-release@v1
        with:
          generate_release_notes: true
```

#### 3.2.3 更新 pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
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
        entry: uv run pytest tests/ -x -q
        language: system
        types: [python]
        pass_filenames: false
```

#### 3.2.4 添加 CODEOWNERS

```
# .github/CODEOWNERS
* @nehcuh
/src/vibesop/core/ @nehcuh
/src/vibesop/workflow/ @nehcuh
/tests/ @nehcuh
```

---

### 3.3 Phase 3: 测试覆盖提升

**目标**: 从 3/10 提升到 8/10（行覆盖率 80%+，分支覆盖率 50%+）

#### 3.3.1 创建根目录 conftest.py

```python
# tests/conftest.py
"""Root conftest with shared fixtures."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

@pytest.fixture
def temp_dir(tmp_path):
    """Temporary directory for testing."""
    return tmp_path

@pytest.fixture
def mock_llm_client():
    """Mock LLM client to avoid API calls."""
    with patch('vibesop.llm.anthropic.AnthropicClient') as mock:
        mock.return_value.query.return_value = {
            'skill_id': '/review',
            'confidence': 0.95
        }
        yield mock

@pytest.fixture
def sample_skill():
    """Sample skill definition for testing."""
    from vibesop.core.models import SkillDefinition
    return SkillDefinition(
        id='/test',
        name='Test Skill',
        description='A test skill',
        trigger_when=['test']
    )
```

#### 3.3.2 测试优先级矩阵

| 模块 | 当前覆盖 | 目标覆盖 | 优先级 | 预估工作量 |
|------|---------|---------|--------|-----------|
| cli/commands/ | 0% | 60% | P0 | 3 天 |
| installer/ | 0% | 80% | P0 | 2 天 |
| hooks/ | 0% | 80% | P0 | 1 天 |
| semantic/ | 0% | 80% | P1 | 2 天 |
| integrations/ | 0% | 80% | P1 | 1 天 |
| utils/ | 0% | 80% | P1 | 1 天 |
| core/routing/ | 23% | 85% | P1 | 2 天 |
| core/skills/ | 29% | 85% | P1 | 1 天 |
| adapters/ | 35% | 85% | P2 | 1 天 |
| builder/ | 34% | 85% | P2 | 1 天 |
| security/ | 31% | 85% | P2 | 1 天 |
| workflow/ | 46% | 85% | P2 | 1 天 |

#### 3.3.3 测试策略

**CLI 命令测试**（最关键）:
- 使用 `typer.testing.CliRunner` 隔离测试
- Mock 文件系统操作
- 验证输出内容（不仅 exit_code）
- 测试正常路径 + 异常路径

```python
# tests/cli/test_route.py
from typer.testing import CliRunner
from vibesop.cli.main import app

runner = CliRunner()

def test_route_finds_skill():
    result = runner.invoke(app, ["route", "review my code"])
    assert result.exit_code == 0
    assert "/review" in result.stdout
    assert "confidence" in result.stdout

def test_route_no_match():
    result = runner.invoke(app, ["route", "xyzabc123"])
    assert result.exit_code == 1
    assert "No matching skill" in result.stdout
```

**Installer 测试**:
- Mock 文件系统（`pyfakefs` 或 `tmp_path`）
- 验证文件创建/删除
- 测试回滚机制

**添加 pytest 插件**:
```toml
[project.optional-dependencies]
dev = [
    # ... existing
    "pytest-mock>=3.14.0",
    "pyfakefs>=5.7.0",
]
```

#### 3.3.4 覆盖率门禁

```toml
[tool.coverage.report]
fail_under = 80
show_missing = true
```

---

### 3.4 Phase 4: 架构重构

**目标**: 从 7.5/10 提升到 8.5/10

#### 3.4.1 拆分 core/ 包

当前 `core/` 过于臃肿，拆分为独立包：

```
src/vibesop/
├── core/                      # 保留核心模型和配置
│   ├── __init__.py
│   ├── models.py              # Pydantic 数据模型
│   ├── config.py              # 配置加载器
│   └── preference.py          # 偏好学习
│
├── routing/                   # 独立包（原 core/routing/）
│   ├── __init__.py
│   ├── engine.py
│   ├── semantic.py
│   ├── fuzzy.py
│   └── cache.py
│
├── skills/                    # 独立包（原 core/skills/）
│   ├── __init__.py
│   ├── base.py
│   ├── loader.py
│   └── manager.py
│
├── memory/                    # 独立包（原 core/memory/）
│   ├── __init__.py
│   ├── base.py
│   ├── manager.py
│   └── storage.py
│
└── checkpoint/                # 独立包（原 core/checkpoint/）
    ├── __init__.py
    ├── base.py
    ├── manager.py
    └── storage.py
```

**向后兼容**: 在 `core/__init__.py` 中保留 re-export:

```python
# 保持向后兼容
from vibesop.routing.engine import SkillRouter
from vibesop.skills.manager import SkillManager
# ... 其他 re-exports
```

#### 3.4.2 CLI 命令分组

当前 30+ 个扁平命令，重组为子命令组：

```python
# src/vibesop/cli/main.py
import typer

app = typer.Typer(no_args_is_help=True)

# 路由相关
route_app = typer.Typer(help="Skill routing and detection")
app.add_typer(route_app, name="route")

@route_app.command()
def single(query: str):
    """Route a single query."""
    ...

@route_app.command()
def select():
    """Interactive skill selection."""
    ...

@route_app.command()
def validate():
    """Validate routing configuration."""
    ...

# 配置相关
config_app = typer.Typer(help="Configuration management")
app.add_typer(config_app, name="config")

@config_app.command()
def semantic():
    """Configure semantic matching."""
    ...

# 工作流相关
workflow_app = typer.Typer(help="Workflow orchestration")
app.add_typer(workflow_app, name="workflow")

# 安装相关
install_app = typer.Typer(help="Installation and setup")
app.add_typer(install_app, name="install")

# 诊断相关
doctor_app = typer.Typer(help="Diagnostics and health")
app.add_typer(doctor_app, name="doctor")

# 保留常用命令在顶层
@app.command()
def auto(query: str):
    """Auto-detect intent and execute."""
    ...

@app.command()
def skills():
    """List all available skills."""
    ...

@app.command()
def version():
    """Show version."""
    ...
```

**新旧兼容**:
- 旧命令 `vibe route` → 新命令 `vibe route single`
- 旧命令 `vibe route-select` → 新命令 `vibe route select`
- 保留旧命令为别名（deprecated 警告）

#### 3.4.3 依赖注入（轻量级）

不引入重型 DI 框架，使用简单的容器模式：

```python
# src/vibesop/core/container.py
"""Simple dependency injection container."""

from typing import Dict, Any, Callable

class Container:
    _services: Dict[str, Any] = {}
    _factories: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, name: str, instance: Any):
        cls._services[name] = instance
    
    @classmethod
    def factory(cls, name: str, factory_fn: Callable):
        cls._factories[name] = factory_fn
    
    @classmethod
    def resolve(cls, name: str) -> Any:
        if name not in cls._services and name in cls._factories:
            cls._services[name] = cls._factories[name]()
        return cls._services[name]
    
    @classmethod
    def reset(cls):
        """Clear all services (for testing)."""
        cls._services.clear()
```

**使用示例**:

```python
# 注册
Container.factory("router", lambda: SkillRouter())
Container.factory("skill_manager", lambda: SkillManager())

# 使用
router = Container.resolve("router")

# 测试时 mock
Container.register("router", MockRouter())
```

---

### 3.5 Phase 5: 工程纪律提升

#### 3.5.1 版本自动管理

使用 `hatch-vcs` 从 git tag 自动获取版本：

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.hooks.vcs]
version-file = "src/vibesop/_version.py"
```

删除手动维护的 `version = "2.1.0"` 和 `_version.py`。

#### 3.5.2 偏好学习负反馈

当前只有正向反馈，添加负反馈机制：

```python
# src/vibesop/core/preference.py

class PreferenceLearner:
    def record_feedback(
        self,
        skill_id: str,
        query: str,
        helpful: bool,  # 新增：是否有帮助
        confidence: float
    ):
        """Record user feedback (positive or negative)."""
        key = f"{skill_id}:{query}"
        
        if helpful:
            self._positive_feedback[key] = self._positive_feedback.get(key, 0) + 1
        else:
            self._negative_feedback[key] = self._negative_feedback.get(key, 0) + 1
        
        # 更新评分（负反馈扣分）
        score = self._calculate_score(skill_id, query)
        self._scores[skill_id] = max(0.0, score)  # 不低于 0
```

**CLI 命令**:

```python
@app.command()
def feedback(
    skill_id: str = typer.Argument(...),
    helpful: bool = typer.Option(True, "--helpful/--not-helpful"),
    query: str = typer.Option(..., "--query")
):
    """Record feedback for a skill recommendation."""
    learner = PreferenceLearner()
    learner.record_feedback(skill_id, query, helpful)
    
    if helpful:
        typer.echo(f"✅ Thanks! '{skill_id}' score increased.")
    else:
        typer.echo(f"📉 Noted. '{skill_id}' score decreased for similar queries.")
```

#### 3.5.3 性能基准测试

创建 `tests/benchmark/` 目录：

```python
# tests/benchmark/test_routing_performance.py
import pytest
import time

@pytest.mark.benchmark
def test_routing_latency(benchmark):
    """Test routing engine latency."""
    router = SkillRouter()
    
    def route_query():
        return router.route("review my code")
    
    result = benchmark(route_query)
    assert result.primary_match.confidence > 0.5
    assert result.latency_ms < 10  # < 10ms target

@pytest.mark.benchmark
def test_semantic_latency(benchmark):
    """Test semantic matching latency."""
    # ... similar
```

**Makefile 添加**:

```makefile
benchmark: ## Run performance benchmarks
	uv run pytest tests/benchmark/ -v --benchmark-only
```

#### 3.5.4 路由统计

在路由引擎中添加统计收集：

```python
# src/vibesop/routing/engine.py

class SkillRouter:
    def __init__(self):
        self._stats = {
            'total_queries': 0,
            'layer_hits': {0: 0, 1: 0, 2: 0, 3: 0, 4: 0},
            'avg_confidence': 0.0,
        }
    
    def route(self, query: str) -> RoutingResult:
        self._stats['total_queries'] += 1
        
        # ... routing logic ...
        
        self._stats['layer_hits'][matched_layer] += 1
        return result
    
    def get_stats(self) -> dict:
        """Get routing statistics for optimization."""
        return self._stats.copy()
```

---

### 3.6 Phase 6: 最终验证

#### 3.6.1 全量回归测试

```bash
# 1. Lint
uv run ruff check .
uv run ruff format --check

# 2. Type check
uv run pyright

# 3. Test
uv run pytest --cov=src/vibesop --cov-report=term-missing

# 4. Benchmark
uv run pytest tests/benchmark/ -v

# 5. E2E
uv run pytest tests/e2e/ -v
```

#### 3.6.2 文档一致性检查

创建脚本验证文档与代码一致性：

```python
# scripts/check_docs.py
"""Check documentation consistency with code."""

import re
from pathlib import Path
from vibesop.cli.main import app

def check_cli_commands():
    """Verify all documented commands exist."""
    # Parse CLI_REFERENCE.md for commands
    # Compare with actual commands in app
    # Report discrepancies
    pass

def check_broken_links():
    """Check for broken file references in docs."""
    # Parse all .md files for file links
    # Verify each file exists
    # Report broken links
    pass

if __name__ == "__main__":
    check_cli_commands()
    check_broken_links()
```

---

## 4. 工作量估算

| Phase | 内容 | 预估工作量 | 风险 |
|-------|------|-----------|------|
| Phase 1 | 文档治理 | 1 天 | 低 |
| Phase 2 | CI/CD 搭建 | 1 天 | 低 |
| Phase 3 | 测试覆盖 | 2 周 | 中 |
| Phase 4 | 架构重构 | 1 周 | 高（破坏性变更） |
| Phase 5 | 工程纪律 | 3 天 | 低 |
| Phase 6 | 最终验证 | 2 天 | 低 |
| **总计** | | **约 3 周** | |

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 架构重构引入 bug | 高 | Phase 3 先建立测试保护网，重构前后对比测试 |
| 测试工作量超出预期 | 中 | 优先覆盖核心路径，非关键模块可后续补充 |
| CLI 分组破坏现有脚本 | 中 | 保留旧命令为别名，deprecated 警告过渡 |
| CI/CD 配置复杂 | 低 | 从简单开始，逐步增加复杂度 |

---

## 6. 成功标准

优化完成后，以下指标应达到：

| 指标 | 当前 | 目标 |
|------|------|------|
| 综合评分 | 6.5/10 | 8.5/10 |
| 测试行覆盖率 | 16% | 80%+ |
| 测试分支覆盖率 | 3.1% | 50%+ |
| CI/CD | 无 | PR 自动验证 |
| 文档一致性 | 4/10 | 8/10 |
| 零覆盖文件数 | 53 | 0 |
| 断裂文档引用 | 12+ | 0 |
| CLI 命令组织 | 扁平 30+ | 分组 5-6 组 |

---

## 7. 向后兼容承诺

- ✅ 所有现有 API 保持兼容（通过 re-export）
- ✅ CLI 旧命令保留为别名（带 deprecated 警告）
- ✅ 配置文件格式不变
- ✅ 技能定义格式不变
- ⚠️ `core/routing/` 等路径迁移到新位置（旧路径仍可用）

---

## 8. 自评审

### 8.1 Placeholder 扫描
- ✅ 无 TBD/TODO
- ✅ 所有章节完整

### 8.2 内部一致性
- ✅ 架构设计与实施计划一致
- ✅ 工作量估算与任务分解一致
- ✅ 依赖关系合理（测试在重构前）

### 8.3 范围检查
- ✅ 聚焦于评审提出的 6 个问题
- ✅ 没有引入无关功能
- ⚠️ 范围较大（3 周），但用户选择了"全量优化"

### 8.4 歧义检查
- ✅ 所有目标有明确数值指标
- ✅ 每个 Phase 有明确的完成标准
- ✅ 风险有具体缓解措施

---

**下一步**: 用户评审此设计文档，通过后调用 writing-plans 创建详细实施计划。
