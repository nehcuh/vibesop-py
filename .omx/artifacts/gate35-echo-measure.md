# gate35 回声基线测量 (measure_echo_share.py)

- project_root: `/Users/huchen/Projects/vibesop-py`
- measured_at: 2026-08-22T13:28:08+00:00

> ⚠ vibesop-py 自身池太小（miss 池 5），不构成痛点基线；
> 痛点语料基线见同目录 `gate35-echo-measure-cmspark.md`
> （cmspark：miss 池 525、卡片 21、回声 42.9%、风险人口 1.7%）。

## 结果

- miss 池大小: 5
- (a) miss 池 agent-prompt 形状占比（双报）:
  - 完整谓词 `_is_agent_prompt_shape`（含 150 字符规则）: 0/5 = 0.0%
  - 前缀谓词 `_has_agent_prompt_prefix`（修订 C, 无长度规则）: 0/5 = 0.0%
- (b) 已入队卡片回声占比（前缀谓词, 重议门槛口径）: 0/0 = n/a（pending 卡片 0 张, project+global 双 scope 去重）
- (c) 长 query 风险人口（>150 字符且非 agent 前缀）miss 占比: 0/5 = 0.0%

## 重议门槛参照（gate34 不做清单, 修订 G）

队列卡片回声率 >80% 且长 query 风险人口占比 <1% 才可重议 intake 过滤。

⚠ SAMPLE TOO THIN: miss 池 5 < 30 —— 只报数字, 不下结论（沿用 ≥30 再议纪律）。

⚠ 无 pending 候选卡片: (b) 卡片口径无法计算 （先运行 `vibe skill scan-candidates` 入池后再测）。
