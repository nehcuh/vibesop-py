# Health 轮「未知 ≠ 错误」裁决（记忆摘录）

> **性质**：记忆摘录入库。原文仅存于 Claude 项目记忆（`~/.claude/projects/-Users-huchen-Projects-vibesop-py/memory/feedback-health-round-unknown-not-false.md`，originSession a1d207ac），仓库内无独立测量 artifact——按 F10「凡被 tracked 文档引用的产物必须在 tracked 路径」原则，摘录入库供 `docs/research/research-survey.md` §2 工具 #3 引用。**发生日期未在记忆内记录**（记忆条目记录于 2026-09-09）；证据等级「记忆摘录【文档】」，未复测。

## 裁决内容（原文摘录）

经验体检（health-learning）修复轮中，主控驳回「缺失 `was_correct` 默认 `False`」的防膨胀方案：未知不等于错误，默认 False 会压低评分并触发误弃用（false deprecation）。

- 未知是「无证据」，既不能计 True 也不能计 False
- 后续 health 轮次数据入口采用严格输入语义：缺失/非 bool 一律排除在已确认统计之外（跳过 + warning 日志或严格拒绝），不改 schema 加 Unknown 字段
- 批量导入原子化：校验全部通过才落库
- **首选 skip-on-load 而非保留 nullable unconfirmed 记录**——后者会让 export→import 往返破裂或引入 null 值

## 引用口径

- 综述 §2 工具 #3「fail-closed 优先」的另一起点：「未知 ≠ 错误，选 skip-on-load 不选 nullable」即本文件。
- 发生时间早于 2026-09-03 的 S58/S65（fail-closed 成文锚点）与否，记录不可判；综述不声称时序。
