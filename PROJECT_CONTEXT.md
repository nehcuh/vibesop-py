# Project Context

## Session Handoff

<!-- handoff:start -->
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

### 2026-08-27 S50 [vibesop-py] gate46 块2 quickstart 双平台 aha — 已 push CI 全绿

**Session Summary**:
- 标准门流程全闭环：设计稿 → grok+claude-pi 双路确认（v2.1 PASS）→ 实施 → 双路实施复审（均 NEEDS_FIX）→ P1 全清/裁决 → 8 原子提交
- 交付：4 演示技能（双语 keyless）+ quickstart 双语路由演示与注入预览 + `vibe route --hook --platform` 参数化 + CI quickstart-e2e（Linux+Windows 矩阵）
- 关键修复：injector builtin 四级解析阶梯；`write tests` 从 tags 移入 triggers
- 验证：6416 passed / 0 failed；wheel e2e（隔离 HOME + offline）全绿；CI 双 workflow 全绿（run 33082003477/33082003560）

**Next Steps**:
1. GIF 录制（W5 发布 gate；`docs/demo-recording-guide.md`，probe 输出兜底）
2. recall 演示 defer 独立 mini-gate
3. W1 test.pypi 发版无限期 defer
<!-- handoff:end -->
