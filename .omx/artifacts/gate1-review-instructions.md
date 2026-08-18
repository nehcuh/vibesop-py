你是资深代码 reviewer,对 VibeSOP 路由系统改造里程碑 M1("度量脊柱")做门禁复审。用中文,只给判断和论据,不要客套。

## 背景

VibeSOP 是 skill 路由系统(Python)。M1 的目标是"先修数据再修路由",包含四个子项:
- M1a:修 unified.py `_try_early_layers` 把 Semantic Index 层误记为 AI_TRIAGE 的 routing_path/tracer 污染(4 处枚举值)。
- M1b:新增 scripts/replay_routing.py —— 离线重放 analytics.jsonl 历史日志,--no-llm 模式下只跑确定性层,输出新旧决策一致率/层分布/top-20 变化。
- M1c:新增 scripts/build_eval_from_logs.py —— 从生产日志抽取/去重/分层采样 ~130 条 eval 候选,用 triage 日志弱标注(needs_review),--merge 合并人工确认条目进主 eval 集。
- M1d:src/vibesop/core/analytics.py 新增 LastRouteTracker —— .vibe/last_route.json 记录上次路由(只存哈希),为 analytics 事件追加隐式信号:seconds_since_last_route / is_rapid_reroute(<10s) / query_overlap_with_last(Jaccard>0.5)。锁用 cross_process_lock blocking=False,容错静默降级。

## 此前的设计约束(复审时要检查是否遵守)

1. 最小改动,不引入新依赖,不动无关代码。
2. 跨进程状态文件要防 RMW race,且故障不得影响路由主流程。
3. 旧日志必须可读(只增不改字段)。
4. 已知预存在测试失败 2 个(与本次无关,已在 HEAD 上复现确认)。

## 复审要求

1. 逐文件审 diff,找:正确性 bug、边界条件、并发/race、向后兼容破坏、测试盲区。
2. 特别攻击:M1d 的 non-blocking 锁取舍;M1b 的 old_layer=routing_layers[-1] 启发式;M1c 的弱标注"最新 wins"假设;M1a 是否还有遗漏的误标点。
3. 给出门禁结论:PASS / PASS_WITH_NITS / BLOCK,若 BLOCK 列出必须修复项(编号、文件、原因)。
4. 控制在 600 字内。

## 复审包(完整 diff + 新文件全文)

