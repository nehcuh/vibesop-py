# Gate37 实施第二轮复审任务书

你是 gate37 实施第一轮评审者。第一轮 findings(pi 1 MAJOR+3 NIT;claude 3 NIT）已全部修复，修复后完整 diff 在随附 gate37-impl-r2.diff。规格仍是 .omx/artifacts/gate37-synthesis.md(§3/§6/§6.1)。

## 修复声明
- pi-MAJOR:dismiss 分支改为只认显式标记（`dismissed: true` 或 `retention_reason` 字段）才移入 retention；无标记 expect:[] 保持 scored no-match 语义；已对真实 extended 实证零迁移（100 条负例 0 移动）。测试锁定。
- claude-NIT-1:redact 先于判重/回填。NIT-2：真实 loader source 键契约测试。NIT-3:CLI_REFERENCE 文案对齐。
- pi-NIT:_parse_span_time 时区四用例；_append_entries comment-only 保留头部；retention schema(needs_review:false+必有 retention_reason）与文档表述修正。

## 任务
1. 验证你第一轮每个 finding 是否被正确修复（可对 /Users/huchen/Projects/vibesop-py 工作树只读核查）;pi 重点核：无标记 expect:[] 不再被扫、显式标记路径正确、零迁移实证是否可信。
2. 检查修复本身有没有引入新问题。

## 输出格式（严格遵守）
```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```
只读核查，不要修改文件，不要客套。
