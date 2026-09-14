监督者已完成首12审计，允许继续同一个正式360清单的剩余348，完成全量报告。不要重新征求用户许可。

先读 .experiment 外部的 /Users/huchen/Projects/vibesop-py/.experiment/formal-first12-supervisor-audit.json 和 beliefs.md。审计：360唯一分配；完整source freeze一致；12次全部原始响应input/output/cache==ledger；请求和response/error数量对应；任务hash对应；当前Docker image ID与manifest一致。无调用丢失。

方向判断：
1. 原正式cohort已经冻结，继续原规则，不修改任何freeze source、不更换任务、预算、模型、stage caps、成功门槛或统计；原样留存失败。用 --resume 同一 runs/20260913T023645Z --max-new 348，固定8并发。直到360全部terminal。不要每12次停一次，进展写STATUS；进程错误则保护现有文件，排查执行环境，恢复只选尚未开始项。
2. 首12有5例C/D因 independent-0 阶段2400输出token额度耗尽而全流程退出，未进入hidden eval。这提示**硬阶段终止策略可能主导差值**。最终主结论只能是此特定流程+预算包络的端到端效果，不能把这种失败说成‘专家更笨/多智能体普遍无效/代码更差’。逐类区分stage cap、global T/I/K、I_precheck、API/协议、hidden implementation failures，并统计各组真正进入整合和hidden eval的比例。保留原始例子支持机制解释（推断要标明）。后续可能需要单独的预先声明敏感性实验验证软阶段结束；不要在本cohort偷偷修复。先完成原360，交给监督者判断该后续验证。
3. 发现容器冻结实现与文档的偏差：tasks/common.py 实际仍用tag python:3.12-slim启动，runner只在batch boundary验证image id。不要现在改冻结源或谎称argv已锁digest。报告准确记录‘批次边界ID核对一致，启动argv仍是tag’，保存结束时image inspect。运行期间不要pull/tag更新该镜像。
4. 严格成功定义包含ownership/path违规；检查所有工具记录与notes，不能只看通过隐藏测试。若runner状态与预注册定义不符，保留raw status，列为协议偏差，请监督者仲裁，禁止静默改原始结果。

完整报告要求（中文，面向工程读者）：
- 完成360后才给正式推断，确认每组72、每task30、每task/spec/arm重复3；无missing/running/pending再计算，不从首12推断。
- 使用冻结analysis计算主D-A：12任务等权，配对2spec*3repeat，20000次cluster bootstrap seed20260913；精确报告点/95%区间/+10pp门槛解释。次要比较标探索。
- 每组、task、spec通过率；每组输入/输出/cache/tool/cost均值、中位数、总体；实际价格估算与发票区分，来源链接/计费时段写清。失败机制、阶段停在哪、隐验进入率；不要拿无隐验当代码bug。
- 至少3-5个可点击实际记录案例：spec/模型动作/工具或隐藏反例/错误或成功/能证明与不能证明什么。
- 记录旧45+新30校准与正式360分开，全部中间commit/日志/修复轨迹，原始结果路径与复现命令。
- 用标准绘图库生成可导出图（建议SVG+PNG：各组通过率、资源消耗、失败构成、任务热力图、D-A任务差异/CI）。不要用当前report.py手写固定宽度SVG作正式资源图（值>1会截断）。绘图/中文排版可以另写presentation-only脚本到不在freeze集合的报告目录；不得更改冻结统计实现；明确这是展示层。
- 完整REPORT.md落在 docs/experiments/multi-expert-formal/REPORT.md 并在run目录保留副本，不能只交现在report.py那十行自动摘要。包含实验问题、五组流程图、任务来源/范围、方法、结果、机制、局限、实践建议。结论依据数据；不预设多专家必然输。
- 审计全部360：原始usage+cache对ledger、请求响应/error配对、monotonic IDs、source/task/manifest hash未漂移，检查没有隐藏评估反馈进入模型请求。保存审计JSON和说明，失败不隐藏。

最终将结果/图表/报告和日志提交实验branch（不merge main、不push、不改生产代码），更新外部supervision/results/beliefs。报告完成且审计过后结束本轮headless，我会独立判断重要结果与是否需要敏感性验证。此处先去执行，不要只回复计划。
