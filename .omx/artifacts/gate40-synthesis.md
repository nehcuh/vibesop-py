# gate40 综合裁决稿：止血与真实痛点（r2，三路评审收敛后）

> 日期：2026-08-23 · 流程：三路独立对抗 → 综合 r1 → claude+pi+grok 三路评审（均 PASS_WITH_NITS，0 BLOCK；9 MAJOR + 13 NIT）→ 本稿 r2
> r2 修订与正文回写同一动作完成，逐条处置见 §8。主项机制**按评审重设计**：环境变量方案废弃，改 Python 侧 `local_files_only` + 显式重试。

## 0. 裁决总览

| 项 | 裁决 | 关键证据与修订 |
|---|---|---|
| **hook 冷启动 HF Hub 在线等待** | **进，主项；机制改为 Python 侧共享加载 helper** | 测量档案 gate40-hook-coldstart.md：online 中位 17.7s（Lane C 批 34.8s）→ offline 4.4s，4x 下界两批稳定；grok 发现 Grok hook timeout=10s（grok_build.py:189）**今天就在杀进程** |
| 项 5 evaluator Counter | **进** | 热点 evaluator.py:201-204 O(distinct×records) 实测 2915ms→单遍 92µs；诚实论证=二次复杂度随增长必咬人（真实量级今已亚毫秒，pi 复核）；optimization_service 不加缓存 |
| 项 4 空 skill_id | **进，rescope 为纯遥测写值 + 读侧 sentinel 排除** | 见 §3：property/result.skill_id 一律不动（有注入/instinct 消费者）；读侧 `_route_hit_skill_id` 加 "fallback-llm" 排除（fire+outcomes 同谓词） |
| 项 2 薄样本 | **进，双 conjunct 版** | F-deprecate = F ∧ ≥30d ∧ total_routes≥3 **∧ routing_accuracy<0.5**；archive 加 ≥3 闸。CHANGELOG 只宣称"证据门槛 1→3 + 质量下限"，不得宣称"质量 vs 用量已修复"（pi）；薄 F 真空区披露 |
| 项 1 dashboard 五处 | **进，搭车** | 另发现仓内 6 处同型硬编码（recall_cmd/trace_cmd/pool_cmd/dag_rebuilder）记档不修 |
| 项 3 容量 | **砍（记档量化重议条件）** | bridge 单 run >2s 或 spans >100MB；死配置留 hygiene 批 |

## 0.1 换皮回归自查（r2）

- 主项不动模型选择/embedding 语义/EmbeddingMatcher 默认关/`enable_embedding` 默认 False（manager.py:144-154）——只动加载失败路径，grok 换皮核查通过。
- 项 4 不碰三套 trigger 匹配逻辑，也不改 `OrchestrationResult.has_match` property 与 `result.skill_id`（结果契约不动，grok-MAJOR-3 选 (A) 变体）——改的只有 span metadata 写值与读侧谓词。
- 项 2 是 gate38 §5.4 / gate39 §4.2 明文 deferred 的处置语义裁决，非新分数。
- 项 5 同值重算，零行为变化。

---

## 1. 主项：embedding 加载离线优先 + 显式在线重试（r2 重设计）

### 1.1 证据

- 测量档案 `.omx/artifacts/gate40-hook-coldstart.md`：online 16.7/18.4/17.7（Lane C 批 34.8/37.9）→ offline 6.0/4.4/4.1。4x 下界可信；online 恒慢 13-30s/prompt。
- 紧迫性佐证（grok/claude）：Grok hook `timeout: 10`（grok_build.py:189）对现状 16s+ **已经在杀进程**；Kimi 15s（kimi_cli.py:181）、Pi 15s（vibesop-route.ts.j2:51）贴边。
- 加载点全仓共 6 处（三路核实）：`strategies.py:599`、`learner.py:695`、`triage_recall.py:123`、`promote_verifier.py:136`、`_layers.py:403`、`indexer.py:480`；另 `observability/embedding.py:50` 用带前缀名。
- r1 环境变量方案废弃原因（三路收敛）：`HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` 在 huggingface_hub import 时冻结（import 时冻结机制属实，原行号引用有误——pi 勘误），进程内无法翻转重试；缓存目录检测脆弱（partial snapshot/自定义 HF_HOME 误判）；bash 模板方案要求逐项目重跑 `vibe build` 才生效，且 Claude/Kimi hook 模板直接 `python -c AgentRuntime`（vibesop-route.sh.j2:70-82）**绕过 CLI**，"CLI 入口导出"根本覆盖不了。

