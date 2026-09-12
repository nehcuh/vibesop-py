# BM25 中文召回预检发现（2026-07-29）

> **性质**：预检发现摘录。原文仅存于 Claude 项目记忆（`~/.claude/projects/-Users-huchen-Projects-vibesop-py/memory/project-task-id-bug-and-cross-project.md`，originSession e43d6ad0），仓库内无独立测量 artifact——按 F10「凡被 tracked 文档引用的产物必须在 tracked 路径」原则，摘录入库供 `docs/research-survey.md` §5/附录 B #18 引用。证据等级降为「记忆摘录【文档】」，未复测。

## Finding 3 — BM25 在中文真实 query 上完全失败（原文摘录）

- cmspark 10 个「截图权限」相关 query（同一问题、不同表述：弹窗/权限/授权/批准/录制/屏幕和音频/截图）
- Jaccard ≥ 0.3 配对数 = **0**
- 推论：embedding 是 day 1 主路径，不是 W2.5 兜底；BM25 仅 fallback

## 同批 Finding 1/2（背景）

- Finding 1：task_id 双层 bug（`main.py:724` 未传 task_id + contextvars 跨不了子 agent CLI 进程）→ 修复方向为 task_id 确定性派生
- Finding 2：spans 按 project 完全分散（cmspark 470 真实 spans；「截图权限」问题 17 种表述无法跨项目 recall）

## 引用口径

- 综述 §5「BM25 严格口径：10 个同题异表 query 的 Jaccard≥0.3 配对数 = 0」出处即本文件。
- 「0% 召回」的简写口径见 `docs/task-memory-loop-article.md:179`；设计文档 `2026-07-29-task-memory-product-design.md` 仅有「预检 Finding 3」字样，不含数字。
