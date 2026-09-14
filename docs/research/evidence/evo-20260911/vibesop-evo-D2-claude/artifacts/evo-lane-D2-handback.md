# Lane D2 handback — near_miss 负例 + 生产 no-match 聚合

> 工人：claude · worktree `/Users/huchen/Projects/vibesop-evo-D2-claude` · 分支 `feat/evo-D2`
> 基线 60fd0487 · 任务书 `docs/specs/2026-09-11-evo-lane-D2.md` · 计划 `.omx/artifacts/evo-lane-D2-plan.md`

## Status: DONE

两个 commit（未 push，未 `git add -A`，未刷 baseline）：

- `b1145156` test(benchmark): add 14 near_miss negatives to routing_eval.yaml
- `f7293b45` feat(scripts): add aggregate_nomatch.py production no-match aggregator

## 改动文件清单

| 文件 | 性质 |
|---|---|
| `tests/benchmark/routing_eval.yaml` | 追加 14 条 near_miss（77 insertions / 0 deletions；五条 must_not_inject + 乱码条原样未动，`git diff` 验证无删行） |
| `scripts/aggregate_nomatch.py` | 新建（聚合器） |
| `tests/unit/test_aggregate_nomatch.py` | 新建（14 tests，全 tmp fixture） |

未触碰：`scripts/eval_routing.py`、`src/` 任何文件、`routing/benchmark.py`、其他题集 YAML。

## 命令 + 退出码（全部本 worktree 实跑）

| 命令 | 退出码 | 结果 |
|---|---|---|
| `uv run pytest tests/unit/test_aggregate_nomatch.py -q` | 0 | 14 passed |
| `uv run pytest tests/unit/test_eval_routing.py -q`（HF_HUB_OFFLINE=1） | 0 | 8 passed（确认加条不破坏 D1 测试面） |
| `uv run ruff check scripts/aggregate_nomatch.py tests/unit/test_aggregate_nomatch.py` | 0 | All checks passed |
| `uv run ruff format --check <同上两文件>` | 0 | already formatted |
| `HF_HUB_OFFLINE=1 uv run python scripts/eval_routing.py --hermetic --file tests/benchmark/routing_eval.yaml --json-out /tmp/evo-d2-hermetic.json` | **0** | 53 queries（skipped_env 2）top-1 47/53（88.7%）；JSON 已存 /tmp/evo-d2-hermetic.json |
| `uv run python scripts/aggregate_nomatch.py --spans .vibe/observability/spans.jsonl`（read-only smoke） | 0 | n_route=1 n_nomatch=0 rate=0.0000 wilson95=[0, 0.7935] |

### Hermetic 那次的关键数字

- **最低集 must_not_inject：仍全绿（5/5 ok1=true）**，从 per_query 逐条核对。
- **near_miss 过灌数：2/14**，均为 keyword 层：
  - `工地上的工人六点准时收工下班` → `builtin/session-end`（conf 0.95）
  - `herd instinct is what drives most market bubbles` → `builtin/instinct`（conf 0.50）
  - 其余 12 条 near_miss 正确拒判（ok1=true）。
- 6 条 misroute 里另外 4 条为**存量已知失败**（deep-diagnosis ×3 + slash-evaluate ×1，全部 fallback-llm，baseline 里 ok1 本来就是 False），与本 lane 加条无关——加条只增不改，且逐 query 独立路由。

## 我无法验证的部分

- **生产 no-match 基线率**：本 worktree 的 spans.jsonl 只有 1 条 route span（本会话自己），没有可用的生产窗口。聚合器在真实 span 上的 smoke 只证明了管线通（n_route=1, hit）。真实基线须在主工作区/生产 spans 上由 grok 跑：`uv run python scripts/aggregate_nomatch.py --spans <主仓>/.vibe/observability/spans.jsonl [--since ...]`。
- near_miss 的 **语义层表现**（embedding/ai_triage 开启时）未测——本轮口径就是 hermetic（两层关闭），方向 A 才管语义层。
- Windows 上 `--spans` 默认路径拼接未实测（纯 pathlib，理论无碍，CI 会兜）。

## 对 hermetic fingerprint / CI 的影响

- **fingerprint 必 stale**：`compute_fingerprint` 把 dataset 文件内容算进去，我改了 `routing_eval.yaml` → 集成时 `eval_routing.py --hermetic --check` 会 **exit 3**。这是预期（优化计划 §6 已预告「D2 若改了题集则先看 exit 3」），由 grok 在集成时统一 `--update-baseline`（无需 `--force`：must_not_inject 全绿，4 条存量 fail 是 known-fail，14 条新 near_miss 是新条目不构成 true→false 翻转；其中 2 条会以 ok1=false 进 known-fail——它们是**观测发现**，不是回归）。
- CI 其余面零影响：没动 `src/`、`benchmark.py`、`eval_routing.py`；新测试不联网、不碰真实 spans。

## 建议 grok 下一步

1. 集成时先跑验收命令四件套（plan §6），对 exit 3 按 hermetic 常规流程刷 baseline；刷完确认 must_not_inject 5 条仍全绿、2 条 near_miss 过灌进 known-fail 而非被 `--force` 吸收。
2. 在主工作区 spans 上跑一次聚合器拿生产基线数（方向 D 的「生产基线」成功判据还差这一步）。
3. 2/14 过灌里 `收工→session-end`（0.95）是高质量信号：keyword 层对触发词裸匹配无域过滤，值得进 ROADMAP 观察项（不设闸）。
4. `herd instinct` 那条 conf 只有 0.50 也过了 keyword 闸——若后续要收紧，注意别误伤真 instinct 正例（本套 3 条 instinct 正例当前全绿）。
