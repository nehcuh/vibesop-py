# Final Phase：对抗式审查

## 前置条件
- [ ] 所有 Phase 0-N 的改动已实施
- [ ] 所有中间验证 checklist 已通过

## 全量文件清单验证

| 文件 | 阶段 | 验证项数 |
|------|------|----------|
| phase-0-fan-out-diagnosis.md | Phase 0 | 3 项 |
| phase-1-路由层改造.md | Phase 1 | 2 项 |
| phase-2-引擎重写.md | Phase 2 | 2 项 |
| phase-3-适配器扩展.md | Phase 3 | 2 项 |

## 安全审查
- [ ] 无命令注入风险（不拼接用户输入到 shell 命令）
- [ ] 无路径遍历风险（已验证所有路径参数）
- [ ] 无子进程权限泄露（子进程不继承多余权限）
- [ ] 无 DoS 风险（循环/递归有边界限制）

## 编译验证
- [ ] `uv run pytest tests/` 全部通过
- [ ] 无 import 错误
- [ ] 无类型错误（如使用 type checker）

## 功能验证清单
- [ ] [phase-0-fan-out-diagnosis.md] 所有 P0 问题已识别并列出涉及文件
- [ ] [phase-0-fan-out-diagnosis.md] 文件依赖关系已描述
- [ ] [phase-0-fan-out-diagnosis.md] 分析报告格式符合要求
- [ ] [phase-1-路由层改造.md] Phase 1 的实现符合需求描述
- [ ] [phase-1-路由层改造.md] 现有测试全部通过
- [ ] [phase-2-引擎重写.md] Phase 2 的实现符合需求描述
- [ ] [phase-2-引擎重写.md] 现有测试全部通过
- [ ] [phase-3-适配器扩展.md] Phase 3 的实现符合需求描述
- [ ] [phase-3-适配器扩展.md] 现有测试全部通过

## 输出
确认所有验证项通过后，输出最终完成报告。


### 技能路由提示

在执行本阶段的每个步骤时，如果遇到需要选择工具的决策点，
请运行 `vibe route "<当前子任务描述>"` 来动态选择最合适的技能。
