# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-27 15:30

**Session**: KIMI 深度评审交叉验证 + P0/P1 缺陷修复

**Summary**:
1. **三轮交叉验证**: 对照 VibeSOP 源代码验证 KIMI 的 17 项评审发现，纠正 2 项误报（CRITICAL-8, HIGH-8）
2. **9 项 P0/P1 修复**:
   - P0: OptimizationService 空列表 IndexError, rejected_candidates Pydantic 字段错配, 中文 AI Triage `split()` 绕过, ConfigSource.get 假值 bug, CLI feedback 方法名错误
   - P1: `_get_cached_candidates()` 死代码激活, `_build_match_result` context=None 修复, `filter_routable` resolve() 缓存, SkillRecommender 去重, scope 默认值 "project"→"global"
3. **新增配置**: `ai_triage_short_query_bypass_chars` 字段（字符数阈值替代单词计数）
4. **测试**: 218 个核心路由/编排/反馈测试全通过，commit `6c50373`

**Key Decisions**:
1. KIMI "飞轮未转动" 论断需修正: PreferenceBooster/InstinctLearner 已在 matcher pipeline 路径闭合，仅在非 matcher 层和自动退化环节有断点
2. CRITICAL-12（中文 AI Triage 绕过）应升为 P0，影响所有中文查询
3. 暂缓修复: 线程安全、FeedbackCollector O(n)、TaskDecomposer 技能上下文、自动退化/淘汰

**Files Modified**:
- `src/vibesop/core/routing/unified.py` — 6 处修复 (context 参数, call sites, Recommender, warmup, layer_details)
- `src/vibesop/core/routing/_layers.py` — 中文 bypass 字符数阈值
- `src/vibesop/core/routing/_pipeline.py` — rejected_candidates Pydantic 字段
- `src/vibesop/core/routing/optimization_service.py` — 空列表 IndexError
- `src/vibesop/core/routing/candidate_manager.py` — resolve() 缓存 + scope 默认值
- `src/vibesop/core/config/manager.py` — ConfigSource sentinel + 新配置字段
- `src/vibesop/core/skills/config_manager.py` — scope 默认值
- `src/vibesop/cli/feedback.py` — 方法名 + query 参数
- `tests/core/routing/test_ai_triage_production.py` — 测试查询适配

**Test Status**:
```
218 passed, 0 failed ✅ (1 pre-existing E2E failure excluded)
  - routing: 118 passed
  - orchestration: 64 passed
  - feedback: 36 passed
```

**Next Steps**:
- 修复线程安全 (_total_routes 锁, _LazyEmbeddingMatcher 双重初始化)
- FeedbackCollector 改为 JSONL 追加写入
- TaskDecomposer prompt 注入可用技能列表
- RetentionPolicy 自动退化到 DEPRECATED
- 安全审计：符号链接过滤、审计先于解析

---

### 2026-04-23 16:30

**Session**: Agent Runtime 层实现 + 平台适配 + E2E 验证

**Summary**:
1. **Agent Runtime 核心模块**（4 个模块，36 单元测试）
2. **平台适配**: Claude Code (hooks), Kimi CLI (AGENTS.md), OpenCode (plugin)
3. **E2E 验证**: 13 tests passed

**Key Decisions**:
1. Claude Code hook 脚本作为文档/参考生成
2. E2E 采用 Python 层模拟

**Next Steps**:
- 真实平台验证
- `vibe build --platform=all`

<!-- handoff:end -->
