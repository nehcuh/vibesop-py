# VibeSOP 项目讨论总结与纠偏建议

> **日期**: 2026-04-30
> **版本**: 基于 5.3.2 代码评审
> **状态**: 需要文档更新 + 代码纠偏

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
| **定位** | "VibeSOP 是 SkillOS，不执行技能" | 内置了 slash-analyze 等具体技能 | ❌ 偏离 |
| **技能管理** | "完整生命周期：发现→安装→路由→编排→评估→保留/淘汰" | build 时覆盖外部技能 SKILL.md | ❌ 破坏 |
| **学习系统** | "InstinctLearner，记住什么有效" | 代码存在，需手动触发 | ⚠️ 未自动化 |
| **上下文感知** | "session 智能追踪，自动重路由" | 框架存在，hook 未激活 | ⚠️ 未自动化 |
| **跨平台** | "Claude Code, Cursor, Continue.dev" | 3 个适配器已实现 | ✅ 基本满足 |

### 2.2 核心 Bug：build 流程覆盖外部技能

**问题**: `vibe build claude-code` 时，`_render_skill_content()` 用薄包装模板覆盖了 gstack/superpowers/omx 的完整 SKILL.md。

**影响**:
- gstack/review: 296行模板 → 46行空壳
- omx/analyze: 原始流程 → 51行元数据
- superpowers/systematic-debugging: 多文档辅助 → 51行元数据

**结果**: Agent 匹配到技能后，只能看到元数据，无法执行完整流程。

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

### P0（立即修复）

1. **修复 build 流程不覆盖外部技能 SKILL.md**
   - 文件: `src/vibesop/adapters/claude_code.py:345-400`
   - 方案: 如果 skill_dir 已是正确 symlink，跳过渲染
   - 重建所有外部技能的 SKILL.md 为原始完整内容

2. **移除 slash-analyze**
   - 删除 `core/skills/slash-analyze/`
   - 路由逻辑：分析请求 → 匹配 omx/analyze（如安装）或 gstack/review 或通用 fallback

3. **统一版本号**
   - README.md 从 5.3.0 更新为 5.3.2

4. **修复 basedpyright 14 个 errors**

### P1（本周）

5. **处理 planning-with-files**
   - 选择 A: 移出为独立 vibesop-workflows 包
   - 选择 B: 保留但明确标注为 "通用工作流示例"
   - 推荐 A

6. **清理所有 DeprecationWarning**

7. **制定覆盖率提升计划**
   - 分阶段: 20% → 40% → 60% → 75%
   - 优先覆盖 security/, installer/, market/

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

## 六、一句话总结

> **VibeSOP 的 PHILOSOPHY 是对的，但代码走偏了。**
>
> 它应该是一个纯粹的 SkillOS——管理技能但不生产技能、路由但不执行、分发但不篡改。
>
> 修复 build 流程的覆盖 bug，移除偏离定位的内置技能，诚实标注实验性功能，
> VibeSOP 就能回到正确的轨道上。
