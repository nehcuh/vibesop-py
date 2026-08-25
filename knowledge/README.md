# VibeSOP 知识库（cmspark 导出）

为 [cmspark](https://github.com/) 知识库系统生成的 VibeSOP 项目知识导出快照——
导入后可在 cmspark 对话中直接询问关于 VibeSOP 项目的问题。

> 本文件是导入说明，本身**不参与导入**。导入内容是 `vibesop/` 子目录。

## 格式规范（遵循 cmspark 知识文档规范）

每个 `.md` 文件 = 一个知识文档：YAML frontmatter + markdown 正文。

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 文档 id（kebab-case） |
| `description` | 建议 | ≤500 字符，用于列表展示与匹配 |
| `type` | 是 | `domain_knowledge`（本项目知识均为此类） |
| `tags` | 可选 | ≤8 个，辅助检索 |

正文按 `##` 主题分节——cmspark 按 chunk 做 TF-IDF 检索，自包含的小节命中率最高。

## 知识文档清单

| 文件 | 覆盖内容 |
|------|---------|
| `vibesop/vibesop-overview.md` | 定位/愿景/核心概念/技术栈/关键指标 |
| `vibesop/vibesop-install-quickstart.md` | 安装/quickstart/doctor/LLM 配置与降级 |
| `vibesop/vibesop-cli-commands.md` | 60+ 命令分组地图（路由/技能/记忆观测/工作流） |
| `vibesop/vibesop-architecture.md` | 三层架构/目录表/adapter 三模式/SKILL.md v3.0 规范 |
| `vibesop/vibesop-routing.md` | 四层路由漏斗/置信度/会话感知/降级/偏好学习 |
| `vibesop/vibesop-task-memory.md` | recall/trace/instinct/Discovery 队列/跨项目池 |
| `vibesop/vibesop-platforms.md` | 6 平台矩阵/部署命令/触发机制 |
| `vibesop/vibesop-development.md` | uv/pytest/质量链/CI/发布流程 |
| `vibesop/vibesop-faq.md` | 高频问答（LLM key/Windows/隐私/安全/中文） |

## 导入方法（cmspark 侧）

**方式一（推荐）——文件夹导入**：

1. 打开 cmspark 扩展侧边栏 → 知识面板（KnowledgeSubPanel）
2. 点「导入文件夹」按钮，选择本目录下的 `vibesop/` 文件夹
3. companion 会服务端遍历目录、逐个导入并自动生成唯一 id

**方式二——多文件导入**：在知识面板选多个 `.md` 文件导入（面板会顺序导入防止并发 FileReader 竞态）。

导入后：知识文档进入全局知识目录（`global/`），对话中通过知识选择 UI 按需激活；
cmspark 会对 query 做 chunk 级 TF-IDF 检索，把命中的段落注入上下文。

## 维护约定

- 本目录是**导出快照**（point-in-time），不参与项目文档版本一致性检查
  （`scripts/check_doc_versions.py` 的 SKIP_DIRS 已豁免 `knowledge/`）
- 内容以 8.1.0 为基准。大版本演进后重新生成，而不是在此堆补丁
- 修改格式需对照 cmspark 源码规范：`companion/src/skills/skill-engine.ts`
  的 `allowlistKnowledgeFrontmatter()`（frontmatter 白名单）与
  `importKnowledge()`（导入路径）
