# Lane F1 设计 — spec 缺口与注入策略

> Status: DESIGN LOCKED
> 日期: 2026-09-21 · worktree `feat/distill-f1` · 基线 `f57f7faa`
> 输入: `docs/specs/2026-09-21-skill-distill-landing.md`(总计划)、
> research-survey §7 F1 / §9.2 #1、`.omx/artifacts/skill-distillation-review-20260921.md` P1、
> `docs/research/2026-09-09-agent-skills-paper.md`

## 0. 一句话

F1 的结论是「技能的价值以 spec 缺口为前提」。本 lane 把它的两个可操作面做成产品:
**下游**(注入层)给写满的任务书打 report-only 标签 `spec_gap: low|unknown`,注入行为零变化;
**上游**(技能层)新增 `task-briefing` 内置技能,教 agent 在粗任务先写满任务书再执行。
选路径 **C = A + B**。

## 1. 用户是谁、何时触发

| 面 | 用户 | 触发时机 |
|---|---|---|
| B(spec_gap 注释) | 机器消费者:hook JSON 读取方(shell hook wrapper / 未来的 F2 消费分账),以及收到信封的 agent 本身 | 每次 single 模式技能注入且 query 可得时自动评估;无人工触发面 |
| A(task-briefing 技能) | (i) 收到粗任务请求、在执行前应该先写满任务书的 agent;(ii) 显式要求「写任务书 / task brief」的人 | 仅显式 briefing 意图(「写任务书」「task brief」「/task-briefing」等窄触发词)。**不**以「任务模糊」为触发条件——用未验证启发式劫持所有粗 query,是论文笔记禁止项在路由侧的镜像 |

两者都是写任务书的人/路由注入两个受众的分工:B 管已经写满的,A 管还没写满的。

## 2. 「spec 写满」的操作定义(可测试判定)

判定函数 `assess_spec_gap(query) -> "low" | "unknown"`(位于 `skill_injector.py`,确定性、零 LLM):

> `spec_gap: low` ⇔ **长度条件** 与 **信号条件** 同时成立:
> - 长度:`len(query.strip()) >= 150`(对照样本:R6 模型原话「任务书本身就是完整需求文档」的 query、本轮 F1 任务书自身;闲聊/短指令均在 50 字符以下)
> - 信号:以下三族信号中 **≥2 族**命中(每族一个编译正则,bilingual):
>   1. **验收/可验证**:验收、接受标准、acceptance、退出码、exit code、测试通过、tests pass、pytest、全绿、CI green、可验证
>   2. **范围边界(含非目标)**:不要、不得、禁止、不做、仅限、仅在、do not、don't、must not、non-goal、out of scope、超出…范围
>   3. **具体交付物**:路径式 token(`/` 分隔)、输出、产出、交付、deliverable、handback、commit、push、PR、文件
> - 其它一切情况(长度不足、信号 <2 族、空、None、任何异常)→ `unknown`。**fail-open:启发式自身出错时按 unknown,绝不抑制注入。**

设计原则是**精确率优先**:R1-R3/R7 五次平手只证明「写满时注入冗余无害但不增益」,而假阳性
(把没写满标成 low)会诱导 agent 低估技能。所以宁可大量 unknown,只在高置信(长度 + 双信号合取)时说 low。

**误判代价(承认)**:
- 假阳性(low,实际没写满):信封注释建议 agent「任务书优先」→ 可能藏技能。缓解:注释是 advisory 措辞、注入内容一字不少、不跳过任何步骤、拿不准就照常跟技能;且合取条件使假阳性需要 150+ 字符的「看起来很完整」文本。
- 假阴性(unknown,实际写满):维持现状全量强制注入——已知代价是上下文冗余而非正确性损失(五次平手的实证边界)。可接受,不动。

## 3. 产品路径选择:C(A + B)

- **B 单独不够**:评审 P1 的另一半是「22 个内置技能无一承载『先写满任务书』」;只做注释,写满纪律仍只活在文档里。
- **A 单独不够**:「写满场景仍会全量注入冗余技能」的观测面留在原地;F2 的消费分账将来无法按 spec 缺口切片。
- **C 的分工不重叠**:A 管上游(把粗任务变写满——正是 F1「粗糙=显形」半边的预防针),B 管下游(给写满的打标,供 agent 软降级与 F2 分账)。总计划给本 lane 的可写文件本就同时包含技能目录和注入层,选 A-only/B-only 会空置一半授权面。
- **禁止项的落实**:不恢复「每次注入」的讨论(现状注入率不变);不用启发式跳过/抑制注入(B 只注释,不删字节);`unknown` 是默认值而 `low` 是高置信例外——启发式是标签生成器,不是闸。

## 4. 对外契约

| 面 | 契约 | 旧客户端兼容 |
|---|---|---|
| `InjectionResult` | 新字段 `spec_gap: str = "unknown"`;`inject_single_skill(..., spec_query: str \| None = None)` 新可选参数 | 缺省参数,既有调用零变化 |
| `AgentRuntimeResult` | 新字段 `spec_gap: str = "unknown"` | dataclass 尾部追加,默认值 |
| hook JSON(`to_hook_json`) | 新增顶层键 `"specGap": "low"\|"unknown"` | JSON 增量键;仓内无 `to_hook_json` 消费者(实测 grep),shell hook 走 `to_hook_response`——旧客户端遇未知键即忽略;**缺字段一律按 unknown 处理** |
| hook response(`to_hook_response`) | single 命中且 `spec_gap=="low"` 时,`additionalContext` 信封内注入一行 report-only 注释(由 injector 在信封生成,`agent_runtime` 不重复加工);systemMessage(用户可见面)不加 | 注释只在 low 时出现;unknown/notice/no-match/plan 路径字节不变 |
| span metadata | single 模式路由后写 `metadata["spec_gap"]`(值恒有,给 F2 分账做分母) | 新键,既有谓词(has_match/skill_id/mode)不读它,惰性 |
| CLI | 无新 flag;`route --hook` 全链路自动携带(query 本来就是输入) | — |

