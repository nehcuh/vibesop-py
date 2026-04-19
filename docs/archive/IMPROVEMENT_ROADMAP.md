# VibeSOP-Py 改进路线图

> **版本**: 4.1.0 → 5.0.0
> **制定时间**: 2026-04-18
> **目标**: 从技术导向转向愿景导向，实现真正的开放技能生态

---

## 执行摘要

基于深度项目审查，我们发现：
- ✅ **技术基础扎实** (9/10代码质量，82%测试覆盖率)
- ⚠️ **哲学传承不足** (4/10，缺少"为什么"的阐述)
- ❌ **外部集成表面化** (3/10，只能检测不能使用)

**核心转变**: 从"功能开发"模式 → "架构整合"模式

---

## 四大支柱

### 🔴 P0-1: 外部技能动态加载 (Week 1-2)
**影响**: 开放生态的基石
**当前**: 只检测不使用
**目标**: 真正执行外部技能包

### 🔴 P0-2: 架构一致性 (Week 2-3)
**影响**: 长期可维护性
**当前**: 重复抽象、配置碎片化
**目标**: 统一架构叙事

### 🟡 P1-1: 路由准确率 (Week 3-4)
**影响**: 用户满意度
**当前**: 85%
**目标**: 90%+

### 🟢 P1-2: 哲学文档 (Week 4)
**影响**: 新用户理解和贡献
**当前**: 技术导向
**目标**: 愿景导向

---

## 详细实施计划

## Phase 1: 外部技能动态加载 (Week 1-2)

### 目标
让 superpowers/gstack/omx 等外部技能包可以真正被使用，而不只是被检测。

### Step 1.1: 设计外部技能执行接口 (Day 1-2)

**文件创建**:
- `src/vibesop/core/skills/executor.py` (新文件)

**核心接口**:
```python
class ExternalSkillExecutor:
    """外部技能执行器 - 从 SKILL.md 读取并执行工作流"""

    def execute_skill(
        self,
        skill_id: str,
        context: dict[str, Any],
    ) -> SkillResult:
        """执行外部技能

        Args:
            skill_id: 技能标识符 (如 "superpowers/tdd")
            context: 执行上下文

        Returns:
            SkillResult: 执行结果

        Raises:
            SkillNotFoundError: 技能不存在
            SkillExecutionError: 执行失败
            SecurityViolationError: 安全违规
        """
```

**依赖**:
- `core/skills/parser.py` (已有，需增强)
- `core/skills/base.py` (已有)
- `security/skill_auditor.py` (已有)

**验收**:
- [ ] 接口定义清晰
- [ ] 类型注解完整
- [ ] 文档字符串完整
- [ ] 单元测试通过

### Step 1.2: 增强 SKILL.md 解析器 (Day 3-4)

**文件修改**:
- `src/vibesop/core/skills/parser.py`

**新增功能**:
```python
class SkillParser:
    def parse_workflow(self, skill_md: Path) -> Workflow:
        """解析 SKILL.md 中的工作流定义

        提取:
        - 工作流步骤序列
        - 每步的类型 (指令/验证/工具调用)
        - 参数和默认值
        - 条件分支
        """

    def parse_triggers(self, skill_md: Path) -> list[Trigger]:
        """解析技能触发条件

        识别:
        - 关键词触发
        - 场景触发
        - 依赖条件
        """
```

**验收**:
- [ ] 可以解析现有内置技能的 SKILL.md
- [ ] 可以解析 superpowers/gstack/omx 的 SKILL.md
- [ ] 解析错误有明确的错误消息
- [ ] 测试覆盖率 >85%

### Step 1.3: 实现工作流执行引擎 (Day 5-7)

**文件创建**:
- `src/vibesop/core/skills/workflow.py` (新文件)

**核心类**:
```python
class WorkflowEngine:
    """工作流执行引擎"""

    def execute(
        self,
        workflow: Workflow,
        context: ExecutionContext,
    ) -> WorkflowResult:
        """执行工作流

        支持:
        - 顺序步骤
        - 条件分支
        - 循环 (有限次数)
        - 错误处理
        """

    def validate_step(self, step: WorkflowStep) -> bool:
        """验证步骤安全性"""
```

**安全机制**:
- 沙箱执行 (限制可用的工具)
- 超时控制
- 资源限制
- 危险操作检测

**验收**:
- [ ] 可以执行简单工作流
- [ ] 错误处理健壮
- [ ] 安全机制生效
- [ ] 性能可接受 (<100ms per step)

