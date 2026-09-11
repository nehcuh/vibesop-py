# Lane A handback — 语义层可靠性画像（--profile-semantic）

**Worker**: claude（worktree `vibesop-evo-A-claude`，branch `feat/evo-A`）
**日期**: 2026-09-11 · 基线 commit `c4dbf187`（branch HEAD，未合入其他 lane 的新提交）
**任务书**: `docs/specs/2026-09-11-evo-lane-A.md`

## 1. Status: DONE

（证伪 (b) 是本 lane 的合法科学结论，不是执行失败 —— 任务书写明「语义层稳定度 ≈ 1.0 → 证伪 (b)，降级为低频抽检建议，不要再加预算」。画像已产出并落 tracked 路径。）

## 2. 改动文件清单

| 文件 | 性质 |
|---|---|
| `scripts/eval_routing.py` | 新增 `--profile-semantic` / `--profile-runs` / `--profile-out` 姿态 + 聚合小函数（同文件）；hermetic 路径零改动 |
| `tests/unit/test_eval_routing.py` | 新增 10 个 profile 测试（FakeRouter/_CyclingRouter，CI 不跑真 embedding） |
| `docs/benchmark/semantic_profile/semantic_profile_e9d1f1aa6691097a.json` | 真跑 N=10 后写入的机器可读画像 |
| `docs/benchmark/semantic_profile/semantic_profile_e9d1f1aa6691097a.md` | 人读摘要 |
| `.omx/artifacts/evo-lane-A-handback.md` | 本文件（见 §7 注：需 `git add -f`） |

环境准备（不改 tracked 文件）：`uv sync --extra dev --extra semantic`——`semantic` extra 是 pyproject 既有声明（sentence-transformers 5.7.0 / torch 2.13.0 等）；模型权重 `paraphrase-multilingual-MiniLM-L12-v2` 本机 HF 缓存已有，全程离线加载。

## 3. 命令 + 退出码（全部复跑于最终代码状态）

| 命令 | 退出码 | 结果 |
|---|---|---|
| `uv run ruff check src/ tests/ scripts/` | 0 | All checks passed |
| `uv run ruff format --check scripts/eval_routing.py tests/unit/test_eval_routing.py` | 0 | 2 files already formatted |
| `HF_HUB_OFFLINE=1 uv run pytest tests/unit/test_check_artifact_links.py tests/unit/test_eval_routing.py tests/unit/test_aggregate_nomatch.py tests/unit/test_parse_gate_findings.py -q` | 0 | 76 passed |
| `uv run pytest tests/unit/test_eval_routing.py -q` | 0 | 21 passed（含 10 个新 profile 测试） |
| `uv run python scripts/eval_routing.py --hermetic --check` | **0** | 门禁不受影响（改动后复验） |
| `uv run python scripts/eval_routing.py --profile-semantic` | **0** | 见 §4 结果摘要 |

## 4. 结果与判读

- **控制组**（embedding 关、其余 pin 相同）：N=10 × 55 题，primary/layer 稳定度均**恰为 1.0** → 未触发证伪 (a)，harness 自检通过。
- **语义组**（embedding 开、AI triage 关）：N=10 × 55 题，mean primary 稳定度 **1.0**、mean layer 稳定度 **1.0**、0/55 题不稳定、直方图 `{'1.0': 55}` → **证伪 (b)**：固定输入下语义层方差（本机、本栈、in-process）为零，建议 lane A 降级为低频抽检，不再加预算。
- **embedding 真实参与了路由**：语义组 primary layer 分布 `keyword 210 / embedding 180 / fallback_llm 110 / explicit 50`（控制组 `keyword 260 / fallback_llm 240 / explicit 50`）。1.0 不是「语义层没跑」的假象——embedding 赢下 180/550 (32.7%) 路由，且把 fallback 从 240 压到 110。loader 调用计数 = 1（防「静默退回确定性路径」的诚实性守卫，`PROFILE_INVALID_NO_EMBEDDING_LOAD` 分支单测覆盖）。
- JSON 按任务书记录：N、HF_HOME 指真缓存、OMP=1、torch 单线程（get_num_threads=1）、torch 2.13.0 / sentence-transformers 5.7.0 / transformers 5.15.0 / huggingface_hub 1.27.0 / numpy 2.5.2、python 3.12.13、macOS arm64、git commit、数据集指纹（`SEMANTIC_PROFILE_POSTURE` 独立命名空间，文件名 = 指纹短码）。

