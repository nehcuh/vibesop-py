全量套件出来了：**5466 passed, 14 skipped** [executed]——与包声明 “1786 passed, 2 skipped” 再次严重不符。所有证据齐了，出复审结论。

---

# 门禁 7b 复审结论(claude 路)

## 一、BLOCK 修复闭环验证 ✅ 竞态真正消除

**[inspected] 修复结构正确**：
- unified.py:771-781——`full_matchers` 读取、swap、第一遍执行、`finally` 复原**全部**在 `with self._route_lock:` 临界区内;`_route_lock` 为 `threading.Lock()`(unified.py:329),全仓唯一获取点即 ：771(grep 证实)，无重入死锁。
- 换的对象与执行对象同一:`pipeline = self._matcher_pipeline`(:763),而 `_pipeline.run_matcher_pipeline` 经 _pipeline.py:29 委托 `router._matcher_pipeline.try_matcher_pipeline`,迭代的就是被换的 `self._matchers`(matcher_pipeline.py:91)。
- 纵深防御:`if len(calibrated) != len(full_matchers)` 守卫使“陈旧 reduced 快照被当 full 复原”这类交错在当前代码形状下不可达(守卫为 False 时既不换也不复原)。

**[executed] 突变测试**(真实 UnifiedRouter + 真实锁 + 真实 matcher 列表，仅替换方法体)：

| 形态 | 结果 |
|---|---|
| 现代码(控制组，8 线程×10 次) | 无损坏，列表 3/3 |
| **M2 = gate7 原始形态**(锁外读 + 无条件换/复原) | **2/2 轮永久丢失 levenshtein(2/3)——测试断言可击杀** |
| M1 = 包内提议突变(仅锁外读，守卫保留) | 状态无害 |

**突变推理答复**：测试对 gate7 原始 bug 形态**真钉死**；但对包内字面提议的“读取移回锁外”(M1)测试**不会失败**——因守卫使其状态良性。残余缺陷只是行为级(M1 下陈旧快照致第一遍被跳过，levenshtein 可间歇参与聚合)，可用 per-call 断言(calibrated 命中查询的 `primary.layer != LEVENSHTEIN`)补杀，非必须。

## 二、五个攻击点

1. **BLOCK**——见上，闭环。
2. **OSA ≥6 边界** [executed]:恰 6 字符异义对**仍可误匹配**：casual/causal 距离 1、score 0.833 ≥ 0.7,端到端可路由(strategies.py:558-563 公式 `1-d/max`)。except/expect=2、form/from=2 被挡；deamon/daemon=1 正确保留。**可接受的残余**：末位兜底语义(前三层全空才落地)+ 弱层命中送人审。但 casual/causal 应作为具名例写入注释/决策记录——现在注释只点名 4-5 字符风险。
3. **wrapped-junk 双重判断**：route() 链自洽(:1017→:1021→:1025,遥测用解包后 query;测试断言 miss/pending 零写入 [executed])。**不一致场景存在，但不在 route() 内**——见新发现 #1。
4. **suppress hash-only**:场景成立(dismiss 后 24h 同串 query 经新技能的人审入口被压)，但仅影响 review 队列、hash 是 lower+strip 精确串(unified.py:1216)复述不受压、legacy 空 hash 回落已测。**可接受**。
5. **锁共存** [inspected]:indexer.py **零锁**(grep 无 cross_process_lock);sidecar `{index_path}.lock` 仅增量路径使用，project/global 路径不同→不会互相等锁，**无死锁**。但互斥单边：并发全量 `skills index` 的整体重写可在增量 merge 后落地覆盖之(窗口窄、可自愈)→ NIT,建议 build_index 收编同款 sidecar。

## 三、自行挖掘的新问题

- **#1(主要)orchestrate/PlanBuilder 路径无 unwrap** [inspected]:orchestrator.py:170 直调 `_single_skill_route`,后者有 junk 守卫(unified.py:495)但**无 unwrap**(:1021 只在 route())。`<user_query>修 bug</user_query>` 经 orchestrate 时 wrapper 原样进多意图检测/分诊/matcher——unwrap 注释(:99-102)声称要解决的生产污染在次路径存活。非本 diff 引入(预存在类)，修法一行(unwrap 下沉到 `_single_skill_route` 头部)。**NIT**。
- **#2 pass-2 锁外瞬态** [executed]:另一线程第一遍持 reduced 列表期间，并发的“全量”第二遍(unified.py:785)及 `_finalize_no_match` 最近邻扫描(:941)静默缺 levenshtein——probe 实证窗口内 typo 查询返回 None(正常应 systematic-debugging@levenshtein)。瞬态降级非损坏 → NIT。**但这是 gate7 claude 明确建议“顺手修”的项，gate7b 既未修也未列入遗留清单——修复清单完整性缺口**。
- **#3 测试计数二次失实** [executed]:包称 1786/2,实测全量 **5466 passed, 14 skipped**(165s);与本仓 gate7 NIT-7(1775 vs 5440/14)同款问题复发。全绿不影响结论，但包的验证声明口径持续不可信。
- **#4 global 降级文案分支零测试** [inspected]:修复 #9 的核心产物(`scope=="global"` + loader None → "project-scope only" 警告)无测试;`test_global_scope_saves_to_global_layer` mock loader 返回技能，锁住的是生产不可达路径(真实 global 安装 SkillLoader 看不见，gate7 pi (b) 已证)。

## 四、遗留清单核对

| 项 | 判定 |
|---|---|
| NIT-e dedup 折叠→alternatives | 接受 ✓(设计变更，no_match 时 miss counter 兜底) |
| NIT-f CJK 确认语 | 接受 ✓,但**“已注释”只部分成立**：routing_pending.py:76-77 是泛化 multi-token 注释，未点名 CJK 确认语类(pi 实测“知道了”/“可以吗”穿透)——补一行点名 |
| NIT-g 闸门在 store 层 | 接受 ✓ [inspected] `try_enqueue` 生产调用方唯一(unified.py:1221) |
| claude NIT-2 闸门边界 | 接受 ✓ |
| CJK 转置门限产品决策 | 记录位置仅 .omx/artifacts 评审包，docs/ROADMAP 无痕——决策应落正式 backlog |
| **不该遗漏的** | gate7 claude 的 pass-2 进锁建议：未修且未记录(新发现 #2) |

## 五、结论

**PASS_WITH_NITS**(0 BLOCK / 7 NIT)

BLOCK 修复闭环成立：临界区完整、守卫纵深、异常复原、原 bug 形态被并发测试击杀 [executed];9 项修复全部落地，目标测试 204 passed [executed]、全量 5466/14 绿 [executed]。所有新发现均为瞬态降级、文档精度或预存在缺口，无一满足 BLOCK 门槛。建议合入前顺手处理：NIT-1(pass-2 进锁或明确记录豁免)、NIT-2(unwrap 下沉);其余按队列。