### Step 1.4: 集成到 SkillManager (Day 8-9)

**文件修改**:
- `src/vibesop/core/skills/manager.py`

**新增方法**:
```python
class SkillManager:
    def execute_skill(
        self,
        skill_id: str,
        context: dict[str, Any] | None = None,
    ) -> SkillResult:
        """执行技能（内置或外部）"""
```

**验收**:
- [ ] 统一的执行接口
- [ ] 内置和外部技能行为一致
- [ ] 错误处理一致
- [ ] 向后兼容 (不破坏现有 API)

### Step 1.5: 测试和文档 (Day 10)

**测试文件**:
- `tests/core/skills/test_executor.py` (新)
- `tests/core/skills/test_workflow.py` (新)
- `tests/integration/test_external_skills.py` (新)

**测试用例**:
- 执行内置技能
- 执行 superpowers 技能
- 执行 gstack 技能
- 错误处理 (技能不存在、执行失败)
- 安全违规检测
- 边界条件 (空工作流、循环、超时)

**文档**:
- `docs/external-skills-guide.md` (新)
- 更新 README.md
- 更新 API 参考

**验收**:
- [ ] 所有测试通过
- [ ] 测试覆盖率 >80%
- [ ] 文档完整
- [ ] 示例代码可运行

### 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 工作流执行复杂度高 | 中 | 高 | 分阶段实现，先支持简单工作流 |
| 安全漏洞 | 低 | 高 | 强制安全审计，沙箱执行 |
| 性能问题 | 中 | 中 | 缓存解析结果，懒加载 |
| 破坏向后兼容 | 低 | 高 | 增量添加 API，保留旧 API |

---

## Phase 2: 架构一致性 (Week 2-3)

### 目标
清理历史遗留的重复抽象，统一架构叙事，消除配置碎片化。

### Step 2.1: 文档化三层架构 (Day 1-2)

**文件创建**:
- `docs/architecture/three-layers.md` (新)

**内容**:
```
1. 核心层 (core/)
   - 路由引擎 (routing/)
   - 技能管理 (skills/)
   - 匹配算法 (matching/)
   - 优化系统 (optimization/)
   - 记忆系统 (memory/, instinct/)
   - 算法库 (algorithms/)

2. 适配器层 (adapters/)
   - Claude Code 适配器
   - OpenCode 适配器
   - 未来平台适配器

3. 构建层 (builder/)
   - 配置渲染器
   - 模板引擎
   - 文档生成器

边界规则:
- core/ 不依赖任何适配器
- adapters/ 可以依赖 core/
- builder/ 可以依赖 core/ 和 adapters/
- 适配器之间互不依赖
```

**验收**:
- [ ] 架构图清晰
- [ ] 模块职责明确
- [ ] 依赖关系可视化
- [ ] 新贡献者能理解

### Step 2.2: 统一配置管理 (Day 3-4)

**文件修改**:
- `src/vibesop/core/config/manager.py`

**新增功能**:
```python
class ConfigManager:
    def deep_merge_configs(
        self,
        *configs: dict[str, Any],
    ) -> dict[str, Any]:
        """深度合并多个配置

        优先级:
        1. CLI flags (highest)
        2. .vibe/config.yaml (项目)
        3. ~/.config/vibe/config.yaml (用户)
        4. core/policies/*.yaml (默认)
        """

    def get_effective_config(
        self,
        config_type: ConfigType,
    ) -> dict[str, Any]:
        """获取生效的配置（已合并所有来源）"""
```

**文档化配置优先级**:
- 创建 `docs/configuration/priority.md`
- 明确每个配置文件的用途
- 明确哪些可以被覆盖
- 提供配置示例

**验收**:
- [ ] 合并规则明确
- [ ] 文档清晰
- [ ] 测试覆盖各种组合
- [ ] 向后兼容

### Step 2.3: 评估并清理 triggers/ 模块 (Day 5-6)

**文件分析**:
- `src/vibesop/triggers/` (如果存在)
- `tests/triggers/`

**决策树**:
```
1. triggers/ 有独特用途？
   是 → 保留，但明确文档化其与 core/routing/ 的区别
   否 → 标记废弃，迁移到 core/routing/

2. 如果保留:
   - 重命名避免混淆 (如 intent-detection/)
   - 明确其使用场景
   - 文档化与 routing/ 的关系

3. 如果废弃:
   - 迁移有用功能到 core/
   - 添加废弃警告
   - 在下个主版本移除
```

**验收**:
- [ ] 决策已记录
- [ ] 代码已更新或标记废弃
- [ ] 文档已更新
- [ ] 测试已更新