### 1.2 设计（r2）

- **新共享 helper**（落 `core/observability/embedding.py` 或就近模块，实施时选 6 处共同的最近公共层）：`load_sentence_transformer(model_name)`。**异常分类学钉死（grok-MAJOR-1 + pi-NIT，防"裸 except 重试"把毫秒级 fail-open 变成 13-30s 在线等待、Grok 10s timeout 在 fail-open 前杀进程）**：
  ```python
  try:
      return SentenceTransformer(model_name, local_files_only=True)
  except (ImportError, KeyboardInterrupt, SystemExit, MemoryError):
      raise  # 不重试：非缓存缺失类，原样抛给加载点既有 except
  except Exception:
      return SentenceTransformer(model_name)  # 缓存缺失/损坏 → 显式在线重试（含首次下载）
  ```
  二次异常**原样重抛**（不包新类型——strategies.py:600-604 只捕 ImportError，今天加载失败就冒泡，helper 不得改变各点既有 fail-open 形态：_layers/triage_recall/indexer/promote_verifier 是 except Exception、learner.py:697 吃 (ImportError, OSError, RuntimeError)、strategies 只吃 ImportError）。**helper 无状态**（每调用独立；triage_recall 的 sticky `_model_failed` 等语义归各加载点自持）。
- **缓存探测整个消掉**：未缓存→local_files_only 直接抛→在线重试完成首次下载。HF_HOME/布局/partial snapshot 问题全部不存在。坏缓存=在线重试补全，非静默降级（r1 的静默降级洞关闭）。
- **6 处加载点全部改走 helper**（一处实现，hook/CLI/grok/pi 全覆盖，随包升级自动 rollout，无需逐项目 rebuild）。记录每次加载走了哪条路径（logger.debug）。
- **测试**：mock SentenceTransformer——首次调用断言 `local_files_only=True`；缓存缺失类失败→在线重试被调；**非缺失类单败（ImportError/MemoryError）→零在线调用、原异常原样冒泡**；双败→既有 fail-open 路径不变；离线成功→零在线调用。orbstack e2e 回归（容器内无 HF 缓存→验证首次下载路径；有缓存→验证离线快路径）。
- **超时余量披露**（grok-NIT）：修后中位 4.4s、样本最大 6.0s，对 Grok 10s 余量 ~4s——本 gate 不动任何 timeout 值，CHANGELOG/文档点名，用户面建议另行告知。

### 1.3 明确不做

- 不动模型选择/embedding 语义；不改 EmbeddingMatcher 默认关；不加预热守护进程；不动 bash hook 模板；不动各平台 hook timeout 值。

## 2. 项 5：evaluator 单遍 Counter 修复（r2 钉死）

- `evaluator.py:201-204` 的每技能重建 `all_counts` → 单遍 `Counter(r.routed_skill for r in records)`。**钉死形态（grok-NIT）**：`evaluate_skill`（公开方法，无参路径）自己算 Counter（单遍）；`evaluate_all_skills` hoist 一次后经**可选参数**传入（向后兼容的公开签名扩展，非字面"签名不动"——claude-NIT 措辞修正）。这样 `optimization_service.py:180`、`_listing.py:244`、`slash_commands.py:367` 的直调路径也自动降到每调用 O(records)。
- 复杂度论证（pi-NIT 措辞）：O(distinct²×records)（evaluate_all_skills 总量）随数据增长必咬人；不依赖"今天 32ms"的合成规模说法。
- 测试：现有评估值断言零改动=回归证明；合成数据耗时上界断言（松阈值）；修后复测数字进 commit message。

