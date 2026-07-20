# VibeSOP 后续工作路线图

> 基于 Phase 1 深度诊断（16 个 Agent，80+ 发现）
> 已完成：P0 修复（6 项，commit `684646f`）

---

## 总进度

| 阶段 | 状态 | 项数 | 估计工期 |
|------|------|------|----------|
| ✅ P0 | 已完成 | 6 | 已完成 |
| ✅ P1 | 已完成 | 15 | 已完成 |
| 🔜 P2 | 待开始 | 13 | 3-5 天 |
| 📋 P3 | 待开始 | 8 | 2-3 天 |

---

## ✅ P1 — 架构解耦 + 安全加固（已完成）

### 架构解耦（4 项 — 全部完成）

| # | 问题 | 状态 |
|---|------|------|
| **P1-1** | routing ↔ orchestration 循环依赖 | ✅ 添加 `get_skill_loader()` + 消除 `getattr` |
| **P1-2** | `AgentRouter` 修改私有属性 | ✅ 添加 `set_llm_factory()` 公共方法 |
| **P1-3** | `PlanBuilder` 通过 `getattr` 访问 `_skill_loader` | ✅ 合并到 P1-1 |
| **P1-4** | `GrokBuildAdapter` 绕过 `HookBasedAdapter` 层级 | ⏸ 延至 P2（大重构，需独立 PR） |

### 安全加固（3 项 — 全部完成）

| # | 问题 | 状态 |
|---|------|------|
| **P1-5** | Windows `_acquire_tick_lock` 空操作 | ✅ 文件创建锁替代 |
| **P1-6** | Bun 回退无沙箱执行 | ✅ UX 改进（安全门已存在） |
| **P1-7** | `LLMConfig.api_key` 纯文本存储 | ✅ `field(repr=False)` + 自定义 `__repr__` |

### 正确性修复（5 项 — 全部完成）

| # | 问题 | 状态 |
|---|------|------|
| **P1-8** | 42+ 处 `except ... : pass` 静默吞错 | ⚠️ 高风险项已修复，剩余 ~36 处延至 P2 |
| **P1-9** | `skill_installer` 注册表子串误匹配 | ✅ YAML 结构化编辑 |
| **P1-10** | `transactional._restore_snapshot` 空操作 | ✅ 基类抛出 `NotImplementedError` |
| **P1-11** | `reorchestrator` 目标检测启发式过松 | ✅ 意图-步骤对应关系检测 |
| **P1-12** | `ConflictResolver` 默认策略缺少显式覆盖 | ✅ 添加 `ExplicitOverrideStrategy` |

### 集成修复（3 项 — 全部完成）

| # | 问题 | 状态 |
|---|------|------|
| **P1-13** | `VALID_TARGETS` 在 3 个 CLI 文件中重复 | ✅ 提取到 `constants.py` |
| **P1-14** | CLI 到 CLI 耦合 | ✅ 提取到 `_utils.py` |
| **P1-15** | `agent/` 使用 `ValueError` 而非 `VibeSOPError` | ✅ 添加 `PlanNotFoundError`、`SingleIntentRoutingError` |

---

## 🔜 P2 — 测试补全 + 质量提升（待开始）

### 测试补全（5 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| **P2-1** | `atomic_writer.py` 零测试 | `utils/atomic_writer.py` | 安全关键工具，需原子写入测试 |
| **P2-2** | `cost_tracker.py` 零测试 | `routing/cost_tracker.py`, `llm/cost_tracker.py` | AI 调用预算监控 |
| **P2-3** | `router_factory.py` 零测试 | `routing/router_factory.py` | 路由组件构造 |
| **P2-4** | `overlay.py` 零测试 | `builder/overlay.py` | 配置合并逻辑 |
| **P2-5** | 9 个外部技能测试在 CI 中跳过 | `tests/integration/test_external_skills_real.py` | 添加最小测试技能包 |

### 代码质量（4 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| **P2-6** | `_shared.py` 740 行混合关注点拆分 | `adapters/_shared.py` | 文档生成 / 技能查找 / 环境检测分模块 |
| **P2-7** | `ClaudeCodeAdapter.render_config` ~200 行重复 | `adapters/claude_code.py:156-372` | 合并为单方法 `render_skills` 参数 |
| **P2-8** | `understander.py` ~400 行硬编码规则 | `core/skills/understander.py` | 迁移到 YAML 配置文件 |
| **P2-9** | `init_support.py` ~250 行硬编码 TOML 模板 | `installer/init_support.py` | 迁移到 Jinja2 模板 |

### 低风险清理（3 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| **P2-10** | `test_analyze_command.py` + `test_analyze_commands.py` 疑似重复 | `tests/cli/` | 合并或移除 |
| **P2-11** | 7 个根级测试文件归属子目录 | `tests/` | 结构性整理 |
| **P2-12** | 清理 `TYPE_CHECKING` + 内联 import 模式 | 20+ 文件 | 减少碎片化导入 |

---

## 📋 P3 — CI 完善 + 运维提升

### CI/CD（4 项）

| # | 问题 | 说明 |
|---|------|------|
| **P3-1** | 添加 macOS CI | Apple Silicon 为主要开发平台，当前无覆盖率 |
| **P3-2** | 基准测试门禁 | `pytest-benchmark` + GitHub Action 比对 |
| **P3-3** | Windows CI 转阻塞 | 当前 `continue-on-error: true`，观察期结束后移除 |
| **P3-4** | 恢复 Dependabot 配置 | `.github/dependabot.yml` + `uv` 生态 |

### 可观测性（2 项）

| # | 问题 | 说明 |
|---|------|------|
| **P3-5** | 结构化日志 | `structlog` 或 JSON 日志 + 关联 ID |
| **P3-6** | 分布式追踪 | OpenTelemetry span 注入路由管道 10 层 |

### 部署（2 项）

| # | 问题 | 说明 |
|---|------|------|
| **P3-7** | 生产 Dockerfile | `python:3.12-slim` + `uv` + VibeSOP wheel |
| **P3-8** | 信任存储/包锁文件权限 | `0o600`，防止全局可读 |

---

## 执行建议

```
P1 批次（当前）
├── 批次 A: 架构解耦（P1-1 ~ P1-4）     → 4 项，2-3 天
├── 批次 B: 安全加固（P1-5 ~ P1-7）     → 3 项，1-2 天
├── 批次 C: 正确性修复（P1-8 ~ P1-12）  → 5 项，2-3 天
└── 批次 D: 集成修复（P1-13 ~ P1-15）   → 3 项，1 天

P2 批次
├── 批次 A: 测试补全（P2-1 ~ P2-5）     → 5 项，2-3 天
├── 批次 B: 代码质量（P2-6 ~ P2-9）     → 4 项，2 天
└── 批次 C: 清理（P2-10 ~ P2-12）       → 3 项，1 天

P3 批次
├── 批次 A: CI/CD（P3-1 ~ P3-4）        → 4 项，1-2 天
├── 批次 B: 可观测性（P3-5 ~ P3-6）     → 2 项，1-2 天
└── 批次 C: 部署（P3-7 ~ P3-8）         → 2 项，1 天
```

**每个批次执行规范**（使用 `adversarial-optimization` 技能）：
1. 制定计划 → 对抗 Agent 审查
2. 逐项执行 → 独立评审 Agent 实时确认
3. 批次完成 → Kimi 代码复审 + OrbStack e2e
4. 提交 atomic commit

> 技能文件：`~/.claude/skills/adversarial-optimization/SKILL.md`
> 触发词：`adversarial optimization` / `对抗验证` / `三审三校`
