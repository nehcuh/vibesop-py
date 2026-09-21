# F9+F10 设计：promote 晋升四要素 + gate43 测量入库 + workflow 悬空修复

> **Status: DESIGN LOCKED**
> 日期：2026-09-21 · lane：kimi（F9+F10）· worktree：`/Users/huchen/Projects/vibesop-distill-kimi` · 分支：`feat/distill-f9`
> 源：总计划 `docs/specs/2026-09-21-skill-distill-landing.md` §0/§4；评审 `.omx/artifacts/skill-distillation-review-20260921.md` P1 F9 / P2 F10 / P3 workflow
> 原则约束（不可推翻）：过滤自动化、不过滤人审（gate34 裁决）→ 缺项只能 WARN，永不 FAIL、永不阻断 activate；promote 继续「灯不是闸」。

## 1. 四要素：字段名、位置、占位文案、人审最低完成定义

四个要素（论文笔记建议 #4；survey §7 F9）：**前提 / 反例 / 验证方法 / 来源成败**。

**位置决策：正文 H2 标题，不进 frontmatter。** 理由：

- frontmatter 被 SkillLoader / 路由 profile 消费（`EmbeddingRecall._candidate_text`、
  `SkillIndexer._compute_profile_text` 读 id/description/intent/triggers），塞长文人审内容会
  污染匹配画像，且要过 `_sanitize_yaml_value` 截断——四要素是给人审的长文，不是给机器的字段。
- H2 标题可被 verifier 用确定性文本扫描定位，零解析依赖、零 YAML 风险。

**字段名（canonical，英文 H2 + 占位文案带中文注释）：**

| 要素 | H2 标题 | 占位文案（renderer 输出） |
|---|---|---|
| 前提 | `## Prerequisites` | `- TODO: state the conditions under which this pattern holds（前提：什么条件下这个模式才成立 — 环境 / 输入形状 / 前置状态）` |
| 反例 | `## Counterexamples` | `- TODO: name a real case where this pattern failed or did not apply（反例：这个模式不成立 / 失败过的真实案例）` |
| 验证方法 | `## Verification` | `- TODO: how this pattern was / can be verified（验证方法：用什么命令 / 测量 / artifact 证明它有效，挂路径）` |
| 来源成败 | `## Source Outcomes` | `- TODO: record the success/failure of the source executions this skill was distilled from（来源成败：来源执行的成功与失败各是什么，含 cluster provenance）` |

插入位置：`## Steps` 之后、`## Acceptance Checklist` 之前（与 gate31 骨架并存：Acceptance
Checklist 是「技能描述的工作」的验收条，Verification 是「这个模式本身」的验证证据——两者不合并，
避免 verifier 找不到确定性锚点）。

**人审最低完成定义**：每个 H2 节存在，且节内至少有一行「实质内容」——非空、非 HTML 注释、
不以 `TODO` 开头。全新 promote 草稿四节全是 TODO 占位 → 四要素判定为「缺」→ WARN，
这正是「未人审不完整」的信号；人填掉 TODO 后 WARN 消除。零新 FAIL、零阻断。

## 2. verifier：WARN 码与现有 PASS/WARN 的并存

`promote_verifier.py` 的 badge 文档明文：badge 回答的是**触发召回**，不是**内容质量**
（模块 docstring： Lane C objection 的收口方式就是把内容质量排除在 badge 口径外）。
因此四要素检查**不进** `lint_warnings`（它参与 `badge = PASS if lint_ok …` 的判定），
而是作为独立的描述性分组：

- `PromoteVerdict` 新增字段 `promotion_elements: dict[str, Any]`，
  形状：`{"checks": {"prerequisites": bool, "counterexamples": bool, "verification": bool,
  "source_outcomes": bool}, "missing": [...], "warnings": [...]}`。
  `from_dict` 对老行容忍缺键（dataclass 默认值，既有惯例）。
- 缺项 WARN 码（进顶层 `warnings`，机读前缀）：
  - `promotion-element-missing: prerequisites`
  - `promotion-element-missing: counterexamples`
  - `promotion-element-missing: verification`
  - `promotion-element-missing: source_outcomes`
