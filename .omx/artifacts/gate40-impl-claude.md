## Verdict
PASS_WITH_NITS

## Findings

**规格符合性（对照 r2.2 §1-§5）**——逐条核实通过：

- 主项：`embedding_loader.py:45-56` 异常分类学与 §1.2 伪码语义逐字一致（非缺失类原样抛零重试、缓存缺失类单次在线重试、二次异常原样重抛无包装）；6 加载点全改走 helper，src 下 `SentenceTransformer(` 直调仅剩 helper 内 2 处（零漏网）；各点既有 except 形态零改动（strategies 仅 ImportError 重写 / learner 三元组 / triage_recall sticky / promote_verifier state / _layers → None / indexer 两段式）；helper 无状态；`observability/embedding.py` FastEmbed 栈零触碰，双栈分离成立。
- 项 4：`models.py:791-795` property、result.skill_id/skill_name/alternatives、`agent_runtime.py:172` hook 响应全部原样（结果契约）；top_skills 与 span skill_id 同源（hook 单一 `_span_skill_ids`，CLI 单一 `_span_skill_id` 门+内容）；miss 行双生产者一律 ""；fallback 行先于 unjoined 判定 continue；对账式扩展 Σ三列+unjoined+fallback=hit 总数；recall 第三读者消费方（recall.py:349-351 `if sk_id:` guard）无波及；gold_detection docstring 反面记载已改写，`is_route_miss_span` 函数体零改动。
- 项 2：双 conjunct（≥3 ∧ accuracy<0.5）+ archive ≥3 闸（C/D/F）+ 模块/类/方法 docstring 与 reason 字符串全量同步；测试覆盖 thin 全组合零处置、accuracy=1.0 反例、0.5 边界、archive 正例、warn 不变。
- 项 5：单遍 Counter 等价（`max(default=0)` 语义不变），无参路径自算 + hoist 可选参数。
- 项 1：五处全换 `_spans_path()`，无 exists-gate，prod 路径逐字节不变；6 处非 dashboard 记档行号全部属实（recall_cmd:150 / trace_cmd:437:522 / pool_cmd:124:391 / dag_rebuilder:227）。

**不变量**：tool_call_bridge（_is_miss/_classify/_is_hit/_classify_hit）、skill_promote（gate30 upsert/_is_agent_prompt_shape）、embedding.py 双锁、trigger 语义所在文件均不在改动清单——零触碰。

**测试**：targeted 190 passed；全量 6261 passed / 14 skipped（基线 6234，零回归，152s 无 HF 卡死）；ruff 新碰文件净（12 报告全在未触碰存量行）；check_docs 过。四个“真能红”断言结构成立（精确 `call_args_list` / 精确 dict 相等 / property pin 与写值翻转共存）。

**WS 申报偏差 7 项全部裁决合理**：helper 落点是 spec 明文授权的“就近模块”且 FastEmbed 栈隔离使其成为唯一正确选择；recall 后置过滤强于 spec 的一行内联；两处夹具 1→3 是新规则下正例的必要最小适配（断言零改动）；dag=True 双写暴露的 dev/prod 错位已记档。

Findings 清单：

- [MAJOR] hook 侧 span 写值的步覆盖只有前 5 步：`agent_runtime.py:677-691` 的 `_span_skill_ids` 数据源是 `result.skill_id`（steps[0]）+ `result.alternatives`（:564 仅填 steps[1:5]），而 plan_builder 无步数上限（squad/tournament 可产 >5 步）——真步在第 6+ 步且前 5 步全 fallback/空的计划会写 `has_match=true ∧ skill_id=""`，与项 4 要消灭的活洞群 A 同型，违背“span metadata 自洽”的本项验收口径（CLI 侧扫全部 `_steps` 无此洞，两生产者不对齐）。触发窄、读侧兜住（fire 排除 / outcomes unjoined 可见），建议下个 gate 改扫 `result.plan` 全部 steps 或记档+边界测试钉死。
- [NIT] indexer 包缺失日志级别漂移：`indexer.py:471-481` import 对象换成总可导入的 embedding_loader 后，包缺失从第一段 `logger.debug("not installed")` 移到第二段 `except Exception` → `logger.warning`。fail-open 语义不变，已申报（WS1），但未在 CHANGELOG 点名。
- [NIT] `learner.py:511-512` 无关 format 折行（两行合一行，恰 100 字符）——gate40 无关的格式 churn，已申报（WS1），无语义变化。
- [NIT] 测量档案未补项 2/4/5 查询口径：`gate40-hook-coldstart.md` 无 gate40 后更新；CHANGELOG 引用的 1061/2822、1088/2440、“两 dogfood 现场 feedback 文件不存在”均无谓词/时间窗/现场的口径留档——spec §7 与 gate37 修订 G 纪律缺口。
- [NIT] 容器内冷/热缓存两态 e2e 验证（spec §1.2 claude-NIT 采纳项）无任何 artifact 佐证；taxonomy 仅被单测 mock 覆盖，首次下载实机路径未见留档。
- [NIT] CHANGELOG“只是不再被处置”仅指 deprecate 通道：accuracy=1.0 的薄 F 在 90d 后仍会被 archive（有意，测试钉了正例 `test_f_grade_archive_after_90d_with_sufficient_routes`），措辞未点名该路径。
- [NIT] 工作树当前为单一未提交状态，spec §7 要求主项/项5/项4/项2/项1 五个独立 commit——push 前需拆分（与 gate39 复审同款提醒）。

对账说明：随附 diff 与工作树逐字一致（29 文件 stat 全吻合 + 关键文件 blob hash 逐一比对 + 抽样逐字核对），评审基于工作树真实状态。
