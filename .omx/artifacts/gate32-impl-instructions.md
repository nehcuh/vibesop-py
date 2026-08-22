# Gate 32 实施复审 — v3（A1 triggers 预填 + A2 SkillProfile.triggers + A3 回放基线）

## 背景

v1 提案（触发器词典层 P0 + per-field max-pooling P1 + 预填 triggers P2 + 灰区放行 P3）经四路独立对抗 + claude/pi/grok 三路评审后大修。三路裁决:本 gate 不动路由行为，只做闭环修复 + 测量基础设施。三路评审文档在 .omx/artifacts/gate32-{claude,pi,grok}.md，对抗提案在 gate32-v2-proposal.md（可先读）。

## 本 diff 实现内容

### A1 — 渲染器预填 triggers(src/vibesop/core/observability/skill_promote.py)
- `_render_skill_md` frontmatter 新增 `triggers: [...]`,样本 = candidate.queries[:5] 经 `_is_low_information_query` + 新增 `_is_agent_prompt_shape`(B4-lite:agent 提示词前缀黑名单 + 150 字符上限）过滤,逐条 `_sanitize_yaml_value`(quoted flow list)
- global scope:TODO 注释占位（M12 隐私边界,不预填原始 query)
- 全部过滤光:TODO 占位注释（无活跃 triggers 键）
- M7 F3 完好：name/description 中性占位不动;编辑守卫（draft_sha256）保证未编辑草稿不可激活,索引器只见人工过目后的 triggers

### A2 — SkillProfile.triggers(src/vibesop/core/skills/indexer.py)
- 新字段 + to_dict/from_dict(legacy 行缺键 → [])
- `_spec_triggers()` 静态helper;build_index 的 fresh 与 cache-hit 双路径填充(cache-hit restamp 与 pack_owner 同款);pack 增量路径双 loop 同样填充（futures dict 改为携带 (sid, ls));`_index_newly_added_skill`(skill_commands.py）在 embedding 计算前填充
- `_compute_profile_text` 末尾拼接 triggers——0.45 embedding 门可见;**刻意不进 query_patterns**(Jaccard 0.20 快路径无 margin 门,pi BLOCK-3 / grok M1)
- INDEX_VERSION 1.4.0 → 1.5.0

### A3 — scripts/replay_routing_baseline.py（新增 ~480 行 + 33 测试）
- 真实 query 取 metadata["query"](200 截断标记;span name 是展示文本);miss 判定 is_route_miss_span
- P0-shadow(exact 不限长度 / containment trigger ≥6 字符）只记录不动路由;identity-diff 改判清单;agent 形状剔除;sha1 确定性抽样裁决表
- cmspark 首跑:3549 route span / 650 miss / P0-shadow 22 query 29 pairs / 0 collision

## 复审重点

1. A1 的卫生谓词边界:prefix 黑名单会不会误杀真实用户 query(如 "you are" 开头的合法英文指令)?150 字符上限会不会杀掉合法长指令？
2. A2 的 cache-hit restamp 与 content_hash 的交互:prompt 已含 triggers → 改 triggers 必失 hash 走 fresh 路径,restamp 只剩 pre-1.5.0 迁移价值——这个论证对不对?有没有反例?
3. A3 的 P0-shadow 规则与将来 P0-lite 激活规则的口径一致性(将来激活时 shadow 数据还有没有效)?
4. 测试是否钉住了三路评审的 must-fix(BLOCK-1/2/3、MAJOR-1/2/3、grok M1-M5、claude MAJOR-1/2/3/4)?

## 输出要求

PASS / PASS_WITH_NITS / BLOCK;findings 按 BLOCK/MAJOR/NIT 分级,给文件:行号与理由。
