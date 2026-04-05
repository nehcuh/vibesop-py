# VibeSOP 架构整合计划

> **目标**: 从"检测外部工具"转向"真正整合外部工具"，从"技术堆砌"转向"哲学驱动"

## 现状诊断

### 已完成（v3.0）
- ✅ UnifiedRouter - 统一路由入口
- ✅ ExternalSkillLoader - 外部技能发现与安全审计
- ✅ SkillSecurityAuditor - 技能安全检查
- ✅ ConfigManager - 统一配置管理
- ✅ PRINCIPLES.md - 项目原则文档

### 核心问题
1. **ExternalSkillLoader 与 SkillLoader 未整合** - 外部技能只能被发现，无法被执行
2. **技能执行鸿沟** - superpowers/gstack 技能无法真正加载和执行
3. **Autoresearch 理念缺失** - 没有"研究即代码"的自我改进循环

## 改进计划

### Phase 1: 打通外部技能执行通道（核心）

**目标**: 让 `execute_skill("superpowers/tdd")` 真正工作

**任务**:
1. 整合 ExternalSkillLoader → SkillLoader
   - 让 SkillLoader 能够加载 ~/.claude/skills/ 下的技能
   - 安全审计通过的技能自动加入可用技能池
   
2. 实现外部 SKILL.md 解析执行
   - 解析 superpowers/gstack 的 SKILL.md 格式
   - 将外部技能映射为内部 PromptSkill/WorkflowSkill
   
3. 添加技能包自动检测与提示
   - 检测已安装的技能包
   - 提示用户可用的外部技能

### Phase 2: Autoresearch 理念落地

**目标**: 实现"研究即代码"的自我改进循环

**任务**:
1. 设计 experiment 记录格式
   - 记录尝试、结果、结论
   - 与现有 memory/ 系统整合
   
2. 实现 Instinct 提取
   - 从实验记录中提取模式
   - 自动生成建议
   
3. 创建 autoresearch 工作流
   - 自动生成假设
   - 执行实验
   - 记录结果

### Phase 3: 验证与完善

**任务**:
1. 编写集成测试
   - 测试外部技能加载执行全流程
   - 测试安全审计机制
   
2. 更新文档
   - 说明外部技能如何使用
   - 提供配置示例

3. 验证 PRINCIPLES.md 落地
   - 检查所有功能是否符合原则
   - 添加原则检查工具

## 实施步骤

### Step 1: 创建整合分支
```bash
git checkout -b feature/external-skill-execution
```

### Step 2: 修改 SkillLoader
添加外部路径支持：
- ~/.claude/skills/
- ~/.config/skills/
- 安全审计通过的外部技能

### Step 3: 实现技能解析适配器
将外部 SKILL.md 转换为内部 Skill 对象

### Step 4: 测试验证
测试 superpowers/tdd 等技能能否真正执行

## 预期成果

1. **用户体验**:
   ```python
   manager = SkillManager()
   # 自动发现并加载 ~/.claude/skills/superpowers/tdd/SKILL.md
   result = await manager.execute_skill("superpowers/tdd")
   ```

2. **哲学落地**:
   - Structure > Prompting: 通过外部 SKILL.md 定义工作流
   - Memory > Intelligence: 实验记录自动沉淀
   - Verification > Confidence: 安全审计强制执行

3. **避免堆砌**:
   - 不是简单复制 superpowers/gstack
   - 而是通过统一接口整合，形成协同效应

## 时间预估

- Phase 1: 2-3 小时
- Phase 2: 4-6 小时
- Phase 3: 2-3 小时

**总计**: 8-12 小时完整实施
