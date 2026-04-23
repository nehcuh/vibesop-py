# VibeSOP Agent Runtime 层与平台适配优化计划

> **Status**: Draft  
> **Date**: 2026-04-23  
> **Based on**: 平台 Hooks 能力调研 + version_05.md + skillos-productization.md  
> **Theme**: 补齐 "意图识别 → 技能匹配 → 自动加载执行" 的最后闭环  
> **Scope**: v4.3 → v4.4

---

## 1. 问题定义

### 1.1 核心断层

当前架构实现了强大的**路由引擎**（UnifiedRouter）和**编排引擎**（Orchestration），但 AI Agent（Claude Code / OpenCode / Kimi CLI）**并不知道在何时、如何调用它们**。

```
用户消息: "分析架构并优化性能"
    ↓
[AI Agent 直接回答] ←── 断层在这里！Agent 没有调用 VibeSOP 路由
    ↓
❌ 没有意图识别
❌ 没有技能匹配
❌ 没有加载 skill 内容
❌ 没有多技能编排
```

### 1.2 调研结论（平台能力差异）

| 平台 | Pre-Message Hook | System Prompt 修改 | Pre-Tool Hook | 推荐策略 |
|------|------------------|-------------------|---------------|----------|
| **Claude Code** | ✅ UserPromptSubmit（可 block + 注入 additionalContext） | ⚠️ 间接（CLAUDE.md + additionalContext） | ✅ PreToolUse | **Hooks + 提示词混合** |
| **OpenCode** | ✅ chat.message | ✅ experimental.chat.system.transform | ✅ tool.execute.before | **Plugin 完整方案** |
| **Kimi CLI** | ❌ 无 | ⚠️ AGENTS.md + skill 元数据 | ❌ 无 | **纯提示词降级** |

### 1.3 优化原则

1. **平台优先**：根据平台能力上限设计方案，不假设不存在的能力
2. **渐进降级**：Claude Code → OpenCode → Kimi CLI，能力递减但体验连贯
3. **透明可控**：用户始终能看到决策过程，能干预、能关闭
4. **复用现有**：不重复造轮子，基于已有 `AgentRouter` + `OrchestrationResult` 构建

---

## 2. 架构设计：Agent Runtime 层

在现有 `AgentRouter` 之上，新增四个模块组成 **Agent Runtime**：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AI Agent Platform                             │
│  (Claude Code / OpenCode / Kimi CLI)                                │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼───────┐  ┌────────▼────────┐  ┌──────▼──────┐
│ Claude Code   │  │   OpenCode      │  │  Kimi CLI   │
│ Adapter       │  │   Plugin        │  │  Prompt     │
│ (Hooks)       │  │   (TypeScript)  │  │  (AGENTS.md)│
└───────┬───────┘  └────────┬────────┘  └──────┬──────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                     AgentRuntime (NEW)                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │IntentInterceptor│ SkillInjector │ DecisionPresenter│PlanExecutor│ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘ │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│              Existing Infrastructure (Reused)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ AgentRouter  │  │ UnifiedRouter│  │Orchestration │               │
│  │ .route()     │  │ .orchestrate()│  │ .build_plan()│               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 模块设计

### 3.1 IntentInterceptor（意图拦截器）

**职责**：在每次用户消息到达时，决定是否触发 VibeSOP 路由。

