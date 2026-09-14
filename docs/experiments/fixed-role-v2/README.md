# 固定角色委员会 v2

**状态：未完成，保留工作目录。** 本页在 2026-09-14 目录整理时建立，依据已有记录登记，不代表新执行或独立复验。

## 阅读顺序

1. [2026-09-14 00:26 中间发现](../2026-09-14-fixed-role-interim-findings.md)：241 条原正式终态；另有 4 条已启动缺终态、115 条未启动；完整 360 次主实验和独立 72 次人数诊断尚未完成。
2. [设计期协议](../fixed-role-committee-v2-protocol.md)及[矩阵](../fixed-role-committee-v2-matrices.md)：保留历史原文。“未启动”描述的是设计期，不能覆盖后续运行记录。
3. 本地 `.experiment/v2/`：运行记录、冻结凭据、评审裁决和修订证据。
4. 本地 `.experiment/worktree/docs/experiments/fixed-role-v2/`：实验实现、角色包、任务、验收器和基线；该目录的 STATUS.md 也可能是较早状态，须结合时间戳与运行凭据阅读。

## 保留范围

实验分支 `codex/fixed-role-committee-v2` 在清理时有 32 个 main 历史之外的提交，以及未提交成果。此次没有合并、重置或删除该 worktree，也没有重跑、补算或修改冻结数据。

仅移除了作者侧 Rust `.verify-cache/target/` 编译输出。Cargo 下载缓存、基线、日志、运行轨迹和候选产物均保留；再次运行原验证脚本时会重新编译。

本地路径与版本见 [evidence-manifest.json](evidence-manifest.json)。
