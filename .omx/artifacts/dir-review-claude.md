核验完成(14 处代码/数据证据)。先给核验结论，再逐题裁决。

---

## 0. 包内事实核验结果(影响裁决的增量信息)

**证实**：F1 生产不可达(clustering.py:328-331 同源投影，`zip(strict=True)` 只可能被手工 fixture 触发)；F2 assert 是刻意 fail-loud(skill_promote.py:798 注释明说)；F3 机制(name=query 截断 :978-979,description=模板样板 :980-984);F6 可触发(存量 query 实含 `\n\n` 和 700+ 字符，queries_block :985-988 不折叠不截断)；F5(routing_pending.py 仅 `threading.Lock`,unified.py:1139 每次路由新建实例全量重写)；_WEAK_MATCH_LAYERS 只标记不修路由(routing_pending.py:349-372);auto-config.yaml 已活在语义索引里(`project/auto-config.yaml/auto-config` + LLM 生成 description);`vibe skill add` 六个 Phase 无索引重建且完成文案宣称 "ready to use!"(skill_commands.py:536-545);global 安装路径 bug 实锤(skill_installer.py:59 相对路径 + 全局 `project_path=~/.vibe` → `~/.vibe/.vibe/skills/`,不在 candidate_manager.py:239-245 发现路径)→ 从“疑似待验证”升级为已证实。

**修正**：包内说 pending “全部 levenshtein@1.0 或 no-match 入队”——实际 **4/7 levenshtein、3/7 纯 no_match**("可以"、"/debug"、"route my query")。纯 levenshtein 门限最多清 4/7,“错误路由和队列噪音一起消失”高估了。

**新证(包内没有的)**：
- LevenshteinMatcher 的病根是**分母幸存者偏差**(strategies.py:530-547):只对通过 0.7 阈值的 token 求平均，未匹配 token 被丢弃不计 0——“使用 review” 只有 "review" 计分所以 1.0。不是“短 query”问题，是覆盖率信息被 scorer 扔了。
- unified.py:182-183 自述“各 matcher **并行**跑、max confidence 获胜——非串行兜底”，与文件头 ：11 “keyword → tfidf → embedding → levenshtein” 的串行设计注释**互相矛盾**——虚报 1.0 的层在并行 max 里系统性压过校准层。min_confidence 默认 0.3、auto_select 0.6(manager.py:133-134)。
- instincts.jsonl(现已 15 条，本会话又新增 6 条)**全部 success_count=0** → auto-boost 分支从未触发过；且发现 auto_routing 自动抽取无源头过滤(详见盲区 1)。

**待验证**(未及核验，不构成结论依据)：dashboard/server.py:477-482 assert 先例；triage_recall 无余弦阈值(仅证实 `_candidate_text` 因 id 恒非空 ：177-188);promote `--scope global` 目标 `~/.vibe/skills/` 是否由 pool/symlink 另路发现；scripts/eval_routing.py 的 eval 集构成。

---

## 问题 1:Review Checklist 折中设计——通过，但需加一条机械强制

**结论**：保留，条件是激活路径强制执行“未删 Checklist 不得激活”；若不加强制，则砍。

**理由**：僵尸化的三个成因是条目与数据脱钩、无人被迫读、可橡皮图章通过。折中设计逐条引用草稿真实数据(改写 name/description、确认 queries 单一性、span 埋点名改指令步骤、“何时不该用：____”填空)，前两个成因已消解——数据缺位时条目自曝(如 queries 空时模板写 "(no representative queries recorded)",checklist 引用它就逼人处理)。但第三个成因没消解：我核验了现状，模板 footer 只有纯 advisory 的 "Edit before use"(skill_promote.py:1081-1082),(delete before activating) 若也只是标题文案，和 footer 一样是装饰，僵尸化风险真实。机械强制很便宜：发现/激活路径对仍含 `## Review Checklist (delete before activating)` 标记的 SKILL.md 拒绝加载或拒绝 sync,checklist 就从“文档”变成“强制读过”的证据。完整领域占位节维持砍——砍方论据(spans 里无验收/反模式信号，嫁接是范畴错误)成立。

**置信度**：高(结论)；中(强制点的具体挂载位置实现时定)。

