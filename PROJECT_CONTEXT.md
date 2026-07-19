# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-07-19 (S32) Windows 兼容生产化 — 多 agent 动态工作流
**Session**: Windows 环境从零搭建（uv + Python 3.12）→ 88 failed 基线 → 设计/对抗/开发/评审/验证多 agent 工作流 → 0 failed + CI 全绿。
**Completed**:
- 根因分析（4 agents）：6 桶 88 失败，9 个真实生产 bug；全套文档 `docs/dev/windows-compat/`（01-06 + README）
- P0-P4 开发：编码显式 utf-8 统一 + `utils/encoding.py` locale 回退（治 GBK 自毒）、`utils/symlinks.py` 能力 probe + `.vibe-copy-source` marker、shlex 反斜杠转义+posix、tracker/badges fd 泄漏修（Windows 状态曾永不落盘）、`_isolated_home` 三层测试隔离、CI `test-windows` job
- 评审：双 agent（生产+测试质量）+ pi 两次 SHIP + Grok 独立 SHIP；3 Major 修复（YAML 回退/marker 容错/pin 测试）
- 提交：`a275caa`（主提交）→ CI 首轮抓 `_flatten_skill_name` 反斜杠 bug（probe-skip 盲区）→ `ab9c8df` 修复 → **CI 全绿**（Windows 3.12/3.13 + ubuntu 零回归）→ `4cf9a36` 文档收尾
**Verification**: 本地 4282 passed/0 failed；CI windows-latest + ubuntu 全绿；ruff/basedpyright 0 err
**Next**: ① test-windows 观察期至 ~2026-08-02 后转强约束（删 `continue-on-error`）② 遗留项（05-review.md）：atomic_writer 并发 tmp 碰撞、conftest ClassVar 登记制维护 ③ backlog：Zed adapter、文档深度治理、双 PromptChainGenerator 合并

### 2026-07-18 (S31) fanout 诊断 + panel 分拆 + 质量收口
**Session**: 六路并行诊断 → control panel 分拆为独立仓库 → 全部已知问题收口 → CI 转绿。
**Completed**:
- Fanout 诊断（6 explore agents）：定位 main CI 双红因（.vibe 脚本 I001 + 注册表耦合测试）、release.yml 结构性损坏（workflow_call 缺失，发布从未跑通）、版本三方漂移、15 个堆积分支
- Panel 分拆：154 个 WIP 文件提交保护 → 创建 nehcuh/vibesop-py-panel（私有）并推为 main（36 提交全历史）→ worktree 转独立克隆（环境完整迁移）→ 主仓删 panel 规划文档（a1b3227）
- 仓库清理：origin 15 个陈旧分支删除（bundle 备份于 vibesop-py-branch-backup-20260718.bundle，确认无用可删），本地/远端只剩 main
- 质量收口 3 提交：c18d703（CI 门：ruff 排除 .vibe、测试 tmp project_root 隔离、bandit skips 收编 pyproject——原 [tool.bandit."skips"] 从未生效、pip-audit 全 extras、uv 0.11.19、删 mypy）、80b37e5（dependabot→uv、verify-* 脚本重写、删 sync-core.sh、benchmark 双目录合并）、2efdaf6（CHANGELOG 补 59 提交、INDEX 修死链+ADR-004、删陈旧 docs/PROJECT_CONTEXT.md）
**Verification**: CI run 29636446131 全 6 job 绿；本地 4067 passed / 覆盖率 74.65%；bandit/pip-audit（含 torch/transformers）0 问题
**Next**: ~~用户新提案（商店/未命中/蒸馏/Langfuse）~~ 已全部落地（P0–P4，2026-07-18，CI 绿）。**后续工作项目（用户确认 2026-07-18）：Zed adapter**（已入 ROADMAP Backlog）；~~Windows 副本兜底补测试~~（已于 S32 完成：mock OSError 回退单测 + CI Windows job）。其余 backlog：文档深度治理（49 坏引用/187 版本漂移）、双 PromptChainGenerator 合并、`InstinctLearner._load_sequences` 加载怪癖、squad 逐角色步骤展开的确定性

<!-- handoff:end -->
