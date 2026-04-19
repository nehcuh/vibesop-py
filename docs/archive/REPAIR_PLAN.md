# VibeSOP 工程修复计划

> **制定时间**: 2026-04-18
> **基于**: KIMI 专业评审反馈
> **目标**: 从 Beta 提升到 Production Ready

---

## 📋 修复总览

**当前状态**: ⚠️ Beta（功能完整，需要工程加固）
**目标状态**: ✅ Production Ready

**预计总工时**: 10-14 小时
**优先级**: P0 > P1 > P2

---

## 🎯 Phase 1: P0 紧急修复（2-3 小时）

### 任务 1.1: 修复测试失败 ⏱ 30 min

**问题**: 测试使用了错误的 AuditResult 字段名

**文件**: `tests/core/skills/test_executor.py`

**修复步骤**:
1. 找到所有使用 `summary=` 的地方
2. 改为 `reason=`
3. 运行测试验证

**代码变更**:
```python
# 修复前
mock_audit.return_value = AuditResult(
    is_safe=False,
    threats=[...],
    summary="Security audit failed",  # ❌
)

# 修复后
mock_audit.return_value = AuditResult(
    is_safe=False,
    threats=[...],
    reason="Security audit failed",  # ✅
)
```

**验证**:
```bash
python -m pytest tests/core/skills/test_executor.py -v
# 预期：所有测试通过
```

---

### 任务 1.2: 明确架构定位 ⏱ 1 小时

**问题**: "路由引擎"vs"执行引擎"的定位矛盾

**决策**: 选择"选项A：诚实化"

**更新文件**:
- `README.md`
- `PHILOSOPHY.md`
- `docs/architecture/three-layers.md`
- `src/vibesop/core/skills/executor.py` (注释)

**新的定位声明**:
```markdown
## VibeSOP 是什么？

VibeSOP 提供**智能路由**和**轻量级技能执行**：

### 智能路由（核心功能）
- 理解你的意图（自然语言，支持中英文）
- 找到最合适的技能（从 45+ 技能中选择，94% 准确率）
- 学习你的偏好（越用越准确）

### 轻量级执行（辅助功能）
- 快速验证技能是否适合当前任务
- 本地测试和调试
- CI/CD 自动化测试

**注意**: 复杂生产场景推荐使用原生 AI Agent（如 Claude Code、Cursor）。
```

**删除/修改的免责声明**:
- ❌ "VibeSOP is NOT an execution engine"
- ✅ "VibeSOP provides lightweight skill execution for quick validation"

---

### 任务 1.3: 修复 Loader 实例重复 ⏱ 30 min

**问题**: SkillManager 和 ExternalSkillExecutor 各自创建 Loader 实例

**文件**: `src/vibesop/core/skills/executor.py`, `src/vibesop/core/skills/manager.py`

**修复步骤**:
1. 修改 `ExternalSkillExecutor.__init__` 接受 `loader` 参数
2. 在 `SkillManager.__init__` 中注入 `loader`
3. 确保只有一个 Loader 实例

**代码变更**:

```python
# executor.py
class ExternalSkillExecutor:
    def __init__(
        self,
        project_root: str | Path = Path.cwd(),
        loader: SkillLoader | None = None,  # 新增参数
    ):
        self.project_root = Path(project_root)
        self._loader = loader or SkillLoader(project_root=self.project_root)  # 复用或创建
        # ...

# manager.py
class SkillManager:
    def __init__(self, project_root: str | Path = Path.cwd()):
        self.project_root = Path(project_root)
        self._loader = SkillLoader(project_root=self.project_root)
        self._executor = ExternalSkillExecutor(
            project_root=self.project_root,
            loader=self._loader,  # 注入同一个实例
        )
```

**验证**:
```bash
python -c "
from vibesop.core.skills import SkillManager
sm = SkillManager()
print(sm._loader is sm._executor._loader)  # 应该输出 True
"
```

