---
name: vibesop-routing
description: VibeSOP 路由引擎 — 四层路由漏斗（EXPLICIT/KEYWORD/SEMANTIC_INDEX/AI_TRIAGE）、置信度与确认流、会话感知重路由、无 LLM 降级、偏好学习与主动发现
type: domain_knowledge
tags:
  - vibesop
  - routing
  - semantic-matching
---

# VibeSOP 路由引擎

## 路由是什么

`vibe route "<query>"` 把自然语言 query（中英文均可）匹配到最佳技能，输出路由决策报告：选中技能、置信度、各层执行轨迹、备选技能。这是 VibeSOP 的核心入口。

## 四层路由漏斗

路由按层依次尝试，先命中先赢：

1. **EXPLICIT**——`@skill_id` 显式语法直接指定技能，零歧义
2. **KEYWORD**——关键词层（含会话结束信号、守卫技能等显式信号检测）
3. **SEMANTIC_INDEX**——本地语义索引（sentence-transformers embedding 余弦相似度）；环境缺 embedding 模型时跳过
4. **AI_TRIAGE**——LLM 意图分诊（多维度理解复杂/模糊 query），最终兜底给出高置信选择

每层的命中与耗时都会展示（如 `SEMANTIC_INDEX (16.0ms)` / `AI_TRIAGE (1398.0ms)`），可观测、可解释。

## 置信度与确认流

- 路由报告展示置信度百分比；高置信直接执行，低置信会给出备选排名表（Rank / Skill ID / Description / Confidence / Layer）
- `--yes`（`-y`）临时跳过确认
- 用户显式指定的技能不受自动降级影响

## 会话感知路由（session-aware）

- 会话智能追踪**默认开启**（`routing.session_aware: true`），自动记录工具使用历史，支持多轮对话上下文重路由
- 关闭途径：`vibe config set routing.session_aware false`（三个理由：性能零开销、隐私不记录、控制完全自决）
- `vibe session check-reroute` 检测当前会话是否该换技能

## 智能降级（v5.2+）

技能质量不达标时自动降权直至禁用：使用率、成功率、新鲜度等多维评分，阈值全部可配置。这让技能生态保持健康——技能被管理，而不是无限堆积。

## 偏好学习

```bash
vibe feedback record "debug this" "systematic-debugging" --correct
# 下次同 query 置信度提升
```

反馈环（v8.0）还包括：未命中查询本地匿名计数（仅存哈希），重复未命中触发搜索安装建议；`vibe skills suggestions` 统一收件；`vibe skills distill` 一键蒸馏为项目级技能（LLM 生成 + 全文审定 + 安全审计）。

## 主动发现（DISCOVER）

每次路由后自动推荐尚未使用但匹配当前工作流的技能，标记 `[DISCOVER]`，让用户持续发现生态中适合自己的技能。

## 无 LLM 降级模式

没配 LLM key 时退化为关键词/TF-IDF 匹配：短查询尚可，长查询与模糊中文表述命中率显著下降。生产使用建议配 Anthropic/OpenAI key 或本地 Ollama。

## 观测与调试

- `vibe route-stats`——路由统计
- `vibe trace metrics / replay`——span 级观测与回放
- `vibe doctor`——环境体检（LLM/hooks/平台）
- 路由 span 会写本地 traces，供任务记忆环（recall）与 dashboard 复用
