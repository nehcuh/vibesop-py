# Gate40 实施双路复审任务书

你是独立高级评审，复审 VibeSOP 项目 gate40 的实施。项目根：/Users/huchen/Projects/vibesop-py。

## 设计规格

`.omx/artifacts/gate40-synthesis.md`（**r2.2 终稿**，§8 有全部三轮收敛记录）+ 测量档案 `.omx/artifacts/gate40-hook-coldstart.md`。先读它们，再读随附 gate40-impl.diff。

## 范围（五个独立 commit 的内容）

1. 主项：`core/embedding_loader.py` 共享 helper（local_files_only 优先 + 异常分类学 + 显式在线重试）+ 6 处加载点改走它。
2. 项 5：evaluator.py 单遍 Counter（evaluate_skill 可选参数扩展 + evaluate_all_skills hoist）。
3. 项 4：CLI/hook span metadata 写值按"首个真技能步"谓词（has_match/skill_id/top_skills 同源）+ 读侧 `_route_hit_skill_id` sentinel 排除 + skill_outcomes `fallback` 顶层计数 + recall.py 第三读者 + gold_detection docstring 改写。
4. 项 2：feedback_loop F-deprecate 双 conjunct（≥3 + accuracy<0.5）+ archive ≥3 闸 + docstring/reason 全量同步。
5. 项 1：dashboard server.py 五处 spans 硬编码走 `_spans_path()`。

## 评审要点

1. **规格符合性**逐条对照 r2.2 §1-§5，重点：
   - helper 异常分类学伪码逐字一致；各加载点既有 except 形态零改动；helper 无状态。
   - 项 4：property/result.skill_id/skill_name/alternatives 零改动（结果契约）；top_skills 与 span skill_id 同谓词；miss 行 skill_id 双生产者一律 ""；fallback 行不进 unjoined；对账式 Σ三列+unjoined+fallback=hit 总数。
   - 项 2：双 conjunct + archive 闸 + docstring/reason 字符串同步。
   - 项 1：不镜像 exists-gate；生产逐字节不变。
2. **不变量**：三套 trigger 语义、双 embedding 分离（helper 不得混入 observability/embedding.py 的 FastEmbed 栈）、`_is_agent_prompt_shape`、gate30 upsert、`_is_miss`/`_classify`/`_is_hit`/`_classify_hit` 函数体、存储双锁。
3. **测试说服力**：非缺失类单败→零在线调用（真能红）；property 不变 pin 与 span 写值翻转共存；sentinel→fallback 计数（不进 unjoined）pin；项 2 反例（accuracy=1.0 不 deprecate）。
4. **WS 申报偏差裁决**：WS1 helper 落点（新模块 core/embedding_loader.py 而非 observability/embedding.py，理由=双 embedding 分离）；WS1 learner.py 一处 format 折行；WS1 indexer 包缺失日志路径微调；WS3 recall.py 后置过滤（非一行内联）+ dict 分支惰性证实；WS4 的 TestFeedbackLoopOptIn 夹具 total_routes 1→3 最小偏差（断言零改动）；WS5 的 _write_span dag=True 双写 fixture（dag_rebuilder.py:227 不在范围）；主代理集成修复（test_stale_readonly/test_optimize_cmd 夹具 1→3）。逐项判断合理性。
5. **文档同步**：CHANGELOG gate40 条目（主项测量数字、项 4 双向量级披露 1061/2822 与 1088/2440、项 2 措辞边界"证据门槛 1→3+质量下限"非"已修复"、薄 F 真空区、两现场限定）；CLI_REFERENCE outcomes 的 fallback 段；check_docs 双过。
6. **隐藏破坏面**：grep `load_sentence_transformer|local_files_only|fallback` 兜底；6 加载点之外有没有漏网的 SentenceTransformer( 直调；fire 列 sentinel 排除对其他消费方的波及。

## 输出格式（严格遵守）

```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```

只读核查（grep/read/跑测试），不要修改任何文件，不要客套。
