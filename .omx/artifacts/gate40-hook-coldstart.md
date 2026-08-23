# gate40 主项测量复核：hook 冷启动（2026-08-23）

方法：cmspark 生产 hook `.claude/hooks/vibesop-route.sh`，同一 prompt
（"帮我 review 一下最近的改动"），online 与 offline 各 n=3 连跑。

## 结果

| 模式 | n=3 墙钟（s） | 中位 |
|---|---|---|
| online（现状） | 16.67 / 18.40 / 17.66 | 17.7 |
| offline（HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1） | 6.00 / 4.37 / 4.09 | 4.4 |

- Lane C 前测：online 34.8/37.9 → offline 5.1。两批测量绝对值不同
  （HF Hub 限流状态随时间漂移），方向与量级一致：online 恒定慢
  13-30s，offline 稳定 4-6s，**~4x 差距的下界可靠**。
- offline 路由输出正确性：实测命中
  `custom/you-are-an-independent-architecture-adversarial-re-bd1bc217`
  （82%）并给出 alternatives——语义索引在 offline 下正常工作
  （模型已缓存）。
- 佐证：analytics.jsonl 纯路由计算 16-25ms；spans route span
  duration 中位 16.4s（811 条，口径不纯但量级一致）。

## 结论

修复成立：模型已缓存时导出 offline 环境变量，消除每次 prompt 的
HF Hub 在线等待。未缓存时必须保持在线（首次下载），fallback
fail-open。

## 补充口径留档（实施复审 claude-NIT,2026-08-24）

### 项 4 双向量级（谓词钉死）

- fallback-llm 桶：`spans.jsonl` 中 `metadata.has_match is true ∧
  metadata.skill_id == "fallback-llm"`。cmspark：30d fire 窗口
  1061/2822（37.6%，最大桶）；hit outcome join 后 1088/2440
  （44.6%；其中 1086 行早于 M12 修复 0d5f9d4（2026-08-21T06:03Z）
  为化石，2 行 2026-08-23 为活洞 B）。本仓：7 行（6 行 08-17/18
  single + 1 行 07-31 orchestrate）。
- CLI orchestrated 空 skill_id：`metadata.has_match is true ∧
  metadata.skill_id == "" ∧ mode == "orchestrated"`（orchestrator.py
  :472-478 一律 primary=None）。cmspark 69 行 / 本仓 11 行——
  修复后其中有真步者进入 fire（潜在增量上界）。
- 空 skill_id 三口径：outcome-join 口径 85 行（pi，全 hook 全
  ≤08-21）；gate39 unjoined 口径 37/2437；直扫 spans 口径 18 行
  （07-30→08-23 含 single）。

### 项 2 燃料核查

`feedback.json` / `execution_feedback.json` 在本仓与 cmspark 的项目
级 `.vibe/` 及全局 `~/.vibe/` 均不存在（2026-08-23 查）——"今天零
行为变化"仅限这两个已知现场。

### 项 5 性能标定

合成 200 技能 × 2000 反馈记录（mock feedback/exec/prefs，隔离每技
能文件 I/O），`evaluate_all_skills` 本机三次取末次：修前 1.059s →
修后 0.0116s（~91x）。Lane A 初测（700×5000）：median 20.8s →
热点块 2915ms→单遍 92µs。热点=evaluator.py:201-204 每技能重建
全量计数（evaluate_all 总量 O(distinct²×records)）。

### 冷/热缓存两态 e2e

- 冷缓存（无 HF cache）：orbstack 容器 e2e（smoke + llm routing
  7/7）——容器无 HF 缓存，首次下载路径经 helper 在线重试完成，
  全程通过。
- 热缓存：本机 offline 测量 n=3（4.09-6.00s），local_files_only
  快路径 + 路由结果正确（82% 命中）。