## 问题 2:levenshtein 门限作为主线——成立，但“长度门限”形态是错的

**结论**：成立且是本轮第一优先级，但应改形为“**scorer 覆盖率修复 + levenshtein 降回串行末位 + 入队信息闸门**”三件套，而不是给短 query 加长度墙。

**理由**：(a) 病根在 scorer:未匹配 token 不进分母，修法是把全部 meaningful token 计入(未过 0.7 的记 0)+ 覆盖率要求——这同时消灭“使用 review”型虚高且**不伤真 typo 修正**("reivew my code" 全 token 高相似，修后仍高分)。(b) 并行 max 聚合让虚报 1.0 压过诚实层；层优先级枚举(unified.py:167)本来就设计 levenshtein 为末位，恢复“仅当高层无果时才采纳”的串行语义即可，合法 typo query 仍能被兜住。(c) 数据证明 3/7 噪音走 no_match 通道，levenshtein 修完它们仍在——需要入队侧信息闸门(见下)。

**误杀风险控制**(用户点名的审视点)：① 不做全局长度门限——"/review"(6 字符)和“使用 review”都是合法短形态，长度墙会误杀；② slash 命令前置精确解析:`/^\/(\w[\w-]*)$/` 且命中技能名 → 走 EXPLICIT 强路由，不进模糊层，保护最典型的短指令；③ 信息闸门按 token 不按字符，CJK 2 字算 1 meaningful token(复用 strategies.py:140-145 既有约定)，“可以”这类 1-token 应答语才被拦；④ 被拦 query 写入 MissCounter 降级不删数据，真误杀会以 frequent miss 浮出；⑤ 同 query 2 秒内配到两个不同技能(待审数据第 5/6 条)证明该层胜者不稳定，降级为末位后此不稳定性不再有路由权力。

**置信度**：高(诊断与方向)；中(覆盖率阈值 ~0.6、是否加 0.55 置信 cap,需 eval_routing before/after 校准)。

## 问题 3:auto-boost——整段拆除，不做改形

**结论**：拆除 boost 分支，保留 decay 侧；“只调 confidence 不加 success_count”的改形否决。

**理由**：机制链已核验闭合：gold_detection.py:75-77 用 `success_count` 判 gold → boost 直接铸造 gold 信号 → 抬 gold_rate → promote 阈值。改形否决因为 confidence 同样进路由优化(optimization_service.py:328 `find_matching(min_confidence=0.6)`)——伪信号换字段继续污染，还丢掉拆除的语义清晰性。decay 保留的理由是不对称性成立：miss counter 是真实路由失败计数(负信号有外部来源)，正信号唯一合法来源是人(与 unified.py:1105 “auto record_outcome 会毒化 Wilson confidence” 的既有设计哲学一致——boost 是漏网的同款)。**对存量 dogfood 数据影响为零**：15 条 instinct success_count 全 0、success_rate 全 0,boost 从未触发，无需迁移回填，没有任何现有 confidence 是被 boost 抬上去的。附带要求：拆 boost 后，instinct_cmd.py:846-855 那段“为 boost 可达性而遍历全部 instincts”的长注释必须同步改写，否则留下僵尸注释误导后人。

**置信度**：高。

## 问题 4:Tier 划分——骨架合理，4 处调整

**结论**：整体维持提案方框架，调整如下。

1. **“promote 文案补提示”从 Tier1 降格项升为 Tier1 实修**:`vibe skill add` 无索引重建 + 完成文案谎称 "ready to use"(skill_commands.py:536-545)是**每次安装都踩的激活断点**，且是 P0 装 oneshot-web-spec 的直接前置。Phase 6 做增量索引该技能；做不了至少把文案改为“运行 `vibe skills index` 前不可语义路由”。停在“提示”是 Tier3,真钩子是 Tier1。
2. **auto-config.yaml 污染 Tier3→Tier2**:已实证活在当前索引，是 F3“空壳+强 profile”的活体案例，且揭示 discovery 接受非 SKILL.md 文件——修法便宜(索引/发现侧只认 SKILL.md + 清一次存量)，不是假设卫生问题。
3. **global 路径 Tier3→Tier2**:从“验证”变“修”(双重 `.vibe` 已实锤)；且发现 sibling:promote 全局目标 `~/.vibe/skills/`(skill_promote.py:1029)同样不在 `_build_search_paths`,与 installer 的 `~/.vibe/.vibe/skills` 两处约定不一致【待验证 pool/symlink 是否另路发现】——修必须统一，不能各修各的。
4. **被低估的**：P0 的 before/after eval 没定义 query 集构成。若拿 routing_pending 那 7 条垃圾当 eval 集，结论无效。集必须含：真实历史 query(spans)+ 垃圾反例 + 与 oneshot-web-spec 语义相邻的 query(抢流量检测)。**被高估的**：F2(python -O 对本地 CLI 威胁模型牵强，注释明说 fail-loud 刻意；维持 Tier3 或干脆记录决定后不动)。

