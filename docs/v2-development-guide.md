# VibeSOP-Py v2.0 开发快速指南

> **在 `feature/v2.0-workflow-engine` 分支上进行开发**
> **创建日期**: 2026-04-04

---

## 🚀 快速开始

### 1. 确认当前分支

```bash
git branch  # 应该显示 * feature/v2.0-workflow-engine
git status  # 应该显示 "On branch feature/v2.0-workflow-engine"
```

### 2. 开发环境准备

```bash
# 确保虚拟环境激活
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate     # Windows

# 安装开发依赖
uv pip install -e ".[dev]"

# 验证环境
vibe --help
pytest --version
```

### 3. 查看开发任务

```bash
# 查看开发日志
cat DEVELOPMENT_LOG.md

# 查看路线图
cat docs/roadmap-2.0-summary.md

# 查看本周任务
cat docs/roadmap-2.0-timeline.md | grep -A 20 "Week 1"
```

---

## 📋 Phase 1 开发任务清单

### Week 1: Pipeline 基础框架

#### ✅ 已完成
- [x] 创建分支 `feature/v2.0-workflow-engine`
- [x] 设置目录结构
- [x] 添加数据模型 (`models.py`)
- [x] 添加异常类 (`exceptions.py`)

#### 🚧 进行中
- [ ] 实现 `WorkflowPipeline` 核心类
  - [ ] `add_stage()` 方法
  - [ ] `execute()` 方法
  - [ ] `get_next_stage()` 方法
  - [ ] 依赖关系解析
  - [ ] 循环依赖检测

#### 📋 待办
- [ ] 实现预定义工作流
  - [ ] `security-review` 工作流
  - [ ] `config-deploy` 工作流
  - [ ] `skill-discovery` 工作流

- [ ] 编写单元测试
  - [ ] `PipelineStage` 测试 (10 tests)
  - [ ] `WorkflowPipeline` 测试 (15 tests)
  - [ ] 工作流集成测试 (5 tests)

---

## 🛠️ 开发工作流

### 日常工作流

```bash
# 1. 拉取最新代码（如果有远程）
git fetch origin
git rebase origin/main

# 2. 创建功能分支（如果需要）
git checkout -b feature/pipeline-core

# 3. 开发和测试
# 编辑代码...
uv run ruff check src/vibesop/workflow
uv run pytest tests/workflow -v

# 4. 提交代码
git add .
git commit -m "feat: implement WorkflowPipeline core logic"

# 5. 推送到远程（如果有）
git push origin feature/pipeline-core
```

### 代码检查清单

**提交前检查**:
- [ ] 代码通过 ruff 检查: `uv run ruff check`
- [ ] 代码格式化: `uv run ruff format`
- [ ] 类型检查通过: `uv run pyright src/vibesop/workflow`
- [ ] 所有测试通过: `uv run pytest tests/workflow -v`
- [ ] 测试覆盖率足够: `uv run pytest --cov=src/vibesop/workflow`

---

## 📁 重要文件说明

### 源代码文件

```
src/vibesop/workflow/
├── __init__.py           # 模块导出
├── models.py             # 数据模型（已创建）
├── exceptions.py         # 异常类（已创建）
├── pipeline.py           # WorkflowPipeline 核心（待实现）
├── state.py              # 状态管理（待实现）
└── pipelines.py          # 预定义工作流（待实现）
```

### 测试文件

```
tests/workflow/
├── __init__.py           # 测试模块（已创建）
├── test_models.py        # 模型测试（待创建）
├── test_pipeline.py      # Pipeline 测试（待创建）
└── test_workflows.py     # 工作流测试（待创建）
```

---

## 🎯 开发目标

### Week 1 目标
- [ ] 完成 `WorkflowPipeline` 核心实现
- [ ] 3 个预定义工作流可用
- [ ] 40+ 单元测试通过
- [ ] 87%+ 代码覆盖率

### Phase 1 目标（Week 1-3）
- [ ] 完整的工作流编排引擎
- [ ] 状态持久化系统
- [ ] 恢复和重试机制
- [ ] CLI 集成完成
- [ ] 333+ 测试通过
- [ ] 88%+ 代码覆盖率

---

## 📊 进度跟踪

### 更新开发日志

