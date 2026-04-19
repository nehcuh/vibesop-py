# VibeSOP 用户指南

> **面向所有用户：了解 VibeSOP 如何帮助你**
>
> **For All Users: Understand how VibeSOP helps you**

---

## 什么是 VibeSOP？ What is VibeSOP?

### 简单来说 In Simple Terms

VibeSOP 就像一个**智能助手**，它：

1. **听懂你想做什么**（自然语言，支持中英文）
2. **帮你找到最合适的工具**
3. **记住你的偏好**
4. **在任何 AI 工具中都能用**

VibeSOP is like a **smart assistant** that:

1. **Understands what you want to do** (natural language, English + Chinese)
2. **Finds the right tool for you**
3. **Remembers your preferences**
4. **Works with any AI tool**

---

## 为什么我需要 VibeSOP？ Why Do I Need VibeSOP?

### 问题 The Problem

AI 辅助开发工具太多、太复杂：

- 😕 **"我想做代码审查，但不知道该用什么命令"**
- 😕 **"这个工具用不习惯，想换个工具但又要重新学"**
- 😕 **"听说有个技能包很厉害，但不知道怎么用"**

### 解决方案 The Solution

VibeSOP 让你：

- ✅ **用自然语言表达意图** - 不需要记忆命令
- ✅ **自动找到最合适的技能** - 不需要猜测
- ✅ **跨平台通用** - 学一次，到处用
- ✅ **越来越聪明** - 记住你的选择

---

## 核心概念 Core Concepts

### 1. 技能 Skills

**技能**就像一个小的工作流程或专家知识包。

**Skills** are like small workflows or expert knowledge packages.

例如：
- `systematic-debugging` - 系统化调试工作流
- `gstack/review` - 代码审查技能
- `superpowers/tdd` - 测试驱动开发

### 2. 路由 Routing

**路由**就是根据你的意图，找到最合适的技能。

**Routing** is finding the best skill based on your intent.

```bash
你: "帮我调试这个错误"
     ↓
VibeSOP: 我理解了，你需要调试
     ↓
VibeSOP: 最合适的是 systematic-debugging 技能
     ↓
结果: systematic-debugging (95% 置信度)
```

### 3. 偏好学习 Preference Learning

VibeSOP 会记住什么对你有效，下次更准确。

VibeSOP remembers what works for you, so next time it's more accurate.

---

## 快速开始 Quick Start

### 安装（1 分钟） Install (1 minute)

```bash
# 克隆仓库
git clone https://github.com/nehcuh/vibesop-py.git
cd vibesop-py

# 安装（推荐使用 uv，更快）
uv sync

# 或者用 pip
pip install -e .
```

### 第一次使用（30 秒） First Use (30 seconds)

```bash
$ vibe route "帮我调试这个错误"

📥 Query: 帮我调试这个错误
✅ Matched: systematic-debugging
   Confidence: 95%
   Layer: scenario
   Source: builtin

💡 Alternatives:
   • gstack/investigate (82%)
   • superpowers/debug (75%)
```

**完成！** 你已经成功使用 VibeSOP 路由到最合适的技能。

**Done!** You've successfully routed to the best skill using VibeSOP.

---

## 使用场景 Use Cases

### 场景 1: 我遇到了错误 I Have an Error

```bash
$ vibe route "我的测试失败了"

✅ Matched: systematic-debugging (95%)
```

**解读**: VibeSOP 理解你遇到了测试失败，推荐使用系统化调试工作流。

### 场景 2: 我想审查代码 I Want to Review Code

```bash
$ vibe route "review my PR"

✅ Matched: gstack/review (93%)
```

**解读**: VibeSOP 理解你想审查 PR，推荐使用 gstack 的代码审查技能。

### 场景 3: 我想优化性能 I Want to Optimize Performance

```bash
$ vibe route "make it faster"

✅ Matched: superpowers/optimize (89%)
```

**解读**: VibeSOP 理解你想优化性能，推荐使用 superpowers 的优化技能。

### 场景 4: 我想重构代码 I Want to Refactor Code

```bash
$ vibe route "重构这个函数"

✅ Matched: superpowers/refactor (91%)
```

**解读**: VibeSOP 理解你想重构代码，推荐使用 superpowers 的重构技能。

---

## 常用命令 Common Commands

### 查看所有技能

```bash
$ vibe skills available

📚 Available Skills (45 total)

builtin (17 skills)
  • systematic-debugging - 找出根本原因再修复
  • verification-before-completion - 完成前必须验证
  ...

gstack (19 skills)
  • gstack/review - PR 前审查
  • gstack/qa - 系统化 QA 测试
  ...

superpowers (7 skills)
  • tdd - 测试驱动开发
  • brainstorm - 结构化头脑风暴
  ...
```

