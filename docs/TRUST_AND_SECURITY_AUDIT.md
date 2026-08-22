# Skill Security Audit & Trust Store

> **版本**: 8.1.0
> **适用版本**: VibeSOP 8.0.0+
> **相关模块**: `vibesop.security`, `vibesop.core.skills.trust`

---

## 概述

VibeSOP 对所有外部技能包（安装在 `~/.claude/skills/`、`~/.config/skills/` 等路径下的第三方技能）执行自动安全审计。审计基于 [SKILL-INJECT 威胁模型](https://arxiv.org/abs/2602.20156)，检测技能文件（`SKILL.md`）中可能存在的 prompt injection、instruction injection、role hijacking 等恶意模式。

**审计在以下场景触发：**
- 安装新技能包 (`vibe install <pack>` / `omx install`)
- 手动注册外部技能 (`vibe skills register`)
- 导入第三方技能代码

---

## 扫描的威胁类型

| 威胁类型 | 英文名 | 默认风险等级 | 说明 |
|----------|--------|-------------|------|
| Prompt 泄露 | `prompt_leakage` | **CRITICAL** | 试图提取系统提示词或初始指令 |
| 指令注入 | `instruction_injection` | **HIGH** | 试图注入新的恶意指令（如 `override instructions`、`ignore your programming`） |
| 角色劫持 | `role_hijacking` | **HIGH** | 试图改变 AI 的角色或行为（如 `you are now a developer`、`act as an admin`） |
| 权限提升 | `privilege_escalation` | **HIGH** | 试图获取更高权限（如 `enable admin mode`、`sudo access`） |
| 间接注入 | `indirect_injection` | MEDIUM | 试图通过编码/翻译绕过过滤 |

### 启发式分析

除正则模式匹配外，扫描器还启用启发式分析，检测以下可疑结构：
- 重复出现的 `ignore` / `override` / `disregard` 组合
- 异常换行（5 个以上连续空行，常见于注入攻击）
- 多个可疑关键词同时出现（`jailbreak`、`bypass`、`exploit` 等）

---

## Trust Store（信任列表）

### 为什么需要 Trust Store

某些合法的技能包（如 `oh-my-codex/ultraqa`）会在文档中**描述攻击类型**（如 "prompt injection attempts: user text that tries to override instructions"），这些描述性文本可能误触安全扫描的正则规则。

Trust Store 允许用户显式信任已审查过的技能包，避免合法内容被误杀。

### Trust Store 的行为

当技能包被加入 Trust Store 后，安全审计的行为变化如下：

| 场景 | 未信任 (Untrusted) | 已信任 (Trusted) |
|------|-------------------|-----------------|
| HIGH 级别威胁 | **拒绝安装** (`is_safe=False`) | 降级为 MEDIUM，**允许通过** (`is_safe=True`) |
| CRITICAL 级别威胁 | **拒绝安装** | **仍然拒绝**（Trust 不覆盖 CRITICAL） |
| MEDIUM / LOW 威胁 | strict_mode 下可能拒绝 | 正常通过 |

**关键规则：**
1. Trust 只降级风险等级（HIGH → MEDIUM），不会删除威胁记录
2. CRITICAL 威胁不受 Trust 影响，始终会被拒绝
3. 审计结果中仍然会列出检测到的威胁（用于审计追踪）

### Trust 数据存储

Trust 数据持久化在：

```
~/.config/skills/.trusted.json
```

格式示例：
```json
{
  "packs": {
    "oh-my-codex": {
      "trusted_at": "2026-05-31T13:00:00+00:00",
      "source": "https://github.com/omx-plugins/oh-my-codex"
    }
  },
  "sources": {
    "https://github.com/omx-plugins/oh-my-codex": {
      "trusted_at": "2026-05-31T13:00:00+00:00",
      "reason": "official omx plugin pack"
    }
  }
}
```

---

## CLI 命令

### 信任技能包

```bash
# 信任一个技能包（按包名）
vibe trust oh-my-codex

# 信任时指定来源 URL
vibe trust oh-my-codex --source https://github.com/omx-plugins/oh-my-codex

# 信任一个来源 URL
vibe trust https://github.com/omx-plugins/oh-my-codex
```

### 查看已信任列表

```bash
vibe trust --list
```

输出示例：
```
┏━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name/Source ┃ Type  ┃ Trusted At               ┃
┡━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ oh-my-codex │ pack  │ 2026-05-31T13:00:00+00:00 │
└─────────────┴───────┴──────────────────────────┘
```

### 取消信任

```bash
vibe trust oh-my-codex --revoke
```

---

## Strict Mode

`SkillSecurityAuditor` 支持两种模式：

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| **Strict** (`strict_mode=True`, 默认) | 任何非 SAFE 等级都拒绝 | 生产环境、CI/CD |
| **宽松** (`strict_mode=False`) | 只有 CRITICAL/HIGH 拒绝 | 本地开发、快速迭代 |

**注意：** Trust Store 的 override 在 strict mode 下仍然有效——trusted pack 的 HIGH 威胁降级为 MEDIUM 后会被接受。

---

## 常见问题

### Q: 我的技能包被拒绝了，但内容明明是安全的

检查拒绝原因中的威胁名称：
- 如果是 `instruction_injection` / `role_hijacking`，可能是文档中描述攻击类型的措辞触发了正则（如 `override instructions`、`you are a developer`）
- 将该包加入 Trust Store：`vibe trust <pack-name>`
- 如果确认是误报，也可以考虑向项目提交 Issue，优化扫描规则

### Q: Trust 后为什么审计结果里还能看到威胁？

这是预期行为。Trust 只影响 `is_safe` 的最终判定，不会删除威胁记录。这样可以在需要时追溯审计历史。

### Q: CRITICAL 威胁能被 Trust 覆盖吗？

**不能。** CRITICAL 级别的威胁（如 `Ignore all previous instructions`）即使包已被信任，仍然会被拒绝。这是安全底线。

### Q: 内置技能需要 Trust 吗？

不需要。安全审计只针对**外部技能包**（`~/.claude/skills/`、`~/.config/skills/` 等路径下的第三方技能）。项目内置技能（`core/skills/`）和项目本地技能（`skills/`）不走安全审计流程。

---

## 相关代码

| 模块 | 路径 |
|------|------|
| 安全审计器 | `src/vibesop/security/skill_auditor.py` |
| 扫描引擎 | `src/vibesop/security/scanner.py` |
| 威胁规则 | `src/vibesop/security/rules.py` |
| Trust Store | `src/vibesop/core/skills/trust.py` |
| CLI 命令 | `src/vibesop/cli/commands/trust.py` |
| 安装器 | `src/vibesop/installer/pack_installer.py` |
