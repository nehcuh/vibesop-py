# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-07-31 S39 [vibesop-py + cmspark] 定位对抗 → Sprint1 → dogfood

**Session Summary**:
- 对照 [LLM Space](https://github.com/deer-flow/llm-space)：相邻不重叠；吸收 UX（回放/成本）不吸收 Thread IDE
- 4 路对抗终裁（devil/user/eng/competitive）→ Binding `docs/decisions/2026-07-31-product-evolution-adversarial.md`
- Pi CONDITIONAL → Sprint 1 GO：RoutingPending + accept/dismiss + replay inject + stats
- cmspark dogfood：`uv tool install --reinstall`；`vibe build` claude-code/grok-build；弱层 levenshtein 入队 fix
- Commits on main（未 push）：`b5d9fe2` feat Sprint1；`f77943f` fix weak-layer pending

**Key Decisions**:
- 北极星 aha：「指出路由蠢 → accept → 更准 → 第三次回放」；禁止元审计/显微镜当 P0
- 完成度倒挂：memory ~85% 已发货；METRIC ~25% 断线 — 先接线效用，不绿野 memory
- conf 阈值 alone 不够：levenshtein/custom/fallback_llm 也要进 pending
- 路由 pending ≠ skill-suggestion 队列（pi H1）

**Next Steps**:
1. 可选 `git push origin main`（ahead 2）
2. cmspark 日常：`vibe instinct stats/pending` 观察 14 天 kill criteria
3. Sprint 2：`vibe task show` + Inbox 薄盘（树先于 Cytoscape）
4. Dashboard Phase C 仍 defer 到 Task 真相之后

### 2026-07-28 S38 [vibesop-py] Dashboard v3 Phase A 收尾 + Phase B 全 ship

**Session Summary**: Task 10–13 + Phase B API + ReflectionStore RMW P0 fix；21 commits pushed.

**Next Steps** (still valid): Phase C UI after Sprint 1/2 utility；AtomicWriter sibling lock deferred.
<!-- handoff:end -->