### Step 2.4: 消除重复的路由逻辑 (Day 7-9)

**文件审查**:
- `core/routing/` vs `triggers/` vs `semantic/` (如果存在)
- 识别重复的 TF-IDF、embedding、匹配逻辑

**重构方案**:
```python
# 统一的匹配接口
class IMatcher(Protocol):
    def match(
        self,
        query: str,
        candidates: list[SkillCandidate],
    ) -> list[MatchResult]:
        """匹配技能"""
```

**迁移策略**:
1. 保留 `core/matching/` 作为统一的匹配层
2. 将其他模块的匹配逻辑迁移到此处
3. 更新所有调用点
4. 添加废弃警告

**验收**:
- [ ] 无重复的匹配逻辑
- [ ] 统一的接口
- [ ] 性能不退化
- [ ] 测试覆盖

### Step 2.5: 验证和文档 (Day 10)

**架构验证**:
- 运行所有测试
- 检查模块依赖图
- 确认边界清晰

**文档更新**:
- 更新 `docs/architecture/overview.md`
- 更新 `docs/architecture/three-layers.md`
- 创建 `docs/architecture/decisions.md` (架构决策记录)

**验收**:
- [ ] 所有测试通过
- [ ] 架构文档完整
- [ ] 依赖图清晰
- [ ] 无架构违规

### 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 破坏向后兼容 | 中 | 高 | 增量重构，保留旧 API |
| 配置合并错误 | 中 | 中 | 全面测试，添加验证 |
| 触发现有bug | 低 | 中 | 完整测试套件 |
| 文档不完整 | 低 | 低 | 强制文档更新 |

---

## Phase 3: 路由准确率优化 (Week 3-4)

### 目标
将路由准确率从 85% 提升到 90%+。

### Step 3.1: 分析路由失败案例 (Day 1-2)

**数据收集**:
- 收集用户反馈
- 分析现有路由日志
- 识别失败模式

**分析维度**:
- 按技能类型分析
- 按查询类型分析
- 按层级分析
- 按置信度分布分析

**输出**:
- `docs/analysis/routing-failures.md`
- 失败案例分类
- 优先改进清单

**验收**:
- [ ] 至少收集 50 个失败案例
- [ ] 分类清晰
- [ ] 有明确的改进方向

### Step 3.2: 调优 TF-IDF 权重 (Day 3-4)

**文件修改**:
- `src/vibesop/core/matching/tfidf.py`

**参数调优**:
```python
class TFIDFMatcher:
    # 当前权重
    WEIGHTS = {
        "name": 1.0,
        "description": 0.8,
        "intent": 1.2,
        "tags": 0.5,
    }

    # 调优后权重 (待实验)
    OPTIMIZED_WEIGHTS = {
        "name": 1.5,        # ↑ 提高名称权重
        "description": 0.6,  # ↓ 降低描述权重
        "intent": 1.5,      # ↑ 提高意图权重
        "tags": 0.8,        # ↑ 提高标签权重
    }
```

**实验设计**:
- A/B 测试不同权重配置
- 在测试集上评估
- 选择最优配置

**验收**:
- [ ] 准确率提升 >2%
- [ ] 性能不退化
- [ ] 有 A/B 测试数据

### Step 3.3: 补充场景映射 (Day 5-6)

**文件修改**:
- `core/registry.yaml`
- `core/policies/task-routing.yaml`

**新增场景**:
```yaml
scenario_patterns:
  # 新增场景
  - trigger: "代码审查"
    skill: "gstack/review"
    confidence: 0.95

  - trigger: "性能优化"
    skill: "superpowers/optimize"
    confidence: 0.92

  # 更多...
```

**验收**:
- [ ] 新增至少 20 个场景映射
- [ ] 覆盖常见查询
- [ ] 测试通过

### Step 3.4: AI Triage 参数调优 (Day 7)

**文件修改**:
- `src/vibesop/core/routing/triage_service.py`

**参数优化**:
- 温度参数
- Top-p 参数
- 提示词优化

**验收**:
- [ ] 准确率提升 >1%
- [ ] 成本不增加
- [ ] 延迟不增加

### Step 3.5: 用户反馈循环 (Day 8-9)

**文件创建**:
- `src/vibesop/core/feedback.py` (新)

**功能**:
```python
class FeedbackCollector:
    def collect_feedback(
        self,
        query: str,
        routed_skill: str,
        was_correct: bool,
        actual_skill: str | None = None,
    ) -> None:
        """收集路由反馈"""

    def generate_report(self) -> FeedbackReport:
        """生成反馈报告"""
```

