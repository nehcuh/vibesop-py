# 留存池洞察挖掘 — routing_eval_retention.yaml(22 条)

> 挖掘日期:2026-08-19 audit 留存 → 2026-08-21 挖掘。retain_until 2026-09-19,
> 到期后按文件头指示 purge。数据来源:`tests/benchmark/routing_eval_retention.yaml`
> (22 条 = 130 条原始生产流量的 17%;12 低信号碎片 + 10 agent-to-agent 提示)。

## 总览:两类流量,两种失效模式

| 类别 | 数量 | 占原始流量 | 路由层表现 |
|---|---|---|---|
| 低信号碎片(续聊/选项回复/探针) | 12 | 9.2% | 无独立路由信号,弱标注几乎全是"当时活跃的工作流"(8/12 riper-workflow) |
| agent-to-agent 提示(子代理指令) | 10 | 7.7% | 意图匹配结构性失效——弱标注近乎随机(UX 验收→design-an-interface;computer-use 研究→mattpocock/review;深度分析→improve-codebase-architecture) |

8-19 的标注审计把这两类移出评分集是对的:它们不含路由 ground truth。
但它们是真实使用模式的原材料,以下是可以落地的四条洞察。

## 洞察 1:续聊流量需要"形状规则",精确匹配列表拦不住(最有行动价值)

当前 `_is_low_information_query`(skill_promote.py:144-171)= 14 个精确匹配
token + 拉丁 ≤4 字符规则。用留存池 12 条实测:**只拦住 1/12**(`B+C`)。

漏掉的 11 条呈现三种清晰形状:

- **续聊前缀 + 计划相位词**:`继续往后做吧`、`继续 Phase2b 和 Phase3`、
  `继续 P2 抛光`、`开始 M1`、`做 D1c` —— 前缀 ∈ {继续,开始,做},负载只是
  相位 token(`M1`/`D1c`/`Phase2b`/`P2` = `[A-Z]?\d+[a-z]?` 或 `Phase\s?\d`),
  无任何实质宾语。
- **选项回复形状**:`1. 接受 C′ 2. D`、`1. 互斥 2. 不禁 evaluate 3. ...`、
  `加吧` —— 枚举/字母选项开头,是对 agent 提问的回答。
- **状态/探针**:`我看下恢复了`、`reply with exactly: claude-ok`。

**行动**:把 `_is_low_information_query` 从"词表"升级为"词表 + 形状规则"
(续聊前缀+纯相位负载;枚举/选项开头的回复),留存池 12 条直接转测试 fixture。
必须带反例防过杀:`清理吧`(标定对,2 字 CJK 带意图)、`继续`后接实质任务
(如"继续处理 backlog 里的 X 文件"——有具体对象则放行)。这是 miss 池的
防污染前置闸,直接护住 M2 的 0.70 余弦阈值(calibration 已证明低信息量
query 在 0.72-0.82 区间cosine-match 一切)。

## 洞察 2:agent-to-agent 提示是可检测的独立流量类别,且自身就是工作流候选

10 条子代理指令有稳定的结构签名,检测特征廉价且高精度:

- 角色开场:`You are an adversarial SKEPTIC` / `You are an independent
  PRODUCT/UX acceptance agent`(全大写角色名)
- 输出契约:`<output-contract>` JSON schema 块(2 条逐字同构)、
  `VERDICT: APPROVE | ...` 结尾行、file:line 引用清单、METHOD 节

**两个方向**:

a) **路由侧**:识别为"编排器→子代理"流量后默认弃权——这类提示不是技能
   请求,发起方(编排 agent)已经知道要干什么,匹配任何用户技能都是噪音。
b) **发现侧(M12 闭环的活样本)**:SKEPTIC+output-contract 模板出现 2 次
   近乎逐字、PI REVIEWER gate 出现 2 次——这正是 M12 寻找的"多次类似、
   处理方式一致 → 可归纳工作流"模式。用户的真实习惯里已经存在一个有结构的
   重复模板:**对抗性子代理复审派发**(角色+取证方法+结构化裁决契约)。
   它本身就是 promote 候选(人工提炼成 skill,非自动生成)。

## 洞察 3:续聊流量的正确"路由"是上一步——会话粘性(routing continuity)

12 条低信号碎片的弱标注里 8 条是 riper-workflow——不是因为它们表达了
riper 意图,而是因为那是**当时活跃的工作流**。对选项回复/续聊指令,正确
行为不是重新匹配,而是"保持在当前技能"。这需要路由层有跨轮会话概念
(CLI 侧 W5.0.A.4 每次调用铸新 session_id,天然没有粘性;agent_runtime
hook 路径有真实 session)。**路线图项**,不进当前里程碑:在 agent 会话内,
当新 query 被判为续聊/选项回复且上一轮有激活技能时,优先保持而非重匹配。

## 洞察 4:流量构成量化——17% 的生产流量不含路由 ground truth

9.2% 续聊噪音 + 7.7% agent 间指令。任何 routing 准确率指标的分母都应先
剔除这两类,否则指标被结构性稀释(本次 91.6% 是在清洗后集合上量的,口径
正确)。后续 build_eval_from_logs 类脚本可考虑把这两个检测器前置,产出
"可路由流量"而非"全部流量"。

## 处置建议(按文件头的 purge 指引)

1. **可做(小改动)**:洞察 1 的形状规则 + 12 条 fixture 转测试——建议作为
   M12 数据积累期的插空任务,走标准 gate 流程。
2. **暂不做**:agent-to-agent 提示**不要**加回评分集——在弃权检测器存在
   之前它们没有 ground truth;检测器落地后挑 2-3 条作 `expect: []` 负例。
3. **保留文件**至 2026-09-19;本报告已提取全部可挖掘洞察,到期可直接
   purge,无需二次挖掘。
4. 洞察 2b 的"对抗性复审派发"模板,等 M2 出口重验(miss 池 ≥30)时
   对照真实 miss 簇确认是否自然浮现,浮现则走 promote 人工提炼。