```python
# src/vibesop/agent/runtime/intent_interceptor.py

class IntentInterceptor:
    """Intercept user messages and trigger skill routing when appropriate.
    
    Platform-specific implementations:
    - Claude Code: UserPromptSubmit hook calls this
    - OpenCode: chat.message plugin hook calls this  
    - Kimi CLI: System prompt instructs AI to self-trigger
    """
    
    def should_intercept(self, query: str, context: InterceptionContext) -> InterceptionDecision:
        """Decide whether to intercept this message for skill routing.
        
        Returns:
            InterceptionDecision with:
            - should_route: bool
            - reason: str
            - suggested_mode: "single" | "orchestrate" | "none"
        """
        # 1. 短查询快速放行（避免过度路由）
        if len(query.strip()) < 10:
            return InterceptionDecision(should_route=False, reason="Too short")
        
        # 2. 元查询放行（用户问关于 VibeSOP 本身的问题）
        if self._is_meta_query(query):
            return InterceptionDecision(should_route=False, reason="Meta query")
        
        # 3. 显式技能调用（如 /review）→ 直接路由
        if self._has_explicit_skill_override(query):
            return InterceptionDecision(should_route=True, mode="single", reason="Explicit override")
        
        # 4. 默认：建议 orchestrate（让下游决定是单技能还是多技能）
        return InterceptionDecision(should_route=True, mode="orchestrate", reason="Default")
    
    def _is_meta_query(self, query: str) -> bool:
        """检测用户是否在问关于 VibeSOP 系统本身的问题。"""
        meta_patterns = [
            r"vibe\s+(route|skill|config)",
            r"为什么.*路由",
            r"技能.*(怎么|如何|为什么)",
            r"routing.*(work|how)",
        ]
        return any(re.search(p, query, re.I) for p in meta_patterns)
```

**平台适配**：

| 平台 | 触发方式 | 实现 |
|------|----------|------|
| Claude Code | `UserPromptSubmit` hook | Shell script 调用 `vibe route --auto "<query>"` |
| OpenCode | `chat.message` plugin | TypeScript plugin 直接调用 AgentRouter API |
| Kimi CLI | System prompt 指令 | AGENTS.md 中写入 "收到非平凡任务时先调用 vibe route" |

---

### 3.2 SkillInjector（技能注入器）

**职责**：路由成功后，将 skill 内容注入 AI 的当前上下文。

```python
# src/vibesop/agent/runtime/skill_injector.py

class SkillInjector:
    """Inject matched skill content into agent context.
    
    Platform-specific injection methods:
    - Claude Code: additionalContext via hook JSON output
    - OpenCode: output.system.push() in system.transform hook
    - Kimi CLI: Cannot inject → AI must ReadFile skill content
    """
    
    def inject_single_skill(
        self,
        skill_id: str,
        platform: PlatformType,
    ) -> InjectionResult:
        """Inject a single skill's content."""
        skill_content = self._load_skill_content(skill_id)
        
        if platform == PlatformType.CLAUDE_CODE:
            # Return JSON for UserPromptSubmit hook to inject as additionalContext
            return InjectionResult(
                method="additionalContext",
                payload={"additionalContext": f"\n\n[ACTIVE SKILL: {skill_id}]\n{skill_content[:2000]}\n"},
            )
        
        elif platform == PlatformType.OPENCODE:
            # Return system prompt fragment for experimental.chat.system.transform
            return InjectionResult(
                method="systemPrompt",
                payload=f"<skill-context id='{skill_id}'>\n{skill_content}\n</skill-context>",
            )
        
        elif platform == PlatformType.KIMI_CLI:
            # Kimi cannot inject → return ReadFile instruction
            return InjectionResult(
                method="instruction",
                payload=f"请先读取 ~/.kimi/skills/{skill_id.replace('/', '-')}/SKILL.md，然后按照 skill 指导执行。",
            )
    
    def inject_execution_plan(
        self,
        plan: ExecutionPlan,
        platform: PlatformType,
    ) -> InjectionResult:
        """Inject a multi-step execution plan."""
        plan_summary = self._format_plan(plan)
        
        if platform == PlatformType.CLAUDE_CODE:
            return InjectionResult(
                method="additionalContext",
                payload={"additionalContext": f"\n\n[EXECUTION PLAN]\n{plan_summary}\n"},
            )
        
        elif platform == PlatformType.OPENCODE:
            return InjectionResult(
                method="systemPrompt",
                payload=f"<execution-plan>\n{plan_summary}\n</execution-plan>",
            )
        
        elif platform == PlatformType.KIMI_CLI:
            # 生成逐步指令
            steps_instruction = "\n".join(
                f"步骤 {i+1}: 使用 {step.skill_id} skill 完成「{step.intent}」"
                for i, step in enumerate(plan.steps)
            )
            return InjectionResult(
                method="instruction",
                payload=f"任务已分解为以下步骤，请按顺序执行：\n{steps_instruction}",
            )
```

