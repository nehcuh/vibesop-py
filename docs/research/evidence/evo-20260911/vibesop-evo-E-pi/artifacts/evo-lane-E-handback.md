# Lane E handback — 产物持久化收口

**Status: DONE**

- worktree：`/Users/huchen/Projects/vibesop-evo-E-pi` · branch `feat/evo-E`
- commit：`c8a6e87c feat(obs): track omx artifacts and guard dangling links`（**未 push**）
- 计划：`.omx/artifacts/evo-lane-E-plan.md`

---

## 1. 改动文件清单

| 文件 | 动作 | 说明 |
|---|---|---|
| `.gitignore` | 修改 | 删掉整目录 `.claude/`（原 143 行）；新增 OMX 短命目录 6 条 + `.claude` local-only 3 条 |
| `scripts/check_artifact_links.py` | 新增 | 断链守卫（298 行） |
| `tests/unit/test_check_artifact_links.py` | 新增 | 36 个测试（349 行） |
| `.claude/commands/r3-r4-impl.md` | 新增（复制自主仓库） | E3，与主仓库 `diff -r` 一致 |
| `.claude/hooks/guard_protected_paths.py` | 新增（复制自主仓库） | E3，与主仓库 `diff -r` 一致 |

**没有**提交：`.claude/settings.local.json`、`.claude/scheduled_tasks.json`、`.claude/worktrees/`（均在 `.gitignore` 中）；`docs/specs/*`（grok 的 lane 派工文档，不在我的可写清单）。

### E1 实际写入的规则

```gitignore
.omx/tmp/  .omx/scratch/  .omx/cache/  .omx/runtime/  .omx/logs/  .omx/state/
.claude/settings.local.json  .claude/worktrees/  .claude/scheduled_tasks.json
```

`.omx/`、`.omx/artifacts/` **没有**作为规则出现（只有一段注释在解释"不要加"，规则行层面由 `test_repo_gitignore_does_not_ignore_omx_root` 断言守住）。

---

## 2. 命令 + 退出码（laneb 指定的三条 + 补充证据）

```
$ uv run pytest tests/unit/test_check_artifact_links.py -q
....................................                                     [100%]
36 passed in 1.62s
exit=0

$ uv run ruff check scripts/check_artifact_links.py tests/unit/test_check_artifact_links.py
All checks passed!
exit=0

$ git status --short
?? docs/specs/2026-09-11-evo-lane-C.md
?? docs/specs/2026-09-11-evo-lane-Cgold.md
?? docs/specs/2026-09-11-evo-lane-D1.md
?? docs/specs/2026-09-11-evo-lane-D2.md
?? docs/specs/2026-09-11-evo-lane-E.md
?? docs/specs/2026-09-11-evolution-direction-proposal.md
?? docs/specs/2026-09-11-evolution-optimization-plan.md
exit=0
```

补充：

```
$ uv run pytest tests/unit -q
661 passed in 3.35s                          exit=0     # 全量单测；其中本 lane 36 个 → 非本 lane 基线 625，无回归

$ uv run ruff format --check <两个新文件>
2 files already formatted                    exit=0     # （首次运行对 test 文件做过一次 reformat）

$ uv run basedpyright --level error scripts/check_artifact_links.py tests/unit/test_check_artifact_links.py
0 errors, 0 warnings, 0 notes                exit=0     # 预提交钩子里的类型闸

$ uv run python scripts/check_artifact_links.py
<9 条 stale 明细 + 汇总>
check_artifact_links: 37 reference(s) — 28 ok, 0 dangling, 9 stale.
exit=0

$ uv run python scripts/check_artifact_links.py --strict
exit=1

$ uv run python scripts/check_artifact_links.py --include-untracked
DANGLING docs/specs/2026-09-11-evo-lane-E.md:12: dangling: .omx/artifacts/evo-lane-E-plan.md
check_artifact_links: 63 reference(s) — 41 ok, 1 dangling, 21 stale.
exit=1

$ git add .omx/artifacts/evo-lane-E-plan.md          # 故意失败，见 §4
The following paths are ignored by one of your .gitignore files:
.omx
hint: Use -f if you really want to add them.
exit=1

$ git commit -m "feat(obs): track omx artifacts and guard dangling links"
exit=0   →   c8a6e87c
```

---

## 3. E2 设计决定（偏离字面要求之处，必须由 grok 复核）

字面要求是「缺跟踪 → exit 1」。目标**不存在于任何地方**（既不在索引，也不在工作树）时，我**没有**让守卫红灯，而是分成两档：

| 判定 | 条件 | 退出码 |
|---|---|---|
| `ok` | 目标在 `git ls-files`（精确 / glob / 目录前缀） | 0 |
| `dangling` | **在工作树里存在但未被跟踪** | **1** |
| `stale` | 索引与工作树都没有 | 默认 0（打印告警）；`--strict` 时 1 |

理由（两条，都可被反驳）：

1. `dangling` 正是 R3/R4 prereg 那次事故的形状——文件在磁盘上、文档引用了它、`git add -f` 才能进去。`dangling → exit 1` 精确命中这个故障。
2. `stale` 是**已经消失**的引用，`git add` 修不了。当前 HEAD 上就有 9 处（见 §5），一档到底会让守卫天生红灯——**一个永远红的闸没人看**。`--strict` 保留了完整的 fresh-clone 不变量，谁要谁开。