- **badge 判定一字不动**：`PASS if (lint_ok and shadow all_caught and recall_ok and index_ok)`
  保持原样。触发召回完美的草稿仍可 PASS，同时四要素缺项以 WARN 码并列展示——
  两盏灯各答各的问题，「灯不是闸」不变，activate 永不需 `--force`。
- pipeline 清单追加 `"promotion_elements"`，RULESET_VERSION 由 `gate36-r1` 升为
  `gate36-r2`（verdict 语义变了，攒 ≥30 条的阈值讨论不混规则集——沿用既有注释纪律）。
- 解析方式：`_extract_draft_frontmatter` 已取 frontmatter；四要素用同一份 draft 文本做
  确定性 H2 扫描（正则 `^## Prerequisites\s*$` 等，多行模式），失败/不可读 → 四项全 missing
  + WARN，永不 raise（与全模块「never raises」一致）。

## 3. skill-craft 与 promote 渲染共用一份结构

单一 canonical 结构 = 上表四个 H2 + 同文案 TODO 占位。两处改动：

- `src/vibesop/core/observability/skill_promote.py::_render_skill_md`：
  在 Steps 与 Acceptance Checklist 之间渲染四节（所有 scope 一致；四要素不含 query / 项目标识，
  不触 M12 隐私边界）。
- `core/skills/skill-craft/SKILL.md`「Skill Generation Template」代码块：
  在 `## Steps` 与 `## Examples` 之间插入同样四个 H2 + 同义 TODO 占位，并在模板下注明
  「四要素为晋升人审必填项；promote verifier 以 WARN 码报告缺项，不阻断」。
- 测试钉死两边标题一致：render 测试断言四个 H2 原文；文档侧用 grep 级断言
  （`tests/` 新增用例读 skill-craft SKILL.md 检查四个 H2 与占位关键词存在），
  防两套标题漂移。

不新增第四个「摘要表」之类的第二套结构——四要素只在这两个 H2 集合里存在。

## 4. workflow 悬空：选「改 SKILL.md 第 3 步为无 Grok workflow 时 5+N 自举」

两个候选：(a) 把最小 `adversarial-review` workflow 入库 `.grok/workflows/`；(b) 改技能不再依赖
未跟踪 workflow。**选 (b)**，理由：

- Grok workflow 是 `.rhai` 脚本（`memory/session.md:211` 引 `fix-from-review.rhai`），
  本机无 Grok runtime 可验证——入库一个从未执行过的 .rhai 等于编造机制（违反「可信靠测量」），
  且项目惯例一直是 `.grok/workflows/` 不入库（`memory/session.md:41/258`）。
- 技能第 4 步已经有自举路径（"Elsewhere: spawn the same 5+N panel yourself"），
  悬空只在第 3 步的措辞把注册 workflow 写成了依赖。

**第 3 步改法**：注册 workflow 降为「Grok 本机便利项」——`.grok/workflows/adversarial-review`
存在时可用并传 `args.base/head/patch`；不存在（新 clone / 非 Grok 平台）时直接走第 4 步的
5+N 自举（5 独立镜头 + 每发现 1 refute-first skeptic + synthesizer），行为完全等价。
**新 clone 行为**：clone 后技能零外部依赖可用，第 3 步的机器本地文件是可选项不是前提。
`core/skills/adversarial-panel/SKILL.md` 只改第 3 步（和第 4 步一行呼应措辞），不动其它。

## 5. gate43 入库

- 从主仓磁盘只读复制 `.omx/artifacts/gate43-t7-echo-measure.md`、
  `gate43-t14-echo-measure.md` 到本 worktree 同路径，`git add -f`
  （`.git/info/exclude` 含 `.omx/`，worktree 共享 git dir）。**不改测量正文一个字**。
- 不编造 t21：T+21 复检无产物，本 lane 不生成任何 `gate43-t21*` 文件。
- `scripts/check_artifact_links.py` 现状（本 worktree，基线 `f57f7faa`）：
  1108 引用 — 640 ok / **9 dangling** / 459 stale。9 条 dangling 全部指向 gate43 测量：
  - `docs/archive/research-artifacts.md:666-667`（2 条）
  - `docs/essays/agent-trust/archive/2026-09-12-agent-trust-wechat-illustrated.md:371`（2 条）
  - `docs/essays/agent-trust/archive/2026-09-12-agent-trust-wechat.md:476`（2 条）
  - `docs/essays/agent-trust/article.md:342`（2 条）
  - `memory/session.md:535` glob `gate4*-t*-measure.md`（1 条）
  入库后 8 条精确路径变 ok，glob 因命中 tracked 路径也变 ok → **dangling 清零**。
  459 条 stale 是历史挂账（本机与 index 均无文件），按总计划不属本轮、不顺手修。
  `check_artifact_links.py` 脚本本身不需要改（守卫口径已覆盖，dangling 本来就是 fatal）。