## 5. 我无法验证的部分（不装懂）

1. **跨进程/跨机器稳定性**：本画像 = 单进程、模型加载一次、顺序 10 轮。跨进程方差未直接测（旁证：同输入两次 encode 逐位相同；env/版本已记录供未来复跑对比）。提案 unknown #2 的「同 commit 双跑逐条对比」可作为后续抽检形式。
2. **AI triage 开启时的方差**：任务书明确本轮只开 embedding，未测。
3. **Windows**：profile 姿态未在 Windows 跑（hermetic 门禁的 Windows parity 不受影响）。
4. **适配器保真度假设**：见 §6——产品 embedding 路径当前必崩，画像测的是「pipeline 契约下的 EmbeddingMatcher 行为」，产品代码修复前的「真实产品行为」不存在、无法测。

## 6. 重大发现：产品 embedding 路径当前是坏的（P0 级，移交 grok）

`enable_embedding=True` 时 `route()` 必崩：`MatcherPipeline` 以 `matcher.match(query, filtered, context, top_k=...)` 调用（matcher_pipeline.py:147），而 `LazyEmbeddingMatcher.match()` 签名无 `top_k` → `TypeError`（不在 pipeline 捕获的异常类型里，直接穿透到 route 调用方）。任何未被 keyword≥0.95 早退的 query 都会触发。既有单测只用了宽松签名的 FakeMatcher，从未让真 Lazy 代理过真 pipeline（`tests/unit/core/routing/test_matcher_pipeline.py:181`）。

- 本 lane 的处置：**in-process 适配器**（`_LazyMatcherAdapter`，仅存在于 harness，转发 1:1 到真 `EmbeddingMatcher.match(..., top_k=...)`），`SEMANTIC_PROFILE_POSTURE` 里显式记录 `embedding_matcher_adapter: lazy-top-k-forwarding-in-process`。这与 hermetic 既有 monkeypatch 先例同类，产品代码零改动。
- 不修产品代码的原因：任务书「不许改：产品路由代码」。修复归属 grok 派工（一行签名修 + 一个真链路产品测试）。

## 7. 对 hermetic fingerprint / CI 的影响

- `HERMETIC_POSTURE`、`--check` 0/1/3、吸收守卫、题集、baseline 文件：**零接触**（`git diff` 仅 scripts/eval_routing.py + 测试 + 新产物目录）。
- `--hermetic --check` 改动后复跑 exit 0。
- profile 退出码恒 0（CONTROL_BLOCKED / PROFILE_INVALID 只进报告字段，不做 gate）；唯一非 0 是 exit 2 =「跑都没跑成」（模型/依赖离线不可用），已在 docstring 注明这不是质量判决。
- CI 无新依赖：profile 不进 CI；单测不 import torch（版本采集对缺失包记 "not-installed"）。
- **注**：`.git/info/exclude` 仍含 `.omx/`（共享 git dir，按计划 §3 属 grok 收口项，E 的 .gitignore 规则已在本分支但 info/exclude 行未删）。因此本 handback 需要 `git add -f` 落库；`docs/benchmark/` 不受影响（check-ignore 验证过）。

## 8. 建议 grok 下一步

1. **派产品修复**：`LazyEmbeddingMatcher.match` 加 `top_k`（或 `**kwargs` 转发）+ 一个 `enable_embedding=True` 的真链路产品测试。修复合入后删 harness 适配器（posture 变化 → 指纹自然翻新，重跑一次 profile 即可对账）。
2. **接受证伪 (b)**：lane A 降级为低频抽检——建议触发条件 = torch/transformers/sentence-transformers 升级（提案 unknown #7）或产品 embedding 修复合入时各复跑一次（单会话成本）。
3. **E 收口**：删共享 `.git/info/exclude` 的 `.omx/` 行（本 handback 已用 `-f` 抢救，但下个 lane 不应再需要）。
4. （可选）Wave 3 的「A 控制组复跑解释」：如需跨进程确定性证据，双进程各跑一次 profile、diff 两份 JSON 的 per_query 即可，无需新代码。