---

## 🔧 Phase 2: P1 重要修复（6-8 小时）

### 任务 2.1: 替换 eval() 为安全求值 ⏱ 3-4 小时

**问题**: `eval()` 存在安全隐患，可能被绕过

**文件**: `src/vibesop/core/skills/workflow.py`

**解决方案**: 实现 AST-based 安全表达式求值

**实现步骤**:
1. 创建 `_safe_eval_condition()` 函数
2. 使用 `ast` 模块解析表达式
3. 白名单验证节点类型
4. 执行求值

**代码实现**:

```python
import ast

def _safe_eval_condition(self, condition: str, context: ExecutionContext) -> bool:
    """Safely evaluate a condition expression using AST parsing.

    Only allows a whitelist of AST node types for security.
    """
    try:
        # 解析表达式为 AST
        tree = ast.parse(condition, mode='eval')

        # 定义允许的节点类型白名单
        ALLOWED_NODES = {
            ast.Expression,      # 根节点
            ast.Name,            # 变量名
            ast.Constant,        # 常量（数字、字符串、布尔值）
            ast.Compare,         # 比较运算
            ast.BoolOp,          # 布尔运算（and, or）
            ast.UnaryOp,         # 一元运算（not, +, -）
            ast.BinOp,           # 二元运算（+, -, *, /, etc.）
            ast.And,             # and 操作符
            ast.Or,              # or 操作符
            ast.Not,             # not 操作符
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,  # 算术运算
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,  # 比较运算
            ast.Call,            # 函数调用（仅允许白名单函数）
        }

        # 允许的内置函数
        ALLOWED_FUNCTIONS = {
            'len', 'str', 'int', 'float', 'bool',
            'abs', 'min', 'max', 'sum',
            'any', 'all', 'enumerate',
            'isinstance', 'hasattr', 'getattr',
        }

        # 遍历 AST，检查所有节点是否在白名单中
        for node in ast.walk(tree):
            if not isinstance(node, tuple(ALLOWED_NODES)):
                logger.error(f"Unsafe AST node: {type(node).__name__}")
                return False

            # 额外检查函数调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id not in ALLOWED_FUNCTIONS:
                        logger.error(f"Function not allowed: {node.func.id}")
                        return False
                else:
                    # 不允许复杂调用（如 obj.method()）
                    logger.error(f"Complex call not allowed: {ast.dump(node)}")
                    return False

        # 准备求值上下文
        eval_context = {
            'True': True,
            'False': False,
            'None': None,
        }

        # 添加变量（从 context 中）
        if context and context.variables:
            eval_context.update(context.variables)

        # 执行求值
        result = eval(compile(tree, '<string>', 'eval'), {"__builtins__": {}}, eval_context)
        return bool(result)

    except (SyntaxError, ValueError, TypeError, NameError) as e:
        logger.error(f"Failed to evaluate condition: {condition}, error: {e}")
        return False
```

**单元测试**:

```python
# tests/core/skills/test_workflow_safe_eval.py
def test_safe_eval_basic():
    """Test basic safe evaluation."""
    engine = WorkflowEngine()
    context = ExecutionContext(variables={'x': 5, 'y': 10})

    # 允许的操作
    assert engine._safe_eval_condition("x == 5", context) is True
    assert engine._safe_eval_condition("x < y", context) is True
    assert engine._safe_eval_condition("x > 10 or y > 5", context) is True
    assert engine._safe_eval_condition("not (x > 10)", context) is True

def test_safe_eval_blocks_dangerous():
    """Test that dangerous operations are blocked."""
    engine = WorkflowEngine()
    context = ExecutionContext(variables={'x': 5})

    # 阻止危险操作
    assert engine._safe_eval_condition("__import__('os')", context) is False
    assert engine._safe_eval_condition("open('/etc/passwd')", context) is False
    assert engine._safe_eval_condition("eval('1+1')", context) is False
    assert engine._safe_eval_condition("().__class__", context) is False
```

