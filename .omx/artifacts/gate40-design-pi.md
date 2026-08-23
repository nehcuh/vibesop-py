Usage: vibe route [OPTIONS] [query]
Try 'vibe route --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Got unexpected extra argument(s) (review 一下最近的改动\），online 与        │
│ offline 各 n=3 连跑。  ## 结果  | 模式 | n=3 墙钟（s） | 中位 |              │
│ |---|---|---| | online（现状） | 16.67 / 18.40 / 17.66 | 17.7 | |            │
│ offline（HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1） | 6.00 / 4.37 / 4.09 |    │
│ 4.4 |  - Lane C 前测：online 34.8/37.9 → offline 5.1。两批测量绝对值不同     │
│ （HF Hub 限流状态随时间漂移），方向与量级一致：online 恒定慢                 │
│ 13-30s，offline 稳定 4-6s，**~4x 差距的下界可靠**。 - offline                │
│ 路由输出正确性：实测命中                                                     │
│ `custom/you-are-an-independent-architecture-adversarial-re-bd1bc217`         │
│ （82%）并给出 alternatives——语义索引在 offline 下正常工作   （模型已缓存）。 │
│ - 佐证：analytics.jsonl 纯路由计算 16-25ms；spans route span   duration 中位 │
│ 16.4s（811 条，口径不纯但量级一致）。  ## 结论  修复成立：模型已缓存时导出   │
│ offline 环境变量，消除每次 prompt 的 HF Hub                                  │
│ 在线等待。未缓存时必须保持在线（首次下载），fallback fail-open。)            │
╰──────────────────────────────────────────────────────────────────────────────╯
核查完毕。以下为独立复审结论（全部证据经代码/数据复核，含 3 个只读测量脚本在 /tmp 复核）。

## Verdict
PASS_WITH_NITS（3 个 MAJOR 必须吸收为设计修订后方可进入实施；主项机制不得按现状开工）

## Findings

- [MAJOR] **主项：声明的 "offline 失败→在线重试" fallback 未入设计，部分缓存下是静默行为变化且无测试**。§1.1 明示该 fallback"必须设计进去"，但 §1.2 的唯一机制是"缓存存在→导出 + helper 出错→不导出"，无任何重试路径。实际失败路径：snapshot 目录存在但文件不全/损坏 → `SentenceTransformer` 抛异常 → `_layers.py:403` 与 `triage_recall.py:123` 的 try/except fail-open（triage_recall 还 sticky `_model_failed=True`，整个进程生命周期禁用 recall 线）→ 语义层静默降级。而今天同一场景会在线补全（慢但成功）。"回归：offline 导出后路由结果与在线一致"只覆盖全缓存 happy path，失败路径未测未披露。**裁定：二选一**——(a) 切换机制到 `local_files_only=True` + 显式重试：sentence-transformers 5.7.0 实测支持该参数（`.venv/.../sentence_transformers/sentence_transformer/model.py:160`），设计稿自评"更佳"，且天然实现重试、pytest 可测、helper 单一实现（消除 bash/python 谓词分裂）；或 (b) 维持环境变量但把重试需求显式降级为"接受的 fail-open 降级"，补一条"缓存存在但加载失败"路径测试 + CHANGELOG 披露。（另：§1.2 helper 未钉缓存谓词——HF_HOME/HUGGINGFACE_HUB_CACHE 覆盖、hub `snapshots/<hash>` 布局 vs 旧 torch 缓存两态，误判方向要么 no-op 要么堵死"首次下载必须能发生"。）

- [MAJOR] **项 4 hook 侧："cmspark 无实证样本"与仓内数据矛盾，且 "fallback-llm" 桶污染后果未点名**。本仓 `.vibe/observability/spans.jsonl` 实测 **6 行**（08-17~08-18，platform=claude-code）`has_match=True ∧ skill_id=="fallback-llm"`——正是 steps[0]-fallback 活洞的实证，合成稿未找到（其"无实证"表述事实不完整）。这同时意味着：该洞写出的 "fallback-llm" 是非空字符串，读侧谓词（skill_health.py `_route_hit_skill_id` 仅非空 str；skill_outcomes 同款）**不过滤它** → 在 outcomes/fire 视图制造假 "fallback-llm" 技能桶。修复写侧之外，应给读侧谓词加 "fallback-llm" 排除（或披露该桶），否则 6 行存量及修前任何新行继续污染。