## 3. 项 4：空 skill_id —— 纯遥测写值对齐 + 读侧 sentinel 排除（r2 rescope）

### 3.1 根因（三路实测合并，口径钉死）

- **化石群**（hook，≤2026-08-21T03:06Z）：M12 修复（0d5f9d4，08-21T06:03Z）前 mode-derived `has_match` 属性在 intercepted miss 上恒 True。pi 独立口径：outcome-joined 空 skill_id 85 行全 hook 全 ≤08-21；grok/我原口径 37/2437（仅 outcome join 范围）。**两口径数字都录入档，谓词写清**（gate37 修订 G 纪律）。
- **活洞群 A**（CLI orchestrated all-fallback，本仓 08-18~23 持续产）：`OrchestrationResult.has_match`（models.py:791-795，`primary 非 fallback ∨ plan.steps 非空`）在 all-fallback 计划下为 True → cli/main.py:903-914 写 has_match=true + skill_id=""。**CLI 语义落后 hook 侧**（agent_runtime.py:557-559 all-fallback 判 miss）。
- **活洞群 B**（hook，steps[0]-fallback）：本仓 6 行实证（08-17~18，has_match=true ∧ skill_id="fallback-llm"——pi 找到，r1"无实证"表述作废）。
- **分类学补记（pi/grok 确认轮）**：直扫 spans 的 has_match=true ∧ skill_id="" 共 18 行（07-30→08-23 含 single 模式）与 85 行 outcome-join 口径、37 行 gate39 口径是三套谓词三个数字，各有口径已钉；single-mode 空行被空串 guard 排除出 fire、outcomes 落 unjoined，无影响。另：**CLI orchestrated 一律 primary=None**（orchestrator.py:472-478）——今天所有 CLI orchestrated hit（cmspark 69 / 本仓 11）都写 skill_id="" 不进 fire；§3.2 修复后其中有真步的将开始进 fire（增量披露义务见 §3.2）。`agent_runtime.py:560-563` router_matched 取 any-real-step 而 skill_id 无条件取 steps[0]。

### 3.2 改动范围（钉死：只动 span metadata 写值与读侧谓词）

