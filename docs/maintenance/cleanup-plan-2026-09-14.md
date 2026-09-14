# 项目整理方案与盘点（2026-09-14）

状态：**已按用户确认执行（2026-09-14）**。以下保留批准时的盘点与计划；实际结果见 [清理结果](cleanup-result-2026-09-14.md)。

## 关键发现

- 共 28 个工作目录：主仓 + 27 个额外 worktree；额外 worktree 中 24 个存在 tracked/untracked 改动。
- 8 个 evo 分支和固定角色实验分支均有 main 历史之外的提交；evo 的 `git cherry main` 检查也都显示非等价补丁。不能把目录陈旧当作成果已合并。
- 主仓 HEAD 为 `de5370add3284ec45beef4bf10c469a687a0ad0c`，相对本地 origin/main ahead 3；未联网刷新。主仓原有 1 个跟踪文件改动（docs/INDEX.md）及 20,451 个未跟踪文件，大部分是正式/敏感性实验 runs。
- 1 个 stash 是另一版 skill-routing-explained 草稿，保留。
- `.experiment/` 约 53 GiB，其中 worktree 约 46 GiB，独立 v2 运行/审查数据约 7.1 GiB。**两者有包含关系，不能重复相加。**
- 实验 worktree 的 `docs/experiments/fixed-role-v2/authors/rstdx/.verify-cache/target/` 占约 44 GiB，是最大编译缓存候选；同级 cargo-home 约 742 MiB，首次整理保留，降低重新下载依赖的成本。
- `docs/experiments/` 约 318 MiB；`.omx/artifacts/` 约 138 MiB（718 个直接文件）；`.omx/ppt-20260909/` 约 102 MiB。体积小不代表无价值，不按扩展名批量删除。
- `docs/decisions/` 有 86 个直接文件，其中 63 个 `_review-*` 过程评审。研究综述引用其中多份以及 worktree 内 handback，先建立迁移映射再移动。
- docs/experiments/README.md 和主仓 v2 协议仍称“未启动”，但 2026-09-14 interim findings 已记录后续正式运行。实验 worktree STATUS.md 也落后于部分后续资料。索引应按时间区分设计期、运行期、冻结结果与后续修订，不能覆盖历史原件或依据旧状态删除数据。

## 建议目录

```text
docs/
  INDEX.md                         # 唯一完整导航；README 保留简短入口
  user/, dev/, architecture/, api/  # 当前使用/开发文档，保留既有结构
  adr/, specs/, proposals/          # 决策、契约、待实施方案
  research/
    README.md                      # 各研究线：状态、结论、证据位置
    ...                            # 研究综述/论文笔记；移动旧文需更新引用
  experiments/
    README.md                      # 实验登记册：旧多专家实验与 fixed-role-v2 分开
    <experiment-id>/
      README.md                    # 当前状态 + 原始冻结版本位置
      protocol/, reports/          # 小体积、可审阅材料
      evidence-manifest.json       # 原始数据位置、校验值、冻结版本
  essays/
    agent-trust/
      article.md                   # 当前对外主稿
      preview.html
      assets/
      archive/                     # 旧主稿、图文版、编辑核对原件
  archive/
    reviews/<topic-or-batch>/       # 过程评审、brief、终裁；按主题组织
    plans/<year>/                  # 已完成/废弃计划，标 superseded-by
  maintenance/
    cleanup-plan-2026-09-14.md      # 本方案
    cleanup-inventory-2026-09-14.json

../vibesop-py-archives/2026-09-14/    # 拟建本地冷归档，不提交大型原始数据
  worktrees/<name>/                 # refs、补丁、未跟踪文件、独有运行证据
  experiments/<experiment-id>/      # 停用批次的完整证据，校验后再迁移
```

原始数据冷归档是同盘整理，不是异地备份，也不会本身释放空间。需要释放空间的只有已验证可重建缓存与已保存成果的工作目录副本。归档期间保持文件名、冻结字节与目录内部相对关系；运行数据中的绝对路径通过 manifest 保存原址映射，必要时保留兼容入口。

## 分批处置

1. **保存恢复材料。** 为每个拟退役 worktree 保存 HEAD/分支、index 与工作区分别的 binary patch、未跟踪文件、被忽略的独有 `.omx` / `.vibe` 研究证据；以 Git bundle 保存所有本地 refs 和 stash。记录 SHA-256 清单，验证 bundle 和归档能恢复后再移除目录。保留全部分支和 stash，本轮不做强制分支删除。
2. **清缓存。** 在确认无运行者、路径确为未跟踪编译输出、可重建后，清理精确路径 `.verify-cache/target/`。不删除 `.experiment/v2/runs/`、冻结快照、日志、候选产物、隐藏验收器与基线源码。首次保留 cargo-home 和主仓 .venv；旧 worktree 的 .venv 可随退役回收。
3. **退役旧工作目录。** health（4）、next（4）、verify（5）、win（5）共 18 个先收口；evo（8）将独有提交与 handback 建索引并归档后退役目录。分支继续可恢复。fixed-role 实验工作目录暂留，研究尚未完成，32 个独有提交和大量未提交成果需要单独收口。
4. **整理文档。** 先建立实验/研究索引与 evidence manifest，再把已结束评审移入 archive/reviews。保留裁决正文及引用关系。文章当前主稿以 docs/INDEX.md 指向的 docs/2026-09-12-agent-trust-wechat.md 为候选主版；essays 中另外两稿内容不同，保存版本历史，不当重复文件删除。
5. **核验。** 对照迁移前哈希与 Git 清单；确认每个旧 worktree 的提交和未提交成果均可恢复；检查所有受影响 Markdown/HTML 相对链接、图片和研究引用；验证剩余 worktree 注册及磁盘占用。目录整理不改产品代码，不需要整套产品回归；若移动脚本依赖的数据路径，做对应读取/重放冒烟验证。

