# 定位与版本文档同步 — 2026-09-14

## 结果

项目定位统一为：**围绕可靠 AI 辅助开发的工程工具与实证研究**。SkillOS 保留为技能管理子系统名称，不再代表整个项目。

- 重写中英文 README，保留安装、平台配置、LLM 配置、工作流示例和开发入口，详细命令移交现有手册。
- 新建 [POSITIONING.md](../POSITIONING.md)，将工程工具、实证研究和工程方法的边界写清楚。
- 同步项目状态、工程原则、路线图、项目上下文、架构入口与知识库总览。
- 同步 `pyproject.toml` 的包简介和 CLI 帮助文案；未改变命令行为。
- 删除 README 中缺少可追溯依据的安装耗时/错误率对比、固定准确率/延迟表，以及“经验必然复利”等承诺。测量结果改由研究报告说明条件和出处。
- 去掉状态页“所有计划完成”“全项目 production-ready”的旧总括，不将未合并分支或未完实验列为已发行能力。

## 版本决策

核对来源：`pyproject.toml`、`uv.lock`、运行时包元数据、[PyPI JSON](https://pypi.org/pypi/vibesop/json)、[GitHub Release](https://github.com/nehcuh/vibesop-py/releases/tag/v8.2.0)及 `gh release list`。

| 对象 | 核对结果 |
|---|---|
| 源码、锁文件和本机运行时 | 8.3.0 |
| 最新公开 PyPI / GitHub Release | 8.2.0（2026-09-03） |
| PyPI 8.3.0 / 8.3.1 | 均不存在（核对日） |
| 8.3.1 的来源 | 提交和 CHANGELOG 中的内部修复批次名称 |

本次保留源码版本 8.3.0，并标注未发布。定位更新没有增加 API 或行为，不另升版本；下一次发行依实际变更和兼容范围决定。CHANGELOG 的 8.3.0 节改成未发布源码基线，并保留原基线日期，避免与公开发行混淆。

未创建 release commit、tag、GitHub Release 或 PyPI 发布。

## 实际验证

- `uv lock --check`：通过，锁文件未变。
- `uv run vibe --version`：8.3.0；源码、锁文件、安装元数据一致。
- 根命令和 `route` 的 `--help`：新介绍可见。
- `uv run ruff check src/vibesop/cli/main.py`、`ruff format --check`：通过。
- `tests/cli/test_help_man.py` 与 `tests/scripts/test_typecheck_skill_copy.py`：**21 passed**。
- 本轮核心入口文档本地链接检查：**246 个有效，0 个缺失**。
- `uv build --wheel`：成功；wheel 元数据中的版本、简介与 README 内容已核对。仅本地构建，不上传。
- `git diff --check`：通过。

未运行全面产品回归或模型实验。本轮源码变更仅为 CLI 说明文字和包简介。前一轮清理的“产品文件不变”验证记录属于清理完成时的快照，本次文案变更是后续独立操作。

修改前文件快照和本地构建产物分别保存在 `../vibesop-py-archives/2026-09-14/documentation-refresh-before/` 与 `documentation-refresh-build/`。当前改动与前一轮整理均未提交或推送。