信封注释措辞(report-only,advisory,不指示跳过):

```
[VibeSOP report-only] spec_gap: low — this task brief already reads like a complete
requirements document. The skill above is injected in full; follow the brief where
it is more specific than the skill. When unsure, follow the skill as usual.
```

## 5. 非目标

- 不改路由匹配器(关键词/TF-IDF/levenshtein/embedding 层的代码零接触)
- 不改 hermetic(`benchmark.py`、数据集、基线文件零写入;基线刷新是 grok Wave 1.5 的事)
- 不当 CI 门禁、不加 required job;spec_gap 永远 report-only
- 不声称「技能无用」/「写满场景技能无价值」——F1 是条件结构,不是排他性结论
- 不跳过、不抑制任何注入;orchestrate/plan 信封不动;notice/no-match 路径不动
- 不解决 R8 盲评结算(「粗糙=显形」半边仍是人评未结算,本 lane 只做预防侧)

## 6. 测试计划

新文件 `tests/agent/runtime/test_spec_gap_annotation.py`:

**golden(应 low)**:
- 长任务书(≥150 字符,含路径 + 验收清单 + 「不要 push」非目标)→ low —— 结构对照 R7 任务书
- 长英文 brief(acceptance criteria + do not + deliverable 路径)→ low

**负例(应 unknown)**:
- 短闲聊「今天天气怎么样」/ "that's all for now" → unknown
- 中长度但只有单族信号(如只提到文件)→ unknown(合取门槛)
- 长但纯叙事无信号 → unknown(长度单独不充分)
- 空串 / None / 会让 `.strip()` 抛错的对象 → unknown(fail-open)

**注入器/运行时**:
- `inject_single_skill(..., spec_query=<长任务书>)`:claude-code payload 含 `[ACTIVE SKILL]` 横幅 + report-only 注释 + 正文完整;`spec_gap=="low"`
- 不传 `spec_query`:payload 无注释,`spec_gap=="unknown"`(既有字节不变)
- `AgentRuntimeResult().to_hook_json()` 含 `"specGap":"unknown"` 默认键
- handle_query 单技能命中后 `result.spec_gap` 与 injector 一致(沿用现有 fake-router 测试模式)
- span metadata 写入 spec_gap(single 模式)
- notice/demote 路径 spec_gap 不产生信封注释(注释只在成功注入体上)

**吸收守卫(人工验证,进 handback 不进步骤)**:
跑 `scripts/eval_routing.py --hermetic` 对照基线 entries——新增技能后 ok1 不得翻转、
不得有任何 query 路由到 task-briefing(61 条数据集无「任务书/task brief」字样,触发词已避开)。
指纹 sha 会因 registry/技能树追加而变(结构性,非行为性)→ `--check` 退出码 3(stale),原因写进 handback,不修 benchmark,不刷新基线。

## 7. 建议 grok 写入 project-knowledge 的 F1 条目草稿

```
F1(spec 缺口)可操作面已落地(2026-09-21, feat/distill-f1):
- 注入层: skill_injector.assess_spec_gap() 给 ≥150 字符且 ≥2/3 信号族(验收/边界/交付物)
  的 query 打 spec_gap=low,信封加 report-only 注释;注入内容零变化,fail-open 到 unknown。
  hook JSON 新键 specGap;span metadata 记 spec_gap(F2 分账可按此切片)。
- 技能层: 新增 builtin/task-briefing(窄触发: 任务书/task brief 显式意图),
  教 agent 粗任务先写满任务书(目标/交付/验收/非目标),对齐 adversarial-panel 的
  When-NOT-to-use/Anti-Patterns/Exit Criteria 质量栏。
- 边界: 启发式精确率优先、只注释不闸;「写满=冗余」是五次平手的条件结论,
  不是「技能无用」;R8 盲评未结算前不得引用「粗=显形」半边。
- 遗留: hermetic 指纹因 registry+技能树追加结构性变更(行为零翻转,eval 已核对),
  基线刷新归 Wave 1.5;spec_gap 与 F2 消费分账的 join 是下一步。
```

## 8. 实施清单(Phase 2 授权范围)

1. `core/skills/task-briefing/SKILL.md` 新建(frontmatter 窄触发;正文含 When NOT to use / Anti-Patterns / Exit Criteria)
2. `core/registry.yaml` 末尾追加 task-briefing 条目(不改既有 id)
3. `src/vibesop/agent/runtime/skill_injector.py`:`assess_spec_gap()` + `SPEC_GAP_*` 常量 + `InjectionResult.spec_gap` + `inject_single_skill(spec_query=...)` 信封注释
4. `src/vibesop/agent/runtime/agent_runtime.py`(仅注释/字段):`AgentRuntimeResult.spec_gap`、注入调用传 `spec_query`、`to_hook_json` 加 `specGap`、span metadata 写 `spec_gap`
5. `tests/agent/runtime/test_spec_gap_annotation.py` 新建
6. 设计文档(本文件)+ `.omx/artifacts/distill-lane-f1-handback.md`
