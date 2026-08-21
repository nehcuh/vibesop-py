写入 artifact 未获授权，评审直接在此输出。

---

## 总评： PASS_WITH_NITS

无 BLOCK。验证手段：36 测试全过、25 例边界探针、collect 计数、ruff 全过（均 [executed]）。与 gate19-pi.md 独立复核，四条 NIT 全部收敛且经执行证实，另补 3 个新证据（罗马数字、无动词助词形式、全角标点）。

核心逻辑正确：剥离循环终止性成立（每轮至少去 1 字符，前缀集内部无重叠，frozenset 迭代序不影响结果）；大小写处理正确（Rule A 用小写 q，Rule B 刻意用原始大小写保 `[A-Z]` 选项 token）；「做/开始」开头的真实指令实测全部放行（`做个页面`/`开始菜单打不开`/`做 3 个按钮` → False）；12 条 fixture 判定与洞察报告 7 拦 5 放完全一致；e2e 入池验证接线正确（`skill_promote.py:1054`）。

## Findings

### NIT-1（过杀 — 唯一错杀方向，与 Pi NIT-1 收敛）
**`skill_promote.py:187,255-264`** — `_OPTION_TOKEN_RE = [A-Z][′']?` 匹配任何独立单大写字母，实测 5 个真实任务形状全被拦：`1. 完成 A 模块`、`1. 看 A 和 B 的差异`、`1. 对比 A 方案和 B 方案`、`1. 方案 I 更好`（罗马数字）、`1. 修 X 文件 2. 加日志` → 全 True。现有反例只锁了「NPE 是词」和「>30 长枚举」，没锁「裸字母+实词宾语」形状——模块注释 `skill_promote.py:167-168` "every rule ships with a must-NOT-catch counterexample" 对 Rule B 不成立。建议：裸字母选项 token 后不得紧跟 CJK/字母字符（`C′ 2.`、行尾 `D` 通过，`A 模块`、`A 和 B` 放行），并补 2-3 例进 counterexample 测试。

### NIT-2（死正则 + docstring 不实，与 Pi NIT-2 收敛）
**`skill_promote.py:178-179,248`** — token 先按空白切分，token 内不可能含空白，`phase\s*\d+` 的 `\s*` 是死代码；实测 `继续 phase 3` → False，与注释 "phase 3 (whole-token fullmatch)" 直接矛盾。无空格 `phase3` 本就被第二分支覆盖。漏拦方向可接受，注释须改：删 `\s*` 或 split 前归一化。

### NIT-3（Rule A 无前缀也触发，与 Pi NIT-3 收敛）
**`skill_promote.py:200-204,228-252`** — docstring 称 "continuation prefix + …"，实现不要求剥除过任何前缀。实测 `M1 和 M2`/`M1 跟 M2`/`和 M1` → 全 True。裸相位列表拦截本身合理，但要么加 `stripped_any` 标志、要么 docstring 如实声明「纯相位/助词列表亦拦」。

### NIT-4（测试缺口 + 指令计数笔误，与 Pi NIT-4 收敛并扩充）
**`tests/core/observability/test_miss_recurrence_admission.py:479-573`** —
- collect 实测新类 **19 例**（18 参数化 + 1 e2e），指令称「21 例参数化」计数有误。
- 反例缺 NIT-1 过杀形状（补入会直接 fail 当前实现，应随修复落地）；缺 `接着` 前缀与 `继续 phase 3` 空格形式 fixture。
- 全角标点边界：实测 `继续吧!`（ASCII）→ True 但 `继续吧！`（全角）→ False，`_STRIP_PUNCT`（:181）缺 `！？：；` 全角变体，一行可修（漏拦方向）。
- `抛光`（:176）标注「语气/连接词」措辞不准——实义动词，`接着抛光` → True 行为可接受，注释应如实标注。

## Residual Risks

1. **Rule B 裸字母过杀（最大残留）**：枚举 + 单字母标签的真实任务（≤30 字符）静默掉出 miss 池——仅观察侧数据丢失，路由不受影响；NIT-1 收紧前建议对 Rule B 命中打 debug 日志审计。
2. **经验拟合面窄**：规则来自 retention 池 12 条单次采样；新形状（「麻烦继续」类）不命中，建议 2026-09-19 retention 到期前复挖对比命中率。
3. **全角标点变体漏拦**：`继续吧！` 类进入 miss 池，略降池纯度，无错杀。
4. **无前缀纯相位列表被拦**：直接以 `M1 和 M2` 发起任务时观察侧不可见（路由不受影响）。

---

双评审（claude + pi）独立收敛于 PASS_WITH_NITS，四条 NIT 一一对应。如需，我可以把 NIT-1 的收紧（裸字母后置字符约束 + 3 个反例 fixture）与 NIT-2/3 的文档修正直接落地。