**集成**:
- 在 CLI 中添加反馈命令
- 自动收集错误路由
- 定期生成报告

**验收**:
- [ ] 反馈机制可用
- [ ] 有至少 100 条反馈数据
- [ ] 报告有用

### Step 3.6: 验证和基准测试 (Day 10)

**测试**:
- 在测试集上评估
- 与基准对比
- 性能测试

**文档**:
- 创建 `docs/benchmarks/routing-accuracy.md`
- 记录改进过程
- 记录最终结果

**验收**:
- [ ] 准确率 >= 90%
- [ ] 性能不退化
- [ ] 有完整基准数据
- [ ] 文档完整

### 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 过拟合测试集 | 中 | 中 | 使用多个测试集，交叉验证 |
| 性能退化 | 低 | 中 | 性能基准测试 |
| 准确率不达标 | 低 | 高 | 多个改进方向并行 |

---

## Phase 4: 哲学文档完善 (Week 4)

### 目标
补充项目哲学文档，从技术导向转向愿景导向。

### Step 4.1: 重写 README (Day 1-2)

**当前问题**:
- 重点在技术特性
- 缺少"为什么"的阐述

**新结构**:
```markdown
# VibeSOP

> **不是演示配置，是生产级SOP**
>
> 一套 AI 辅助开发的标准工作流——个人用它积累知识、团队用它统一规范

## 为什么需要 VibeSOP？

[问题陈述]

## 核心原则

[哲学阐述]

## 如何工作

[技术细节]

## 快速开始

[使用指南]
```

**验收**:
- [ ] 前3段讲"为什么"
- [ ] 有清晰的愿景陈述
- [ ] 技术细节在后半部分
- [ ] 有角色导向的引导

### Step 4.2: 创建哲学文档 (Day 3)

**文件创建**:
- `docs/PHILOSOPHY.md` (新)

**内容**:
```markdown
# VibeSOP 哲学

## 设计原则

1. Discovery > Execution
   [解释]

2. Matching > Guessing
   [解释]

...

## 为什么这些原则重要？

[阐述]

## 如何应用这些原则？

[示例]
```

**验收**:
- [ ] 所有核心原则都有阐述
- [ ] 有实际例子
- [ ] 与 PRINCIPLES.md 一致
- [ ] 易于理解

### Step 4.3: 角色导向文档 (Day 4)

**文件创建**:
- `docs/for-individual-developers.md` (新)
- `docs/for-teams.md` (新)
- `docs/for-engineering-managers.md` (新)

**内容结构**:
```markdown
# 个人开发者指南

## VibeSOP 如何帮助你？

[价值主张]

## 典型工作流

[示例]

## 快速上手

[步骤]
```

**验收**:
- [ ] 每个角色有专门文档
- [ ] 有具体的使用场景
- [ ] 有清晰的开始步骤
- [ ] 互相关联

### Step 4.4: 快速入门指南 (Day 5)

**文件创建**:
- `docs/quickstart.md` (新)

**内容**:
```markdown
# 5分钟快速入门

## 第一步: 安装

[命令]

## 第二步: 第一次路由

[示例]

## 第三步: 查看技能

[命令]

## 下一步

[链接]
```

**验收**:
- [ ] 新用户能在5分钟上手
- [ ] 有清晰的截图/示例
- [ ] 每步都可验证
- [ ] 有下一步指引

### Step 4.5: 更新贡献者指南 (Day 6-7)

**文件修改**:
- `CONTRIBUTING.md`

**新增内容**:
```markdown
## 设计原则

[链接到 PHILOSOPHY.md]

## 架构概览

[链接到架构文档]

## 开发流程

[步骤]

## 代码审查清单

[检查项]
```

**验收**:
- [ ] 新贡献者能理解项目方向
- [ ] 有清晰的开发流程
- [ ] 有代码审查标准
- [ ] 与其他文档互相关联

### Step 4.6: 验证和发布 (Day 8-10)

**验证**:
- 所有文档链接有效
- 所有示例可运行
- 新用户测试

**发布**:
- 创建 PR
- 团队审查
- 合并主分支
- 更新 CHANGELOG

**验收**:
- [ ] 所有文档完整
- [ ] 示例可运行
- [ ] 新用户测试通过
- [ ] 已发布

### 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 文档不一致 | 低 | 中 | 统一审查 |
| 示例过时 | 低 | 低 | 自动化测试 |
| 用户理解困难 | 中 | 中 | 用户测试 |