其中 next-grok tracked/untracked 干净且无 main 外提交，可在检查被忽略的 .vibe 独有数据后优先退役。evo-A、evo-wave1 虽干净但有独有提交。win-grok 的 1 个改动文件、win-pi 的 3 个改动文件与当前主目录字节相同；其余“与主目录不同”不自动代表遗漏合并，也可能是后续修改，保存后再判断。

## 工作目录逐项清单

“main 外提交”是 Git 可达性计数，不将不同分支的共享提交相加。未跟踪数量不包含 ignored 文件，清理前仍须单独保存其中的独有证据。

| 工作目录名 | 分支 | main 外提交 | 跟踪文件改动 | 未跟踪文件 | 建议 |
|---|---|---:|---:|---:|---|
| `vibesop-py` | `main` | 0 | 1 | 20451 | 保留主目录 |
| `vibesop-evo-A-claude` | `feat/evo-A` | 9 | 0 | 0 | 先归档再退役 |
| `vibesop-evo-B-pi` | `feat/evo-B` | 10 | 4 | 0 | 先归档再退役 |
| `vibesop-evo-C-kimi` | `feat/evo-C` | 2 | 0 | 7 | 先归档再退役 |
| `vibesop-evo-Cgold-kimi` | `feat/evo-Cgold` | 1 | 0 | 7 | 先归档再退役 |
| `vibesop-evo-D1-claude` | `feat/evo-D1` | 1 | 0 | 7 | 先归档再退役 |
| `vibesop-evo-D2-claude` | `feat/evo-D2` | 2 | 0 | 7 | 先归档再退役 |
| `vibesop-evo-E-pi` | `feat/evo-E` | 1 | 0 | 7 | 先归档再退役 |
| `vibesop-evo-wave1` | `feat/evo-wave1` | 17 | 0 | 0 | 先归档再退役 |
| `vibesop-health-claude` | `codex/health-learning` | 0 | 4 | 0 | 先归档再退役 |
| `vibesop-health-grok` | `codex/health-routing` | 0 | 7 | 1 | 先归档再退役 |
| `vibesop-health-kimi` | `codex/health-adapters` | 0 | 6 | 1 | 先归档再退役 |
| `vibesop-health-pi` | `codex/health-validation` | 0 | 5 | 1 | 先归档再退役 |
| `vibesop-next-claude-20260909` | `codex/practice-next-claude` | 0 | 2 | 0 | 先归档再退役 |
| `vibesop-next-grok-20260909` | `codex/practice-next-grok` | 0 | 0 | 0 | 先归档再退役 |
| `vibesop-next-kimi-20260909` | `codex/practice-next-kimi` | 0 | 1 | 1 | 先归档再退役 |
| `vibesop-next-pi-20260909` | `codex/practice-next-pi` | 0 | 0 | 3 | 先归档再退役 |
| `worktree` | `codex/fixed-role-committee-v2` | 32 | 45 | 25096 | 保留未完实验 |
| `vibesop-verify-ci-20260909` | `codex/verify-ci-20260909` | 0 | 10 | 0 | 先归档再退役 |
| `vibesop-verify-claude-20260909` | `codex/verify-claude-20260909` | 0 | 2 | 1 | 先归档再退役 |
| `vibesop-verify-grok-20260909` | `codex/verify-grok-20260909` | 0 | 5 | 3 | 先归档再退役 |
| `vibesop-verify-kimi-20260909` | `codex/verify-kimi-20260909` | 0 | 3 | 1 | 先归档再退役 |
| `vibesop-verify-pi-20260909` | `codex/verify-pi-20260909` | 0 | 39 | 4 | 先归档再退役 |
| `vibesop-win-ci-20260909` | `codex/win-ci-20260909` | 0 | 1 | 0 | 先归档再退役 |
| `vibesop-win-claude-20260909` | `codex/win-claude-20260909` | 0 | 2 | 0 | 先归档再退役 |
| `vibesop-win-grok-20260909` | `codex/win-grok-20260909` | 0 | 1 | 0 | 先归档再退役 |
| `vibesop-win-kimi-20260909` | `codex/win-kimi-20260909` | 0 | 3 | 0 | 先归档再退役 |
| `vibesop-win-pi-20260909` | `codex/win-pi-20260909` | 0 | 2 | 1 | 先归档再退役 |

## 路由覆盖记录（已获确认）

路由计划 `918049d5-90b` 被 VibeSOP 拒绝，step 1 `using-git-worktrees` 原因 `unsafe content`；execution_ready=false。本方案未执行该计划，也未绕过扫描或修改技能安全设置。

已找到技能源 `/Users/huchen/.config/skills/superpowers/skills/using-git-worktrees/SKILL.md`，其用途是创建隔离工作目录，与本次退役旧目录不匹配。建议本次不采用该技能，改用本方案的 Git 清单、校验归档、精确清理、引用验证流程。

项目 `.pi/docs/routing-protocol.md` 的 Agent Override Protocol 明确要求：**“Get user confirmation: WAIT for explicit user approval before proceeding”**。因此需要用户确认一次路由覆盖及本方案后，才开始实际迁移/删除。不需要修改全局路由配置。

用户随后明确回复“同意”。本次沿用批准方案覆盖 using-git-worktrees 路由，已记录 user_override；无需再次确认。
