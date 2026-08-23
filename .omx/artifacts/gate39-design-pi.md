/bin/sh: 30: No such file or directory
核查完成。以下为独立复审结论（只读审计，未改动任何文件）。

## Verdict

PASS_WITH_NITS

主项非换皮、事实层全绿，两处 MAJOR 均为廉价规格补丁，不阻塞。

**证据核查结果（抽查 12+ 处全部属实）**
- cmspark 数据：`route_outcomes.jsonl` 3068 行，hit 2437（expired 1268 / reask 1167 / moved_on 2）/ miss 631，expired 占 hit 52.0% —— 与稿 §1.1 逐字一致；join 实测 2437/2437 全命中（唯一例外见 MAJOR 2）
- `promote_verifier.py:11-12` 明确"触发召回"非"内容质量" ✓ backfill 砍除理由 (a) 成立
- `skill_health.py:41-47` dev/prod 选择、`:97-133` feedback 计数 ✓
- `tool_call_bridge.py:130` 常量 / `:229` 读 / `:273` 写侧 `SpanWriter(storage_path=...)` 绕过 `span_writer.py:64-69` 自检 —— 双错属实（注：gate38 旧引 `:97,:195` 行号已漂移，本稿行号与现文件吻合）
- `span_writer.py:55` pytest 自检、`:64-69` 显式 path 优先、仅 16384 截断、全仓无轮转 ✓
- `retention.py:51-190` 全类、`:87` uses<3、`:113` auto-archive 广告、`:152-179` apply_auto_actions；生产零 import（仅 `test_retention.py:5`）；三处代码引用齐（`candidate_manager.py:265` / `feedback_loop.py:122` / `evaluator.py:86`）✓
- `feedback_loop.py:147` `total_routes < F_MIN_ROUTES(=3)`，且 grade 只在 `total_routes==0` 时取 "?"（evaluator.py）→ 薄样本(1-2)是 F 规则唯一燃料 ✓ 推迟裁决成立
- `dashboard/server.py:137/:195/:296/:330/:344` 五处硬编码 ✓；`skill_commands.py:205-220` 脚注体系 ✓；`vibe skills health`（`skills_commands/_health.py`）命名占用属实 ✓
- pytest 收集 6232 = 6218+14 ✓；cmspark 无 `promote_verdicts.jsonl`（verdict=0）✓
- `test_tool_call_bridge.py:32-33` 硬编码 `spans.jsonl` + pytest 下 `is_dev_environment()==True` → fixture churn 预警属实，代价评估（改 helper + 一条 pin）合理

## Findings

- [MAJOR] gate38 双挂点披露的半边被无声丢弃。gate38 §1.2 裁定"同一警示写进 fire 列头脚注/CLI_REFERENCE（披露必须抵达引诱发生的界面）"；本稿 §1.2 只给新命令配脚注，§5 文档同步只提 CLI_REFERENCE，`vibe skill list` fire 列脚注（`skill_commands.py:212-215`）未被要求同步。选独立子命令降低了并置诱惑面，但不免除 fire 列脚注义务——用户仍可在 fire 列旁拼 outcome 比率而无警示。裁决：fire 列脚注一行须随主项 commit，或显式记档推迟并给理由。（`src/vibesop/cli/commands/skill_commands.py:212-215`、`.omx/artifacts/gate39-synthesis.md §1.2/§5`）

- [MAJOR] 空 skill_id 总体未裁决、未披露。cmspark 实测 join 虽 2437/2437，但其中 37 行（1.5%）源 span 的 `metadata.skill_id` 为空串（样本 `4ff2a23fff21495e`：`"skill_id": "", "has_match": true`）——真实脏数据总体。§1.2 只规定"span_id 在 spans 里不存在→跳过"，未覆盖"span 存在但 skill_id 空/缺"；实现将静默丢弃 37 行，与"脚注不虚构"纪律冲突，用户对不上桥侧披露的 2437。此同时暴露 gate38 写侧守卫活洞（hit 带空 skill_id 在产）。裁决：显式规定空/缺 skill_id→跳过 + 对应测试 + 脚注一句披露，写侧洞记档。（`/Users/huchen/Projects/cmspark/.vibe/observability/spans.jsonl`）

- [NIT] backfill 砍除理由 (c) 的瓶颈归因与实测矛盾。cmspark 12 技能全期 fire≥30（fallback-llm 1088、riper-workflow 411…，跨度约 2 月，月 fire≥30 头部显然可达）；硬瓶颈是 verdicts=0（无文件），非 fire。"双前置的瓶颈是单技能月 fire≥30"表述不实，砍除结论不受影响（(a)(b) 已足），记档表述应更正。（`.omx/artifacts/gate39-synthesis.md §0`）

- [NIT] reask 判定证据混入 CLI 路径。`_classify_hit` 的 `later_same_task` 扫描全量 route_spans（`_load_route_spans` 含 CLI span，`tool_call_bridge.py:368-375`），仅命中池排除 CLI——hit outcome 的 reask 可由后续 CLI 重路由触发。脚注"hook 路径命中 only"关于行来源为真，但 reask 计数含 CLI 证据；防"reask 多=技能差"误读需加半句"reask 证据含任意路径后续路由"。（`src/vibesop/core/observability/tool_call_bridge.py:656-689`）

- [NIT] RetentionPolicy 删除的文档引用未在 §3 枚举。代码三处引用完备、生产零 import 已核；但 GOALS.md:48/:105/:125 与 docs/architecture/skill-runtime-interface.md:265/:266/:341（:341 是字面"类→文件"映射表）仍引用 RetentionPolicy。§3 只留"实施时 grep 兜底"，建议枚举已知引用，防文档清扫漏网。

- [NIT] outcomes 文件无 dev/prod 分体，设计未明示。`route_outcomes.jsonl` 写侧恒为 prod 名（`tool_call_bridge.py:450-505`，无 dev 变体）；§1.2 只镜像 spans 的 dev/prod 选择，未写明 outcomes 文件恒读 `route_outcomes.jsonl`。应显式：dev 下组合为 `spans.dev.jsonl × route_outcomes.jsonl`。

- [NIT] CLI 形态裁决（独立子命令 vs list 加列）无理由陈述。独立命令本身可辩护（不在 fire 列并置 outcome 列），但稿未论证；且与 MAJOR 1 联动——选独立命令不豁免 fire 列脚注同步。建议一句话固化理由。

- [NIT] 跨技能原始计数可比性误导。高频技能（fallback-llm 级）reask 原始数必然最高；脚注禁"拼比率"只覆盖 fire/outcome 方向，未覆盖"reask 原始数跨技能直接排序"的误读。建议补"原始计数跨技能不可比（fire 基数不同）"。