**置信度**：高(4 处各有代码证据)；中(第 3 处的 promote-global 半边)。

## 问题 5:盲区(3 个，均有数据实证)

1. **auto_routing instinct 自动抽取无源头过滤**——包内完全未提，且是弱层垃圾的**第二条传播链**:instincts.jsonl 实证每次路由(含弱层)都自动铸造 instinct(conf 0.5):"review my code"→fuck-my-shit-mountain、"nonsense query..."→session-end、100+ 连发 "debug" 的退化 pattern、**本次评审会话自己的完整 prompt(含换行、700+ 字符)也被全文存为 pattern**。这些 pattern 正是 feedback-collect decay/boost 和 `get_instinct_for_query` 的操作对象——队列之外，instinct 库在被直接下种。需要：弱层/低置信命中不 auto_extract + pattern 卫生上限 + 存量清理。
2. **`<user_query>` 标签残留进匹配管线**:pending 第 1 条证明部分平台 hook 把 XML 包装 prompt 原样送入路由，"user"/"query" 成为真实 token 参与匹配。修 Q2 若不做 query 预清洗(剥标签)，门限会被标签噪音绕过；也是 “route my query” no_match 的可能成因。
3. **两处全局路径约定分裂**(Q4-3 已展开)：installer 与 promote 各写各的全局目标，且都不在发现路径——这是 sibling-feature 审计教训的现行案例。

---

## 修订后方向清单

**Tier1(错误路由止血 + 信号链保真)**
1. levenshtein 校准三件套：scorer 覆盖率修复(未匹配 token 计 0)+ 恢复串行末位语义(或 0.55 cap,二选一经 eval 定)+ slash 精确解析前置
2. 入队信息闸门：剥 `<user_query>` 类标签 → 最低信息检查(token 计、CJK 约定)→ 拦截写入 MissCounter 不入队(P2 原案的有效内核在此吸收)
3. feedback-collect boost 整段拆除(含 ：846-855 注释同步改写)
4. F3 description 从代表性 query 派生 + F6 queries_block 折叠截断
5. F5 routing_pending cross_process_lock
6. skill add 激活断点实修(Phase 6 增量索引或改文案)——P0 的前置

**Tier2**
7. Review Checklist 节 + “未删不可激活”机械强制
8. auto_extract 源头过滤(弱层不建 instinct)+ pattern 卫生 + 存量清理
9. auto-config.yaml 污染：发现/索引只认 SKILL.md + 清存量
10. global 路径统一修复(双重 `.vibe` + promote 全局目标一致性 + 发现路径补齐)
11. triage_recall 最低余弦阈值【待验证部分】

**Tier3**
12. P0 oneshot-web-spec 装池 + before/after eval(依赖 6;eval 集构成按 Q4 要求)
13. F2 assert 显式守卫或记录“维持 fail-loud”决定

**维持砍**：F1、完整领域占位节、P2 原案位置(内容已被 2 吸收)、skill-craft profile 机制。

**与提案方的主要差异**：① Tier1 的“promote 文案”升级为“索引激活实修”(文案版降 Tier3);② auto-config 污染与 global 路径从 Tier3 验证项升为 Tier2 修复项；③ 新增盲区 1(auto_extract 过滤)整条进 Tier2——这是四路评估和提案方都没看到的第二条污染链；④ levenshtein 主线的形态从“加门限”改为“修 scorer + 降层级”，理由是长度门限会被 "/review"/“使用 review” 这类合法短形态误杀，而 scorer 修复对真 typo 无损。
