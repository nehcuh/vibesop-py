# VibeSOP 开发者快速指南

> **面向开发者：5 分钟上手 VibeSOP**
>
> **For Developers: Get started with VibeSOP in 5 minutes**

---

## 我是开发者，VibeSOP 能为我做什么？

### 问题 Problem

你正在使用 AI 辅助开发工具（Claude Code, Cursor, Continue.dev 等），但：

- ❌ 记不住那么多技能命令
- ❌ 不知道哪个技能最适合当前场景
- ❌ 想要在不同工具间切换而不失去技能
- ❌ 想要创建自己的技能

### 解决方案 Solution

VibeSOP 为你提供：

1. **智能路由** - 自然语言输入，自动找到最合适的技能
2. **跨平台** - 一套技能，在所有 AI 工具中使用
3. **偏好学习** - 越用越准确
4. **开放生态** - 创建自己的技能

---

## 快速开始 Quick Start

### 1. 安装 Install

```bash
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py
uv sync  # or pip install -e .
```

### 2. 第一次使用 First Use

```bash
$ vibe route "帮我调试这个错误"

✅ Matched: systematic-debugging
   Confidence: 95%
```

**就这么简单！** 你不需要记住任何命令。

---

## 常用场景 Common Scenarios

### 场景 1: 调试错误 Debugging Errors

```bash
$ vibe route "database connection failed"

✅ Matched: systematic-debugging (95%)

# 现在你知道该用 systematic-debugging 工作流
# 在 Claude Code 中，这个技能会自动加载
```

### 场景 2: 代码审查 Code Review

```bash
$ vibe route "review my PR"

✅ Matched: gstack/review (93%)
```

### 场景 3: 性能优化 Performance Optimization

```bash
$ vibe route "make it faster"

✅ Matched: superpowers/optimize (89%)
```

### 场景 4: 重构代码 Refactoring

```bash
$ vibe route "重构这个函数"

✅ Matched: superpowers/refactor (91%)
```

---

## 创建自己的技能 Create Your Own Skills

### Step 1: 创建技能目录

```bash
mkdir -p ~/.claude/skills/my-review
cd ~/.claude/skills/my-review
```

### Step 2: 创建 SKILL.md

```markdown
# My Code Review Skill

> 我的自定义代码审查技能

## Metadata

```yaml
name: my-review
version: 1.0.0
namespace: custom
type: prompt
```

## Description

我的代码审查工作流，专注于：
- 安全漏洞
- 性能问题
- 代码风格

## Triggers

- "review my code"
- "代码审查"
- "check code"

## Workflow

1. 检查安全问题
2. 检查性能问题
3. 检查代码风格
4. 提供改进建议
```

### Step 3: 使用你的技能

```bash
$ vibe route "review my code"

✅ Matched: custom/my-review (95%)
```

---

## 集成到 AI 工具 Integrate with AI Tools

### Claude Code

```bash
vibe build claude-code --output ~/.claude
```

### Kimi Code CLI

```bash
vibe build kimi-cli --output ~/.kimi
```

### Cursor

```bash
vibe build cursor --output ~/.cursor
```

### Continue.dev

```bash
vibe build opencode --output ~/.continue
```

---

## 高级用法 Advanced Usage

### 偏好学习 Preference Learning

```bash
# 记录正确的路由
vibe feedback record "debug this" "systematic-debugging" --correct

# 记录错误的路由
vibe feedback record "test this" "superpowers/tdd" \\
    --wrong "gstack/qa" --confidence 0.7

# 查看反馈报告
vibe feedback report
```

### 会话智能路由 Session Intelligent Routing

```bash
# 启用跟踪（Claude Code）
vibe session enable-tracking

# 检查是否需要重新路由
vibe session check-reroute "design architecture" \\
    --skill "systematic-debugging"

# 查看会话摘要
vibe session summary
```

---

## 开发技巧 Tips for Developers

### 1. 自然语言输入

```bash
# ✅ 好的查询
vibe route "帮我找出这个错误的原因"
vibe route "如何优化这段代码的性能"

# ❌ 不好的查询（太简单）
vibe route "错误"
vibe route "优化"
```

### 2. 提供上下文

```bash
# ✅ 好的查询（有上下文）
vibe route "我刚刚部署后数据库连接失败，帮我调试"

# ❌ 不好的查询（无上下文）
vibe route "数据库失败"
```

### 3. 中英文都可以

```bash
vibe route "帮我 review 代码"  # 中文
vibe route "review my code"    # 英文
```

---

## CLI 常用命令 CLI Cheat Sheet

```bash
# 路由查询
vibe route "<query>"

# 列出所有技能
vibe skills available

# 查看技能详情
vibe skills info <skill-id>

# 安装技能包
vibe install gstack

# 检查环境
vibe doctor

# 反馈
vibe feedback record "<query>" "<skill>" --correct
vibe feedback report

# 会话路由
vibe session enable-tracking
vibe session check-reroute "<query>" --skill "<current-skill>"
vibe session summary
```

---

## 常见问题 FAQ

### Q: VibeSOP 会执行技能吗？

A: 不会。VibeSOP 只负责**路由**（找到正确的技能），不负责执行。执行由你的 AI 工具完成。

### Q: 准确率有多高？

A: 94% 总体准确率。AI Triage 层达到 95% 准确率。

### Q: 支持哪些 AI 工具？

A: 所有支持 SKILL.md 规范的工具：Claude Code, Cursor, Continue.dev, Aider 等。

### Q: 如何提高准确率？

A: 使用 `vibe feedback record` 记录反馈，VibeSOP 会学习你的偏好。

### Q: 可以离线使用吗？

A: 可以。没有 API key 时，VibeSOP 使用关键词和 TF-IDF 匹配（准确率稍低）。

---

## 下一步 Next Steps

- 📖 阅读完整文档: [README.md](../README.md)
- 🏗️ 了解架构: [docs/architecture/](architecture/)
- 🎯 查看技能规范: [docs/SKILL_SPEC.md](SKILL_SPEC.md)
- 💬 参与讨论: [GitHub Discussions](https://github.com/nehcuh/vibesop-py/discussions)

---

**版本 Version**: 4.2.0
**更新时间 Last Updated**: 2026-04-18
