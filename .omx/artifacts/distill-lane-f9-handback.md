# Handback — distill lane F9+F10（kimi）

> **Status: DONE**
> 日期：2026-09-21 · worktree：`/Users/huchen/Projects/vibesop-distill-kimi` · 分支：`feat/distill-f9`
> 设计文档（Phase 1，Status: DESIGN LOCKED）：`docs/specs/2026-09-21-distill-f9-design.md`

## 1. 改动文件清单

| 文件 | 改动 |
|---|---|
| `docs/specs/2026-09-21-distill-f9-design.md` | 新增，Phase 1 设计（六问全答） |
| `src/vibesop/core/observability/skill_promote.py` | `_render_skill_md` 在 Steps 与 Acceptance Checklist 之间渲染晋升四要素 H2（Prerequisites / Counterexamples / Verification / Source Outcomes）+ TODO 占位；docstring 同步 |
| `src/vibesop/core/observability/promote_verifier.py` | 新增 `promotion_elements` 描述性分组 + 4 条 `promotion-element-missing: <element>` WARN 码；RULESET_VERSION `gate36-r1`→`gate36-r2`；badge 判定一字未动 |
| `core/skills/skill-craft/SKILL.md` | 生成模板段插入同四个 H2 + 同义占位 + 「晋升四要素」说明行（与 promote 渲染共用一份 canonical 结构） |
| `core/skills/adversarial-panel/SKILL.md` | 第 3 步重写：`.grok/workflows/adversarial-review` 降为本机可选便利项，5+N 自举为主路径——新 clone 零依赖；第 4 步一行呼应 |
| `.omx/artifacts/gate43-t7-echo-measure.md` | 新增入库（主仓磁盘只读复制 + `git add -f`，diff 核验正文零改动） |
| `.omx/artifacts/gate43-t14-echo-measure.md` | 同上 |
| `ci/artifact-links-baseline.json` | 守卫设计的再冻结：删除 9 条 gate43 引用（它们从 stale/dangling 变 ok），459 occ / 451 keys |
| `tests/core/observability/test_promote_verifier.py` | 新 `TestPromotionElements` 6 例；pipeline 集合断言补 `promotion_elements`；coverage map 加一行 |
| `tests/core/observability/test_skill_promote_render.py` | 新 `TestPromotionElementsSkeleton` 4 例（含与 skill-craft 标题一致的防漂移钉） |
| `tests/unit/test_check_artifact_links_baseline.py` | 冻结常量按再观测更新（1108/649/459/451），注释记 checkpoint |
| `.omx/artifacts/distill-lane-f9-handback.md` | 本文件 |

未改：`core/registry.yaml`、`skill_injector`、`scripts/check_artifact_links.py` 脚本本体、gate43 测量正文、F1/F2 文件。

## 2. 设计决策摘要（六问）

1. **四要素**：正文 H2（不进 frontmatter——避免污染路由画像与 YAML 截断），位置 Steps 后 /
   Checklist 前；占位统一 `- TODO: …（中文注释）`；人审最低完成 = 节存在且 ≥1 行实质内容
   （非空、非 HTML 注释、非 TODO）。
2. **verifier**：缺项 WARN 码 `promotion-element-missing: prerequisites|counterexamples|
   verification|source_outcomes`，进顶层 `warnings` 与 `promotion_elements` 分组；
   **不进** `lint_warnings`——badge 口径保持「触发召回」（模块 docstring 既定边界），
   PASS/WARN 两级不变，永不 FAIL、永不阻断 activate。
3. **共用结构**：四个 H2 是 promote 渲染与 skill-craft 模板唯一一份结构，
   测试 `test_skill_craft_template_shares_canonical_headings` 钉死防漂移。
4. **workflow 悬空**：选「改 SKILL.md 第 3 步」而非入库 .rhai——本机无 Grok runtime，
   入库未执行过的 .rhai 等于编造机制；且项目惯例 `.grok/workflows/` 不入库。
   新 clone 行为：技能零外部依赖，直接走第 4 步 5+N 自举。
5. **gate43 入库**：两文件 `git add -f` 入库，正文 diff 核验零改动；**未编造 t21**。
   `check_artifact_links.py`：dangling **9 → 0**（8 条精确引用 + 1 条 session glob 全解）。
6. **project-knowledge 草稿**：见设计文档 §6（F9/F10 各一段，可直接抄）。

## 3. 命令 + 退出码

