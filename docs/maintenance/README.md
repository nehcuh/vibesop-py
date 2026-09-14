# 项目维护与恢复

- [2026-09-14 定位与版本文档同步](documentation-refresh-2026-09-14.md)：README、定位、发行状态与验证范围。
- [2026-09-14 清理结果](cleanup-result-2026-09-14.md)：已完成操作、验证与保留项。
- [批准的整理方案](cleanup-plan-2026-09-14.md)：原始盘点和处置范围。
- [worktree 清单](cleanup-inventory-2026-09-14.json)：原始分支、改动数量与归档位置。
- [文件迁移与证据映射](cleanup-migration-2026-09-14.json)：旧路径、新路径及哈希。
- [验证记录](cleanup-verification-2026-09-14.json)：Git、归档和链接检查。

## 本地恢复入口

冷归档位于仓库旁边的 `../vibesop-py-archives/2026-09-14/`，包含完整恢复说明、Git bundle、26 个旧工作目录的快照和补丁，以及已结算实验的原始 runs。这是同盘恢复材料，不是异地备份；其中有仅存在于本机的未提交成果。

从主目录恢复任一旧 worktree 到一个不存在的新路径：

```sh
uv run python ../vibesop-py-archives/2026-09-14/restore_worktree.py vibesop-health-grok /absolute/path/to/restore-directory
```

脚本在原提交上创建 detached worktree，恢复暂存/未暂存补丁和工作文件，并校验内容及 Git 状态；不会移动已有分支。归档时保留了所有分支和 stash。Python 虚拟环境需按需运行 `uv sync` 重建。

## 后续约定

- 每条研究线只有一个登记入口，明确“设计期 / 执行中 / 中间结果 / 已结算”。当前状态写在索引里，冻结原件保留历史口径。
- 结论和小体积证据放入 `docs/research/` 或对应实验目录；大体积运行轨迹保存在有校验清单的冷归档。归档数据不是 Git 克隆自带文件。
- 过程评审按主题进入 `docs/archive/reviews/`，保留 brief → 独立意见 → 终裁关系。计划只有在确认完成或被替代时才归档。
- 文章的当前稿、预览、配图与历史稿放在同一个文章目录。
- worktree 收口前保存独有提交、暂存区、工作区、未跟踪和 ignored 证据；校验恢复后再移除目录。保留分支不等于保存了未提交成果。
- 不把历史 AGENTS.md 当作目录指令，不把尚未完成的实验按旧状态清空。