---

## 里程碑和验收标准

### Milestone 1: v4.1.0 (Week 2)
**目标**: 外部技能动态加载

**验收标准**:
- [ ] 可以执行 superpowers/gstack/omx 技能
- [ ] 安全审计通过
- [ ] 测试覆盖率 >80%
- [ ] 文档完整

### Milestone 2: v4.2.0 (Week 3)
**目标**: 架构一致性

**验收标准**:
- [ ] 架构文档完整
- [ ] 配置合并规则明确
- [ ] 无重复抽象
- [ ] 所有测试通过

### Milestone 3: v4.3.0 (Week 4)
**目标**: 路由准确率 90%+

**验收标准**:
- [ ] 准确率 >= 90%
- [ ] 有用户反馈机制
- [ ] 有基准测试数据
- [ ] 文档完整

### Milestone 4: v5.0.0 (Week 5)
**目标**: 哲学文档完善

**验收标准**:
- [ ] README 愿景导向
- [ ] 角色导向文档完整
- [ ] 快速入门可用
- [ ] 贡献者指南完整

---

## 风险管理

### 高风险项

1. **外部技能执行复杂度**
   - 风险: 工作流执行比预期复杂
   - 缓解: 分阶段实现，先支持简单工作流

2. **破坏向后兼容**
   - 风险: 架构重构破坏现有功能
   - 缓解: 增量重构，保留旧 API

3. **准确率不达标**
   - 风险: 优化后仍达不到 90%
   - 缓解: 多个改进方向并行

### 依赖关系

```
Phase 1 (外部技能) ← 独立，可并行
Phase 2 (架构) ← 独立，可并行
Phase 3 (准确率) ← 依赖 Phase 2 (需要统一架构)
Phase 4 (文档) ← 可并行，但最好在架构稳定后
```

**建议执行顺序**:
1. Week 1-2: Phase 1 (外部技能) + Phase 2 (架构) 并行
2. Week 3: Phase 3 (准确率)
3. Week 4: Phase 4 (文档)

---

## 成功指标

### 定量指标

| 指标 | 当前 | 目标 | 测量方法 |
|------|------|------|----------|
| 路由准确率 | 85% | 90%+ | 测试集评估 |
| 外部技能可用性 | 0% | 100% | 可以执行外部技能 |
| 架构一致性 | 60% | 90%+ | 代码审查 |
| 文档完整性 | 40% | 90%+ | 文档覆盖 |
| 测试覆盖率 | 82% | 85%+ | pytest cov |

### 定性指标

- [ ] 新用户能在 10 分钟内理解项目愿景
- [ ] 贡献者能快速理解架构
- [ ] 外部技能包可以无缝使用
- [ ] 路由结果准确可靠
- [ ] 代码易于维护和扩展

---

## 下一步行动

### 立即开始 (Week 1, Day 1)

1. **创建改进分支**
   ```bash
   git checkout -b improvement/v4.1-external-skills
   ```

2. **设置任务追踪**
   ```bash
   # 查看任务列表
   vibe tasks list

   # 开始第一个任务
   vibe tasks start 1
   ```

3. **开始 Phase 1, Step 1.1**
   - 创建 `src/vibesop/core/skills/executor.py`
   - 定义 `ExternalSkillExecutor` 接口
   - 编写单元测试

### 每周检查

- **Monday**: 规划本周任务
- **Wednesday**: 中期检查，调整计划
- **Friday**: 周总结，更新进度

### 里程碑评审

- **Week 2 End**: v4.1.0 评审
- **Week 3 End**: v4.2.0 评审
- **Week 4 End**: v4.3.0 评审
- **Week 5 End**: v5.0.0 评审

---

## 附录

### A. 相关文档

- [深度审查报告](DEEP_REVIEW_REPORT_V2.md)
- [项目定位](POSITIONING.md)
- [核心原则](PRINCIPLES.md)
- [架构概览](architecture/README.md)

### B. 参考资料

- [SKILL.md 规范](https://github.com/anthropics/claude-code)
- [superpowers 项目](https://github.com/obra/superpowers)
- [gstack 项目](https://github.com/anthropics/gstack)

### C. 联系方式

- 项目负责人: @huchen
- Issue: https://github.com/nehcuh/vibesop-py/issues
- 讨论: https://github.com/nehcuh/vibesop-py/discussions

---

**文档版本**: 1.0.0
**最后更新**: 2026-04-18
**状态**: ✅ 已批准，准备执行