### 查看技能详情

```bash
$ vibe skills info systematic-debugging

╭──────────────────────────────────────────────╮
│ Systematic Debugging                          │
├──────────────────────────────────────────────┤
│ ID: systematic-debugging                      │
│ 描述: 找出根本原因再修复                      │
│                                                │
│ 何时使用:                                     │
│ - 出现错误消息                                │
│ - 测试失败                                    │
│ - "出问题了"                                  │
╰──────────────────────────────────────────────╯
```

### 安装新技能包

```bash
$ vibe install gstack

📦 Found skill pack: gstack
   Skills discovered: 19
   Install target: ~/.config/skills/gstack/
   Continue? [Y/n]

✅ gstack installed successfully
```

---

## 提高准确率 Improve Accuracy

### 反馈正确的路由

```bash
$ vibe feedback record "调试错误" "systematic-debugging" --correct

✓ Recorded correct routing: 调试错误 → systematic-debugging
```

### 反馈错误的路由

```bash
$ vibe feedback record "测试功能" "superpowers/tdd" \\
    --wrong "gstack/qa" --confidence 0.7

⚠ Recorded incorrect routing: 测试功能 → superpowers/tdd (should be: gstack/qa)
```

### 查看反馈报告

```bash
$ vibe feedback report

Feedback Report
Total records: 50
Correct: 47 (94.0%)
Incorrect: 3 (6.0%)
Accuracy: 94.0%

Accuracy by Skill:
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━┓
┃ Skill               ┃ Correct ┃ Wrong ┃ Accuracy ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━┩
│ superpowers/review  │ 8      │ 0     │ 100.0%  │
│ gstack/qa           │ 6      │ 1     │ 85.7%   │
└─────────────────────┴────────┴───────┴─────────┘
```

---

## 最佳实践 Best Practices

### 1. 使用具体的查询

```bash
# ✅ 好的查询（具体）
vibe route "我的数据库连接在部署后失败了"

# ❌ 不好的查询（太简单）
vibe route "数据库问题"
```

### 2. 提供上下文

```bash
# ✅ 好的查询（有上下文）
vibe route "我刚写了新功能，需要帮忙 review"

# ❌ 不好的查询（无上下文）
vibe route "review"
```

### 3. 中英文都可以

```bash
vibe route "帮我 review 代码"  # 中文
vibe route "review my code"    # 英文
vibe route "检查代码"          # 中文
```

---

## 常见问题 FAQ

### Q: VibeSOP 是免费的吗？

A: 是的！VibeSOP 完全开源免费。

### Q: 我需要提供 API key 吗？

A: 不需要。VibeSOP 可以在没有 API key 的情况下工作（使用关键词和 TF-IDF 匹配）。但如果你提供 API key，路由准确率会更高（使用 AI Triage）。

### Q: VibeSOP 会执行技能吗？

A: 不会。VibeSOP 只负责**找到**最合适的技能，不负责执行。执行由你的 AI 工具完成。

### Q: 准确率有多高？

A: 94% 总体准确率。AI Triage 层达到 95% 准确率。

### Q: 支持哪些语言？

A: 支持中文和英文。我们正在计划支持更多语言。

### Q: 我可以在哪些工具中使用？

A: 所有支持 SKILL.md 规范的工具：Claude Code, Cursor, Continue.dev, Aider 等。

### Q: 如何提高路由准确率？

A: 使用 `vibe feedback record` 记录反馈，VibeSOP 会学习你的偏好。

---

## 获取帮助 Get Help

### 文档 Documentation

- [完整文档](../README.md) - Complete documentation
- [哲学](../PHILOSOPHY.md) - Philosophy
- [架构](architecture/) - Architecture

### 社区 Community

- [GitHub Issues](https://github.com/nehcuh/vibesop-py/issues) - 报告问题 Report issues
- [GitHub Discussions](https://github.com/nehcuh/vibesop-py/discussions) - 讨论和问答 Discussions and Q&A

### 命令行帮助 Command Line Help

```bash
vibe --help           # 总体帮助
vibe route --help     # route 命令帮助
vibe skills --help    # skills 命令帮助
```

---

## 下一步 Next Steps

1. ✅ 安装 VibeSOP
2. ✅ 尝试第一次路由
3. ✅ 探索可用的技能 (`vibe skills available`)
4. ✅ 提供反馈，让 VibeSOP 更准确
5. ✅ 集成到你的 AI 工具中

---

**祝你使用愉快！Happy using!**

**版本 Version**: 4.2.0
**更新时间 Last Updated**: 2026-04-18
