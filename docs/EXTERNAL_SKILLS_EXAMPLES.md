# VibeSOP 外部技能 - 完整示例

> **版本**: 4.1.0
> **目标**: 展示如何创建和使用外部技能

---

## 示例 1: 简单的代码审查技能

### SKILL.md

```markdown
---
name: Code Reviewer
description: Quick code review for common issues
namespace: example
version: 1.0.0
---

# Code Reviewer

Perform quick code review to catch common issues.

## Steps

1. Check syntax
   Verify code has no syntax errors

2. Check style
   - Follow PEP 8 guidelines
   - Check naming conventions
   - Verify formatting

3. Check logic
   - Look for obvious bugs
   - Check for edge cases
   - Verify error handling

4. Generate report
   Summarize findings
```

### 使用代码

```python
from vibesop.core.skills.manager import SkillManager

manager = SkillManager()

# 获取技能定义
definition = manager.get_skill_definition("example/code-reviewer")

if definition:
    print(f"工作流: {definition['workflow']['name']}")
    print(f"步骤: {len(definition['workflow']['steps'])}")

    # 执行技能
    result = manager.execute_skill(
        "example/code-reviewer",
        context={"file_path": "main.py"}
    )

    if result["success"]:
        print(f"输出:\n{result['output']}")
```

---

## 示例 2: 数据库迁移技能

### SKILL.md

```markdown
---
name: Database Migrator
description: Safe database schema migration
namespace: database
version: 2.0.0
---

# Database Migrator

Execute database migrations safely with rollback support.

## Steps

1. Backup database
   instruction: Create backup before migration

2. Validate schema
   Check that new schema is valid

3. Run migration
   instruction: Execute migration SQL

4. Verify migration
   - Check data integrity
   - Verify constraints
   - Test queries

5. Commit or rollback
   - Commit if successful
   - Rollback if failed
```

### 使用代码

```python
result = manager.execute_skill(
    "database/migrator",
    context={
        "database": "production",
        "schema_file": "schema_v2.sql",
    }
)

if result["success"]:
    print("迁移成功!")
else:
    print(f"迁移失败: {result['error']}")
```

---

## 示例 3: 带变量的模板生成器

### SKILL.md

```markdown
---
name: Template Generator
description: Generate code from templates
namespace: codegen
version: 1.0.0
---

# Template Generator

Generate code from Jinja2 templates.

## Steps

1. Load template
   Read the template file

2. Substitute variables
   Replace {variable} placeholders

3. Generate code
   Output the generated code

4. Validate output
   Check for syntax errors
```

### 使用代码

```python
result = manager.execute_skill(
    "codegen/template-generator",
    context={
        "template_file": "api_template.j2",
        "model_name": "User",
        "model_fields": ["id", "name", "email"],
    }
)
```

---

## 示例 4: AI Agent 完整集成

### Claude Code 技能

```python
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from vibesop.core.skills.manager import SkillManager

# 初始化
manager = SkillManager()

# 获取技能定义
skill_id = "example/code-reviewer"
definition = manager.get_skill_definition(skill_id)

if definition:
    workflow = definition["workflow"]
    print(f"技能: {workflow['name']}")
    print(f"步骤数: {len(workflow['steps'])}\n")

    # 模拟 Claude Code 执行
    print("Claude Code 执行开始:\n")

    for i, step in enumerate(workflow["steps"], 1):
        step_type = step["type"]
        description = step["description"]

        print(f"步骤 {i}: {description}")

        if step_type == "instruction":
            instruction = step["instruction"]
            print(f"  指令: {instruction}")
            # Claude Code 会执行这个指令

        elif step_type == "verification":
            print(f"  验证: {description}")
            # Claude Code 会验证结果

        elif step_type == "tool_call":
            tool_name = step["tool_name"]
            params = step.get("tool_params", {})
            print(f"  工具: {tool_name}({params})")
            # Claude Code 会调用相应的工具

        print()
```

### 输出示例