## 6. 建议 grok 写入 project-knowledge 的 F9/F10 条目（草稿）

```markdown
### F9 学习环防自污染 → promote 晋升四要素已制度化（2026-09-21, lane kimi）
- promote 草稿与 skill-craft 模板统一带四要素 H2：Prerequisites / Counterexamples /
  Verification / Source Outcomes（前提、反例、验证方法、来源成败；论文笔记建议#4 落地）。
- promote verifier 新增描述性 WARN 码 `promotion-element-missing: <element>`：
  只报不拦，badge 仍只量触发召回（灯不是闸，gate34「过滤自动化、不过滤人审」）。
- 治理证据纪律不变：T+7 −75.2% / T+14 +264% 反弹（`.omx/artifacts/gate43-t{7,14}-echo-measure.md`
  已入库）；T+21 复检仍挂账，反弹未终裁前不得宣称治理成功。

### F10 账本入库是机制 → gate43 测量已 tracked + workflow 悬空已修（2026-09-21, lane kimi）
- `gate43-t7/t14-echo-measure.md` 从成稿机磁盘抢救入库（git add -f）；
  `check_artifact_links.py` 全库 dangling 9 → 0。
- adversarial-panel 第 3 步不再依赖未跟踪的 `.grok/workflows/`：无 Grok workflow 时
  5+N 自举（5 镜头 + refute-first skeptic + synthesizer），新 clone 零依赖可用。
- 纪律照旧：凡被 tracked 文档引用的产物必须 tracked；guard 兜底，不靠习惯。
```

## 7. 改动文件清单（Phase 2 预告）

| 文件 | 改动 |
|---|---|
| `src/vibesop/core/observability/skill_promote.py` | `_render_skill_md` 增加四要素 H2 节（Steps 后 / Checklist 前） |
| `src/vibesop/core/observability/promote_verifier.py` | `promotion_elements` 字段 + 4 条 WARN 码 + RULESET_VERSION 升 r2 |
| `core/skills/skill-craft/SKILL.md` | 生成模板段插入同四个 H2 + 占位 + 说明行 |
| `core/skills/adversarial-panel/SKILL.md` | 第 3 步：workflow 降为可选，自举为主路径 |
| `.omx/artifacts/gate43-t7-echo-measure.md` | 新增（主仓磁盘复制，git add -f，正文不动） |
| `.omx/artifacts/gate43-t14-echo-measure.md` | 同上 |
| `tests/core/observability/test_skill_promote_render.py` | 新测试类：四节存在 / 顺序 / 占位 / 与 skill-craft 标题一致 |
| `tests/core/observability/test_promote_verifier.py` | 新测试类：缺项 WARN 码 / 填全后无码 / badge 不受影响（PASS 保持）/ 老行 from_dict 容忍 |
| `.omx/artifacts/distill-lane-f9-handback.md` | handback（git add -f） |

不改：`core/registry.yaml`、`skill_injector`、`scripts/check_artifact_links.py`、测量正文、
F1/F2 文件。

## 8. 对 hermetic / CI / 既有「灯不是闸」的影响

- hermetic：零接触（不改路由匹配器 / 指纹 / 吸收守卫）。
- CI：零新 job；`check_artifact_links.py` 的 CI 基线模式（`--check-baseline`）只盯 stale 快照，
  dangling 本就 fatal——本轮把 dangling 清零是降压不是新增门禁。
- promote：badge 语义不变（PASS/WARN 两级，永不 FAIL，永不阻断 activate）；
  新增 WARN 码是描述性注解。draft_sha256 编辑守卫不受影响
  （模板变化只影响 promote 时刻新生成的草稿；已存在草稿不被覆写——materialize 幂等）。
