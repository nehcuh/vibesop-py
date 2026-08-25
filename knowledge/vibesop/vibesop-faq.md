---
name: vibesop-faq
description: VibeSOP 常见问答 — 需要单独的 LLM key 吗、Windows 支持吗、和 Claude Code 原生 skills 的区别、数据隐私、外部技能安全、技能怎么写、性能
type: domain_knowledge
tags:
  - vibesop
  - faq
  - privacy
  - security
---

# VibeSOP 常见问答（FAQ）

## 需要 LLM API key 吗？

**生产使用强烈建议**。VibeSOP 是 CLI 子进程，不能复用宿主 Agent（如 Claude Code）内部的 LLM。支持 Anthropic Claude、OpenAI 系（GPT/Kimi）或本地 Ollama。无 LLM 时降级为关键词/TF-IDF 匹配——短查询可用，长/模糊/中文表述命中率明显下降。

## Windows 支持吗？

一等公民支持。CI 在 Ubuntu + Windows 双平台 × Python 3.12/3.13 矩阵上跑全量测试，Windows 是 required gate（红灯阻塞发布）。Windows 特有坑（GBK 编码、盘符冒号、文件锁句柄冲突）都已在产品内处理。

## 和 Claude Code 原生 skills / .cursorrules 有什么区别？

- **跨平台**：一份 SKILL.md 服务 6 个平台（Claude Code/Grok Build/Kimi CLI/Pi/Cursor/OpenCode）+ 任何 SKILL.md 工具，平台差异由 adapter 消化
- **路由**：不是被动等 Agent 发现，而是语义级 query→skill 匹配（四层漏斗：显式语法→关键词→语义索引→LLM 分诊）
- **生命周期管理**：使用率/成功率/新鲜度评分、智能降级、过时检测、交互式清理——技能被管理而非无限堆积
- **任务记忆**：recall 语义召回过往轨迹、instinct 工具序列挖掘、跨项目池复用，这些原生 skills 生态没有

## 数据隐私怎么样？

全部本地存储：全局 `~/.vibe/`、项目 `.vibe/`。无云端依赖、无遥测上报。未命中查询只存哈希计数（本地匿名）。跨项目召回需要显式把项目加入可信池（`vibe pool add`）。

## 安装外部技能安全吗？

`vibe install` 每次自动跑安全扫描：prompt injection 检测、command injection 检测、role hijacking 检测、privilege escalation 检测、path traversal 防护。另有技能包信任名单（`vibe trust`）管理。

## 技能怎么写？

SKILL.md v3.0 规范（`docs/skill-format-spec-v3.md`）：YAML frontmatter + markdown 正文，29 个字段，`SkillSpec` Pydantic model 定义，`vibe spec` 命令族校验。也可以不手写——`vibe skill scan-candidates` 从你的重复任务聚类生成候选，promote 成草稿再改；`vibe skill-craft` 从会话历史提炼。

## 路由准确率/性能如何？

路由准确率约 94%（e2e 路由套件实测口径），性能约 44 QPS（目标 40+）。路由报告展示每层耗时（如语义索引毫秒级、LLM 分诊秒级），慢在哪一层一目了然。

## 复杂任务怎么处理？

两条路：`vibe orchestrate` 把多意图 query 分解为串行/分组执行计划（7 种编排模式：SEQUENTIAL/PARALLEL/FAN_OUT/ADVERSARIAL/LOOP_UNTIL_DRY/TOURNAMENT/PROMPT_CHAIN）；或 `vibe prompt-chain generate` 输出 7 个分阶段提示词文件，独立喂给编程 Agent，再用 `prompt-chain validate` 在 Linux 容器里跑端到端验证。

## 支持中文吗？

原生支持。示例query、文档、错误信息双语；中文语义路由是主要场景之一（embedding 检索保证中文召回，BM25 在中文上基本无效）。

## 在哪看可视化？

`vibe dashboard` 启动 Web 面板：路由统计、技能生态快照、任务轨迹回放、Discovery 候选队列。