```
技能: Code Reviewer
步骤数: 4

Claude Code 执行开始:

步骤 1: Check syntax
  指令: Verify code has no syntax errors

步骤 2: Check style
  指令: - Follow PEP 8 guidelines
  - Check naming conventions
  - Verify formatting

步骤 3: Check logic
  指令: - Look for obvious bugs
  - Check for edge cases
  - Verify error handling

步骤 4: Generate report
  指令: Summarize findings
```

---

## 示例 5: 错误处理和恢复

### SKILL.md

```markdown
---
name: Robust Executor
description: Execute with error recovery
namespace: example
version: 1.0.0
---

# Robust Executor

Execute tasks with comprehensive error handling.

## Steps

1. Try primary approach
   instruction: Execute main logic

2. If fails, try fallback
   condition: primary_success
   condition_value: false
   instruction: Use fallback method

3. Verify result
   Check that output is valid

4. Log result
   Record success or failure
```

### 测试错误处理

```python
result = manager.execute_skill(
    "example/robust-executor",
    context={
        "primary_success": False,
        "fallback_method": "alternative",
    }
)

print(f"成功: {result['success']}")
print(f"输出: {result['output']}")
```

---

## 示例 6: 循环处理

### SKILL.md

```markdown
---
name: Batch Processor
description: Process items in batch
namespace: batch
version: 1.0.0
---

# Batch Processor

Process multiple items with consistent logic.

## Steps

1. Load items
   instruction: Load all items from input

2. Process each item
   instruction: For each item in items, process {item}
   max_iterations: 100

3. Validate results
   Check all items were processed

4. Generate summary
   Report total processed, success count, failure count
```

### 使用代码

```python
items = [
    {"id": 1, "name": "Item 1"},
    {"id": 2, "name": "Item 2"},
    {"id": 3, "name": "Item 3"},
]

result = manager.execute_skill(
    "batch/processor",
    context={"items": items}
)

print(f"处理了 {result['executed_steps']} 步")
print(f"输出:\n{result['output']}")
```

---

## 运行示例

### 完整工作流

```bash
# 1. 安装 VibeSOP
pip install vibesop

# 2. 安装技能包
vibe install superpowers
vibe install gstack

# 3. 列出技能
vibe skills list

# 4. 获取技能信息
vibe skills info superpowers/tdd

# 5. 运行 Python 代码
python your_script.py
```

### 输出示例

```python
# 执行技能
result = manager.execute_skill("superpowers/tdd", context={
    "feature": "User authentication",
    "test_framework": "pytest",
})

# 输出:
# ✓ Initialized: Set up test environment
# ✓ Red: Write failing test
# ✓ Green: Make test pass
# ✓ Refactor: Clean up code
# 
# 执行步骤: 4
# 输出: Red: Write failing test for User authentication...
```

---

## 技巧和最佳实践

### 1. 技能设计原则

- **单一职责** - 每个技能做一件事
- **清晰命名** - 使用描述性的名称
- **完整文档** - 包含使用说明
- **错误处理** - 考虑失败情况

### 2. 工作流编写技巧

- **渐进式** - 从简单到复杂
- **模块化** - 可重用的子步骤
- **可测试** - 每步可独立验证
- **可维护** - 易于理解和修改

### 3. 性能优化

- **缓存技能** - 避免重复加载
- **延迟执行** - 按需加载
- **并行处理** - 独立任务并行
- **资源限制** - 防止资源耗尽

### 4. 安全考虑

- **输入验证** - 验证所有输入
- **权限检查** - 限制访问权限
- **沙箱执行** - 隔离执行环境
- **日志记录** - 记录所有操作

---

## 故障排查指南

### 常见问题

**Q: 如何调试技能？**

A: 使用 `execute_skill()` 本地测试，然后逐步检查每个步骤。

**Q: 如何添加新技能？**

A: 创建 SKILL.md 文件，放在 `skills/` 目录下，或使用 `vibe install`。

**Q: 技能不执行？**

A: 检查：
1. 技能是否已安装
2. SKILL.md 格式是否正确
3. 工作流验证是否通过

**Q: 性能慢？**

A: 尝试：
1. 启用缓存
2. 减少技能数量
3. 优化工作流步骤

---

**更新**: 2026-04-18
**状态**: ✅ 完成
**版本**: 4.1.0
