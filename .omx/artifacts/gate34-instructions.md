# Gate34 三路评审任务书

你是独立高级评审，复审 VibeSOP 项目 gate34 的综合设计稿。项目根：/Users/huchen/Projects/vibesop-py（Python，src/vibesop/）。

## 背景
团队从 EvoTrace 学习提出 4 个优化方向（D1 promote verifier / D2 轨迹去重 / D3 分源阈值 / D4 不可变记录），先经三路独立对抗设计（产品 Lane A、架构 Lane B、质疑 Lane C），主代理已收敛为 gate34-synthesis.md 裁决稿。

## 你要审的材料（随附，按顺序）
1. gate34-synthesis.md —— 裁决稿（主审对象）
2. gate34-laneA-product.md / gate34-laneB-arch.md / gate34-laneC-skeptic.md —— 三路原始报告

## 评审要点
1. **裁决正确性**：四个裁决点（D2 只展示层 / D1 shadow-only 不硬阻断 / D3 只读统计列 / D4 否决）各自是否站得住？有没有被忽略的更强论据（支持或反对）？
2. **代码事实核查**：报告中引用的关键代码位置（skill_promote.py:342-349 的 gate32 注释、:366 谓词、:1429 intake、:141-167 分源阈值、replay_routing_baseline.py 的 shadow 函数、span_writer.py:110 热路径）是否真实存在、含义是否被正确转述？可用只读方式抽查核对。
3. **路线可行性**：阶段一/阶段二的步骤是否有遗漏的依赖、会破坏的不变量（gate30 upsert 语义、双 embedding 分离、双锁存储风格、100µs p95 span 写入门禁、6041 测试基线、tests/conftest.py 全局 embedding stub）？
4. **漏项**：有没有三路都没看到的盲区（安全、多平台、数据迁移、用户交互）？

## 输出格式（严格遵守）
```
## Verdict
PASS / PASS_WITH_NITS / BLOCK（选一个）

## Findings
- [BLOCK|MAJOR|NIT] 描述（附文件:行号 或 报告章节）

## 对各裁决点的意见
（裁决 1-4 各 1-3 句）
```
只输出评审，不要客套。代码核查用只读命令（grep/read），不要修改任何文件。
