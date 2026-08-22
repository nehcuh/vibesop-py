# Gate35 双路复审任务书

你是独立高级评审，复审 VibeSOP 项目 gate35 阶段一的实施（发现队列可读性 + 展示层去噪 + 统计列 + 回声基线测量脚本）。项目根：/Users/huchen/Projects/vibesop-py。

## 设计规格
`.omx/artifacts/gate34-synthesis.md` §3 阶段一 + §6 修订 C/E/F/G/I + §6.1 是定稿规格（评审修订是规范的一部分）。先读它，再读随附的 gate35.diff（实施 diff）。

## 评审要点
1. **规格符合性**：逐条对照定稿——前缀谓词无长度规则且 `_is_agent_prompt_shape` 一字未动；"为什么在这里"只用实存字段（source/gold_rate/span_count/len(task_ids)/first_seen_at）；批量 dismiss 走池状态翻转且 dismiss_reason=shape-batch、不进 DiscoverySignalStore 指纹负名单、豁免 threshold_suggestion 输入、无 --yes 时确认文案点名 bd1bc217；D3 success=count_skill_route_hits≥5、dismiss 列排除 shape-batch；测量脚本同报池子/队列卡片两口径。
2. **不变量**:gate30 upsert 语义、intake 不过滤、看板只读 read-model、CLI/看板沉底逻辑 lockstep、存储层坏行跳过+from_dict 容忍+双锁。
3. **代码质量**：正确性 bug、边界条件（空池/空 queries/缺 analytics）、测试是否真有说服力（防文案说谎、must-NOT-catch 反例、标集=否决集）。
4. **多平台/安全漏项**。

## 输出格式（严格遵守）
```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```
代码核查用只读命令（grep/read），不要修改任何文件。
