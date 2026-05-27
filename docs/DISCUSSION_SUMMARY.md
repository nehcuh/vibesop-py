# VibeSOP 项目讨论总结与纠偏建议

> **日期**: 2026-05-01
> **版本**: 基于 5.4.5 代码评审 (原始评审基于 5.4.1)
> **状态**: 核心偏离已修复，Phase 0 品质收敛进行中
> **最后验证**: 2026-05-23 (v5.4.5 — 所有核心偏离已修复，Phase 0 品质收敛已完成)

---

## 一、项目定位（经讨论确认）

### 1.1 VibeSOP = SkillOS = 技能管理者，不是技能生产者

```
┌─────────────────────────────────────────────────────────┐
│                    VibeSOP (SkillOS)                     │
│                                                          │
│  发现  →  安装  →  路由  →  编排  →  评估  →  保留/淘汰   │
│                                                          │
│  ❌ 不做: 编写技能内容、执行技能流程                        │
│  ✅ 做:   管理技能元数据、分发、生命周期                     │
└─────────────────────────────────────────────────────────┘
                          ↓
              ┌─────────────────────┐
│              │  AI Agent (Claude)   │
│              │                      │
│              │  读取 SKILL.md 正文   │
│              │  → 执行完整技能流程    │
│              └─────────────────────┘
```

### 1.2 技能分类

| 类型 | 例子 | 归属 | 是否保留 |
|------|------|------|---------|
| **管理工具** | slash-route, slash-help, slash-install, slash-list | VibeSOP 内置 | ✅ 核心功能 |
| **通用兜底工作流** | riper-workflow | VibeSOP 内置 | ✅ fallback |
| **具体技能** | slash-analyze, planning-with-files | VibeSOP 内置 | ❌ 移除或移出 |
| **第三方技能包** | gstack, superpowers, omx | 外部安装 | ✅ 完整保留 |

---

## 二、现状与差距

### 2.1 文档定位 vs 代码实现

| 维度 | PHILOSOPHY.md 怎么说 | 代码实际怎么做 | 差距 |
|------|---------------------|---------------|------|
| **定位** | "VibeSOP 是 SkillOS + 轻量引导执行层，管理全生命周期" | 全生命周期管理代码完整 | ✅ 一致 (v5.4.5 已验证) |
| **技能管理** | "完整生命周期：发现→安装→路由→编排→评估→保留/淘汰" | build 时覆盖外部技能 SKILL.md | ✅ 已修复 (commit dad18a2) — _render_skill_content() 优先 symlink，仅 fallback 到模板 |
| **学习系统** | "InstinctLearner，记住什么有效" | 代码存在，需手动触发 | ✅ 已修复 — `analytics_mixin.py:81-90` 置信度 ≥ 70% 自动记录，source="auto_routing" |
| **上下文感知** | "session 智能追踪，自动重路由" | 框架存在，hook 未激活 | ✅ 已修复 — `session_aware=True` 默认开启，`context_mixin.py` 自动重路由 |
| **跨平台** | "Claude Code, Cursor, Continue.dev" | 3 个适配器已实现 + cursor.py 新增 | ✅ 满足 (v5.4.5) |
| **过时文档** | SkillOS 全生命周期定位 | 源码中 5 处仍写 "routing engine, not executor" | ✅ 已修复 (2026-05-24, 本次) |

### 2.2 ~~核心 Bug：build 流程覆盖外部技能~~ ✅ 已修复

> **修复 commit**: `dad18a2` — "fix: philosophy alignment — fix build skill overwrite"
>
> **当前行为**: `_render_skill_content()` (claude_code.py:345-421) 已重写，采用三层回退策略：
> 1. 先从 `_find_skill_content()` 读取原始技能内容
> 2. 再检查中央存储是否存在已安装的包 → 创建 symlink
> 3. 仅当前两步全部失败时才 fallback 到 Jinja2 模板
>
> **关键注释**（第360-362行）: "Critical invariant: NEVER overwrite an external skill's full SKILL.md with the thin Jinja2 template wrapper."

### 2.3 测试覆盖率危机

| 指标 | 实际 | 目标 |
|------|------|------|
| 测试数量 | 2260 | — |
| 通过率 | 99.96% (2259/2260) | 100% |
| **代码覆盖率** | **20.01%** | **75%** |
| 类型检查 | 14 errors + 240 warnings | 0 errors |

### 2.4 版本号不一致

- pyproject.toml: 5.3.2
- README.md: 5.3.0 ❌
- PHILOSOPHY.md: 5.3.2

---

## 三、需要纠偏的内容

### P0（立即修复）✅ 全部完成

1. ~~修复 build 流程不覆盖外部技能 SKILL.md~~ ✅ 已修复
2. ~~移除 slash-analyze~~ ✅ 已移除
3. ~~统一版本号~~ ✅ 已统一 (5.4.1)
4. ~~修复 basedpyright 14 个 errors~~ ✅ 已归零

