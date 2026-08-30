# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-08-30 S53 [vibesop-py] R6 弱模型 A/B 全闭环 + 验证报告 push + 公众号调研报告

**Session Summary**:
- R6 弱模型 A/B（27B 双臂）收官：treatment 22/25（10 文件 2503 行、25 项物理自验全过）vs control 两次尝试零产物（思考循环撞帽 ×2）。treatment 死因为 oMLX 内存守卫中止 prefill（8.11M tokens，死前文件已齐）
- **核心发现**：技能内容从未进入 treatment 上下文——27B 路由 2/2 no-match、0 次 SKILL.md 读取（R5 强模型 80 次）；赢因 = VibeSOP 静态脚手架 + n=1 方差。弱模型格结论：路由层是第一瓶颈，注入效果在路由质量解决前不可检验
- 验证报告同步远程：`855de0a`（R1-R6 总报告 + R6 预注册/报告）CI 绿；连带修 CI 时序 flaky `05d9e29`（indexer 并行断言拉宽双侧裕度），双 run job 级全绿
- 公众号深度调研报告成稿：`.omx/artifacts/ab-validation-wechat-deepdive.md`；R6 产物可访问 http://localhost:8803
- hook 误触发第 4 例现场证据（纯写作请求被编排成 4 角色 squad）

**Key Decisions**:
- R6 treatment 死于 oMLX 中途故障但产物已齐 → 不按预注册规则 5 作废（故障未污染结果，只吞收尾说明）
- CI 时序断言修复原则：拉宽双侧裕度（加大 sleep）而非只挪上限线
- 弱模型格下一实验方向：路由质量，非注入效果

**Next Steps**:
1. R5 第二轮人评（用户，8801/8802）——零增益序列封盘前最后一步
2. P3 backlog 4 项：factory ollama model 透传 / enable_orchestration hook 路径 / multi-intent 输出形状被 grok 丢弃 / cron-prompt 路由 FP
3. 公众号发布（用户侧拿稿）

### 2026-08-28 S52b [vibesop-py] Claude Code 2.1.220 hook 形态翻转 → PR #115 merged

**Session Summary**:
- 用户报告 S51 修复后 hook 仍每条 prompt 127。实机探针（`claude -p` + `--settings` + 探针脚本分文件落日志，4 形态对照）证实 2.1.220 宿主改为 `bash -c` + **会话 CWD** spawn hooks——config-relative `hooks/<name>.sh` 按 CWD 解析，S51 依赖的 path-join 行为已消失
- 修复 PR #115（`f981aac` → merged `f6f32c6`）：生成器两平台统一 `bash <posix-abs>`（唯一新旧宿主双稳形态）；rewrite 升级 legacy 形态（config-relative 需 config_dir 推导）；verify 判定反转（config-relative 全平台 unsafe）；e2e 形态断言收紧
- 验证：全量 6386 passed；真机外部 CWD 点火零报错 + route/mirror exit 0；PR CI 11/11 job 绿（Windows lane 首跑即绿）；本机 `~/.claude` 已重部署
- 教训入 project-knowledge.md（08-26 quoted-POSIX 条目标注已证伪）

**Key Decisions**:
- 唯一跨版本稳形态 = 无引号 `bash <posix-abs>`；引号形态虽在 2.1.220 可跑但仍拒绝（老宿主 path-join 未灭绝 + 与最稳形态不一致）
- config-relative 无 config_dir 推不出绝对路径 → 保持字节原样（低置信不动用户配置），由 verify 标记
- 规范形态必须对用户实际版本实机探针钉死；hook 修复验证必须「外部 CWD」真实点火

**Next Steps**:
1. main post-merge CI 3 run 收尾（CI/E2E/CodeQL @ `f6f32c6`，后台监控中）
2. S52 深度治理主线：六路诊断（分支已建；存量 skill_auditor 1 fail 在该分支）
3. Dependabot 9 PR：小版本批量合，openai/anthropic major 单独评估
<!-- handoff:end -->
