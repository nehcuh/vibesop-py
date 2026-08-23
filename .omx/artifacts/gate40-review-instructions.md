# Gate40 设计稿三路评审任务书

你是独立高级评审，复审 VibeSOP 项目 gate40 的设计综合稿。项目根：/Users/huchen/Projects/vibesop-py。

## 被审对象

`.omx/artifacts/gate40-synthesis.md`（r1，随附全文）+ 主项测量档案 `.omx/artifacts/gate40-hook-coldstart.md`（随附全文）。

范围五项：主项 hook 冷启动 HF_HUB_OFFLINE 修复（Lane C 清单外发现升格）；项 5 evaluator 单遍 Counter 性能修复；项 4 空 skill_id 写侧对齐（CLI has_match 与 hook 同谓词 + 首真步 skill_id）；项 2 F/archive 规则 ≥3 闸对齐；项 1 dashboard 五处 spans 硬编码镜像。项 3 容量治理砍（记档量化重议条件）。

## 历史裁决参照（先读）

`.omx/artifacts/gate34-synthesis.md` 不做清单、gate37 §4、gate38 §5、gate39 §4/§6（均在同目录）。

## 评审要点

1. **主项重点攻击**：测量可信度（两批测量绝对值漂移但方向一致——4x 下界是否足够立项）；offline 导出的风险面（首次安装未缓存时的 fallback 设计是否完备；fail-open 边界；多平台 hook 模板是否都要改——查 build 系统里 hook 模板有几处）；有没有比环境变量更优的注入点（譬如 Python 侧 `local_files_only` 逐级 fallback）？
2. **项 4 语义攻击**：CLI has_match 改与 hook 同谓词——all-fallback orchestrated 从 hit 翻 miss 进发现池，这个发现池组成变化有没有被充分评估（gold_detection 的 CLI miss 处理、miss_counter、发现队列水位）？hook 侧 steps[0]→首真步的改动有没有实证样本支撑（稿中自述 cmspark 无实证）——无证据点修是否符合"无测量不立项"精神？
3. **项 2 语义攻击**：F 规则从 `<3` 翻 `>=3` 后，deprecate 动作的真实命中率变成什么（≥3 反馈且 F 档的门槛是不是永远达不到，使 deprecate 名存实亡）？archive 加 ≥3 闸后 90 天未用的薄样本技能是否永远滞留？"今天零行为变化"的论证（feedback 为空）是否覆盖所有 dogfood 现场？
4. **项 5**：单遍 Counter 修复的正确性（同值重算的证明）；公共签名不动的约束下私有路径加可选参数是否干净；optimization_service 不加缓存的裁决（修复后亚毫秒投影是否可信）。
5. **换皮与不变量**：对照四份历史裁决；主项是否真不动 embedding 语义；项 4 是否真不碰三套 trigger 匹配逻辑（改的是记录值）。
6. **证据核查**：抽查至少 8 处 文件:行号（重点：_layers.py:403、triage_recall.py:123、evaluator.py:201-204、feedback_loop.py:143-148/:178、agent_runtime.py:557-563/:668、cli/main.py:903-914、server.py 五处、manager.py:553-563、tool_sequences.py:137-154 轮转先例）。

## 输出格式（严格遵守）

```
## Verdict
PASS / PASS_WITH_NITS / BLOCK

## Findings
- [BLOCK|MAJOR|NIT] 描述（附 文件:行号）
```

只读核查（grep/read，可在 /tmp 跑只读测量脚本复核），不要修改仓内任何文件，不要客套。