### P1（本周）

5. ~~处理 planning-with-files~~ ✅ 已从 core/skills 移除
6. **清理所有 DeprecationWarning** — ⚠️ 仍有大量 `route()` 调用待迁移
7. **制定覆盖率提升计划** — ⚠️ 20% → 75% 待启动

### P2（本月）

8. **支持 .tmpl 模板渲染**
   - gstack 使用 `bun run gen:skill-docs` 生成 SKILL.md
   - VibeSOP 安装 gstack 后应运行其构建脚本

9. **文档诚实化**
   - 自主学习、上下文感知标注为 "实验性功能，需手动开启"
   - 明确说明当前自动触发机制的限制

10. **生成 API 文档**

---

## 四、PHILOSOPHY.md 需要更新的部分

当前 PHILOSOPHY.md 整体定位准确，但需要以下补充：

### 4.1 在"我们不做什么"中补充

```markdown
### 我们不生产技能内容

VibeSOP 管理技能的分发和生命周期，但不编写、不修改技能的具体执行流程。

- ❌ 不: 把 gstack/review 的完整流程替换为薄包装
- ❌ 不: 内置"项目分析"等具体技能（这是 omx/analyze 或 gstack/review 的职责）
- ✅ 做: 确保 Agent 读取到的是技能的原始完整内容
```

### 4.2 在"技能生命周期"中补充"分发"环节的边界

```markdown
**发现 → 安装 → 路由 → 编排 → [分发: 完整保留技能内容] → 评估 → 保留/淘汰**

分发原则: VibeSOP 只追加元数据 frontmatter，不改正文。
```

### 4.3 补充"实验性功能"声明

```markdown
### 实验性功能

以下功能代码已实现，但自动触发机制尚未完全打通：

| 功能 | 状态 | 使用方式 |
|------|------|---------|
| 自主学习 (InstinctLearner) | 框架完成 | 手动: `vibe skills suggestions` |
| 上下文感知重路由 | 框架完成 | 手动: `vibe session check-reroute` |
| Session 智能追踪 | 框架完成 | 需手动开启 hooks |
```

### 4.4 补充"内置技能清单"

```markdown
### VibeSOP 内置技能（仅管理工具）

| 技能 | 类型 | 说明 |
|------|------|------|
| slash-route | 管理工具 | 路由查询 |
| slash-help | 管理工具 | 系统帮助 |
| slash-install | 管理工具 | 安装技能包 |
| slash-list | 管理工具 | 列出技能 |
| slash-evaluate | 管理工具 | 评估技能质量 |
| slash-orchestrate | 管理工具 | 多技能编排 |
| riper-workflow | 通用兜底 | 无具体技能匹配时的 fallback |
```

---

## 五、后续补齐的内容

### 5.1 技术债务

| 项目 | 优先级 | 工作量 |
|------|--------|--------|
| 测试覆盖率 20% → 75% | P1 | 2-3 sprints |
| basedpyright 收敛 | P1 | 1 sprint |
| 类型安全修复 | P1 | 1 sprint |
| 性能优化 (P95 653ms → <500ms) | P2 | 1 sprint |

### 5.2 功能补齐

| 项目 | 优先级 | 依赖 |
|------|--------|------|
| .tmpl 模板渲染支持 | P2 | 外部包 build 脚本集成 |
| 自动 hook 激活 | P2 | 平台 hook API 稳定 |
| 技能市场完整实现 | P2 | 社区参与 |

### 5.3 生态建设

| 项目 | 优先级 |
|------|--------|
| 发布 vibesop-workflows 独立包 | P2 |
| 完善技能包安装文档 | P2 |
| 建立技能质量评估体系 | P3 |

---

## 六、总结 (2026-04-30 更新)

> ~~**VibeSOP 的 PHILOSOPHY 是对的，但代码走偏了。**~~
> ~~修复 build 流程的覆盖 bug，移除偏离定位的内置技能，诚实标注实验性功能，VibeSOP 就能回到正确的轨道上。~~
>
> **上述 P0 偏离已全部修复** (commit `dad18a2`):
> - ✅ build 覆盖 → symlink 优先策略
> - ✅ slash-analyze / planning-with-files → 已从 core/skills 移除
> - ✅ 版本号 → 统一 5.4.1
> - ✅ 类型错误 → 14→0
> - ✅ InstinctLearner / session 追踪 → 默认自动开启
>
> **2026-05-24 更新**: 文档与代码定位声明已全面对齐 (源码 5 处 + 核心文档 7 处更新)。
> "routing engine, not executor" → "SkillOS managing full skill lifecycle"。
>
> **当前核心矛盾**: 代码方向已回正轨。测试覆盖率从 20% 提升至 73%，类型错误归零。
> 剩余工作: DeprecationWarning 清理、双 YAML 依赖统一、P95 延迟优化。
