# Phase 3：Review the code implementation quality and standards

## 前置条件
- [ ] Phase 0 诊断报告已完成
- [ ] 以下前置步骤已完成：
- Phase 2: Review the architectural design of the project (`ls .vibe/prompts/.phase-2-done`)

## 你必须先阅读的当前文件
- `src/`
- `tests/`
- `docs/`
- `README.md`
- `pyproject.toml`

## 需求

### 任务描述
Review the code implementation for adherence to coding standards, best practices, readability, maintainability, and potential bugs or anti-patterns. Focus on the main source files and recent changes.

Context from previous steps:
- Review the philosophical foundations and guiding principles of the project (completed)
- Review the architectural design of the project (completed)

### 目标技能
`omx/code-review`

### 输出变量
`step_3_result`

## 关键实现要点
| 要点 | 实现方式 |
|------|----------|
| 类型安全 | TypeScript/Python 类型标注完整，无 any 滥用 |
| 错误处理 | 所有错误路径有处理，无空 catch，错误信息有上下文 |
| 资源管理 | 连接/文件/定时器在停止时正确清理，无泄漏 |
| 安全审计 | 检查命令注入、路径遍历、敏感信息泄漏风险 |

## 验证 Checklist
- [ ] Phase 3 的实现符合需求描述
- [ ] 现有测试全部通过

---

## 完成条件
执行完本 Phase 后，创建标记文件：
```bash
echo "phase-3 completed at $(date)" > .vibe/prompts/.phase-3-done
```


### 技能路由提示

在执行本阶段的每个步骤时，如果遇到需要选择工具的决策点，
请运行 `vibe route "<当前子任务描述>"` 来动态选择最合适的技能。
