---
id: kimi-gated-fix
name: Kimi Gated Fix
description: >-
  对已定位到具体代码的定点 bug,用动态工作流编排「Design 精确 diff → kimi 改动前独立复审
  → 仅 APPROVE 才 Apply → build/类型检查验证」,主会话再对完整 git diff 做 kimi 终审。
  每处改动应用前都经 kimi 把关,适合高风险/怕回归的定点修复。
version: 1.0.0
type: cross-cutting
author: VibeSOP User
namespace: cross-cutting
intent: 已诊断到具体代码位置的 bug → 动态工作流 + kimi 改动前复审 + 构建验证 的定点修复
trigger_when: >
  用户需要定点修复高风险 bug，要求改动前 kimi 复审把关，
  或使用 kimi-gated-fix 工作流确保每一处改动都经独立复审
triggers:
  - "kimi 复审"
  - "kimi review"
  - "改动前复审"
  - "kimi 把关"
  - "定点修复"
  - "/kimi-gated-fix"
  - "kimi-gated fix"
tags:
  - fix
  - kimi
  - review
  - dynamic-workflow
  - verification
  - 修复
  - 复审
  - 把关
  - 定点修复
keywords:
  - kimi gated fix
  - kimi 复审
  - 改动前复审
  - 定点修复
  - surgical edit
capabilities:
  - code-fix
  - kimi-review
  - build-verification
  - dynamic-workflow
category: fix
priority: 70
lifecycle: active
scope: project
enabled: true
dependencies:
  - kimi-cli
  - bash
depends_on:
  - builtin/deep-diagnosis-optimization
allowed-tools:
  - Agent
  - Bash
  - Read
  - Write
  - Edit
  - Workflow
confidence: 0.90
commands:
  - vibe kimi-gated-fix
user_invocable: true
steps:
  - skill: builtin/deep-diagnosis-optimization
    intent: 先诊断定位根因到具体代码位置
    order: 0
    phase: prerequisite
    optional: true
  - skill: kimi-gated-fix
    intent: Design → KimiReview → Apply → Verify 定点修复工作流
    order: 1
    phase: fix
---

# Kimi-Gated Fix — 改动前 kimi 复审的定点修复

> 把「每一处改动应用前都让 kimi 独立复审」固化成可复用的动态工作流。
> 沉淀自 2026-06-28 cmspark tray↔daemon WebSocket 死循环修复(实测 CPU 60%→0%)。

## 何时用

- bug **根因已定位**到具体文件/函数(本技能不做全库审计——那是 `deep-diagnosis-optimization` 的活)
- 改动是**定点**的(几处 surgical edit),不是大重构
- 用户要求「改动前让 kimi 复审」/「kimi 把关」/「严谨验证」

## 前置 / 项目参数(每次按项目填)

| 参数 | 说明 | cmspark 实例(参考) |
|---|---|---|
| `KIMI` | kimi 二进制路径(用户全局) | `/Users/huchen/.kimi-code/bin/kimi` |
| `BUILD_CMD` | 类型检查/构建命令 | `npm --prefix companion run build` |
| `TEST_CMD` | 定向测试(可选;避开已知 hang) | `node --test .test-dist/tests/integration/ws-roundtrip.test.js` |
| 打包/部署 | 落到运行环境的命令 | `make package-macos` + 换 .app + 实测 |

**kimi 调用方式(关键,易踩坑)**:用 Write 工具把复审 prompt 写临时文件,再
`$KIMI -p "$(< /tmp/xxx.md)" --output-format text` —— `$(<file)` 把整段多行代码作为单参数传入,避开 shell 转义。解析输出第一行的 APPROVE/REJECT。

## 流程

1. **隔离改动**:`git checkout -b fix/<bug>-<date>`,保持可回滚。
2. **构造 items**:每处改动写成 `{key, file, why, proposedOld, proposedNew}`
   (`proposedOld` 必须是文件里的**精确原文**,含缩进)。连同 `bugContext`(根因一句话)作为 `args` 传给工作流。
3. **跑动态工作流**(本目录 `workflow-template.js`):pipeline 对每个 item 走
   Design → KimiReview → Apply,最后 Verify。
   - **Design**:Read 核对 `proposedOld` 逐字存在,返回精确 oldString/newString(只读)。
   - **KimiReview**:Write 复审 prompt → 跑 kimi → 解析 APPROVE/REJECT → 返回 `{approved, finalNewString}`。
   - **Apply**:**仅 `approved===true` 才 Edit 落盘**;REJECT 跳过并记录。
   - **Verify**:跑 `BUILD_CMD`(+ 可选 `TEST_CMD`)。
4. **兜底(重要)**:若某 item 的 apply 子代理 stall(实战中遇到过连续 stall 6 次、~2h),
   工作流会丢弃该 item 的结果——主会话手动补:对该 item 跑一次 kimi 复审 → APPROVE 则 Read+Edit → 重跑 `BUILD_CMD`。**不要为单点 stall 重跑整个工作流**。
5. **kimi 终审**:`git diff > /tmp/diff.md`,对**完整 diff** 跑一次 kimi 整体复审
   (APPROVE/REJECT + 有无同类遗漏路径 + 回归风险)。
6. **落地**:按项目机制提交/PR;需要部署的跑打包命令 + 替换 + **实测验证症状消失**
   (别只信编译通过——cmspark 案例里源码编译绿但 `.app` 因 node_modules 依赖漂移启动即崩,最终靠整机重打包 + 实测 CPU 归零才确认)。

## 调用动态工作流

脚本:本目录 `workflow-template.js`。改顶部 `PROJECT CONFIG` 几行后:
- 复制到目标项目,用 Workflow 工具 `{scriptPath: "..."}` 跑;
- `args` 传 `{bugContext, items}`。

```js
// args 示例
{
  bugContext: "tray 把 skill.list 响应当推送 → 再发请求 → 死循环",
  items: [{
    key: "A", file: "src/server.ts", why: "响应透传请求 id",
    proposedOld: "        if (ok) {\n          send(x)\n        }",
    proposedNew: "        if (ok) {\n          send({ ...x, id: msg?.id })\n        }"
  }]
}
```

## 不适用

- 全库审计/未知数量的广泛问题 → `deep-diagnosis-optimization`。
- 一行 typo / 显然小改 → 直接改。
- 无 kimi 环境 → 退化成 design→apply→build,跳过 KimiReview 阶段。

---
*由 skill-craft 从 cmspark 死循环修复会话沉淀。workflow-template.js 是可移植核心。*