---

### 3.3 DecisionPresenter（决策展示器）

**职责**：让路由决策过程对用户透明——展示匹配结果、候选技能、选择理由。

```python
# src/vibesop/agent/runtime/decision_presenter.py

class DecisionPresenter:
    """Present routing decisions to user with transparency and control."""
    
    def present_single_result(
        self,
        result: RoutingResult,
        platform: PlatformType,
    ) -> PresentResult:
        """Present single-skill routing result."""
        
        lines = [
            f"🎯 VibeSOP 路由结果",
            f"",
            f"匹配技能: {result.primary.skill_id}",
            f"置信度: {result.primary.confidence:.0%}",
            f"匹配层: {result.primary.layer.value}",
        ]
        
        # 展示候选（让用户知道有其他选择）
        if result.alternatives:
            lines.extend(["", "其他候选:"])
            for alt in result.alternatives[:3]:
                lines.append(f"  • {alt.skill_id} ({alt.confidence:.0%}) — {alt.description or 'No description'}")
        
        # 展示优化层影响（session stickiness, habit boost 等）
        if result.primary.metadata.get("session_boost"):
            lines.append(f"💡 会话粘性提升已应用")
        if result.primary.metadata.get("habit_boost"):
            lines.append(f"💡 习惯学习提升已应用（该查询模式已出现 3+ 次）")
        
        return PresentResult(
            message="\n".join(lines),
            actions=["accept", "switch_alternative", "skip_skill"],
        )
    
    def present_orchestration_result(
        self,
        result: OrchestrationResult,
        platform: PlatformType,
    ) -> PresentResult:
        """Present multi-intent orchestration result."""
        
        plan = result.execution_plan
        lines = [
            f"🔀 VibeSOP 检测到多意图",
            f"",
            f"原请求: {plan.original_query}",
            f"检测到 {len(plan.steps)} 个子任务:",
        ]
        
        for i, step in enumerate(plan.steps, 1):
            deps = f" (依赖步骤 {step.dependencies})" if step.dependencies else ""
            parallel = " [可并行]" if step.can_parallel and not step.dependencies else ""
            lines.append(f"  {i}. {step.skill_id} — {step.intent}{deps}{parallel}")
        
        lines.extend([
            f"",
            f"执行策略: {plan.execution_mode.value}",
        ])
        
        if result.single_fallback:
            lines.append(f"单技能备选: {result.single_fallback.skill_id} ({result.single_fallback.confidence:.0%})")
        
        return PresentResult(
            message="\n".join(lines),
            actions=["execute_plan", "use_single", "edit_plan", "skip_all"],
        )
```

**展示时机**：
- Claude Code: `UserPromptSubmit` hook 返回 `systemMessage` 字段展示在 UI
- OpenCode: plugin 调用 `client.tui.showToast()` 或注入消息
- Kimi CLI: 由于无法拦截，展示在 `vibe route` CLI 输出中

---

### 3.4 PlanExecutor（计划执行器）—— 长期架构

**职责**：让 AI Agent 按 ExecutionPlan 实际执行各步骤。

**现状**：当前 `ExecutionPlan` 只被生成，**没有被执行**。AI Agent 不会自动按 plan 的步骤调用不同 skill。

**方案对比**：

| 方案 | 说明 | 可行性 |
|------|------|--------|
| A. AI 自主执行 | 在 system prompt / additionalContext 中注入 plan，让 AI 自行按步骤执行 | ✅ 所有平台可用 |
| B. Hook 驱动执行 | 用 PreToolUse / tool.execute.before hook 强制控制执行流程 | ⚠️ 仅 Claude/OpenCode |
| C. 子 Agent 分配 | 为每个 plan step  spawn 一个 subagent | ⚠️ 平台需支持 subagent |

**推荐方案 A（通用降级）+ B/C（平台增强）**：

