# R6 预注册：弱模型 A/B（喷气发动机实验台，与 R5 同任务）

> 2026-08-29 · §1–§7 写死，build 后不改；§8 为 build 后事故与协议偏移附录 · 单变量设计
> 动机：R1-R5 四连产物平手（强模型）；价值矩阵中"弱模型"格未测。用户指定弱模型并要求 vibe route 同模型（公平性）。

## 1. 单变量变更（vs R5）

| | R5 | R6 |
|---|---|---|
| 编码模型（双臂同） | grok 默认（xAI 托管，强） | `Qwen3.8-27B-Uncensored-OrcaRouter-MLX-8bit`（oMLX 本地 localhost:11434，~22 tok/s，256k ctx） |
| vibe route LLM（treatment） | deepseek（容器全局配置） | **同一个 27B**（容器全局配置已切 ollama，用户公平性要求） |
| 其余（任务/种子/runner 参数/技能宇宙/hook/评分） | — | 逐字不变 |

## 2. 已验证机制 [executed 2026-08-29]

- oMLX 兼容 OpenAI chat_completions；grok 0.2.111 经 `[model.omlx-qwen]` 自定义端点正常工作
- 弱模型走通 agentic 工具循环：hello.txt 38s / ok.txt 55s / 真任务 3-turn 125s（rc=1 是 max-turns 3 截断，预期内）
- hook 在 headless 下触发（span 130ms/995ms 级）；**multi-intint Execution Plan 输出被 grok 丢弃**——R5 transcript 0 注入，R6 同构（机制parity，不影响单变量）
- 路由实际生效路径 = 模型按协议规则**自调 `vibe route` CLI**；R5 transcript：5 次 vibe route 引用、80 次 SKILL.md、24 次 superpowers
- 30s hook 超时无风险（启发式路径 ~1s）；LLM triage 走 self-call（工具调用无此超时）

## 3. 协议

- 双臂容器同 R5（`vibesop-ab:base`）；`/work` 重置为种子（TASK.md sha256 前缀 8607beff / three.min.js 9274bbce，与 R5 逐字一致）
- runner：与 R5 相同 + `-m omlx-qwen`；`--prompt-file /work/TASK.md --no-subagents --disable-web-search --max-turns 150 --always-approve`
- **顺序执行**（treatment 先）：单台 oMLX，避免双臂争抢显存/调度造成不公
- treatment 有效性三验：① /work/.vibe 出现 run 时段 route span ② transcript 见技能目录/路由行为 ③ route LLM=ollama（配置+延迟特征）

## 4. 评分表（与 R5 逐字相同，5 维 × 5 分，步长 0.5）

- **D1 物理保真**：推力/转速/EGT/燃油流量相互关系物理合理；spool-up 惯性；慢车推力>0、EGT>环境温度
- **D2 3D 交互**：可旋转缩放；5 部件可辨识；标注/选中交互
- **D3 教学法**：部件说明；工作原理；引导式实验流程（联动观察）
- **D4 工程质量**：结构可维护；无 console 错误（node --check + 静态审读）；资源引用 200
- **D5 完成度**：交付物齐备度、实现说明

## 5. 预测（build 前写死）

| # | 预测 | 判据 |
|---|---|---|
| P1 | 双臂总分较 R5（23.5/23.5）显著下降 | 各 ≤18，或至少一臂不可运行 |
| P2 | **核心假设**：treatment 总分 > control ≥3 分（技能对弱模型有抬升） | Δ=T−C |
| P3 | 完成风险：至少一臂 150-turn 用尽或产物不可运行 | rc / 文件 / node --check |
| P4 | treatment 过程层技能消费更多（SKILL.md 引用数、vibe route 调用数） | transcript 计数 |
| P5 | 27B 路由质量低于 deepseek：更多 no-match/低置信 | /work/.vibe spans + transcript |

反向假设（同样当真）：**技能注入对弱模型是净伤害**（上下文污染/注意力稀释）→ Δ ≤ −3。

## 6. 判读规则（写死）

1. Δ ≥ +3：弱模型格方向性支持技能抬升（n=1，仅方向性证据，需 n≥3 复验）
2. \|Δ\| ≤ 2：第 5 连零增益，弱模型格单点也不支持 → 两臂捆绑设计封盘，只余三臂 (c)−(b)
3. Δ ≤ −3：技能伤害弱模型（污染假设成立）→ 记入 harness 假说矩阵"差 harness+技能=主动伤害"的弱模型版
4. 双臂均无产物：不做评分，只报完成度差距 + 过程层
5. oMLX 中途故障：该臂作废重跑（fresh /work），报告注明
6. 墙钟不作判据（R2/R5 已证不稳健）；token 用量记录不判定

## 7. build 后才允许做的事

评分、预测判定、机制提取（SKILL.md 计数、route 结果统计、span 核查）。

## 8. 事故记录（规则 5 情形）

- **尝试 1 作废（treatment，656s rc=1 零产物）**：`max_completion_tokens=8192`（实验方配置）截断弱模型长推理链 → oMLX `max_tokens_truncation` → grok 按错误终止。修复：32768（双臂同步）。
- **路由 LLM 静默失败**：VibeSOP factory ollama 分支不传 config model，硬编码默认 `Qwen3.6-35B-A3B-mlx-mxfp8` 在 oMLX 不存在（实际名 `-mxfp8`）→ 52ms 404 → 无 LLM 回退。修复：`OLLAMA_MODEL` env（双臂 runner 同步导出）。验证 span：`llm:Ollama:Qwen3.8-27B-Uncensored-OrcaRouter-MLX-8bit` ok。
- 上述均为实验基础设施修复，不改变单变量设计；factory model 透传 bug 记 P3 backlog。
- **尝试 2 作废（treatment，2696s rc=1 零产物）**：大任务触发推理模型思考循环——单轮 45 分钟、11006 个 reasoning 事件、零工具调用，撞 32768 上限 → oMLX 以错误上报截断 → grok 整体终止。修复（双臂同参，内部公平保持）：runner 加 `--reasoning-effort low --no-plan`（小任务验证：reasoning 事件 11006→15，28s 完成）。此为对 R5 runner 的协议偏移，记入判读脚注。
