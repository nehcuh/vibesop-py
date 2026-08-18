# 门禁 6 复审报告(M6 对立复审)

验证基线：受影响 5 个测试文件本地复跑 **141 passed [executed]**(包内 1619 全量数字未复跑)。以下逐点回应攻击面并给出新发现问题。

---

## 1. A — decompose 三入口 junk 守卫:通过(2 NIT)

**[inspected]** 三处守卫位置与包内声明一致：cli/main.py:1080、agent/__init__.py:206、agent/__init__.py:242,均复用 unified.py:83-93 的 `_is_junk_query`(lstrip 后前缀判定)，且都置于 LLM/统计之前。`orchestrate()` 入口经 route()(unified.py:946)与 orchestrator.py:196 双重已有守卫覆盖，无遗漏入口。“contains 文案零改动”结论抽查属实(unified.py:84-91 说 prefix、is_explicit_session_end_signal 说 contains 且确为子串实现，均准确)。

**攻击点 2 回应(build_plan 显式 sub_tasks 不拦)——边界正确**：显式 sub_tasks 是调用方自有数据；且每个 sub-task 的 query 在 PlanBuilder 路由时仍会经过 `_single_skill_route` 的 junk 守卫(unified.py:472),下游防御未缺。判定：不是漏洞。测试 `DISCUSSION_QUERY` 钉死了 prefix 而非 substring 语义 **[executed]**,是好测试。

- **NIT-A1**:junk 的 --json 用 `print()`(main.py:1086),同命令正常路径用 `console.print()`(main.py:1105)。同一命令两个输出通道；注释里“rich 换行破坏 JSON”的论据对正常路径同样成立(既有隐患)，建议下轮统一。
- **NIT-A2**:`AgentRouter.decompose()` 对 junk 返回 `[]`,与合法“单意图无分解”的 `[]` 对 API 调用方不可区分(CLI 有黄字文案，API 无标记)。符合本包规格，但建议在 API docstring 注明。

## 2. B(a) — recall_method 置 None:通过

**[inspected]** 三条汇合路径(budget triage_service.py:230、circuit :243、LLM 失败 ：357)均经 `_last_good_route`,固定 None 在 ：629。“LLM 失败路径本次召回已丢弃故 None 语义正确”的推理成立(prefilter 确实跑了，但其结果喂给的是失败的调用，返回的 route 来自 stale 条目)。全仓 grep 确认 `recall_method` 无其他消费方假设 str 类型。测试钉的是可观测 metadata(`result.match.metadata["recall_method"] is None`)**[executed]**,非实现细节。

## 3. B(b) — 缓存 lookup 前移：通过(1 NIT)

**攻击点 1 回应——语义变化可达且安全，已验证**：

- **可达性 [inspected]**:`try_ai_triage_layer` 在 unified.py:640 无条件调用(Step 2,keyword 路径也到达)，所以“完全无 LLM 的主机现在也能吃到 fresh 缓存命中”在生产路径真实可达，不是只有测试可达。
- **安全性 [inspected]**:(i) 条日本身是历史 LLM 决策;(ii) lookup/store 都对**全量**候选集做哈希(triage_service.py:159 / :349),技能被卸载必改变集合 → 降级 stale → `_last_good_route` 再验存在性(:607);(iii) session-end 守卫每次命中重验(:170-172);(iv) budget/circuit 本就只 gate LLM 成本路径，零成本命中绕过它们与改动前的相对顺序一致。
- **VIBE_AI_TRIAGE_ENABLED=0 不 gate 缓存**：核实 env 只在 `init_llm_client`(:471)生效，config 级 `enable_ai_triage`(manager.py:143)在 ：122 是全量 kill switch——代码注释的声明与实现一致。可接受。
- stale-only 无 LLM 时短路且刻意不给 last-good(:210-211),有测试钉死 **[executed]**,不对称性是声明过的设计。

- **NIT-B1**:env 与 config 两级开关的语义差异只写在代码注释里，用户文档未镜像；建议补 env var 文档，否则“设了 0 还在路由”会被当 bug 报。

## 4. C — index_match_threshold:通过(2 NIT)

**攻击点 3 回应——直接访问无遗漏**：**[inspected]** `try_index_layer` 生产调用方仅 unified.py:734/748(传 `self`);`UnifiedRouter._config` 经 property 类型约束为 ConfigRoutingConfig(unified.py:1233-1240),赋值来源是 `get_routing_config()` 的 RoutingConfig。测试侧 test_index_layer.py 的 7 处 MagicMock router 与 7 处显式 `index_match_threshold = 0.35` 一一对应(114/128/143/177/213/258/289),test_scenario_demotion 直接 patch 函数本身。getattr 兜底确属摆设，移除安全。`lt=1.0` 理由核实:_layers.py:488 `(best_score - threshold) / (1.0 - threshold)`,threshold=1.0 会 ZeroDivisionError,排除正确。默认 0.20 行为保持。