```python
class PlanExecutor:
    """Execute an ExecutionPlan by guiding the AI through each step.
    
    Universal approach (works on all platforms):
    - Inject detailed step-by-step instructions into context
    - AI follows instructions autonomously
    
    Enhanced approach (Claude Code / OpenCode):
    - Use hooks to enforce step boundaries
    - Track progress and inject step transitions
    """
    
    def build_execution_prompt(self, plan: ExecutionPlan) -> str:
        """Build a prompt that guides AI through plan execution."""
        
        lines = [
            f"# 执行计划: {plan.original_query}",
            f"",
            f"你必须按以下步骤顺序执行。每完成一步，报告结果后再继续下一步。",
            f"",
        ]
        
        # 按 parallel groups 组织
        groups = plan.get_parallel_groups()
        for group_num, group in enumerate(groups, 1):
            if len(group) == 1:
                step = group[0]
                lines.extend([
                    f"## 步骤 {step.step_number}: {step.intent}",
                    f"- 使用 skill: {step.skill_id}",
                    f"- 任务: {step.input_query}",
                    f"- 输出变量: {step.output_as}",
                    f"",
                    f"完成此步骤后，请明确声明：『步骤 {step.step_number} 完成，输出已保存到 {step.output_as}』",
                    f"",
                ])
            else:
                lines.append(f"## 并行步骤组 {group_num}")
                lines.append(f"以下步骤可以并行执行：")
                for step in group:
                    lines.extend([
                        f"",
                        f"### 步骤 {step.step_number}: {step.intent}",
                        f"- 使用 skill: {step.skill_id}",
                        f"- 任务: {step.input_query}",
                    ])
                lines.extend([
                    f"",
                    f"所有并行步骤完成后，请明确声明：『并行组 {group_num} 全部完成』",
                    f"",
                ])
        
        lines.extend([
            f"",
            f"---",
            f"执行规则:",
            f"1. 严格按照步骤顺序执行",
            f"2. 每步必须读取对应的 SKILL.md",
            f"3. 每步完成后明确报告",
            f"4. 如果某步失败，报告错误并询问是否继续",
        ])
        
        return "\n".join(lines)
```

---

## 4. 平台适配详细方案

### 4.1 Claude Code（Hooks + 提示词混合方案）

**利用能力**：
- `UserPromptSubmit` hook：触发路由 + 注入 additionalContext
- `PreToolUse` hook：跟踪工具使用（已有实现）
- `CLAUDE.md` + `rules/`：静态 system prompt 扩展

**适配实现**：

```json
// .claude/settings.json (由 vibe build claude-code 生成)
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/vibesop-route.sh",
            "timeout": 3
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash|Read|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/vibesop-track.sh",
            "timeout": 1
          }
        ]
      }
    ]
  }
}
```

```bash
# ~/.claude/hooks/vibesop-route.sh
#!/bin/bash
# UserPromptSubmit hook for VibeSOP routing

INPUT=$(cat)
QUERY=$(echo "$INPUT" | jq -r '.user_prompt // empty')

# Skip if no query or too short
if [ -z "$QUERY" ] || [ "${#QUERY}" -lt 10 ]; then
    echo '{}'
    exit 0
fi

# Call VibeSOP orchestrate (returns JSON)
RESULT=$(cd "$CLAUDE_PROJECT_DIR" && vibe route --auto --json "$QUERY" 2>/dev/null)

if [ -z "$RESULT" ]; then
    echo '{}'
    exit 0
fi

# Check if multi-intent detected
MODE=$(echo "$RESULT" | jq -r '.mode // "single"')
PRIMARY=$(echo "$RESULT" | jq -r '.primary.skill_id // empty')

if [ "$MODE" = "orchestrated" ]; then
    # Multi-intent: inject execution plan
    PLAN=$(echo "$RESULT" | jq -r '.execution_plan // empty')
    echo "{\"systemMessage\": \"🔀 VibeSOP 检测到多意图，已生成执行计划。请按注入的上下文执行。\", \"hookSpecificOutput\": {\"additionalContext\": \"[VibeSOP Execution Plan]\\n$PLAN\"}}"
elif [ -n "$PRIMARY" ] && [ "$PRIMARY" != "fallback-llm" ]; then
    # Single skill: inject skill content
    SKILL_CONTENT=$(vibe skills read "$PRIMARY" 2>/dev/null | head -c 3000)
    echo "{\"systemMessage\": \"🎯 VibeSOP 路由结果: $PRIMARY\", \"hookSpecificOutput\": {\"additionalContext\": \"[ACTIVE SKILL: $PRIMARY]\\n$SKILL_CONTENT\"}}"
else
    # Fallback: still show routing info
    echo "{\"systemMessage\": \"🤖 VibeSOP 未找到匹配技能，将以普通模式继续。\"}"
fi
```

