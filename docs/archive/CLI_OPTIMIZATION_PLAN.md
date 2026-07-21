# VibeSOP CLI 优化计划

> **版本**: v4.1.0  
> **目标**: 精简 CLI 命令，消除设计原则冲突  
> **预计工期**: 2-3 天  

---

## 目标

- 命令数量从 **42 个** 精简至 **20-25 个**
- 消除 `execute` 等违反设计原则的命令
- 统一命令结构和命名规范
- 提升用户体验和可维护性

---

## Phase 1: 移除违反设计原则的命令 (P0)

### 任务 1.1: 移除 `execute` 命令

**文件变更**:
```
DELETE: src/vibesop/cli/commands/execute.py
MODIFY: src/vibesop/cli/subcommands/__init__.py
MODIFY: src/vibesop/cli/executor.py (标记为 deprecated)
MODIFY: src/vibesop/cli/main.py (移除 execute 导入)
```

**具体步骤**:
1. 删除 `execute.py` 文件
2. 从 `subcommands/__init__.py` 移除:
   ```python
   # 移除
   from vibesop.cli.commands import execute as execute_mod
   app.command()(execute_mod.execute)
   app.command("execute-list")(execute_mod.list_available)
   ```
3. 更新 README.md，移除 `vibe execute` 示例
4. 保留 `executor.py` 但添加 deprecation warning（内部使用）

**影响**: 
- 移除 191 行代码
- 删除 `vibe route --run` 中的执行功能
- 用户改用 AI Agent 执行技能

---

### 任务 1.2: 统一 `skills` 命令结构

**文件变更**:
```
MODIFY: src/vibesop/cli/main.py (移除 skills 主命令)
MODIFY: src/vibesop/cli/subcommands/__init__.py
MODIFY: src/vibesop/cli/commands/skills_cmd.py (增强)
```

**具体步骤**:
1. 从 `main.py` 移除 `skills_list` 和 `skill_info` 主命令
2. 在 `skills_cmd.py` 中添加:
   - `list` (已有)
   - `info` (从主命令迁移)
   - `install` (从主命令迁移)
   - `remove`
   - `status`
3. 更新调用方式:
   ```bash
   # 旧
   vibe skills
   vibe skill-info gstack/review
   vibe install <url>
   
   # 新
   vibe skills list
   vibe skills info gstack/review
   vibe skills install <url>
   ```

---

## Phase 2: 内部化学习/记忆命令 (P1)

### 任务 2.1: 移除 `memory` 主命令

**文件变更**:
```
MODIFY: src/vibesop/cli/subcommands/__init__.py (移除注册)
DELETE: src/vibesop/cli/commands/memory_cmd.py (可选)
```

**具体步骤**:
1. 从 `subcommands/__init__.py` 移除:
   ```python
   # 移除
   app.command("memory")(memory_mod.memory)
   ```
2. 保留 `core/memory/` 内部实现（路由引擎需要）
3. (可选) 删除 `memory_cmd.py` 或将功能移至 `preferences` 子命令

**说明**: 会话记忆是路由引擎内部机制，不应暴露给用户

---

### 任务 2.2: 合并 `instinct` 到 `preferences`

**文件变更**:
```
DELETE: src/vibesop/cli/commands/instinct_new.py
MODIFY: src/vibesop/cli/subcommands/__init__.py
MODIFY: src/vibesop/cli/main.py (添加 preferences 子命令)
```

**具体步骤**:
1. 删除 `instinct_new.py`
2. 在 `preferences` 子命令中添加:
   ```python
   @preferences_app.command("instincts")
   def list_instincts():
       # 从 instinct_new.py 迁移代码
   ```
3. 或使用更简单的方式：自动学习，无需 CLI 管理

**建议**: 完全移除 instinct CLI，改为自动学习机制

---

## Phase 3: 合并检测/分析命令 (P1)

### 任务 3.1: 合并 `scan`, `detect`, `analyze`

**文件变更**:
```
DELETE: src/vibesop/cli/commands/scan.py
DELETE: src/vibesop/cli/commands/detect.py
DELETE: src/vibesop/cli/commands/auto_analyze.py
MODIFY: src/vibesop/cli/commands/analyze.py (增强)
MODIFY: src/vibesop/cli/subcommands/__init__.py
```

**具体步骤**:
1. 分析三个命令的功能重叠:
   - `scan`: 项目扫描
   - `detect`: 配置检测
   - `analyze`: 会话分析
   - `auto-analyze`: 自动分析

2. 合并为统一的 `analyze` 命令:
   ```python
   @app.command()
   def analyze(
       target: str = typer.Argument(..., help="Target: session, project, config"),
       # ... 其他参数
   ):
       if target == "session":
           _analyze_session()
       elif target == "project":
           _analyze_project()  # 原 scan
       elif target == "config":
           _analyze_config()   # 原 detect
   ```

3. 添加 deprecation 重定向:
   ```bash
   # 旧命令提示
   vibe scan → "Use: vibe analyze project"
   vibe detect → "Use: vibe analyze config"
   vibe auto-analyze → "Use: vibe analyze session --auto"
   ```

---

### 任务 3.2: 整合 `inspect` 到 `doctor`

**文件变更**:
```
DELETE: src/vibesop/cli/commands/inspect.py
MODIFY: src/vibesop/cli/main.py (doctor 命令)
```

**具体步骤**:
1. 检查 `inspect.py` 功能:
   - 如果是项目检查，合并到 `doctor`
   - 如果是技能检查，合并到 `skills info`

2. 在 `doctor` 中添加项目检查功能:
   ```python
   @app.command()
   def doctor(
       check_project: bool = typer.Option(False, "--project", "-p"),
   ):
       if check_project:
           _check_project_structure()
   ```

