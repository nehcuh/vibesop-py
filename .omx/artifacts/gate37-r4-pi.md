Usage: vibe route [OPTIONS] [query]
Try 'vibe route --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (§6 修订 B + §6.1 H 为准\指针）; - §2 裁决  │
│ 4 括号补\强制 redact\; - §6 修订 B 反馈列句、修订 E 流程句各加\已被 §6.1     │
│ 修订 H/I 取代\标注。  ## 任务 只读核查                                       │
│ /Users/huchen/Projects/vibesop-py/.omx/artifacts/gate37-synthesis.md，确认上 │
│ 述三点修复到位、全文无残留矛盾。  ## 输出格式（严格遵守） ``` ## Verdict     │
│ PASS / PASS_WITH_NITS / BLOCK  ## Findings - [BLOCK|MAJOR|NIT] 描述 ```      │
│ 不要客套。无新发现就只给 Verdict。)                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
只读核查完成。逐项核验：

**修复 1 — §2 裁决 2（L36）**
- ✅ 来源列已改 `_get_skill_source` 三值口径、pack 折叠为 external
- ✅ "market" 全文零出现；"promote/手工" 仅以"无数据不标，标了就是说谎"理由留存（与修订 B L87 口径一致），不再作为来源值枚举
- ✅ "该屏已有健康叙事雏形"已从 §2 删除，仅存于修订 F（L102）作为勘误记录
- ✅ 指针已加："全部口径以 §6 修订 B + §6.1 修订 B 补丁/H 为准"

**修复 2 — §2 裁决 4（L48）**
- ✅ "（导出→extended needs_review:true 且**强制 redact**→人审→--merge;dismiss 样本走 retention yaml）" — 与修订 I"落盘前强制 redact"（L123）一致

**修复 3 — §6 标注**
- ✅ 修订 B 反馈列（L89）："⚠ 本句已被 §6.1 修订 H 取代，以 H 为准"
- ✅ 修订 E（L99）："⚠ 本段流程描述已被 §6.1 修订 I 取代——…；以 I 为准"

**残留矛盾扫描**：修订 B 反馈列的"不相交/get_skill_summary"、修订 E 的"禁止手改 yaml/--merge"均为被标注取代的旧句，H（L117-120）与 I（L123）已分别纠正；§3 引用已改为"修订 B+H""修订 E+I"。L3 重启条件三处一致（promote ≥30 且 verdict ≥30）；来源口径 §2/§3/§6/§6.1 四层一致；fire 用 spans、CLI 命中计入、数字勘误（525/4.8%/42.9%、4/7、174）仅作勘误记录。无矛盾残留。

## Verdict
PASS
