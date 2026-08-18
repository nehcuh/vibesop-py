测试执行被权限拒绝，以下结论基于静态代码核实(`[inspected]`):锁语义、字段名、调用点均已逐一读源码验证。

---

## 门禁结论：PASS_WITH_NITS

**已验证成立的关键论断**

- **M1a 修净**:`_layers.py` 残留 4 处 `AI_TRIAGE` 均属 `try_ai_triage_layer` 真实标注;`try_index_layer` 的 LayerDetail 本就是 SEMANTIC_INDEX(`_layers.py:421-499`);`unified.py:569` 为真 triage 调用点。无遗漏误标。
- **M1d 锁取舍正确**:`blocking=False` 竞争时抛 `CouldNotLock`(file_lock.py:40,OSError 子类)，被 `except Exception` 吞 → 丢信号且不写状态，不阻路由。临界区毫秒级，降级方向正确。
- **约束遵守**:`from_dict` 逐键 `.get`,旧读新文件安全;`routing_layers` 键名与 M1b 读取一致(unified.py:932);`record_telemetry=False` 门控 analytics/miss/pending 三写路径(unified.py:842-846),重放不污染遥测、不推进 last_route。

**问题**

1. **[P1] M1c join 系统性失配**：triage 日志存**原始** query(cost_tracker.py:99 "Original user query",未 redact),analytics 存 **redacted** query。凡命中 redaction 的 query 弱标注必为空。修：join 前对 triage 侧过一遍 `redact_sensitive`。
2. **[P1] M1b `_build_router` 硬编码 `project_root=ROOT`**:重放非本仓库日志时，用 vibesop-py 的技能集比对新旧决策，一致率失真。应从 `--log` 父目录推导或加 `--project-root` 参数。
3. **[nit] M1b 层分布口径污染**：M1a 修复前的旧日志 index 决策记为 `ai_triage`,重放后变 `semantic_index`,层分布 diff 被“改标签”淹没而非真实漂移;`no_match` 与历史 `fallback_llm` 哨兵命名不一致，同类问题。报告应标注切分时点。
4. **[nit] M1d 边界**：负秒(时钟回拨)会误判 `is_rapid_reroute`,建议 clamp;analytics 追加失败时 last_route 状态已推进(罕见，无测试覆盖)。
5. **[nit] M1c merge 非原子写**：main 追加 + extended 重写均无 temp+rename,崩溃丢条目；dev 脚本可接受，但违反项目原子写纪律。

**专项裁决**：M1c “最新 wins” 可接受——同 query 后续 triage 覆盖旧标签，配合全量 `needs_review` 人工兜底，风险闭合。M1b `old_layer=routing_layers[-1]` 在早退架构下成立(命中即 return,末层即决策层)，但叠加问题 3 后仅作参考指标。

P1 两项均在离线工具链、下游有人工确认兜底，不阻塞合入，建议 M2 前修。
