# 并行执行设计方案

## 当前状态

ExecutionPlan 只支持串行步骤：
```python
ExecutionPlan(
    steps=[
        ExecutionStep(step_number=1, ...),  # 先执行
        ExecutionStep(step_number=2, ...),  # 再执行
        ExecutionStep(step_number=3, ...),  # 最后执行
    ]
)
```

## 目标

支持并行执行：
```python
ExecutionPlan(
    steps=[
        ExecutionStep(step_number=1, ...),      # 串行
        ExecutionStep(step_number=2, ...),      # 与 step 3 并行
        ExecutionStep(step_number=3, ...),      # 与 step 2 并行
        ExecutionStep(step_number=4, ...),      # 依赖 step 2 和 3
    ]
)
```

## 设计方案

### 1. 扩展 ExecutionStep

```python
class ExecutionStep(BaseModel):
    # ... 现有字段 ...
    
    # 新增字段
    dependencies: list[str] = Field(
        default_factory=list,
        description="Step IDs this step depends on (empty = can run in parallel)"
    )
    can_parallel: bool = Field(
        default=True,
        description="Whether this step can run in parallel with others"
    )
```

### 2. 扩展 ExecutionPlan

```python
class ExecutionPlan(BaseModel):
    # ... 现有字段 ...
    
    # 新增字段
    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.SEQUENTIAL,
        description="How steps should be executed"
    )
    
    def get_parallel_groups(self) -> list[list[ExecutionStep]]:
        """Group steps into parallel batches based on dependencies."""
        # 返回 [[step1], [step2, step3], [step4]]
        # 表示：step1 先执行，step2/step3 并行，step4 最后执行
```

### 3. 执行模式枚举

```python
class ExecutionMode(StrEnum):
    SEQUENTIAL = "sequential"  # 串行执行（默认）
    PARALLEL = "parallel"      # 尽可能并行
    MIXED = "mixed"            # 根据依赖自动决定
```

### 4. 并行调度器

```python
class ParallelScheduler:
    """Schedule and execute steps with parallel support."""
    
    def execute_plan(
        self, 
        plan: ExecutionPlan,
        executor: Callable[[ExecutionStep], Any]
    ) -> list[Any]:
        """Execute plan with parallel steps.
        
        Args:
            plan: Execution plan with dependencies
            executor: Function to execute a single step
            
        Returns:
            List of results in step_number order
        """
```

## 实现步骤

1. 扩展模型 - 添加依赖和并行字段
2. 实现 DAG 分析 - 拓扑排序
3. 实现并行调度器 - asyncio/threading
4. 更新 PlanBuilder - 自动检测可并行步骤
5. 添加测试 - 验证正确性

## 示例

```python
# 用户查询："同时测试前端和后端，然后集成测试"
plan = router.orchestrate("同时测试前端和后端，然后集成测试")

# 生成的计划：
# Batch 1: [test-frontend, test-backend] 并行
# Batch 2: [integration-test] 等待 Batch 1 完成
```
