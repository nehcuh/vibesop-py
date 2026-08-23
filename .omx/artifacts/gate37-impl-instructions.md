# Gate37 实施双路复审任务书

你是独立高级评审，复审 VibeSOP 项目 gate37 的实施（L1 极简 skill lint + L2-lite skill list 健康列 + L4 eval 样本追加流程修复）。项目根：/Users/huchen/Projects/vibesop-py。

## 设计规格
`.omx/artifacts/gate37-synthesis.md`（§3 实施范围 + §6 修订 A-G + §6.1 修订 H/I 及补丁；标注"已被 H/I 取代"的旧句以新修订为准）是定稿规格。先读它，再读随附 gate37-impl.diff。

## 评审要点
1. **规格符合性**：lint ≤3 规则且挂载在安全审计之后独立 advisory（不进 is_safe/has_high);fire 谓词=task∧route:∧has_match is True、镜像 dev 文件选择、单次全表扫描、禁 flock、file-missing→空不 mkdir、列头标"本项目·含 CLI"；反馈列用 get_records() 数 True/False 原始数（禁用 get_skill_summary)、空数据"无记录"、partial 偏置与全局断链披露；来源列三值口径；不算任何比率、不派生处置动作、不调 evaluator/aggregator.success_rate;redact 落盘前强制；dismiss 样本进 retention yaml;lint CLI 退出码恒 0。
2. **不变量**:_is_agent_prompt_shape 冻结、gate30 upsert、intake 零过滤、双 embedding 分离、span 热路径、_is_miss/_classify 语义、存储双锁风格。
3. **代码质量**：正确性 bug、边界（空池/坏行/缺文件/时区）、测试说服力（must-NOT-catch 反例、redact 种子测试）、性能（list 全表扫描的频率）。
4. **文档同步**:CLI_REFERENCE 新列/新命令说明与实现一致；CHANGELOG gate37 条目；check_docs 双过。

## 输出格式（严格遵守）
```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```
只读核查（grep/read），不要修改任何文件。
