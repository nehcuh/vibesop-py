你是资深代码 reviewer,门禁 3 第二轮复审(聚焦三项收尾修复)。用中文,只给判断,500 字内。

## 第一轮回顾

门禁 3 第一轮双 PASS_WITH_NITS,但 pi 指出 M3b scenario 权威废除在默认配置下空转(≤14 字符 triage 必被 bypass,scenario 照样胜;原始事故案例 13 字仍会被误路由),claude 指出 embedding 缓存无模型版本、垃圾过滤 guard 被 orchestrate/sessions 路径绕过。

## 本轮修复(开发者声明,见复审包)

1. scenario_candidate 存在时 triage force=True,跳过 short-query bypass。
2. embedding 缓存 entry 加 model 字段做失效判据。
3. 垃圾 guard 下沉到 _single_skill_route 头部,route() 入口 guard 保留(遥测跳过)。

## 复审要求

1. 判定三项修复是否闭合;force=True 是否引入新问题(成本/延迟面、与 skip_ai_triage context 的交互、budget/熔断 gate 的关系——注意 M2 后缓存在 gate 前)。
2. guard 下沉后四个调用方路径(orchestrator/sessions/plan_builder/workflow_engine)行为是否安全。
3. 结论:PASS / PASS_WITH_NITS / BLOCK。

## 复审包

