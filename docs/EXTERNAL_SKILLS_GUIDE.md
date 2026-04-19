# 外部技能使用指南

> **版本**: 4.1.0
> **目标用户**: 技能开发者、AI Agent 集成者
> **更新时间**: 2026-04-18

---

## 概述

VibeSOP 4.1.0 支持从外部技能包（superpowers、gstack、omx 等）动态加载和执行技能，而不仅仅是检测它们的存在。

### 核心能力

1. **技能发现** - 自动发现所有可用技能
2. **工作流解析** - 从 SKILL.md 解析工作流定义
3. **技能执行** - 本地测试和验证
4. **AI Agent 集成** - 为 Claude Code、Cursor 等提供工作流定义

---

## 快速开始

### 1. 列出可用技能

```python
from vibesop.core.skills.manager import SkillManager

manager = SkillManager()

# 列出所有技能
skills = manager.list_skills()
for skill in skills:
    print(f"- {skill['id']}: {skill['name']}")
```

### 2. 获取技能工作流定义

```python
# 获取工作流定义（用于 AI Agent）
definition = manager.get_skill_definition("systematic-debugging")

if definition:
    workflow = definition["workflow"]
    print(f"工作流: {workflow['name']}")
    print(f"步骤数: {len(workflow['steps'])}")

    for step in workflow["steps"]:
        print(f"  - {step['type']}: {step['description']}")
```

### 3. 执行技能（本地测试）

```python
# 本地执行技能（用于测试）
result = manager.execute_skill(
    "systematic-debugging",
    context={"bug": "NullPointer exception"}
)

if result["success"]:
    print(f"输出:\n{result['output']}")
    print(f"执行步骤: {result['executed_steps']}")
else:
    print(f"错误: {result['error']}")
```

### 4. 验证技能

```python
# 验证技能完整性
validation = manager.validate_skill("systematic-debugging")

if validation["is_valid"]:
    print("✅ 技能有效")
else:
    print("❌ 技能无效:")
    for error in validation["errors"]:
        print(f"  - {error}")
```

---

## 工作流定义格式

### 基本 SKILL.md 结构

```markdown
---
name: My Skill
description: A brief description
namespace: my-namespace
version: 1.0.0
---

# My Skill

Detailed description of what this skill does.

## Steps

1. First step
   Detailed instruction for the first step

2. Second step
   - Sub-step A
   - Sub-step B

3. Verification
   Check that everything is correct
```

### 工作流步骤类型

#### 1. Instruction 步骤（默认）

```markdown
1. Execute the task
   Follow these instructions to complete the task
```

#### 2. Verification 步骤

```markdown
1. Verify the result
   Check that the output is correct
```

#### 3. Tool Call 步骤

```markdown
1. Read the file
   Use read tool to access the file
```

#### 4. Conditional 步骤

```markdown
1. If condition is met
   Proceed with the action
```

#### 5. Loop 步骤

```markdown
1. For each item in items
   Process the item
```

---

## 高级特性

### 变量替换

工作流支持变量替换，使用 `{variable}` 语法：

```markdown
---
name: Template Skill
---

## Steps

1. Greet user
   Hello {name}, you are {age} years old
```

执行时传入变量：

```python
result = manager.execute_skill(
    "template-skill",
    context={"name": "Alice", "age": "30"}
)
```

### 内置工具

VibeSOP 提供内置工具用于工作流：

```python
from vibesop.core.skills.executor import ExternalSkillExecutor

executor = ExternalSkillExecutor(enable_tools=True)

# 注册自定义工具
def my_tool(message: str) -> str:
    return f"Processed: {message}"

executor.register_tool("my_tool", my_tool)
```

**内置工具**:
- `echo` - 回显输入
- `set` - 设置变量
- `get` - 获取变量
- `log` - 记录日志

### 条件执行

工作流支持条件分支：

```markdown
## Steps

1. Check condition
   condition: status
   condition_value: ready
   instruction: System is ready, proceed
```

### 循环执行

工作流支持循环迭代：

```markdown
## Steps

1. Process items
   instruction: For each item in items, process {item}
   max_iterations: 10
```

---

## AI Agent 集成

### Claude Code 集成

```python
# 在 Claude Code 中使用
from vibesop.core.skills.manager import SkillManager

manager = SkillManager()

# 1. 获取技能定义
definition = manager.get_skill_definition(skill_id)

# 2. 将工作流传递给 Claude Code
if definition:
    workflow = definition["workflow"]

    # 3. Claude Code 按照工作流执行
    for step in workflow["steps"]:
        if step["type"] == "instruction":
            print(f"指令: {step['instruction']}")
        elif step["type"] == "tool_call":
            # 调用 Claude Code 的工具
            tool_name = step["tool_name"]
            params = step.get("tool_params", {})
            # 调用工具...
```

### Cursor 集成

```python
# 在 Cursor 中使用
manager = SkillManager()

# 获取技能定义并执行
definition = manager.get_skill_definition("skill-id")

# Cursor 使用工作流定义
# （具体实现取决于 Cursor 的 API）
```

---

## 外部技能包集成

### superpowers 集成

```bash
# 安装 superpowers
vibe install https://github.com/obra/superpowers

# 列出 superpowers 技能
vibe skills list --namespace superpowers

# 获取技能定义
vibe skills info superpowers/tdd
```

### gstack 集成

