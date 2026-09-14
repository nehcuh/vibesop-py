你仍负责具体实施执行和报告，Codex监督方向与结果。原360必须已全部terminal、完整保留、不改freeze。

先读：
- /Users/huchen/Projects/vibesop-py/.experiment/sensitivity-decision.md （在主实验早期记录的触发与固定144方案）
- /Users/huchen/Projects/vibesop-py/.experiment/phase4-supervision-notes.md （报告审计与图表问题，先核对最新文件，已修好不重复改）
- 原360 REPORT.md、analysis/audit与原始失败类型。

先落实报告审计纠偏（展示/审计层可修；主执行freeze不可改），并从原始结果确认触发条件：D失败中至少一半为内部stage_cap终止。若满足，直接按已记录方案执行独立144探索性敏感性实验，不再等授权，不要只写计划或只跑一批就停。若不满足，记录未触发并完成报告。

敏感性目的：隔离硬阶段终止机制。仅D_soft在independent-*或exchange-*的stage_budget_exhausted时保留已有history/private artifacts/partial记录并继续原定后续阶段。**不**加预算、不改角色/提示/任务/输入字节预检、不追加摘要调用、不重写报告内容。原流程未产生deliver note则仍缺失，不能凭空合成专家意见。记录soft_close事件。不捕获global T/I/K、API错误、hang、最终integrate的任何失败；它们仍计0。

144 = 相同12task ×2spec × A(原样) / D_soft ×3repeat；seed20260914，固定8并发。全部资源模型工具与原始相同。内部调用须确保D_soft使用原D的stage_caps与run_arm('D')和原有ROLE提示，不能因新标签未命中stage_caps_for而意外拿到无阶段限制。A不启用任何新机制。新A/D_soft同一批随机交错，不能只拿新D和历史A比。保留全部144失败，无选择重跑；不可池化原360。统计使用原冻结analysis的12task配对bootstrap20k seed20260913、10pp阈值，标签明确‘探索性敏感性分析，受主实验诊断启发’，不是独立新任务确认。

实现放独立 docs/experiments/multi-expert-sensitivity/，复制所需原freeze sources保留相对路径、原任务/QA/隐藏验收文件字节hash相同，保存完整code diff、预注册方法、144全manifest、源码冻结hash。前置验证包括：强制独立阶段额度耗尽后确实进入后续成员/整合；总T与各阶段额度不超；global错误与final截断仍失败；A行为未变；任务/隐藏验收与原始一致；独立workspace/ledger/recorder隔离；resume不重跑terminal。先commit+冻结再144调用。不要修改主目录freeze集合；没有必要重跑已通过的全部gold Docker验收，任务hash相同且新控制路径测试已覆盖即可。

运行完144后生成完整机器可读结果、逐次日志、用量审计、探索性CI，至少两例新D_soft具体轨迹（展示soft_close、最终产物与验收），图用标准绘图工具，中文字体必须可读。将主360和补充144并列写入主目录完整中文REPORT.md（另有敏感性独立REPORT.md），保留主报告先前版本Git历史/快照。

报告应回答：硬阶段终止是否解释主实验劣势？软结束后D_soft相对同批A成功率/成本与区间如何？是否达到+10pp？哪些判断仍不能做（纯角色效应未获可用对照、异质专家、整库任务、强弱模型、skills）。不预设新的结果。仍保留两份研究各自的全部失败与统计，不把后续改变叫原方案结果。

费用说明要明确仅参与模型推理估算，排除Grok研究实施、Codex监督、Docker与人力开销。校准75与原360与补充144分别列示。原协议中独立维护者/盲评维护性未实施不能伪称完成。真实项目机制和构造任务关系要准确。

全量完成+报告/图表审计后提交实验branch，不merge/push，结束本轮供最终监督复核。最终交付仍是完整实验报告，不是中间进度。
