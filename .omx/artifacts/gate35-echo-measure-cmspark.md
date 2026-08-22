# gate35 回声基线测量 (measure_echo_share.py)

- project_root: `/Users/huchen/Projects/cmspark`
- measured_at: 2026-08-22T13:28:08+00:00

## 结果

- miss 池大小: 525
- (a) miss 池 agent-prompt 形状占比（双报）:
  - 完整谓词 `_is_agent_prompt_shape`（含 150 字符规则）: 25/525 = 4.8%
  - 前缀谓词 `_has_agent_prompt_prefix`（修订 C, 无长度规则）: 16/525 = 3.0%
- (b) 已入队卡片回声占比（前缀谓词, 重议门槛口径）: 9/21 = 42.9%（pending 卡片 21 张, project+global 双 scope 去重）
- (c) 长 query 风险人口（>150 字符且非 agent 前缀）miss 占比: 9/525 = 1.7%

## 重议门槛参照（gate34 不做清单, 修订 G）

队列卡片回声率 >80% 且长 query 风险人口占比 <1% 才可重议 intake 过滤。
