# 中间观察：仅校准，不作组织胜负结论

## 1. 模型模式是需要冻结的实验条件

首批 `20260913T010758Z` 的十五次运行全部在首次模型调用处截断。实际 37,799 个 completion tokens 全部属于 reasoning，未输出可交付正文。请求中的 temperature=0 在该 thinking 模式下不生效。不能将十五次错误解释成任务能力失败，更不能比较专家和单体胜负。

## 2. 执行器提前终止可以伪造组织劣势

第二批 `20260913T010956Z` 关闭 thinking 后，C/D 六次运行仍全部被截断规则终止。它们触发的是阶段报告额度，而不是整体额度。该版执行器错误地把内部报告不完整等同于最终产物不可用。修正后需要重新校准全部组，不能保留 A/B 好成绩并只补跑 C/D。

## 3. 完整规格仍可能在分工过程中被误读

第二批 `calibration-intent-v1-E` 的原始规格明确写了：`Exit 0 for success and specified application errors.`

过程链条可在该运行的 call-00 到 call-03 原始响应核对：

1. 规划报告将错误出口改述为“specified application-error code”，只明确了成功时 exit 0。
2. 第二名执行者虽然也收到完整原始规格，仍声称规格没有给出错误码，因此使用惯例 1。
3. 集成产物保留 `_invalid()` 的 `return 1`，最终通过 `sys.exit(main())` 退出。
4. Docker 真实 CLI 验收中，text_type、missing_text、top_level_list、malformed_json 四项失败；正确 JSON 正文不能补救退出码不符合契约。

这是一次有输入、过程、代码与外部验收相互对应的失败。它提醒我们：把 spec 发给所有执行者不等于他们忠实执行，集成仍需逐项核验契约。不能据此推断“分工普遍更差”，也不能断言误读仅由规划摘要造成，因为执行者同时拥有原始 spec。

证据：[该次结果](runs/20260913T010956Z/calibration-intent-v1-E/result.json)、[最终入口](runs/20260913T010956Z/calibration-intent-v1-E/workspace/app.py)、同目录 `call-*-request.json` / `call-*-response.json`。