```bash
# 安装 gstack
vibe install https://github.com/anthropics/gstack

# 列出 gstack 技能
vibe skills list --namespace gstack
```

### 自定义技能包

创建 `skills/` 目录：

```
my-skills/
├── skills/
│   ├── my-skill/
│   │   └── SKILL.md
│   └── another-skill/
│       └── SKILL.md
└── SKILL.md (可选：包级描述)
```

---

## API 参考

### SkillManager

```python
class SkillManager:
    def __init__(
        self,
        project_root: str | Path = ".",
        enable_execution: bool = True,
    ) -> None:
        """初始化技能管理器。

        Args:
            project_root: 项目根目录
            enable_execution: 是否启用本地执行
        """

    def list_skills(
        self,
        namespace: str | None = None,
        include_registry: bool = True,
    ) -> list[dict[str, Any]]:
        """列出所有可用技能。"""

    def get_skill_definition(
        self,
        skill_id: str,
    ) -> dict[str, Any] | None:
        """获取技能工作流定义。"""

    def execute_skill(
        self,
        skill_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行技能（本地）。"""

    def validate_skill(
        self,
        skill_id: str,
    ) -> dict[str, Any]:
        """验证技能。"""
```

### ExternalSkillExecutor

```python
class ExternalSkillExecutor:
    def __init__(
        self,
        project_root: str | Path = ".",
        enable_execution: bool = True,
        execution_timeout: float = 30.0,
    ) -> None:
        """初始化执行器。"""

    def get_skill_definition(
        self,
        skill_id: str,
    ) -> SkillResult:
        """获取技能定义。"""

    def execute_skill(
        self,
        skill_id: str,
        context: dict[str, Any] | None = None,
    ) -> SkillResult:
        """执行技能。"""

    def validate_skill(
        self,
        skill_id: str,
    ) -> tuple[bool, list[str]]:
        """验证技能。"""

    def list_executable_skills(self) -> list[str]:
        """列出可执行技能。"""
```

---

## 最佳实践

### 1. 技能设计

- **清晰的步骤描述** - 每个步骤应该有明确的描述
- **适当的粒度** - 步骤不要太细或太粗
- **错误处理** - 考虑失败情况
- **文档完整** - 包含使用示例

### 2. 工作流编写

- **使用编号步骤** - 更易于理解
- **子步骤用 bullet** - 用于相关操作
- **条件明确** - 清晰的条件判断
- **循环限制** - 防止无限循环

### 3. 测试验证

- **本地测试** - 使用 execute_skill 测试
- **验证完整性** - 使用 validate_skill 检查
- **逐步测试** - 每个步骤单独验证
- **边界测试** - 测试边界条件

### 4. 安全考虑

- **审计技能** - 安装前进行安全审计
- **沙箱执行** - 使用安全的执行环境
- **权限控制** - 限制工具访问
- **输入验证** - 验证用户输入

---

## 故障排查

### 问题：技能找不到

**症状**: `SkillNotFoundError`

**解决**:
1. 检查技能是否已安装：`vibe skills list`
2. 检查技能ID是否正确
3. 检查技能包是否已加载

### 问题：工作流解析失败

**症状**: `ValueError: Invalid workflow`

**解决**:
1. 检查 SKILL.md 格式
2. 验证 frontmatter 格式
3. 确保至少有一个步骤

### 问题：执行超时

**症状**: `TimeoutError`

**解决**:
1. 增加 execution_timeout 参数
2. 优化工作流步骤
3. 检查是否有死循环

### 问题：工具调用失败

**症状**: 工具调用返回错误

**解决**:
1. 检查工具是否已注册
2. 验证工具参数
3. 使用 enable_tools=True

---

## 示例

### 示例 1: 创建自定义技能

```markdown
---
name: Code Generator
description: Generate code from specification
namespace: custom
version: 1.0.0
---

# Code Generator

Generate code based on specification.

## Steps

1. Parse specification
   Read and understand the spec file

2. Generate code
   Create implementation following best practices

3. Verify code
   - Check syntax
   - Run tests
   - Verify functionality
```

### 示例 2: 使用变量

```python
result = manager.execute_skill(
    "code-generator",
    context={
        "spec_file": "spec.md",
        "language": "python",
        "framework": "fastapi",
    }
)
```

### 示例 3: AI Agent 集成

```python
# AI Agent 使用示例
from vibesop.core.skills.manager import SkillManager

manager = SkillManager()

# 1. 获取技能定义
definition = manager.get_skill_definition(skill_id)

if definition:
    # 2. 提取工作流
    workflow = definition["workflow"]

    # 3. AI Agent 执行工作流
    for step in workflow["steps"]:
        step_type = step["type"]
        description = step["description"]

        if step_type == "instruction":
            instruction = step["instruction"]
            # AI Agent 执行指令
            print(f"执行: {instruction}")

        elif step_type == "tool_call":
            tool_name = step["tool_name"]
            params = step.get("tool_params", {})
            # AI Agent 调用工具
            print(f"调用工具: {tool_name}({params})")

        elif step_type == "verification":
            # AI Agent 验证结果
            print(f"验证: {description}")
```

---

## 相关文档

- [架构概述](architecture/README.md)
- [路由系统](architecture/routing-system.md)
- [技能规范](docs/SKILL_SPEC.md)
- [安全指南](security/README.md)

---

**更新**: 2026-04-18
**版本**: 4.1.0
**状态**: ✅ Step 1.5 完成