---

## Phase 4: 清理和优化 (P2)

### 任务 4.1: 标记 experimental 命令

**文件变更**:
```
MODIFY: src/vibesop/cli/commands/skill_craft.py
MODIFY: src/vibesop/cli/commands/import_rules.py
```

**具体步骤**:
1. 在 `skill_craft` 添加警告:
   ```python
   console.print("[yellow]⚠️  Experimental feature[/yellow]")
   ```
2. 检查 `import_rules` 是否 gstack 特有，考虑移除或移至 gstack 包

---

### 任务 4.2: 优化命令文档

**文件变更**:
```
MODIFY: README.md
MODIFY: docs/CLI_REFERENCE.md (创建)
```

**具体步骤**:
1. 更新 README 命令示例
2. 创建简化的 CLI 文档:
   ```markdown
   ## 核心命令
   - `vibe route` - 路由查询
   - `vibe skills` - 技能管理
   - `vibe doctor` - 环境检查
   
   ## 配置命令
   - `vibe init` - 初始化项目
   - `vibe build` - 构建配置
   - `vibe install` - 安装技能包
   
   ## 分析命令
   - `vibe analyze` - 分析会话/项目
   
   ## 其他
   - `vibe quickstart` - 快速开始
   - `vibe version` - 版本信息
   ```

---

## Phase 5: 测试和验证 (P0)

### 任务 5.1: 更新测试

**文件变更**:
```
DELETE: tests/cli/test_execute.py
DELETE: tests/cli/test_memory.py
DELETE: tests/cli/test_instinct.py
DELETE: tests/cli/test_scan.py
DELETE: tests/cli/test_detect.py
MODIFY: tests/cli/test_skills.py
```

**具体步骤**:
1. 删除被移除命令的测试
2. 更新 `test_skills.py` 测试新的子命令结构
3. 添加命令存在性测试:
   ```python
   def test_core_commands_exist():
       assert "route" in app.registered_commands
       assert "skills" in app.registered_commands
       assert "execute" not in app.registered_commands  # 已移除
   ```

---

### 任务 5.2: 验证帮助信息

**检查清单**:
```bash
# 每个命令都应显示清晰的帮助
vibe --help
vibe route --help
vibe skills --help
vibe skills list --help
vibe analyze --help
```

---

## 时间表

| Phase | 任务 | 预计时间 | 依赖 |
|-------|------|----------|------|
| **Phase 1** | 移除 execute | 2 小时 | - |
| | 统一 skills | 3 小时 | - |
| **Phase 2** | 移除 memory | 1 小时 | - |
| | 合并 instinct | 2 小时 | - |
| **Phase 3** | 合并 analyze | 4 小时 | - |
| | 整合 inspect | 2 小时 | - |
| **Phase 4** | 标记 experimental | 1 小时 | Phase 1-3 |
| | 更新文档 | 3 小时 | Phase 1-3 |
| **Phase 5** | 更新测试 | 4 小时 | Phase 1-4 |
| | 验证 | 2 小时 | Phase 5 |
| **总计** | | **24 小时** (3 天) | |

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 用户依赖 `execute` | 高 | 提前发 deprecation warning，提供迁移指南 |
| 测试覆盖率下降 | 中 | 重写关键测试，确保核心功能覆盖 |
| 文档不同步 | 中 | 一次性更新所有文档 |
| 删除过多功能 | 低 | 保留核心，仅移除重复/越界功能 |

---

## 验收标准

- [ ] `vibe execute` 命令不存在
- [ ] `vibe skills` 使用子命令结构
- [ ] `vibe memory` 不存在
- [ ] `vibe instinct` 不存在（或移至 preferences）
- [ ] `vibe scan/detect/auto-analyze` 合并为 `analyze`
- [ ] 命令总数 ≤ 25
- [ ] 所有测试通过
- [ ] README 文档已更新

---

## 附录: 命令对照表

### 保留的命令 (15)

```
vibe route              # 核心路由
vibe doctor             # 环境检查
vibe version            # 版本
vibe record             # 记录偏好
vibe preferences        # 偏好统计
vibe skills             # 技能管理 (typer app)
  ├── list
  ├── info
  ├── install
  ├── remove
  └── status
vibe install            # 安装技能包（快捷）
vibe init               # 项目初始化
vibe build              # 构建配置
vibe config             # 配置管理
vibe analyze            # 分析（合并 scan/detect）
vibe quickstart         # 快速开始
vibe onboard            # 项目引导
cd                      # 上下文管理
```

### 移除的命令 (14)

```
vibe execute            # 违反原则 ❌
vibe execute-list       # 违反原则 ❌
vibe memory             # 内部化 ❌
vibe instinct           # 内部化 ❌
vibe scan               # 合并到 analyze ❌
vibe detect             # 合并到 analyze ❌
vibe auto-analyze       # 合并到 analyze ❌
vibe inspect            # 合并到 doctor ❌
vibe route-stats        # 合并到 preferences ❌
vibe top-skills         # 合并到 preferences ❌
vibe skill-info         # 合并到 skills info ❌
vibe skill-craft        # 标记 experimental/移除 ❌
vibe import-rules       # 标记 experimental/移除 ❌
vibe targets            # 检查必要性 ❌
vibe tools              # 检查必要性 ❌
vibe switch             # 检查必要性 ❌
```

### Legacy 命令 (5, 默认隐藏)

```
vibe deploy             # deprecated
vibe toolchain          # deprecated
vibe worktree           # deprecated
vibe checkpoint         # deprecated
vibe hooks              # deprecated
```
