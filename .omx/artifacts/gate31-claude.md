# Gate 31 复审结果：**PASS_WITH_NITS**

3 个 NIT，无 BLOCK/MAJOR。全部复审重点逐项核实如下。

## 复审重点核实

### 1. 骨架章节零路由影响 — **[inspected] 属实，三道闸门都验证过**

- **匹配层文本**：`idf.py:370-386` `candidate_token_set` 明确契约 "name+description+intent+keywords"，`strategies.py:203-207`（M11 路径）和 `:300-310`（legacy 路径）都只从 candidate dict 取这四个 frontmatter 字段。body 从不被 tokenize，HTML 注释和 TODO 文本对关键词层不可见。
- **未注入保证**：`skill_promote.py:2110-2117` 草稿写在 `.vibe/observability/skill_drafts/`（W4 发现根之外），未注册即零路由。
- **唯一 body→索引入口**：`skill_commands.py:1188` `_index_newly_added_skill` → `SkillIndexer._analyze_skill` 会对 body 做 LLM 分析（语义层）——但这发生在 `skill add` / `promote --activate` 时，而 `_activate_promoted_draft`（`skill_commands.py:2030-2039`）的 edit guard 会在 hash 未变（未编辑）时拒绝激活。未编辑的 TODO 骨架要在显式 `--force` 下才能到达语义索引，属设计内残留，可接受。

### 2. `_slugify` 边界 — **[executed] 12 例探针全部符合预期**

`"把 nits 都收敛了把"`→`nits`；全 CJK/空串/纯破折号→`candidate`；纯 ASCII 正常；`"résumé review"`→`r-sum-review`（按设计丢弃不音译）；emoji 丢弃；截断尾破折号被第二个 `.strip("-")` 处理（`"a-"*30` → 49 字符干净结尾，旧代码会返回带尾破折号的 50 字符——见 NIT-2）。`candidate` 回退由调用方的 `cluster_id[:8]` 后缀保唯一（`skill_commands.py:1936`），测试钉了精确值。

### 3. 隐私（global scope）— **[inspected] 无泄露**

三个新章节 + 空步骤 TODO 全是静态英文模板文本，零插值：不含 query、项目名、用户路径。空步骤 TODO 只引用聚合阈值（≥70%）。query 掩码是既有逻辑且有 `test_global_scope_also_gets_skeleton` 同时钉住。

### 4. 测试 — **[executed] 89 passed（两文件全量）**

4 例 render（章节存在 + 顺序 + 空/非空 steps 互斥 + global）+ 2 例 CLI ASCII（精确值断言）+ checklist 文本更新，行为钉得足够死。

## Findings

**NIT-1** `skill_promote.py:2039, 1951` — global scope 下措辞悬空：When-NOT-to-Apply 的 TODO 说 "requests that look like the above"，空步骤 TODO 说 "reconstruct the procedure from the example queries"，但 global 草稿的 example queries 已被替换为 omission note，两处指代落空。纯文案，无功能影响，可下轮顺手改。

**NIT-2** `skill_commands.py:1285` — 新增的截断后第二个 `.strip("-")` 是承重代码（实测 `"a-"*30` 旧代码返回尾破折号），但无测试直接钉住（现有 CJK 测试的输入都恰好不触发截断边界）。建议补一条 `_slugify("a-" * 30)` 断言。

**NIT-3**（pre-existing，非本轮回归）`skill_commands.py:1282` — `/` 仍被保留：`"fix/bug 把"` → `custom/fix/bug-<c8>`，产生嵌套目录（`materialize` 的 `parents=True` 能兜住不崩，但激活路径对嵌套 id 的 round-trip 未验证）。旧代码同样放行 `/`，不阻塞本轮；既然 gate31 的主题就是目录名卫生，可考虑下轮把 query 派生 slug 中的 `/` 映射为 `-`（`custom/` 前缀由调用方提供）。

## 刻意边界确认

name/description 的 M7 F3 中性占位未被触动（`skill_promote.py:1913-1927` 裁决注释原样保留），本轮只动了 body 和 slug——与声明的边界一致，无异议。