- **NIT-C1**:manager.py:544-545 `get_routing_config` 无 ValidationError 捕获——用户 toml 里 `index_match_threshold = 1.0`(此前是被 TolerantConfig 静默忽略的未知键，_base.py:32)现在会让每条命令崩。与 `min_confidence=1.5` 的既有失败类别一致，不算新级别问题，但这是一个“以前惰性、现在会炸”的键，应进 release note。
- **NIT-C2**(提示性)：已投机写过该键的用户配置将从“忽略”变为“生效”，行为有变——这是本次改动的目的，但属用户可感知变更。

## 5. D — orphan 清理 marker 判定：**BLOCK**

**攻击点 4 回应——有反例，且在主路径上**。向平台 `skills/` 写真实目录的 vibe 路径中，**只有一条**会带上 `.vibe-manifest.json`:

| 路径 | 产物 | marker |
|---|---|---|
| `SkillStorage.install_skill`(storage.py:206-209) | 写入**中心库** | ✅ 写 `.vibe-manifest.json` |
| `link_to_platform` copy 兜底(storage.py:349) | 中心库→平台拷贝 | ✅ copytree 连带 marker(仅因此路径幸存) |
| **`_render_skill_content` 内容命中**(base.py:471-477) | 平台目录**只写 SKILL.md** | ❌ 无 |
| `_render_skill_content` copy 兜底(base.py:532,550-552) | pack 库/源路径→平台拷贝 | ❌ 只有 `.vibe-copy-source`(storage.py:40) |
| pack_installer.py:791-792 | pack 库→平台拷贝 | ❌ 只有 `.vibe-copy-source` |

关键链条 **[inspected]**:`FileBasedAdapter.render_config`(file_based.py:307-318,覆盖 cursor/kimi/opencode)对 manifest 里每个技能 mkdir 后调 `_render_skill_content`;所有 builtin 技能都会被 `find_skill_content` 命中(`_content.py:108-115` 含随 wheel 打包的 `core/skills` 路径)，于是走 base.py:475 只写 SKILL.md——**vibe 自己渲染的主路径产物恰好是无 marker 目录**。Pi 适配器(pi_coding_agent.py:146)同样调用本清理。

**推演执行语义 [executed-by-reasoning]**:builtin/渲染技能从 registry 移除 → 下次 build 走 orphan 分支 → 无 `.vibe-manifest.json` → base.py:207-211 跳过 → stale 目录在平台配置里永久残留(且仍被 agent 平台扫描发现)。M6 之前它是被 rmtree 的。docstring 自己承诺的"prevents stale skills lingering after deleted from the registry"(base.py:159-161)在主渲染路径上失效——清理功能现在只对 symlink 孤儿和中心库拷贝有效。

**测试被改写成迎合新语义而非暴露该缺口**：既有 orphan 测试被反向补造 marker(tests/adapters/test_base.py:405-408);新增"user-owned"测试的 fixture(SKILL.md-only 目录)与 vibe 渲染产物**逐字节相同**——套件固化了歧义。缺一条会失败的测试：“render 流程自己产出的目录能被清理”。

**修复方向**(小改动，方向不必变):`_render_skill_content` 的写文件分支与 copy 分支(base.py:475 / :532)、pack_installer.py:791 拷贝时写入 vibe 所有权 marker;无 marker 才跳过的规则保持。附带 observability 子 nit:跳过只有 debug 日志，renderer.py:116 的 `orphans_cleaned` 计数会静默归零。

---

## 攻击点 5 — 测试钉死行为还是实现：总体合格，一处共谋

junk 守卫测试钉入口行为含 prefix 边界 **[executed]**;triage 测试钉可观测 metadata,用私有属性(`_circuit_breaker.trip`、`_cost_tracker`)是构造状态的合理 seam;config 测试钉校验语义；toml 测试 monkeypatch 私有 `_resolve_config_path` 属必要隔离。唯一实质问题是 D 的回改 fixture(见上)。小 nit:CLI junk 测试钉死了英文文案原文。

---

## 最终结论：**BLOCK**

- A:通过(2 NIT);B:通过(1 NIT);C:通过(2 NIT)。
- D:marker 判定不完备——vibe 自有渲染/拷贝路径(主路径)不写 marker,orphan 清理对其自身主要产物失效，且测试被回改掩盖。必须补“渲染时写 marker”(或等价方案)后再过。
- 其余 5 个 NIT 不阻塞，建议随 D 修复同轮收敛。
