# vibesop-py — Phase 0：全局扇出诊断

## 前置条件
- [ ] 项目已在本地可用
- [ ] 检测到 3 个执行步骤，涉及 2 个技能域

## 你的任务
全面理解当前任务的改造范围，识别所有改造点。

### 原始需求
> 对当前项目从哲学理念、架构设计、代码实现进行深入评审

### Step 1：阅读核心文件来理解项目架构
以下是与本任务相关的技能/模块：
- **omx/analyze** — Review the philosophical foundations and design principles of the project
- **omx/analyze** — Review the architectural design of the project
- **omx/code-review** — Review the code implementation for quality and adherence to standards

#### 具体文件路径
本任务涉及外部 skill（如 omx/analyze），没有映射到具体文件。请自行探索：
- **src/vibesop/** — 核心代码
- **docs/** — 文档
- **tests/** — 测试
- **README.md** — 项目概述
- **pyproject.toml** — 项目配置

### Step 2：识别核心问题
请找出以下关键问题的答案：
1. 当前各模块的职责边界是什么？
2. 需要修改哪些模块？
3. 需要新建哪些模块？
4. 模块间的依赖关系是什么？

### Step 3：输出分析报告
按照以下格式输出：

```markdown
# 扇出诊断报告

## P0（必须修复 — 核心能力缺失）
1. [问题描述] — [涉及文件] — [改造思路]

## P1（重要改进 — 体验提升）
1. ...

## P2（锦上添花 — 可后续优化）
1. ...

## 文件依赖图
（用文字描述模块间的依赖关系）
```

---

## 完成条件
执行完本 Phase 后，创建标记文件：
```bash
echo "phase-0 completed at $(date)" > .vibe/prompts/.phase-0-done
```


### 技能路由提示

在执行本阶段的每个步骤时，如果遇到需要选择工具的决策点，
请运行 `vibe route "<当前子任务描述>"` 来动态选择最合适的技能。