- [MAJOR] **主项 CLI 注入点：HF_HUB_OFFLINE 是 import 时冻结常量，注入位置未钉**。`huggingface_hub/constants.py:203` 实测 `HF_HUB_OFFLINE` 在模块首次 import 时求值，之后 `os.environ` 修改无效（`is_offline_mode()` 返回冻结值）。`import vibesop.cli.main` 实测不引入 huggingface_hub（可行），但设计未钉：导出必须发生在任何传递性 import 之前；且"CLI 入口"未界定范围——embedding 加载点共 6 处（_layers.py:399、triage_recall.py:119、strategies.py:595、promote_verifier.py:132、learner.py:691、indexer.py:472），`vibe route` 之外 discover/promote/instinct 等命令若不在注入范围内，pi 扩展路径修了也白修。须钉：注入点=CLI dispatch 层（子命令路由前）+ 枚举全部 embedding 触发命令。

- [NIT] **项 4 数字 37+66 不可复现**。我的独立查询：outcome-joined hit 空 skill_id = **85 行全 hook、全部 ≤08-21**（07-30:14/07-31:8/08-18:20/08-19:16/08-20:23/08-21:4，佐证 M12 化石归因）；prod spans.jsonl CLI 空 skill_id = **11 行（含 08-23:5）**。方向与结构性归因（hook 化石已停产、CLI all-fallback 持续产）全部证实，但 37/66 具体数字与我的谓词对不上，稿中无查询/口径钉死（gate37 §6 G 的 文件:行号 纪律适用）。

- [NIT] **项 5 的 "32ms/call 超 5ms 砍门槛" 是合成规模专属**。实测复核：50 技能×500 记录（真实量级）per-skill counter 重建 ≈0.18ms，今天就已亚毫秒；32ms 只在 700×5000 合成下成立（我的 bench：dict-per-skill 14140ms → 单遍 Counter 92µs，正确性同值、量级证实）。修复正确且必要，但诚实论证应是"O(distinct×records) 二次复杂度随数据增长必咬人"，不是"今天 32ms"。另 optimization_service 实际闸在 :184（稿引 :180，行号漂移 4 行）。

- [NIT] **项 2：≥3 闸收窄了但没消灭假-F 机制**。实测代数：3 条路由、无显式反馈、usage_frequency<1.0 的技能 quality_score = 0.25×1.0 + 0.15×0.5 = 0.325 → F → 30d deprecate。即"用得相对少"仍是 F 主因，"荒诞"案例（1 条正确路由→F）修好了，3 条变体还在。CHANGELOG 措辞不得宣称"质量 vs 用量"已修复，只能宣称"证据门槛从 1 提到 3"。另：F 档薄样本（1-2 条）现在**任何处置路径都没有**（warn 只认 D），无 warn 无 deprecate 无 archive 的真空区，值得在 CHANGELOG 单列一句。

- [NIT] **项 2 "今天零行为变化"**：核实到 cmspark 与 vibesop-py 均无 execution_feedback 文件、全局 ~/.vibe 亦无（fuel 为空成立），但表述应限定"两个已知 dogfood 现场"，非全量声称。

- [NIT] **gate40 §0 "五项候选的裁决全部配了实测数据" 不实**：仅主项有归档测量档案（gate40-hook-coldstart.md）；项 2/4/5 的实测只在稿内断言、无 artifact、无查询口径，违反本仓"凡声称实测必须可复核"纪律。

- [NIT] 引用勘误：§3 "（_is_miss docstring 明示该分歧有意）"——该分歧实际写于 `gold_detection.is_route_miss_span` docstring（gold_detection.py:160-168，:134 交叉引用），非 _is_miss docstring。tool_sequences 轮转先例实为 `_rotate_if_oversized` :133-151（稿引 :137-154，漂移）。

---

**复核确认（正面，供主代理吸收）**：主项测量方向/量级成立（4x 下界可辩护：min ratio=16.67/4.09≈4.08，绝对值 13-30s/prompt，跨两批稳定；hook 模板唯一——`templates/shared/vibesop-route.sh.j2` 单点渲染至 claude_code/cursor/file_based + pi TS 扩展走 CLI，修复面=1 模板+CLI）；换皮核查通过（五项均为 gate38 §5 / gate39 §4 明文 deferred 项 + Lane C 清单外发现，非 gate34 不做清单复活）；项 4 消费者分析**完备**（span has_match 翻转仅影响 gold_detection 发现池——`_maybe_enqueue_routing_pending`/`should_enqueue_from_route` 读 route result 对象非 span metadata，unified.py:1338；bridge `_is_miss` 排除 CLI，tool_call_bridge.py:278；发现池 docstring 明示 CLI miss 合法）；项 1 五处硬编码全读侧（server.py:137/:195/:296/:330/:344，gate39 §4.1 明文 deferred）；manager.py:553/:559 死配置无消费方属实；evaluator.py:201-204 O(distinct×records) 属实且 `get_records()` 为内存态非重复 I/O；项 2 的 ≥3 为仓内多数票（feedback_loop.py:190、optimization_service.py:184）；CLI 脏行根因 = `OrchestrationResult.has_match`（models.py:791-795，steps 非空即 True）语义落后 hook 侧 `router_matched`（agent_runtime.py:557-559）属实。