如果 grok 认为必须一档到底：把 `main()` 结尾的 `return 1 if dangling or (args.strict and stale) else 0` 改成 `return 1 if (dangling or stale) else 0`，然后先处理掉 §5 的 9 处（需要改 CHANGELOG.md / docs/decisions/，**不在我的可写清单里，我没有动**）。一行改动 + 9 处历史清理，我做不到后者，所以默认值留给 grok 拍。

其他行为：默认只扫 **tracked** markdown（判据 = fresh clone 语义，未提交草稿不会误伤），`--include-untracked` 打开全量；`--root` / `--targets` / `--tracked-list`（注入 `git ls-files` 结果）可测；git 不可用或一个 md 都没扫到 → **exit 2 fail-closed**，不静默放行。

---

## 4. 我无法验证的部分

1. **`.omx/artifacts/` 现在仍然 `git add` 不进去。** `.git/info/exclude:7:.omx/` 还没删（那是 grok 的活）。证据：上面 `git add .omx/artifacts/evo-lane-E-plan.md` → exit 1；`git check-ignore -v` 明确指向 `/Users/huchen/Projects/vibesop-py/.git/info/exclude:7:.omx/`（不是 `.gitignore`）。所以 **E1 对 `.omx/` 的效果只能在 grok 删掉那行之后才算真正生效**；本 handback 与 plan 文件本身也因此在 `git status` 里不可见。我在隔离仓库里重放了 `.gitignore` 规则来单独证明规则本身正确（`test_repo_gitignore_boundary`，14 个参数化用例覆盖 `.omx/artifacts/*` 不被忽略、`.omx/tmp|scratch|cache|runtime|logs|state` 被忽略、`.claude/commands|hooks` 不被忽略、三个 local-only 文件被忽略）。
2. **没有接 CI / pre-commit。** 我的可写清单里没有 `.github/`、`.pre-commit-config.yaml`，且总计划 §1 写的是"零新门禁"。守卫现在是"跑得动、有退出码"，但不是自动闸。
3. **没有跑 hermetic 基准。** 见 §6。
4. **`docs/specs/` 下的 lane 派工文档我没有纳入跟踪**（不在可写清单），所以 `--include-untracked` 才会看见它们引用尚不存在的 handback。

---

## 5. 守卫在真仓库上的当前输出（9 处 stale，grok 需裁决）

```
docs/archive/chrome-sidepanel-task-plan-panel.md:4   ask-claude-task-plan-panel-review-*.md
docs/archive/chrome-sidepanel-task-plan-panel.md:4   ask-grok-task-plan-panel-review-*.md
docs/decisions/2026-09-09-practice-health-roadmap.md:150   health-20260909/
docs/decisions/2026-09-09-practice-next.md:50              next-20260909/
docs/decisions/2026-09-09-verification-progress.md:20      verification-20260909/
CHANGELOG.md:596 / 636 / 664 / 697   gate44 / gate43 / gate42 / gate41-synthesis.md
```

**这 9 处都是"从没进过 git、现在磁盘上也没有"的历史引用**（我逐个 `test -e` 过，全部 ABSENT）。它们不是本轮引入的，也不是我造成的。三个选项：(a) 保留 `stale` 警告档；(b) 把 CHANGELOG/decisions 里的死引用改写成不带路径的叙述；(c) `--strict` 并清理。

另外一条真仓库证据：`--include-untracked` 下出现了 1 条 **dangling**——`docs/specs/2026-09-11-evo-lane-E.md:12` 引用 `.omx/artifacts/evo-lane-E-plan.md`（我写的，在磁盘上，但被 exclude 卡住）。这就是守卫要抓的形状，它在真数据上抓到了。

---

## 6. 对 hermetic fingerprint / CI 的影响

- **零产品代码改动**：`src/` 一个字节没动；`behavior_consistency.py`、`routing/benchmark.py`、`HERMETIC_POSTURE`、`compute_fingerprint`、吸收守卫、R3/R4 prereg 全部未触碰 → **确定性指纹不变**。
- 新增文件只落在 `scripts/` 与 `tests/unit/`：CI 的 ruff / basedpyright 覆盖面变大，但两者在本文件上 exit 0（§2）。**没有**跑 `scripts/eval_routing.py`（本轮无需跑，也不该跑）。
- `.gitignore` 变更不影响任何运行时行为；受影响的是 `git status` 的可见性（这正是目的）。

---

## 7. 建议 grok 的下一步

1. 删 `.git/info/exclude` 的 `.omx/` 行（第 7 行），然后确认：`git add .omx/artifacts/<新文件>` **不需要** `-f`；`.omx/tmp/` 仍然被忽略。
2. 合入 `feat/evo-E` 后跑一次 `uv run python scripts/check_artifact_links.py`，期望 exit 0（0 dangling）。
3. 裁决 §3 的分档，以及 §5 的 9 处 stale 怎么处理。
4. 决定是否把守卫接进 CI（我的意见：先 report-only 跑一轮，`dangling` 已经是零误报的高价值信号）。
5. 把 lane 的 `.omx/artifacts/evo-lane-*-handback.md` 一起入库——否则你刚合的 spec 文档立刻会给守卫刷出一批 dangling，那正是它在做的事。