**规则文件更新**（`rules/routing.md.j2`）：

```markdown
## VibeSOP 自动路由规则

当本规则通过 UserPromptSubmit hook 触发时：

1. **如果注入了 [ACTIVE SKILL: xxx]** → 你必须：
   - 读取该 skill 的 SKILL.md
   - 严格遵循 skill 的工作流程
   - 不得跳过任何步骤

2. **如果注入了 [EXECUTION PLAN]** → 你必须：
   - 按照计划中的步骤顺序执行
   - 每步完成后明确报告
   - 如果某步依赖前一步输出，等待前一步完成

3. **如果没有注入任何内容** → 正常处理用户请求
```

---

### 4.2 OpenCode（Plugin 完整方案）

**利用能力**：
- `experimental.chat.system.transform`：直接修改 system prompt
- `chat.message`：拦截消息
- 完整 TypeScript SDK

**适配实现**：

```typescript
// .opencode/plugin/vibesop/index.ts
import type { Plugin } from "@opencode-ai/plugin";
import { AgentRouter } from "vibesop/agent";  // 或调用 CLI

export default {
  "experimental.chat.system.transform": async (input, output) => {
    // 在每次对话前，检查是否有激活的 skill
    const activeSkill = await getActiveSkill(input.sessionID);
    if (activeSkill) {
      const skillContent = await loadSkillContent(activeSkill);
      output.system.push(`<vibesop-skill id="${activeSkill}">\n${skillContent}\n</vibesop-skill>`);
    }
  },
  
  "chat.message": async (input, output) => {
    const query = input.message.text;
    
    // 短查询放行
    if (!query || query.length < 10) return;
    
    // 调用 VibeSOP 路由
    const result = await routeWithVibeSOP(query, input.sessionID);
    
    if (result.mode === "orchestrated") {
      // 多意图：修改 system prompt 注入执行计划
      const planPrompt = buildExecutionPlanPrompt(result.execution_plan);
      output.system.push(`<vibesop-plan>\n${planPrompt}\n</vibesop-plan>`);
      
      // 向用户展示决策
      await output.client.tui.showToast({
        title: "VibeSOP",
        message: `检测到 ${result.execution_plan.steps.length} 个意图，已生成执行计划`,
        variant: "info",
      });
    } else if (result.primary && result.primary.skill_id !== "fallback-llm") {
      // 单技能：标记为激活 skill（system.transform 会在下一轮注入）
      await setActiveSkill(input.sessionID, result.primary.skill_id);
      
      await output.client.tui.showToast({
        title: "VibeSOP",
        message: `已匹配: ${result.primary.skill_id} (${Math.round(result.primary.confidence * 100)}%)`,
        variant: "success",
      });
    }
  },
  
  "tool.execute.before": async (input, output) => {
    // 跟踪工具使用（用于 session context）
    await recordToolUse(input.sessionID, input.tool, input.args);
  },
} satisfies Plugin;
```

---

### 4.3 Kimi CLI（纯提示词降级方案）

**约束**：
- 无 hooks
- 无 system prompt 动态修改
- 有 `AGENTS.md`（项目级静态上下文）
- 有 `~/.kimi/skills/`（skill 目录）

**降级策略**：

#### A. AGENTS.md 注入（静态规则）

由 `vibe build kimi-cli` 生成项目级 `AGENTS.md`：