```
$ uv run ruff check src/ tests/ --quiet
ruff exit=0

$ uv run pytest tests/unit/ -q --tb=short -k "promote or skill_promote or artifact_links"
265 passed, 781 deselected in 11.48s        # exit 0
（spec 原文 `-k promote or -k skill_promote or -k artifact_links` 经 shell 分词后
  只生效最后一个 -k 且 "or" 变位置参数，no tests ran；上面为等价意图口径）

$ uv run pytest tests/core/observability/test_skill_promote_render.py \
    tests/core/observability/test_promote_verifier.py \
    tests/core/observability/test_skill_promote_candidate.py \
    tests/core/observability/test_skill_promote_store.py \
    tests/cli/test_skill_promote_cli.py tests/cli/test_skill_promote_scope_cli.py \
    tests/unit/test_check_artifact_links.py tests/unit/test_check_artifact_links_baseline.py -q
481 passed in 13.73s                        # exit 0

$ uv run pytest tests/dashboard/test_server_endpoints.py tests/cli/test_phase3_commands.py \
    tests/cli/test_skill_craft.py tests/conformance tests/utils/test_bundled.py \
    tests/core/skills/test_manager_integration.py -q
180 passed                                  # exit 0（四轮合并口径，逐轮均绿）

$ git ls-files .omx/artifacts/gate43-t7-echo-measure.md .omx/artifacts/gate43-t14-echo-measure.md
.omx/artifacts/gate43-t14-echo-measure.md
.omx/artifacts/gate43-t7-echo-measure.md

$ uv run python scripts/check_artifact_links.py
check_artifact_links: 1108 reference(s) — 649 ok, 0 dangling, 459 stale.   # exit 0

# 端到端冒烟（render → verify → 人填后 WARN 码消除）
badge: WARN | ruleset: gate36-r2
warn codes: ['promotion-element-missing: prerequisites', ... 4 条全]
after review: [] {'prerequisites': True, 'counterexamples': True,
                  'verification': True, 'source_outcomes': True}
```

`check_artifact_links.py` 本轮相关条目：**9 条 dangling 全部是本轮应修的 gate43 引用，
已清零**；459 条 stale 为历史挂账（本机与 index 均无文件，`git add` 不可修），
按总计划未顺手处理；其多重集与再冻结的 baseline 一致。

## 4. 我无法验证的部分

- **真实 embedding 模型路径**：本机/测试环境走 fail-open（degraded），
  `_FakeModel` 只钉逻辑不钉真模型数值；recall/index 线的真模型行为未在本 lane 实测。
- **Grok workflow 自举等价性**：第 3 步改写是文档层决策；本机无 Grok runtime，
  「无 workflow 时 5+N 自举」未在 Grok 上实跑过（这正是选方案 b 的理由）。
- **基线冻结常量与上一版观察口径的 1 条差**：上一版注释记 1109 refs / 641 ok，
  本 worktree clean HEAD 实测 1108 / 640（+9 dangling）——冻结机与本机树有 1 条
  引用差，来源未查清；本轮按「实测现状再冻结」处理并留注释。
- 四要素 WARN 码在 CLI/dashboard 渲染层的呈现沿用既有 `warnings` 通道，未逐像素核对。

## 5. 建议 grok 写入 project-knowledge 的 F9/F10 条目

草稿在设计文档 §6（`docs/specs/2026-09-21-distill-f9-design.md`），两段可直接抄：
F9「promote 晋升四要素已制度化（四 H2 + 描述性 WARN 码，灯不是闸）」；
F10「gate43 测量已 tracked（dangling 9→0）+ adversarial-panel workflow 悬空已修
（无 Grok workflow 时 5+N 自举，新 clone 零依赖）」。

## 6. 对 hermetic / CI / 既有「灯不是闸」的影响

- **hermetic**：零接触（未改路由匹配器 / 指纹 / 吸收守卫 / benchmark.py）。
- **CI**：零新 job。`artifact-links` 既有 job 的 baseline 按守卫自身设计再冻结
  （`--write-baseline`，仅删 9 条已修复引用），`decision-source.yaml` 未动。
- **promote 灯不是闸**：badge 判定逻辑一字未改（PASS/WARN 两级，永不 FAIL，
  activate 永不需 `--force`）；新增 WARN 码是纯描述性注解。
  `draft_sha256` 编辑守卫不受影响——模板只影响新 promote 的草稿，
  已存在草稿不被覆写（materialize 幂等语义未动）。
