核查完毕。40+ 处引用抽查（两处差一行的路径/行号小误差，零捏造），全仓 grep 三组消费方，不变量与换皮检查完成。以下为评审结论。

## Verdict
PASS_WITH_NITS

## Findings

- **[MAJOR] §2.2.8 与 §2.3/§2.4 自相矛盾：gate38 落地后存在两个活的自动处置入口，而设计同时命令 help 文案宣称只有一个。** §2.2.8（skill_commands.py:352-373）称 stale --auto “成为唯一受 sanction 自动入口”、help 补写“--auto 是唯一自动处置入口”；但 §2.3 使 `optimize --apply` 调 `analyze_all(auto_deprecate=True)` 真实生效——feedback_loop.py:85-90 在 True 下会执行 deprecate、archive、boost 三种生命周期写入，与 stale --auto 完全同权。照字面实施会发布一条落地即假的 help 承诺；§0.1“本稿删除自动处置而非新增”的定性也不准确（--apply 现为死代码=从不动作，修活即净增一个可用的批量 deprecate/archive 入口）。修活本身可辩护（显式 flag 与 stale --auto 对称、help 已印承诺），裁 §2.4 维持修可以，但必须二选一收口：要么删“唯一”措辞并在 help/文档枚举两个入口，要么把 --apply 的动作面收窄到展示+指引。边界本身（显式 flag、无暗道）未破，故 MAJOR 非 BLOCK。

- [NIT] §2.3 证据精度三处小误：构造 bug 实在 optimize_cmd.py:105（:106 是 analyze_all 调用行，§2.2.6 引用正确、§2.3 差一行）；“5 调用点中两处死代码”计数不准——5 处里仅 :106 一处死，第二处死代码（_apply_optimizations :140-157）不在 5 调用点清单内；且 --apply 的死因表述有误：`:149 apply_auto_actions()` 确不存在，但 :148 同样的构造 TypeError 先触发，AttributeError 根本不可达。修复描述不受影响。

- [NIT] §2.1 下游兼容审计清单不完备（结论经我独立 grep 复核均成立，但按修订 G 纪律应补录）：未列 badges.py:203-223（`all(g in ("A","B"))`，"?" 不授徽章=与今日 "D" 同结果）、retention.py:64-132（精确字母规则+"?" 在 :72 已有无数据先例；且 RetentionPolicy 无生产调用方，是死代码）、_config.py:246-248（实为 `==` 精确匹配而非“dict.get 带 default”，仅建议不动作）、_listing.py:245（数值分桶被 total_routes>0 门挡住，零样本不展示）、evaluator.generate_report 均值(:285，无调用方)。清单外消费方全部免疫是运气+现有闸门，不是审计的功劳。

- [NIT] 数值侧展示语义未审计：quality_score 0.5→0.0 使 `vibe skills quality` 排序中零数据技能从中间跌到底部（_quality.py:60），并在 0% 分数旁配 dim "?"（:102）。“无数据≠差”的防线只建在 grade 侧（must-NOT 测试只测 grade 不为 D/F），分数侧同一谎言换个通道回来。方向可接受但应成为自觉选择：零路由行分数也显示"—"或至少在测试计划补分数渲染断言。

- [NIT] §2.3 --apply 动作/日志不对称：analyze_all(auto_deprecate=True) 会顺带执行 boost（A 档 deprecated→active 翻活，feedback_loop.py:196-204），但 `_log_optimization` 只收集 action∈{deprecate,archive}——被 boost 翻活的技能发生生命周期变更却不进 optimization-log.jsonl 也不进 "Applied Optimizations" 列表。要么全量收集已作用 skill_id，要么 --apply 显式排除 boost。

- [NIT] §3.2 新增休眠 `--strict`（误路由 exit 1）与永久否决的硬阻断形态只差一次接线，且无任何已批准消费方——与本项目自己的“不建常驻设施”裁决（L3）同构的 YAGNI 违例。不接线≠不存在，最便宜的做法是先不加，出现被批准的用途再加。

- [NIT] skipped_env 口径有两个未覆盖的残余：(a) reject-only 条目（expect:[] + reject 含 pack id）在裸环境空过——reject id 不可解析时永不违反、空赚通过率，抬高 recall 分母有效性；(b) extended 头部 :23-32 自述的“~5 条 env-sensitive fallback 路径”未带标注，裸环境仍计 errors。report-only + extended 仅进 artifact 可容忍，但 requires_packs 字段说明（§3.2 重写的 ：23-32 注释）应如实披露这两类噪音，防未来读者把 extended 数字当干净基线。

- [NIT] hit/fire 双总体披露只落在 dev-facing docstring（tool_call_bridge.py:32-47），而用户想拼“fire→成功率”时看的是 `vibe skill list` fire 列——§4 文档清单里 CLI_REFERENCE 只点名 stale/report 两处，未要求 fire 列头/文档同步“与 hit outcome 不可拼比率”警示。披露应到达引诱发生的界面。

- [NIT] hit 派生成本未声明：`_classify_hit` 每 hit 全量扫 route_spans（O(hits×spans)，hit 占 span 大头，≈O(N²)），首跑回灌一次性付满（cmspark 量级无碍，但 spans.jsonl 无界增长时 bridge 每次运行的成本按平方涨）。与既有 miss 派生同渐近类、离线路径，不违 100µs 热路径门，但设计稿应写明该成本与 spans 轮转上界的依赖关系（`_derive_outcomes` 有 :414-467 先例不豁免新增 3-8x 常数）。

**核查通过项（供记录）**：换皮检查三通过——三项均为 gate34/gate37 明文 deferred（gate37 裁决 2/裁决 4/修订 C），CI 为 report-only 真身（eval_routing.py:174 恒 0 + continue-on-error ci.yml:110 先例 + workflow_call caller 见 success，release.yml:15-21 属实），无比率无新分数；不变量零触碰核实（三套 trigger 语义/双 embedding/_is_agent_prompt_shape skill_promote.py:366/gate30 upsert/_is_miss :470-492 与 _classify :495-539 均只增不改）；top_skills 不可逆性论证成立（alternatives 是写时数据，路由器状态随时间漂移不可回放重建，且 gate37 裁决 2 本就点名此物）；route_outcomes.jsonl 现无生产读方，hit 行零污染；5 调用点清单经全仓 grep 确认完备，单提交原子落地+联合 must-NOT 测试下顺序依赖残余风险极小；hit 排除 CLI 的裁定正确（镜像 _is_miss 的 one-shot 空洞弱阳性论证，双总体披露是 a/b 两案皆劣后的最优解）。
