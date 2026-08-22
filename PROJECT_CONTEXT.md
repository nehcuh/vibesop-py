# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-08-22 S40 [vibesop-py + cmspark] 候选池 id 漂移去重（gate30）→ push f76dd61

**Session Summary**:
- M12（语义洞察→技能发现）全收官后的触发器检查发现真 bug：`cluster_id` 随簇增长漂移 → upsert 重复追加（cmspark 池 8 对重复）
- 修复：upsert 同类 Jaccard>0.5 absorb-merge + 守卫全集化；三轮 claude+pi 复审收敛（2 轮真洞全修）
- 验证：5964 passed / e2e 65/65+7/7；push `f76dd61`；cmspark 重扫池自愈（26 行，重复归零）

**Key Decisions**:
- 池层模式身份 = project-agnostic task 词汇集（跨项目同模式 = 一个候选）；W5.1 复合键只管 span 归因
- 守卫阻断集 ⊇ 写路径破坏集；exact-id 例外仅对 unstable 行可达（同 id ⟹ 同成员）
- 候选 ID 会漂移：`5bd44eee`→`64d301b8`，`6a6d554f` 并入 `af55cfff`

**Next Steps**:
1. 用户：cmspark `vibe skill discover` 处理 5 条 stable 候选；bd1bc217 草稿 `--activate`
2. 新开 kimi 会话激活 hooks（M3 行为证据前提）；3 个 dead loop 可 reset 复活
3. 数据触发：簇攒 ≥2 条工具序列 trace → M3 阈值复检；留存池 2026-09-19 前复挖再 purge

### 2026-07-31 S39 [vibesop-py + cmspark] 定位对抗 → Sprint1 → dogfood

**Session Summary**: 产品演化 4 路对抗 Binding + Sprint 1（RoutingPending/accept/dismiss/replay inject）+ cmspark dogfood。后续已由 S40 前的 M12 系列 session 推进（M2 出口验证 5/5、M3 行为门、LoopStore 归属、文档债清零 3f5ef0f/e30f392 均已 push）。
<!-- handoff:end -->
