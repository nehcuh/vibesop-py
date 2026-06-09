# Phase 1：Review the project's philosophical foundations and guiding principles

## 前置条件
- [ ] Phase 0 诊断报告已完成

## 你必须先阅读的当前文件
- `src/`
- `tests/`
- `docs/`
- `README.md`
- `pyproject.toml`

## 需求

### 任务描述
Analyze the current project's philosophical underpinnings, including its core principles, design philosophy, and any documented mission or vision statements. Identify how these philosophies manifest in the codebase and documentation.

### 目标技能
`omx/analyze`

### 输出变量
`step_1_result`

## 关键实现要点
| 要点 | 实现方式 |
|------|----------|
| 哲学一致性 | 检查所有文档中的核心主张是否自洽，无内部矛盾 |
| 术语一致性 | 同一概念在不同文档中使用相同的术语，无混用 |
| 证据基础 | 声称的指标（如95%准确率）有实际数据或测试支撑 |
| 产出要求 | 每个发现必须附带文件引用和具体证据，非主观判断 |

## 验证 Checklist
- [ ] Phase 1 的实现符合需求描述
- [ ] 现有测试全部通过

---

## 完成条件
执行完本 Phase 后，创建标记文件：
```bash
echo "phase-1 completed at $(date)" > .vibe/prompts/.phase-1-done
```


### 技能路由提示

在执行本阶段的每个步骤时，如果遇到需要选择工具的决策点，
请运行 `vibe route "<当前子任务描述>"` 来动态选择最合适的技能。
