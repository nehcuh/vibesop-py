# gate21 复审指令 — 候选池类分离预算 + content-block 信封拆解

你是资深代码评审员。仓库:/Users/huchen/Projects/vibesop-py(Python,包在 src/vibesop)。随附 diff 是本次待审改动。背景:2026-08-21 首次全量真实 dogfood 扫描(cmspark,780 簇 / 408-span miss 池)暴露两个缺陷,堵住 M12 M2 出口(≥1 条真实 miss 准入候选可见)。设计契约:`.omx/artifacts/m12-product-design.md` M2 节;原 deferral 注记在 skill_promote.py 模块注释(本次改写)。

## 改动内容

**F-a 类分离预算(skill_promote.py)**:unstable 诊断行(50 条 gold_rate=0.0)占满 MAX_PENDING=50,miss_recurrence 候选(gold_rate=0.0)在 admit-only-if-better 下恒输 → 准入被堵死。修复:MAX_PENDING=50 只管 stable 可见候选;新增 MAX_PENDING_UNSTABLE=20 管 unstable 诊断桶;`_do_locked_upsert` 按 is_unstable 分类计数,admit-only-if-better 只在同类内比较;驱逐:stable 类 gold_rate 最低出(并列→最老),unstable 类 span_count 最低出(并列→最老)。ScanSummary 新增 unstable_refused_count;CLI 拒绝文案分类标明。gate17b 的同 cluster_id gold 行保护保留。

**F-b content-block 信封(clustering.py)**:`_extract_query` 在 `<user_query>` 解包后接 `_unwrap_content_block_array`——整串是非空 JSON 数组且每块都是 `{"type":"text","text":str}` 时拼接 text(\n 连接);畸形/非 text/混合/内嵌原样放行;信封优先不解二遍。

## 评审重点

1. **F-a 语义正确性**:分类计数/驱逐/准入的边界(同类内比较是否完备;legacy 混合池文件(缺 is_unstable 键)的分类归属;stable 满 + unstable 未满、反之亦然的组合);gate17b 保护是否真不受影响;新驱逐序(unstable 按 span_count)是否合理。
2. **F-b 安全性**:content-block 拆解的误判面(用户真的贴了 JSON 数组当 query 会怎样;`[{"type":"text","text":...}]` 单块是常见合法输入吗);与 `<user_query>` 解包的顺序;嵌套/畸形边界。
3. **一致性**:与仓库防御式存储风格(坏行跳过、双锁)对齐;CLI 渲染口径。
4. **测试质量**:类分离的组合覆盖、legacy 文件兼容、F-b 的放行/拆解边界是否锁住行为。

## 输出格式(严格遵守)

- 先给总评 verdict:PASS / PASS_WITH_NITS / FAIL(有任一 BLOCK 即 FAIL)
- findings 按严重度:BLOCK / NIT,每条含 文件:行号、问题、建议
- 最后列 residual risks
- 用中文,简洁,拿证据说话