- **不改** `OrchestrationResult.has_match` property（结果契约；JSON/确认流/用户体验面保持现状）；**不改** `result.skill_id`（:653 注入门控与 :727 instinct bridge 是其消费者——claude-MAJOR-3）；hook 侧 `skill_name`/`alternatives` 也不动（grok：只改 skill_id 会自相矛盾）。
- **CLI span 写点**（cli/main.py:903-914）：has_match 写值改为与 hook 同谓词（primary 真命中 ∨ 任一步真技能）；skill_id 取 primary 或首个真步，all-fallback → has_match=false + skill_id=""。**top_skills 门（:925）与内容同步改走新谓词**（pi-NIT：门注释明写"与 has_match 同表达式"，不改则同一条 span 内 metadata 自相矛盾；grok-NIT 二选一裁定：top_skills 是 gate38 新遥测、零消费方、非结果契约——与 span skill_id 同谓词构建，保持 span metadata 自洽；tests/cli/test_route_cli_task_id.py:247-251 的"同一表达式"文档同步改写）。
- **hook span 写点**（agent_runtime.py:668/:692 区域）：span metadata 的 skill_id 与 top_skills 取首个 real-skill 步（all-fallback → ""/键省略），不改 result 对象本身（:653 注入门控、:727 instinct bridge 消费 result.skill_id 不动）。
- **miss 侧对称钉死**（claude + pi）：两生产者 miss 行 skill_id 一律 ""（hook 侧不再出现 "fallback-llm"；CLI single-mode miss 同样写 ""）。
- **读侧谓词**：`skill_health._route_hit_skill_id`（fire 列与 outcomes 共享）加 "fallback-llm" sentinel 排除。**第三读者裁决（claude 确认轮）**：`recall.py:377-400` `_extract_skill_id` 也是 span metadata skill_id 读者——其 metadata 分支仅处理 dict 形态（磁盘 spans 为字符串形态，故今天实际惰性），为防未来激活后把 sentinel 当技能展示进 recall/W3 replay，同排 sentinel（一行）；若实施时证实分支不触及磁盘 spans 则记档即可——该桶不是技能（其 reask/expired 是路由未命中信号，属发现队列范畴）。**排除行不进 unjoined**（grok-NIT：否则 1088 行塌缩进 unjoined，对账式表面过、语义错）——outcomes payload 加顶层 `fallback: int` 单独计数；对账式 **Σ三列 + unjoined + fallback = hit 总数**。测试钉死：存量 fallback-llm 行→fallback 计数、不进 unjoined、不进 per-skill 三列。
- **量级双向披露（grok-MAJOR-2，CHANGELOG 与测量档必须带数，禁止只说"噪音"）**：cmspark 实测 fallback-llm = 30d fire 1061/2822（37.6%，当前最大桶；全时 1088）、hit-outcome 1088/2440（44.6%；其中 1086 为 M12 前化石、2 条 08-23 活洞 B）——排除后 fire/outcomes 技能列掉量如上、整桶移入顶层 fallback 计数；反方向：CLI orchestrated 有真步的将开始进 fire（cmspark 69 行潜在增量上界）。
- **发现池影响披露**（三路核实）：翻转后的 CLI all-fallback miss 进 gold_detection 发现池（合法，gold_detection.py:134-143 明示接纳 CLI miss）；bridge `_is_miss` 排除 CLI 故 outcomes 不受污染；miss_counter 不经此路径（cli/main.py:1019 门是 mode=="single"）；MAX_PENDING=50 水位机制在案。~13 行/天量级无风险。
- **docstring 同步（gate17 惯例，claude-NIT）**：gold_detection.py:125-129"the CLI path always did [write the real match verdict]"与 :116-117"producers…excludes the fallback_llm sentinel"恰是活洞群 A/B 的反面记载，必须随本项改写。
- 存量化石行不回写（gate39 unjoined 已兜住）。
- **测试**：all-fallback orchestrated → span has_match=false、skill_id=""（property 不变 pin：result.has_match 仍 True）；首步 fallback+次步真 → span skill_id=次步、has_match=true；hook 同款；读侧 fallback-llm 行不进 fire/outcomes 桶、进 fallback 计数；对账式含 fallback 项；存量 CLI span 测试改动面排查。

## 4. 项 2：F/archive 规则对齐（r2 双 conjunct 版）

- `feedback_loop.py:143-148` F-deprecate：`grade=="F" ∧ days_since≥30 ∧ total_routes < F_MIN_ROUTES` → **`>= F_MIN_ROUTES ∧ routing_accuracy < 0.5`**（双 conjunct——claude-MAJOR-2：单翻 ≥3 不治愈荒诞类，无 exec feedback 时 accuracy=1.0+用得少仍 0.32→F；质量下限把"deprecate=质量差"的语义钉实。模块 docstring 第 4 行"with sufficient data"自证现行 <3 与自述意图相反）。
- `feedback_loop.py:178` archive：加 `total_routes >= F_MIN_ROUTES`。
- **docstring/reason 同步（claude 确认轮）**：`feedback_loop.py:122-127` 规则 docstring（"< 3 uses → deprecate"/"90+ days unused → archive"）与 :152-155 reason 字符串（"only {n} use(s)"）随双 conjunct 同步改写，不只是模块 docstring 第 4 行。
- **新命中总体披露**（grok-MAJOR-2）：修复后 deprecate 仍可触发于"≥3 条路由反馈 ∧ routing_accuracy<0.5 ∧ 闲置 30 天"——这是有意的新人口（真质量差+证据足），CHANGELOG 点名；不得宣称"只对质量差且样本足"以外的任何叙事。薄 F（n=1/2）进入**无 warn/deprecate/archive 的真空区**（pi-NIT），CHANGELOG 单列一句（有意滞留，等真实 feedback 数据再终局裁决）。
- "今天零行为变化"限定表述（pi-NIT）：两个已知 dogfood 现场（cmspark、本仓）feedback 文件均**不存在**（非空文件）。另：archive 的 ≥3 闸作用于 C/D/F 三档（feedback_loop.py:178），薄样本 C/D 的 archive 路径同样关闭——CHANGELOG 一并点名。
- 测试：total_routes=1/2 全组合零处置 pin；≥3+F+30d+accuracy 1.0 → **不** deprecate（质量下限反例）；≥3+F+30d+accuracy<0.5 → deprecate 正例；archive ≥3 闸正例；warn 行为不变 pin。