**验证**:
```bash
python -m pytest tests/core/skills/test_workflow_safe_eval.py -v
# 预期：所有测试通过
```

---

### 任务 2.2: 改用线程池实现超时 ⏱ 2-3 小时

**问题**: `signal.SIGALRM` 在 Windows 不支持，多线程环境不可靠

**文件**: `src/vibesop/core/skills/workflow.py`

**解决方案**: 使用 `concurrent.futures.ThreadPoolExecutor`

**实现步骤**:
1. 移除 signal-based 超时
2. 使用 `ThreadPoolExecutor` 包装执行
3. 添加 `future.result(timeout=...)`

**代码实现**:

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import threading

class WorkflowEngine:
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        # 移除 signal-based 超时
        # self._setup_signal_handler()

    def execute(
        self,
        workflow: Workflow,
        context: ExecutionContext,
    ) -> WorkflowResult:
        """Execute workflow with timeout using thread pool."""

        def _execute_internal():
            """Internal execution in separate thread."""
            try:
                results = []
                for step in workflow.steps:
                    step_result = self._execute_step(step, context)
                    results.append(step_result)

                    if not step_result.success:
                        return WorkflowResult(
                            success=False,
                            error=f"Step failed: {step_result.error}",
                            steps_completed=len(results),
                        )

                return WorkflowResult(
                    success=True,
                    output=context.variables.get('output'),
                    steps_completed=len(results),
                )

            except Exception as e:
                logger.exception("Workflow execution failed")
                return WorkflowResult(
                    success=False,
                    error=str(e),
                    steps_completed=0,
                )

        # 使用线程池执行，带超时控制
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_execute_internal)

            try:
                result = future.result(timeout=self.timeout)
                return result

            except FutureTimeoutError:
                # 取消任务（如果还在运行）
                future.cancel()

                logger.error(f"Workflow execution timed out after {self.timeout}s")

                return WorkflowResult(
                    success=False,
                    error=f"Workflow execution timed out after {self.timeout}s",
                    steps_completed=0,
                )

            except Exception as e:
                logger.exception("Unexpected error during workflow execution")

                return WorkflowResult(
                    success=False,
                    error=f"Unexpected error: {str(e)}",
                    steps_completed=0,
                )
```

**注意**:
- `future.cancel()` 不能强制杀死正在运行的线程，但可以设置标志
- 对于长时间运行的操作，需要在循环中检查取消标志

**可选改进**: 添加取消标志支持

```python
class CancellationFlag:
    """Thread-safe cancellation flag."""

    def __init__(self):
        self._cancelled = False
        self._lock = threading.Lock()

    def cancel(self):
        with self._lock:
            self._cancelled = True

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

# 在 WorkflowEngine 中使用
class WorkflowEngine:
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self._cancellation_flag = None

    def _execute_internal(self):
        # 在循环中检查取消标志
        if self._cancellation_flag and self._cancellation_flag.is_cancelled():
            raise WorkflowCancelledException("Workflow was cancelled")
        # ...
```

**验证**:
```bash
# 测试超时
python -c "
from vibesop.core.skills.workflow import WorkflowEngine
engine = WorkflowEngine(timeout=1)
# 创建一个长时间运行的 workflow
# 验证是否在 1 秒后超时
"
```

---

## 🔨 Phase 3: P2 改进优化（3-4 小时）

### 任务 3.1: SessionContext 依赖注入 ⏱ 1 小时

**问题**: SessionContext 直接实例化 UnifiedRouter，难以测试

**文件**: `src/vibesop/core/sessions/context.py`

**修复步骤**:
1. 添加 `router` 参数
2. 保持向后兼容（默认创建新实例）
3. 更新测试以验证依赖注入

**代码实现**:

```python
class SessionContext:
    def __init__(
        self,
        project_root: str | Path = Path.cwd(),
        router: UnifiedRouter | None = None,  # 新增参数
        session_id: str | None = None,
    ):
        self.project_root = Path(project_root)
        self._router = router or UnifiedRouter(project_root=self.project_root)
        self.session_id = session_id or str(uuid.uuid4())
        # ...
