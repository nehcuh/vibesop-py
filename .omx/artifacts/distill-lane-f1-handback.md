# Lane F1 Handback — spec 缺口与注入策略(claude)

> 2026-09-21 · worktree `/Users/huchen/Projects/vibesop-distill-claude` · branch `feat/distill-f1`
> 基线 `f57f7faa`(与主仓 main 同步)

## 1. Status: DONE

## 2. 设计文档(Phase 1)

`docs/specs/2026-09-21-distill-f1-design.md` — `Status: DESIGN LOCKED`。
选路径 **C(A+B)**:注入层 report-only `spec_gap` 注释 + `task-briefing` 内置技能。
「spec 写满」操作定义:≥150 字符 ∧ 三族信号(验收/边界/交付物)≥2 族 → `low`,
其余含一切异常 → `unknown`(fail-open)。

## 3. 改动文件清单

| 文件 | 改动 |
|---|---|
| `core/skills/task-briefing/SKILL.md` | 新建。窄触发(任务书/task brief/`/task-briefing`);When NOT to use / Anti-Patterns / Exit Criteria 齐全,对齐 adversarial-panel 质量栏 |
| `core/registry.yaml` | 末尾追加 `task-briefing` 条目(仅追加,既有 id 零改动) |
| `src/vibesop/agent/runtime/skill_injector.py` | `assess_spec_gap()` + `SPEC_GAP_*` 常量 + `InjectionResult.spec_gap` + `inject_single_skill(spec_query=...)`:low 时在信封正文前 prepend report-only 注释(notice/拒注入路径不注释;注释先于截断) |
| `src/vibesop/agent/runtime/agent_runtime.py` | 仅字段/传参:`AgentRuntimeResult.spec_gap`、注入调用传 `spec_query=query`、`to_hook_json` 增 `"specGap"` 键、single 模式 span metadata 写 `spec_gap` |
| `tests/agent/runtime/test_spec_gap_annotation.py` | 新建,22 tests |
| `docs/specs/2026-09-21-distill-f1-design.md` | 设计文档 |
| `.omx/artifacts/distill-lane-f1-handback.md` | 本文件 |

## 4. 命令 + 退出码

```
$ cd /Users/huchen/Projects/vibesop-distill-claude
$ uv run ruff check src/ tests/ --quiet                        # exit 0
$ uv run --extra dev pytest tests/agent/runtime/ -q --tb=short # 230 passed, exit 0
$ uv run --extra dev pytest tests/agent/runtime/test_spec_gap_annotation.py -q  # 22 passed, exit 0
# 邻近面(主动加跑):
$ uv run --extra dev pytest tests/test_routing_baseline.py tests/unit/test_eval_routing.py \
    tests/core/skills/ tests/utils/test_bundled.py -q          # 775 passed, exit 0
$ HF_HUB_OFFLINE=1 uv run --extra dev pytest tests/unit/core/routing/ tests/core/routing/ -q  # 756 passed, 2 skipped, exit 0
$ uv run ruff format --check src/vibesop/agent/runtime/ tests/agent/runtime/  # exit 0
# hermetic 吸收守卫:
$ uv run --extra dev python scripts/eval_routing.py --hermetic --json
    # top1 0.8983 = 基线 53/59;ok1 翻转 0;6 条已知 fail 的 primary/layer 逐字同基线;
    # 0 条 query 路由到 task-briefing
$ uv run --extra dev python scripts/eval_routing.py --hermetic --check   # exit 3
    # "fingerprint mismatch — registry/skill/dataset content or posture changed"
```

注:`uv run pytest` 在本仓需 `--extra dev`(裸 `uv run pytest` 报 `Failed to spawn: pytest`)。

## 5. 我无法验证的部分

- **生产路由命中率**:本 lane 只能跑 hermetic + 本机非 hermetic smoke;`task-briefing`
  在 cmspark 等生产通道的实际命中率/回声行为未测(需活体 spans,归 Wave 1.5 之后的观察)。
- **英文长变体的路由稀释**:`write a task brief for this refactor` / `draft a task brief
  for the migration` 掉 no-match(TF-IDF 余弦被稀释;`write a task brief`、`write the task
  brief first`、显式点名、全部中文触发均命中,`/task-briefing` 走 explicit 层 1.0)。
  修它要动匹配器——本 lane 非目标,如实挂账。
- **spec_gap 启发式的真实精确率/召回**:golden/negative 是构造样本;生产 query 上的
  low 占分布未测(等 F2 分账上线后可按 span `spec_gap` 切片回看)。
- **R8 盲评未结算**:F1「粗糙=显形」半边维持人评级,本 lane 未触碰。

## 6. 建议 grok 写入 memory/project-knowledge.md 的 F1 条目草稿

```
F1(spec 缺口)可操作面已落地(2026-09-21, feat/distill-f1, 未合 main):
- 注入层 report-only: skill_injector.assess_spec_gap() 对 ≥150 字符且
  ≥2/3 信号族(验收/边界/交付物)的 query 标 spec_gap=low,信封 prepend
  advisory 注释;注入内容与行为零变化,启发式异常 fail-open 到 unknown。
  契约:hook JSON 新增 specGap 键(增量,缺省=unknown);single 模式 span
  metadata 记 spec_gap(F2 消费分账的分母)。
- 技能层: builtin/task-briefing(窄触发:写任务书/task brief/显式点名),
  教 agent 粗任务先写满任务书(五节:目标/交付/验收/非目标/上下文)。
- 边界: 「写满=技能冗余」是 R1-R3/R7 五次平手的条件结论,n=1/轮、人评为主,
  不是「技能无用」;启发式只注释永不做闸;R8 盲评未结算前不得引用「粗=显形」。
- 指纹: registry+技能树追加 → hermetic 指纹结构性变更(47cc8ba8→4be8256b),
  行为零翻转(eval 核对 ok1 翻转 0、已知 fail 类别逐字同);基线刷新归 Wave 1.5。
- 挂账: 英文长变体 TF-IDF 稀释不中(匹配器层,禁改未修);生产命中率未测。
```

## 7. 对 hermetic / CI / 既有 promote「灯不是闸」的影响

- **Hermetic 指纹**:变了(预期内,结构性而非行为性)。原因:F1 任务书明确要求
  `core/registry.yaml` 追加 + 新建 `core/skills/task-briefing/`,二者都是指纹输入
  (`skills:builtin` 树哈希 + `registry.yaml` 哈希,实测 delta 恰好只有这两个文件)。
  `--hermetic --check` 因此 exit 3(stale)。按任务书指示**未修 benchmark.py、未刷基线**
  (基线文件不在本 lane 可写清单)——Wave 1.5 grok 用 `--update-baseline` 刷新即可,
  吸收守卫已预核:刷新不会吸收任何回归(ok1 翻转 0,已知 fail 的 primary/layer 无退化,
  no_match→wrong-skill 的降级路径为零)。
- **CI**:零新 job、零 required 变化;`routing-eval` 的 decision_source 语义未触碰。
  ruff check / format、agent runtime、routing、skills、bundled 全绿。
- **promote「灯不是闸」**:零接触。spec_gap 全链路 report-only——不抑制注入、不改
  has_match 语义、不影响 demote/refused 路径;notice 载荷不携带注释(测试钉死)。
