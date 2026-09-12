# 优化计划：把「可信」从声称变成可测量（Wave 1–3）

> 源提案：`docs/specs/2026-09-11-evolution-direction-proposal.md`
> 日期：2026-09-11 · 基线：`60fd0487` · 编排：grok（本会话）
> 状态：**执行中**（Wave 1 已派工）

## 0. 技能适配（META-0）

路由命中 `builtin/deep-diagnosis-optimization`（88%）。**跳过 Phase 1 诊断**：提案已完成事实盘点与方向裁决。本计划直接进入 Phase 2 分批落地，并用用户指定的 tmux 多 agent 施工，而不是主会话独占编辑。

保留该技能的：分批、独立复审、执行验证、不把自述当完成。
不保留的：再跑 10 路 map/diagnose、直接合 main。

## 1. 目标与硬边界

**目标**：按提案 §4 顺序落地 E → D → C，再 A → B。全部 report-only，零新门禁。

**硬边界（所有 lane 共用）**

- 不改 R3/R4 判据与范围（prereg 已写死）。
- 不改 `src/vibesop/core/observability/behavior_consistency.py`。
- 不改 `src/vibesop/core/routing/benchmark.py` 的 `HERMETIC_POSTURE` / 指纹 / 吸收守卫。
- 不做语义层门禁、不把 LLM 评审当放行闸、不扩编排/市场/专家团。
- 不自动合 main、不 force-push、不用 `git add -A`。
- 只用 `uv`，不用 pip。
- 工人只在自己的 worktree + feature branch 上提交。

## 2. 波次与并行

```
Wave 1（本轮，E/D/C 并行）
  E     pi      产物持久化收口
  D1    claude  eval_routing 双向误差报告
  D2    claude  near_miss 负例 + 生产 no-match 聚合
  C     kimi    gate findings 解析器 + 单测
  Cgold kimi    10 文件人工金标（只读 gate，写金标）

Wave 1.5（grok 集成）
  合入 worktree 分支 → 主工作区验证 → kimi 复审 diff

Wave 2（E 落地后）
  A     claude  --profile-semantic（依赖 E 的产物落点）
  B1    草案    CI decision_source 注册表（人工认定项先列出，不擅自终裁）

Wave 3
  B2 静态禁入（若 B1 草案被接受）
  A 控制组复跑解释
```

## 3. 文件所有权（禁止跨 lane 写）

| Lane | 可写 | 只读 |
|---|---|---|
| E | `.gitignore`；`scripts/check_artifact_links.py`；`tests/unit/test_check_artifact_links.py`；`.claude/commands/` `.claude/hooks/` 的跟踪化（不加 `settings.local.json`） | 提案、ROADMAP、`.omx/artifacts` 引用 |
| D1 | `scripts/eval_routing.py`；`tests/unit/test_eval_routing.py` | 题集 YAML、benchmark.py |
| D2 | `tests/benchmark/routing_eval.yaml`（只增不减 must_not_inject）；`scripts/aggregate_nomatch.py`；`tests/unit/test_aggregate_nomatch.py` | eval_routing.py、spans 口径 |
| C | `scripts/parse_gate_findings.py`；`tests/unit/test_parse_gate_findings.py`；`tests/fixtures/gate_findings/` | `.omx/artifacts/gate*` |
| Cgold | `.omx/artifacts/gate-findings-gold-10.json` + 对应 md 说明 | 全部 gate 文件（只读） |

`.git/info/exclude` 的 `.omx/` 行由 **grok 在 E 的 gitignore 合入后** 删除，避免五路同时被 untracked 海啸淹没。

## 4. Staffing 与并发观察

| Agent | 并发策略 | 本轮 |
|---|---|---|
| grok | 编排、集成、验证、exclude 收口、Wave 2 派工 | 本 tmux pane |
| claude | **确认支持多路**：两个独立 tmux window + 独立 worktree | D1、D2 |
| kimi | **确认支持多路**：两个独立 tmux window + 独立 worktree + `--auto` | C、Cgold |
| pi | **未证实多路**：Wave 1 只用 1 个新 window。若 Wave 2 需要第二路，用 `--session-id` 另开并观察是否抢会话/锁文件 | E |

现有 window 0 的 kimi/pi/claude pane **不占用**（kimi 在 cmspark、另两路在 main 工作区，避免和未提交的 R3/R4 骨架打架）。

Worktree 布局：

```
/Users/huchen/Projects/vibesop-evo-E-pi          feat/evo-E
/Users/huchen/Projects/vibesop-evo-D1-claude     feat/evo-D1
/Users/huchen/Projects/vibesop-evo-D2-claude     feat/evo-D2
/Users/huchen/Projects/vibesop-evo-C-kimi        feat/evo-C
/Users/huchen/Projects/vibesop-evo-Cgold-kimi    feat/evo-Cgold
```

## 5. 完成定义（每 lane）

工人必须在自己的 worktree 写：

`.omx/artifacts/evo-lane-<id>-handback.md`

必含：

1. `Status: DONE | PARTIAL | BLOCKED`
2. 改动文件清单
3. **命令 + 退出码**（不是「已验证」）
4. 「我无法验证的部分」
5. 对 hermetic fingerprint / CI 的影响说明
6. 建议 grok 下一步

没有 handback + 退出码，一律不算完成。

## 6. 验收命令（集成时 grok 跑）

```bash
uv run ruff check src/ tests/ scripts/
uv run pytest tests/unit/test_check_artifact_links.py \
              tests/unit/test_eval_routing.py \
              tests/unit/test_aggregate_nomatch.py \
              tests/unit/test_parse_gate_findings.py -q
uv run python scripts/eval_routing.py --hermetic --check   # 期望 0；D2 若改了题集则先看 exit 3
```

方向成功判据仍以提案为准：

- E：fresh clone 语义（断链守卫全绿 + 人为 untrack 被引用文件红灯）
- D：一份报告同时呈现两向误差；生产聚合脚本可在缺 spans 时 fail-soft
- C：parser 对金标 10 文件精确率待 Cgold 对齐后由 grok 计算；parser 自身单测必须绿

## 7. 明确不做（本轮）

- A 的 `--profile-semantic`（等 E）
- B 的 CI 注册表终裁（等人工认 job）
- 任何阈值化 / 把 report-only 做成 gate
- 动 R3/R4 接线（那是另一份任务书）