## 5. 项 1：dashboard 五处镜像（搭车）

- server.py 模块级新建 `_spans_path(vibe_dir)` helper（谓词同 skill_health.spans_file_for:41 / span_writer.py:62-63 内联选择，不镜像 exists-gate）；:137/:195/:296/:330/:344 各一行替换。
- fixture churn 同 gate39 模板 + 一条 dev/prod pin。生产逐字节不变。
- 仓内另有 6 处同型硬编码（recall_cmd.py:150、trace_cmd.py:437/:522、pool_cmd.py:124/:391、dag_rebuilder.py:227）——**非 dashboard、非本项**，记档。

## 6. 记档（本 gate 不做）

1. 项 3 容量：重议条件 bridge 单 run >2s 或 spans >100MB；死配置 span_retention_days/span_max_total 留 hygiene 批。
2. 项 4 化石/结构双群根因（含两口径数字）；`OrchestrationResult.has_match` property 与 result.skill_id 的结果契约问题 → 若未来要对齐属契约变更，需消费者审计 + 独立对抗轮。
3. `vibe skill outcomes <skill> --queries` drill-down → gate41 候选。
4. 薄样本 "?" 化展示面不做；F 规则终局裁决等第一批真实 feedback。
5. 各平台 hook timeout 余量（Grok 10s/Kimi 15s/Pi 15s）——主项修复后余量 ~4s，暂不动。
6. 6 处非 dashboard spans 硬编码（§5）。

## 7. 实施纪律

- 分 commit：主项 / 项 5 / 项 4 / 项 2 / 项 1 各自独立。
- 新碰文件 ruff 双净；测试禁内建 hash()；不动不变量清单。
- 全量 pytest 基线 6234 passed/14 skipped；e2e smoke + routing 7/7；主项加容器内冷/热缓存两态验证。
- 文档：CHANGELOG（主项、项 2 双 conjunct 与新人口披露、项 4 fire 列 sentinel 排除、项 1）、CLI_REFERENCE（outcomes fallback 计数脚注）、测量档案补项 2/4/5 的查询口径（gate37 修订 G 纪律）、check_docs 双过。
- 确认制复审（三路 MAJOR 提出方）→ 实施 → 双路复审（claude+pi）→ push。

## 8. 三路评审收敛记录（r2）

| 来源 | finding | 处置 |
|---|---|---|
| pi-MAJOR-1 / claude-MAJOR-1 / grok-MAJOR-1 | 主项 fallback 未入设计；env-var import 冻结无法重试；缓存谓词脆弱；bash 模板覆盖不了绕过 CLI 的 hook | 采纳→§1.2 重设计为 Python 侧 helper + local_files_only + 显式重试，6 加载点全覆盖，缓存探测消掉 |
| pi-MAJOR-2 | "fallback-llm" 桶读侧不排除（6 行实证推翻"无样本"） | 采纳→§3.1 更正 + §3.2 读侧 sentinel 排除 + fallback 计数 |
| pi-MAJOR-3 / claude-MAJOR-1 | 注入点未钉、6 加载点、import 冻结 | 采纳→§1.2（Python 侧方案天然解决） |
| claude-MAJOR-2 / grok-MAJOR-2 | ≥3 单闸不治愈荒诞类；新命中总体未测未披露 | 采纳→§4 双 conjunct（+accuracy<0.5）+ 新人口披露 + 真空区披露 |
| claude-MAJOR-3 / grok-MAJOR-3 | result.skill_id 有非 span 消费者；property 改不改必须钉死 | 采纳→§3.2 rescope 纯遥测；property/result/skill_name/alternatives 全不动；契约问题记档 §6.2 |
| grok-NIT | timeout 余量点名（Grok 今天已在杀进程） | 采纳→§1.1 佐证 + §1.2 披露 + §6.5 记档 |
| grok-NIT | 项 5 形态含糊（无参路径仍旧复杂度） | 采纳→§2 钉死默认路径自算 Counter |
| grok-NIT | 6 处非 dashboard 同型硬编码 | 采纳→§5/§6.6 记档 |
| pi-NIT | 37/66 数字口径不可复现 | 采纳→§3.1 双口径钉死 |
| pi-NIT | 项 5"32ms 超门槛"是合成规模专属 | 采纳→§2 改复杂度论证 |
| pi-NIT | 项 2 措辞（不得宣称质量/用量已修复；真空区；两现场限定） | 采纳→§4 |
| pi-NIT | 实测无 artifact 违修订 G | 采纳→§7 测量档案补口径；实施时补齐 |
| pi/claude-NIT | 引用勘误（gold_detection.py:160-168、_rotate_if_oversized:133-151、optimization_service:184、evaluate_all 总量复杂度） | 采纳→文内修正 |
| claude-NIT | gold_detection docstring 反面记载 | 采纳→§3.2 同步改写 |
| claude-NIT | 测量档缺冷缓存态 | 采纳→§1.2 e2e 两态验证 |