每天结束时更新 `DEVELOPMENT_LOG.md`:

```markdown
### 2026-04-04 (Day 1)
- ✅ 完成 PipelineStage 数据模型
- ✅ 完成 WorkflowResult 数据模型
- 🚧 正在实现 WorkflowPipeline.execute()
- 📝 明天计划: 完成依赖关系解析

**代码统计**:
- 新增文件: 2
- 新增代码行数: ~300
- 测试覆盖: 待添加
```

### 查看进度

```bash
# 查看代码统计
find src/vibesop/workflow -name "*.py" | xargs wc -l

# 查看测试统计
uv run pytest --collect-only tests/workflow

# 查看覆盖率
uv run pytest --cov=src/vibesop/workflow --cov-report=term
```

---

## 🧪 测试策略

### 单元测试

```python
# tests/workflow/test_pipeline.py
import pytest
from vibesop.workflow import WorkflowPipeline, PipelineStage, StageStatus

def test_simple_stage_execution():
    """测试简单阶段执行"""
    stage = PipelineStage(
        name="test_stage",
        description="Test stage",
        handler=lambda ctx: {"output": "done"}
    )

    result = stage.handler({})
    assert result == {"output": "done"}

def test_workflow_with_dependencies():
    """测试带依赖关系的工作流"""
    # TODO: 实现测试
    pass

# 运行测试
# uv run pytest tests/workflow/test_pipeline.py -v
```

### 集成测试

```python
# tests/workflow/integration/test_workflows.py
def test_security_review_workflow():
    """测试安全审查工作流"""
    from vibesop.workflow.pipelines import SECURITY_REVIEW_WORKFLOW

    result = SECURITY_REVIEW_WORKFLOW.execute({
        "input": "test input"
    })

    assert result.success
    assert "scan" in result.completed_stages
    assert "analyze" in result.completed_stages
```

---

## 🚨 常见问题

### Q: 如何运行测试？

```bash
# 运行所有 workflow 测试
uv run pytest tests/workflow -v

# 运行特定测试文件
uv run pytest tests/workflow/test_pipeline.py -v

# 运行特定测试
uv run pytest tests/workflow/test_pipeline.py::test_simple_stage_execution -v

# 带覆盖率报告
uv run pytest tests/workflow --cov=src/vibesop/workflow --cov-report=html
```

### Q: 如何调试代码？

```bash
# 使用 Python 调试器
uv run python -m pytest tests/workflow/test_pipeline.py::test_simple_stage_execution -v -s

# 使用 ipdb 调试器
uv run python -m pytest tests/workflow/test_pipeline.py -v --pdb

# 在代码中设置断点
import pdb; pdb.set_trace()  # 使用标准 pdb
import ipdb; ipdb.set_trace()  # 使用 ipdb（需要安装）
```

### Q: 如何查看依赖图？

```bash
# 查看工作流依赖关系
python -c "
from vibesop.workflow.pipelines import SECURITY_REVIEW_WORKFLOW
for stage_name, stage in SECURITY_REVIEW_WORKFLOW.stages.items():
    print(f'{stage_name}: {stage.dependencies}')
"
```

---

## 📞 获取帮助

### 文档
- **完整路线图**: `docs/roadmap-2.0.md`
- **快速参考**: `docs/roadmap-2.0-summary.md`
- **时间表**: `docs/roadmap-2.0-timeline.md`

### 项目管理
- **开发日志**: `DEVELOPMENT_LOG.md`
- **项目看板**: `docs/roadmap-2.0-board.md`

### 技术支持
- **Issues**: https://github.com/nehcuh/vibesop-py/issues
- **Discussions**: https://github.com/nehcuh/vibesop-py/discussions

---

## 🎉 开始编码！

现在一切准备就绪，可以开始 Phase 1 的开发了：

```bash
# 开始实现 WorkflowPipeline
vim src/vibesop/workflow/pipeline.py

# 或使用你喜欢的编辑器
code src/vibesop/workflow/pipeline.py
```

**第一个任务**: 实现 `WorkflowPipeline` 类的 `execute()` 方法

---

**Happy Coding! 🚀**

**文档版本**: 1.0
**创建日期**: 2026-04-04
**维护者**: VibeSOP-Py Team
