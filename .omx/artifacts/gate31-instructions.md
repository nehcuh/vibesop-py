# Gate 31 复审 — Promote 草稿骨架升级 + ASCII skill_id

## 背景

cmspark 首次真实 promote(vibe skill promote c5ee4c8b）暴露两个产品问题：

1. 生成的 SKILL.md 是空壳——只有簇元数据（query 样本、span 数），没有任何"遇到这类请求该怎么做"的指导。Steps 来自 span step 名 ≥70% 频率，真实 trace 里没有，所以为空。
2. CJK query 直接进入 skill_id(`custom/把-nits-都收敛了把-c5ee4c8b`)——目录名含中文+空格，工具链兼容性风险；name 也是路由匹配文本。

## 改动内容

1. **`_render_skill_md`(src/vibesop/core/observability/skill_promote.py）长出编辑骨架**：新增 "When NOT to Apply" / "Acceptance Checklist" / "Anti-patterns" 三个 HTML 注释引导的 TODO 占位章节（方法论来自 oneshot-web-spec：技能的价值密度在验收条款与边界，trace 合成不出来，就给人工编辑引导槽位）;core_steps 为空时渲染引导性 TODO。promote stdout 的 review checklist 第 3 条同步更新。
2. **`_slugify`(src/vibesop/cli/commands/skill_commands.py) ASCII 化**:CJK/重音字符丢弃（不音译）,"把 nits 都收敛了把"→"nits"；全非 ASCII → "candidate" 回退（调用方追加的 cluster_id[:8] 后缀保唯一）；截断后再 strip("-") 防尾破折号。

## 刻意的边界（复审请不要建议推翻，除非有反证）

- **name/description 保持 M7 F3 裁决的中性占位**(`draft-<cluster>` + 溯源文本）——该裁决有 adjudicated 注释：name 是 INDEX 层最强匹配磁铁（+0.4 containment bonus),query 派生的 name 会让未编辑草稿一注入就 over-match。本轮只给身体加骨架，不动 frontmatter 路由语义。
- description 不改写为 query 派生的自然语言（同上，F3 是评审过的设计，不是疏漏）。

## 复审重点

- 骨架章节是否真的零路由影响（HTML 注释 + TODO 文本会被注入后的匹配层读到吗？strategies.py 的匹配文本是 name+description,body 是否参与？请核实）。
- _slugify 边界：全 CJK、混合、纯 ASCII、截断后尾破折号、""→"candidate"。
- 新章节文本在 global scope（隐私边界）下是否泄露信息。
- 测试覆盖是否钉住行为（4 例 render + 2 例 CLI ASCII + checklist 文本更新）。

## 输出要求

PASS / PASS_WITH_NITS / BLOCK；findings 按 BLOCK/MAJOR/NIT 分级，给文件：行号与理由。
