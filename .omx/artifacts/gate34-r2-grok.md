先按路由协议匹配技能，再只读核对 §6 修订与代码事实。路由还在跑；同时只读抽查 §6 引用的代码锚点。`explicit_guarded_skill_match` 只覆盖 guarded 技能，要确认生产 trigger 的真实路径，再核对 dismiss 与 activate。生产 trigger 路径可能不是 `explicit_guarded_skill_match`；继续核对 activate、dismiss 与看板相关代码。路由命中 `kimi-gated-fix`（修代码闭环），与本任务（只读复核 §6 裁决稿）不符；按任务书只读核对代码后给出结论。

## Verdict
PASS_WITH_NITS

## Findings
- [MAJOR] 修订 B 点名包装 `explicit_guarded_skill_match`（`triage_service.py:541-566` / `unified.py:961-974`）。该函数对 `guarded_skill_name is None` 直接 `continue`（`:559-563`），guarded 集只认 riper / session-end（`:491-498`）。新 draft 走这条线恒 miss，PASS 徽章死。应抽出 `has_explicit_guard_signal` `:533-537` 的 containment（lowercase + 剥撇号、无空白折叠、无 ≥6 下限）套到 **draft 自己的 triggers**；或承认新技能的生产 trigger 路径只有 embedding 双线，trigger 侧只做静态 lint。括注把 p0_shadow 的空白折叠/≥6 字安到生产头上（生产实际是无折叠、无下限、first-hit-wins，见 `replay_routing_baseline.py:157-164`），照着实现会把错误语义焊进 verifier。修订 B
- [MAJOR] 修订 J 的 PASS = shadow 捕获簇内**全部** query，与修订 C / gate32 A1 冲突。簇内回声是合法成员（`skill_promote.py:342-349`）；triggers 预填已滤掉 `_is_agent_prompt_shape`（`:2020-2023`）。混有回声的良好簇（含 bd1bc217 类）会恒 WARN，徽章无区分度。捕获分母应排除展示层 agent-echo（或只计非卫生形状 query）；lint 的「≥1 条代表 query」与 shadow 分母必须写同一口径。修订 J ↔ 修订 C
- [NIT] 修订 A「廉价」只对 trigger 字符串包装成立。修订 B 双线 embedding 在 activate 必跑（M5 强制手改，不能复用 promote 缓存）；conftest 记载真模型加载 10–12s/次（`tests/conftest.py:291-293`）。写明预算：trigger 线必跑，embedding 允许 fail-open/超时降级，禁止为「廉价」跳过 embedding，否则「激活前不盲盒」只剩 trigger。修订 A ↔ 修订 B
- [NIT] 修订 A 的 `draft_sha256` 必须是被验证文件的当前字节哈希，禁止与 `ClusterCandidate.draft_sha256` 对表——后者是生成时基线，activate 后仍不变（`skill_promote.py:453-460`，`:2063-2101`）。对错表则编辑后的 verdict 永远 stale。修订 A
- [NIT] 修订 I 的 dismiss = 全部池状态翻转，未排除 `dismiss_reason=shape-batch`。与修订 E 豁免 `threshold_suggestion`、裁决 3「≥30 再议阈值」平行污染（一次 `--shape agent-echo` 即可灌满分母）。D3 列应单列 shape-batch，不计入 per-source dismiss。修订 I ↔ 修订 E
- [NIT] 修订 J 未定义 embedding `unavailable` 时的 PASS。应分线：unavailable 不参与 PASS/WARN，否则 docker 永远 WARN，与修订 B fail-open、修订 H「不红」拧巴。修订 J ↔ 修订 B/H
- [NIT] 修订 F 写 `first_seen`，字段实为 `first_seen_at`（`skill_promote.py:441`）。修订 F