```

**测试**:

```python
# tests/core/sessions/test_context.py
def test_session_context_with_injected_router():
    """Test SessionContext with injected router."""
    from unittest.mock import Mock

    mock_router = Mock(spec=UnifiedRouter)
    context = SessionContext(router=mock_router)

    assert context._router is mock_router
    # 验证可以使用 mock router
```

---

### 任务 3.2: 文档整理归档 ⏱ 2 小时

**问题**: 文档过于膨胀，难以导航

**方案**: 创建 `docs/archive/` 目录

**执行步骤**:
1. 创建 `docs/archive/` 目录
2. 移动阶段性文档：
   - `PHASE2_ARCHITECTURE_COMPLETE.md`
   - `PHASE3_COMPLETE.md`
   - `PHASE4_COMPLETE.md`
   - `PHASE3_ROUTING_PROGRESS.md`
   - `EXTERNAL_SKILLS_STEP1_4_COMPLETE.md`
   - `EXTERNAL_SKILLS_PROGRESS.md`
3. 创建 `docs/archive/README.md` 说明这些是历史文档
4. 更新 `docs/README.md` 添加归档文档的链接

**保留的永恒文档**:
- `PHILOSOPHY.md`
- `EXTERNAL_SKILLS_GUIDE.md`
- `EXTERNAL_SKILLS_EXAMPLES.md`
- `QUICKSTART_DEVELOPERS.md`
- `QUICKSTART_USERS.md`
- `docs/architecture/*.md`

**创建归档说明**:

```markdown
# Archive - 历史文档

这个目录包含 VibeSOP 开发过程中的阶段性文档。

## 📁 目录结构

- `PHASE2_ARCHITECTURE_COMPLETE.md` - Phase 2: 架构统一完成总结
- `PHASE3_ROUTING_PROGRESS.md` - Phase 3: 路由优化进度记录
- `PHASE3_COMPLETE.md` - Phase 3: 路由优化完成总结
- `PHASE4_COMPLETE.md` - Phase 4: 文档和用户体验完成总结
- `EXTERNAL_SKILLS_*.md` - 外部技能开发的阶段性记录

## ⚠️ 重要说明

这些文档记录了开发过程和决策历史，但可能已经过时。

**对于当前状态，请参考**:
- `../PHILOSOPHY.md` - 核心哲学和使命
- `../QUICKSTART_DEVELOPERS.md` - 开发者快速指南
- `../QUICKSTART_USERS.md` - 用户快速指南
- `../architecture/` - 架构文档

---

**最后更新**: 2026-04-18
```

---

## 📊 验收标准

### Phase 1 完成标准

- [ ] 所有测试通过（0 失败）
- [ ] 文档中的定位声明一致
- [ ] Loader 实例复用验证通过

### Phase 2 完成标准

- [ ] `_safe_eval_condition()` 通过所有安全测试
- [ ] 超时控制在 Windows 和 Linux 下都正常工作
- [ ] 单元测试覆盖率 >90%

### Phase 3 完成标准

- [ ] SessionContext 可以注入 mock router
- [ ] docs/ 目录清晰，易于导航
- [ ] 归档文档有明确说明

---

## 🎯 最终目标

**修复后状态**: ✅ **Production Ready**

**证据**:
- ✅ 所有测试通过
- ✅ 架构定位清晰
- ✅ 安全隐患消除
- ✅ 跨平台兼容
- ✅ 代码质量提升
- ✅ 文档结构清晰

---

**制定时间**: 2026-04-18
**预计完成**: 2026-04-19
**当前状态**: 📋 计划制定完成，准备执行
