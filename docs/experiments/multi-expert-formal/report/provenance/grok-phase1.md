你是本实验的具体执行负责人 Grok。用户要求你实施计划、运行完整实验、保留过程；监督者 Codex 只负责方向与重要结果判断。工作目录 /Users/huchen/Projects/vibesop-py/.experiment/worktree，禁止修改主工作区生产文件。路由已由上游完成，ACTIVE builtin/autonomous-experiment，不要再次 vibe route，不要加载无关 skill/fallback，不要启动其他 agent。

先读 .vibe/experiment.yaml、docs/experiments/multi-expert-e2e-protocol.md、docs/experiments/multi-expert-calibration/RESULTS.md、protocol-fidelity-review.md、observations.md，以及主目录 /Users/huchen/Projects/vibesop-py/.experiment/beliefs.md。校准数据不可修改或充当正式样本。

任务第一阶段：补齐正式端到端执行器及12个独立任务、两版spec、验收与计量，完成非正式校准和可复核的启动门槛。具体执行、编码与测试由你完成。不要停在计划或向用户问批准。

实验五组 A单体 B单体分阶段 C无角色委员会 D同流程专家委员会 E明确子任务分工；12基础任务×2spec×5组×3重复=360正式运行。先同一模型组织对照，不加入强弱模型混合因素。现有配置可通过 vibesop.core.llm_config.VibeSOPConfigManager 获取 DeepSeek key，不打印/写出密钥。请求deepseek-v4-flash实际服务DeepSeek-V4.1-Flash/响应deepseek-flash；使用显式非推理模式（extra_body thinking.type disabled）与温度0并记录响应。SDK无自动重试，计入失败。模型版本别名限制要写清。

必须落实：
1 每组相同工具：读写允许文件、在隔离Docker运行可见测试/CLI、固定问答澄清接口。保留真实会话历史；C/D独立分析+一轮同步交流，角色是唯一预期差异；所有调用计入统一全程T/I/K，单体有权使用全部总额度。不要用一次6000的上限使A实际预算低于多体。限额在发请求前执行，reasoning/cache/输出与工具开销入账。内部报告截断可继续且标注；全局耗尽和最终无效产物失败。
2 E拆解由模型完成且计入成本，两个工人明确文件边界和依赖，集成与修复真实落盘。能串行就按依赖串行；不要把共享代码冲突藏掉。
3 所有待测代码在Docker隔离，禁网、不给密钥/宿主目录/隐藏测试；可见测试与隐藏验收分离。主持者和作者可以接触隐藏测试，参与者只收到任务files/spec及固定问答。
4 12任务需体现路由局部、跨层配置入口、可拆分量化/数据处理三类机制各4项，不能只是改数据当独立任务，不能照搬校准题；端到端从需求到CLI交付。完整/简略spec共享可获知的规范，简略版通过相同问答获得遗漏，不用隐藏偏好处罚。不同任务的真实独立性与难度先审查。
5 任务正确实现+错误变体用于预验收，确认测试敏感度；真实入口测试，不仅内部helper。校准任务不得计入360。保存完整差异、每次调用、工具轨迹、退出原因、配对/随机分配、源码和任务哈希、计量、没有产物的分配记录。不能挑最佳尝试或修改正式验收追求胜率。
6 主比较D-A，其余探索。按基础任务聚类区间，重复/spec不能伪装独立样本。事先10个百分点工程阈值，未定如实写未定。不得以LLM评分做主放行闸。

工作流：仅在 docs/experiments/** 内改代码/文档（历史calibration/runs只读）。每轮先向主目录 .experiment/beliefs.md写预测（最多20belief），在worktree修改，提交git，再运行客观校验，向主目录 .experiment/results.tsv记 actual/compound/verdict并更新belief。6轮上限/3轮不改善停止；该优化循环只优化执行器有效性，不丢弃任何模型样本。失败变更需丢弃时先归档diff和日志到主目录metadata，禁止删模型记录。已有baseline offline pass、formal0、fidelity未满足，勿冒称baseline是正式分数。新 verify_experiment.py作为objective evaluator输出明确rubric与总分（建议各类协议门槛通过计数）。额外准备期消耗必须与模型样本开销分开。

保留进展文件：docs/experiments/multi-expert-formal/STATUS.md，至少每个实质里程碑更新，包含已完成/剩余/运行命令/最近日志/错误/下一步；所有长期命令保存日志并可恢复。完整报告目标 docs/experiments/multi-expert-formal/REPORT.md。

第一阶段退出点：通过准备与校准后，写 docs/experiments/multi-expert-formal/READY_FOR_REVIEW.md，包含各项证据/冻结候选任务哈希/固定资源值/预算估算/实际执行方式及已知限制，并结束本次headless响应给监督者做独立方向复核。此为Codex内部监督点，不要求用户审批。此时不要启动360正式调用。若准备尚未达标，继续修复而不是交一个自称ready的空架子。无需联网调研论文，先执行现有方案。模型数据永远留存。最终简述改动文件、验证、准备状态和下一条执行命令。