```markdown
# VibeSOP Agent 指令

## 核心规则

收到任何非平凡的用户请求时，你必须：

1. **先路由**：运行 `vibe route "<用户请求>"` 获取技能推荐
2. **再加载**：读取推荐 skill 的 SKILL.md
3. **后执行**：严格按照 skill 指导执行

## 判断标准

以下情况**必须**执行路由：
- 用户请求涉及代码审查、调试、优化、架构设计
- 用户请求包含多个子任务（如"分析并优化"）
- 用户请求长度超过 20 个字符

以下情况**可以跳过**路由：
- 简单的问候或确认（"你好"、"ok"）
- 关于 VibeSOP 系统本身的元问题
- 长度少于 10 个字符的查询

## 多意图处理

如果 `vibe route` 返回多意图执行计划（包含多个步骤），你必须：
- 按步骤顺序执行
- 每步读取对应的 SKILL.md
- 每步完成后明确报告进度
- 独立步骤可以并行处理

## 可用技能

{{ skills_list }}
```

#### B. CLI 输出增强（决策透明化）

由于 Kimi CLI 无法拦截消息，所有路由交互发生在 `vibe route` CLI 命令中：

```bash
$ vibe route "分析架构并优化性能"

🔀 多意图检测 (置信度: 94%)

原请求: 分析架构并优化性能

检测到的子任务:
  1. 📐 架构分析 → superpowers-architect (92%)
  2. ⚡ 性能优化 → superpowers-optimize (89%)

执行策略: 串行（步骤2依赖步骤1的输出）

单技能备选: superpowers-architect (87%)

请选择:
  [1] 执行完整计划
  [2] 使用单技能
  [3] 查看步骤详情
  [4] 跳过技能，直接处理
> 1

✅ 已选择执行完整计划

请复制以下指令给 Kimi：

---
# 执行计划: 分析架构并优化性能

你必须按以下步骤执行：

## 步骤 1: 架构分析
- 使用 skill: superpowers-architect
- 任务: 分析当前项目架构
- 完成后声明: 「步骤1完成」

## 步骤 2: 性能优化
- 使用 skill: superpowers-optimize
- 任务: 基于架构分析结果优化性能
- 依赖: 步骤1的输出
- 完成后声明: 「步骤2完成」

执行规则:
1. 每步必须读取对应的 SKILL.md
2. 严格按照 skill 工作流程
3. 每步完成后明确报告
---
```

#### C. README 强化（已有实现增强）

在 `KimiCliAdapter._generate_readme()` 中已有的 MANDATORY Workflow 基础上，增加：
- 多意图检测示例
- 决策透明化说明
- 降级到普通 Agent 的说明

---

## 5. 实施计划

### Phase 1: Agent Runtime 核心（Week 1-2）

| 天数 | 任务 | 产出 |
|------|------|------|
| Day 1-2 | IntentInterceptor 实现 + 测试 | `src/vibesop/agent/runtime/intent_interceptor.py` |
| Day 3-4 | SkillInjector 实现 + 平台适配逻辑 | `src/vibesop/agent/runtime/skill_injector.py` |
| Day 5-6 | DecisionPresenter 实现 + 格式化输出 | `src/vibesop/agent/runtime/decision_presenter.py` |
| Day 7-8 | PlanExecutor（方案 A：通用执行提示） | `src/vibesop/agent/runtime/plan_executor.py` |
| Day 9-10 | AgentRuntime 整合 + 单元测试 | `src/vibesop/agent/runtime/__init__.py` |

### Phase 2: 平台适配（Week 3-4）

| 天数 | 任务 | 产出 |
|------|------|------|
| Day 11-12 | Claude Code hook 模板生成 | `templates/claude-code/hooks/vibesop-route.sh.j2` |
| Day 13-14 | Claude Code `rules/routing.md.j2` 更新 | 注入 skill 后 AI 行为规则 |
| Day 15-17 | OpenCode plugin 模板 | `templates/opencode/plugin/vibesop/` |
| Day 18-19 | Kimi CLI AGENTS.md 生成 + README 增强 | `KimiCliAdapter` 更新 |
| Day 20 | 跨平台一致性测试 | 验证三种平台输出一致性 |

### Phase 3: 集成验证（Week 5）

| 天数 | 任务 | 产出 |
|------|------|------|
| Day 21-22 | `vibe build` 命令更新（支持 --platform=all） | CLI 集成 |
| Day 23-24 | E2E 测试：三种平台的完整流程 | 测试报告 |
| Day 25 | 文档更新 + 发布准备 | 用户指南 |