### r2 确认轮（claude 复审 r2 文本，其 MAJOR 与 pi/grok 收敛）

| 来源 | finding | 处置 |
|---|---|---|
| claude-MAJOR | top_skills 未入钉死枚举，双写点与新谓词不同源会自相矛盾 | 已被 r2.1 覆盖（pi/grok 同指）→§3.2 同谓词构建 |
| claude-NIT | helper 异常契约（原样 re-raise、只捕 Exception） | 已被 r2.1 覆盖（grok-MAJOR-1 伪码） |
| claude-NIT | fallback 计数机制（保留 raw 提取、bucketing 层排 sentinel） | 已被 r2.1 覆盖（grok-NIT） |
| claude-NIT | 第三读者 recall.py:_extract_skill_id | 采纳→§3.2 裁决同上 |
| claude-NIT | 活洞群 B 6→7 行（07-31 还有 1 行 orchestrate） | 采纳→实施时测量档案口径对齐 |
| claude-NIT | feedback_loop 规则 docstring/reason 字符串同步 | 采纳→§4 |
| claude-NIT | optimization_service :180、_listing.py:88、slash_commands.py:383 直调入档 | 采纳→§2 既有修正 |

### r2 确认轮（pi + grok）

| 来源 | finding | 处置 |
|---|---|---|
| grok-MAJOR-1 | helper 裸 except 重试会把毫秒级 fail-open 变 13-30s 在线等待，Grok 10s timeout 先杀进程；六处 fail-open 形态不一 | 采纳→§1.2 异常分类学伪码钉死 + 非缺失类零重试测试 + helper 无状态 |
| grok-MAJOR-2 | sentinel 排除按本仓 6 行写『噪音』，cmspark 量级未测（fire 37.6% 最大桶、outcome 44.6%）；CLI orchestrated 一律 primary=None 的双向影响未披露 | 采纳→§3.1/§3.2 双向数字披露，弃『噪音』叙事 |
| pi-NIT | helper 双败重抛类型与无状态 | 采纳→§1.2（并入 grok-MAJOR-1 处置） |
| pi-NIT / grok-NIT | top_skills 门与内容必须跟新谓词 | 采纳→§3.2 裁定同谓词构建（遥测非契约） |
| grok-NIT | fallback-llm 行不得塌缩进 unjoined | 采纳→§3.2 独立 fallback 计数 + 对账式扩展 + 测试 pin |
| pi-NIT | CLI single-mode miss skill_id 钉 "" | 采纳→§3.2 |
| pi-NIT | 引用勘误 ×3 +『文件不存在』措辞 + archive ≥3 闸及 C/D 档 | 采纳→文内修正 |
| pi-NIT | single-mode 空行分类学 | 采纳→§3.1 补记 |
