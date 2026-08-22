## Verdict
PASS_WITH_NITS

## Findings

规格逐条核对结果（先说结论）：修订 A/B/D/J/K 全部落地——trigger 侧只用泛化抽取的 `query_matches_triggers`（triage_service.py:46-67，语义钉住测试齐备，`has_explicit_guard_signal` 委托后行为不变，71 条 guard 测试通过）；PASS 分母排除 `_has_agent_prompt_prefix` 回声行且 lint 与 shadow 同口径（promote_verifier.py:426-447）；降级永不 PASS、无 FAIL 级、激活路径 try/except 全包且 verifier 不涉 `--force`；verdict 嵌当前文件字节哈希（测试显式断言 ≠ `ClusterCandidate.draft_sha256`）+ trigger 集哈希 + ruleset_version + 分线结果 + 实测管线清单；store 双锁/坏行跳过/200 条/90 天与 `ClusterCandidateStore` 惯例同构；global scope 构造期哈希化（测试断言原文不出现在 to_dict blob）；activate 复用/重跑/`prefer_complete` 三分支均有测试；看板按 scope 过滤明细 + stale 比对 + 与 CLI lockstep；修订 K 仅加 provenance 标注、空簇保持 TODO（渲染/回放 73 测试零回归）；e2e 为纯插入、现有检查未动。不变量：gate30 upsert 与 intake 零过滤未触碰（skill_promote.py 仅 `_render_skill_md` +8 行）、双 embedding 线分离、存储层风格一致。已执行验证：新测试 28+5、promote CLI 63、dashboard 39、observability 全目录 618、routing+CLI 全量 1238 全部通过；ruff 干净；basedpyright 0 errors；smoke 脚本编译通过。以下为 NIT：

- [NIT] 徽章定义比修订 J 字面更严：修订 J 定义 PASS = "lint 全过 + shadow 全捕获"（embedding 线仅 unavailable 时压到 WARN），实现额外要求两 embedding 线可用**且过门**才发 PASS（promote_verifier.py:521-527）。方向保守、验收场景（良好簇 PASS / 降级 WARN）仍成立，但与规格字面不一致——攒 ≥30 条 verdict 讨论阈值前应把该口径回写进规格或 RULESET 文档，避免"非生产数字"争议反过来咬实现。
- [NIT] 规格落位偏差：§3-2 写 "`skill_promote.py` 新增 `verify_draft()`"，实现落在新模块 `promote_verifier.py`（跨模块 import `_has_agent_prompt_prefix`/`_candidate_text`/`_compute_profile_text` 等私有名，basedpyright 5 个 reportPrivateUsage 警告；与 replay 脚本 import 冻结谓词的既有先例一致）。可接受，但属规格字面偏离，应留痕。
- [NIT] "skipped" 被并入 degraded 且文案失真：draft 无 triggers 时 index 线返回 `status: skipped`（promote_verifier.py:622-630），`degraded=True`（:526）触发 CLI 文案 "degraded: embedding 线不可用"（skill_commands.py:1886）——此时模型可能完全可用，只是草稿没有 triggers。建议区分两种状态或改文案。
- [NIT] sticky 模型单例的测试隔离隐患（任务书点名项）：`_MODEL_STATE` 无任何测试重置（promote_verifier.py:123-142）。当前确定性成立（conftest autouse stub 使 import 恒败，嵌套 fake 只出现在 test_indexer/test_triage_recall 且不触本模块），但两条未来路径会永久污染单例并造成顺序依赖 flake：(a) 某测试按 conftest 文档的 `patch.dict` fake 模式调用无 DI 的 `verify_draft`；(b) benchmark 标记测试（stub 豁免，tests/conftest.py:319-326）触达 verifier 加载真模型。建议加一个 autouse fixture 重置 `_MODEL_STATE`。
- [NIT] verdict 明细缺队列同款的读侧二遍脱敏：Discovery 卡片走 `_display_text`（`redact_sensitive`+sanitize，_discoveries.py:78-86，防手改 store 泄密），而 CLI `_print_verdict` 与看板 `renderVerdicts` 直接渲染存量 query 文本（写入侧仅 `sanitize_body_text`，无 `redact_sensitive`）。CLI/看板彼此 lockstep，但与队列防御惯例不一致；威胁面仅限手改 `promote_verdicts.jsonl`（D4 裁决明说手改是支持用法），故降为 NIT。
- [NIT] store 继承 flock-旧 inode + 原子 rename 重写的已知竞态：`append` 在旧 inode 上持锁、`_do_append` 经 AtomicWriter rename 换 inode（promote_verifier.py:266-287），并发第三进程可在新 inode 上自由获锁 → 丢一行。与 `ClusterCandidateStore` 完全同构且是仓内已记录的 deferred 限制（Phase B+1），最坏丢一条 advisory verdict，非回归。
- [NIT] `verify_draft` docstring "Never raises" 过度承诺：两 embedding 线的 `zip(..., strict=True)` 在 try 块之外（promote_verifier.py:580,648），行为异常的模型返回错长向量会抛 ValueError 穿出。当前唯一生产调用方 `_run_shadow_verify` 有全包 try（灯不变闸），仅直接调用方（测试）可能见到异常。
- [NIT] smoke 的 "degraded" 期望与 val-base 镜像耦合：belt-and-braces env 只断网（e2e_command_smoke.py:446-449），若镜像未来自带 torch+模型缓存则该步会诚实 FAIL（模型可用即非降级）。注释已声明依赖，留意镜像变更时同步此断言。

无 MAJOR / BLOCK。多平台（fcntl→`cross_process_lock` 回退、Windows CI 路径已覆盖）与注入面（看板全部 `escapeHtml`、badge CSS 类齐备）未发现漏项。