---

## 6. 关键设计决策

### 6.1 IntentInterceptor 的保守性

**决策**：默认只拦截长度 >= 10 的非元查询。

**理由**：
- 避免过度干扰简单对话
- 降低误路由概率
- 用户可通过显式 `/skill` 或 `vibe route` 主动触发

### 6.2 Skill 注入 vs 指令注入

| 平台 | 注入方式 | 理由 |
|------|----------|------|
| Claude Code | additionalContext | 官方推荐方式，不影响原始 system prompt |
| OpenCode | system.transform | 最灵活，可直接修改 prompt |
| Kimi CLI | 指令（让 AI ReadFile） | 唯一可行方式 |

### 6.3 多技能编排的执行策略

**当前限制**：无法真正强制 AI 按 plan 执行，只能"强烈建议"。

**缓解**：
1. 在注入的 prompt 中使用明确的步骤编号和完成标记
2. 在 Claude Code / OpenCode 中，用 PostToolUse hook 检测步骤完成
3. 未来探索子 Agent 分配（平台支持后）

---

## 7. 与现有计划的对齐

| 现有计划 | 本计划补充 |
|----------|-----------|
| skillos-productization.md (P0 FALLBACK_LLM) | Agent Runtime 在所有平台统一处理 fallback |
| skillos-productization.md (P2 orchestrate 可视化) | DecisionPresenter 在 Agent 侧展示决策 |
| v50-user-experience-closure.md (Task 2 编排交互) | PlanExecutor 让 plan 真正被执行 |
| v50-user-experience-closure.md (Task 1 负向透明度) | DecisionPresenter 展示候选和拒绝原因 |
| version_05.md v5.0 作用域系统 | IntentInterceptor 的 `_is_meta_query` 等过滤逻辑 |

---

## 8. 验收标准

### 8.1 Claude Code
- [ ] `vibe build claude-code` 生成 hook 脚本和规则
- [ ] 用户输入 "review my code" 时，AI 自动加载 gstack-review skill
- [ ] 多意图请求触发时，AI 收到执行计划并执行
- [ ] `vibe route --explain` 在 CLI 展示决策过程

### 8.2 OpenCode
- [ ] `vibe build opencode` 生成 plugin 模板
- [ ] plugin 安装后，对话自动触发路由
- [ ] system prompt 中动态注入 skill 内容
- [ ] 多意图时展示 toast 通知

### 8.3 Kimi CLI
- [ ] `vibe build kimi-cli` 生成强化版 AGENTS.md
- [ ] AGENTS.md 中包含完整的自动路由规则
- [ ] `vibe route` CLI 输出包含可复制的执行指令
- [ ] 无 hooks 情况下，AI 通过 system prompt 自觉遵守路由规则

### 8.4 跨平台一致性
- [ ] 同一查询在三个平台路由到相同 skill（置信度差异 < 5%）
- [ ] 决策展示格式一致（技能名称、置信度、候选列表）
- [ ] Fallback 行为一致（透明降级 + 建议）

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Claude Code hook 超时（3秒） | 高 | 路由结果缓存；使用 `--quick` 模式跳过 AI Triage |
| OpenCode experimental API 变更 | 中 | 封装抽象层，API 变更时只需改 adapter |
| Kimi CLI AI 不遵守 AGENTS.md | 高 | 在 CLI 输出中强化指令；定期评估遵守率 |
| Skill 内容过长（>4000 tokens） | 中 | 注入时截断到 2000 tokens；提供 ReadFile 指引 |
| 多意图检测误触发 | 中 | IntentInterceptor 保守策略；用户可关闭自动路由 |

---

## 10. 立即启动项

1. **Day 1**：实现 IntentInterceptor + should_intercept 核心逻辑
2. **Day 2**：更新 `vibe build claude-code` 生成 hook 脚本
3. **Day 3**：更新 KimiCliAdapter 生成强化版 AGENTS.md
4. **Day 4**：编写跨平台 E2E 测试脚本（模拟三种平台的用户流程）

---

*Plan written based on platform hooks research + existing architecture*
