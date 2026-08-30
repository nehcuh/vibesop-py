# R6 报告：弱模型 A/B（喷气发动机实验台）

> 2026-08-29 · 预注册见 `ab-jet-weak-prereg.md`（§1–§7 build 前写死，§8 为 build 后附录）
> 编码模型双臂同：`Qwen3.8-27B-Uncensored-OrcaRouter-MLX-8bit`（oMLX localhost:11434）
> treatment 的 vibe route LLM = 同一个 27B（用户公平性要求，已验证）

## 1. 运行记录

| 臂 | 尝试 | 时长 | rc | 死因 | 产物 |
|---|---|---|---|---|---|
| treatment | 1 | 656s | 1 | max_completion_tokens=8192 截断思考链（实验方配置失误） | 0 |
| treatment | 2 | 2696s | 1 | 单轮思考循环 11006 reasoning 事件零工具调用，撞 32768 帽 | 0 |
| **treatment** | **3** | **19970s** | **1** | **oMLX 内存守卫 prefill 中途中止（61 turns、累计输入 8.11M tok）** | **10 文件 / 2503 行** |
| control | 1 | 5310s | 1 | 思考循环撞 32768 帽；全程仅 2 次工具调用（`list_dir` + 1 终端命令，均在第 40 分钟） | 0 |
| control | 2 | 2561s | 1 | 同上，0 次工具调用，10935 reasoning 事件 | 0 |

协议偏移（双臂同步，见预注册 §8）：`max_completion_tokens=32768`、`--reasoning-effort low --no-plan`。

**Protocol gap（control runner 参数时点未记录）**：control 各尝试实际生效的 runner 参数时点未被记录——`--reasoning-effort low --no-plan` 是在 treatment 尝试 2 作废后才加入的（见预注册 §8），但 control 尝试 1/2 是否在该修复之后运行、是否携带同参数，无记录可核验。若 control 未使用 `--reasoning-effort low --no-plan`，则存在 runner 协议混杂（双臂不同参），完成度对比的内部公平性进一步受损。

treatment 尝试 3 的死因裁定：oMLX 内存守卫属预注册规则 5 的"oMLX 中途故障"，但**全部交付物在中止前已完成**（最后文件写于 13:07:39，中止在其后），故障只吞掉了收尾消息。裁定不作废——重跑 5.5 小时只为补一段 200 字说明不符合规则 5 的目的（结果未被故障污染）。D5 按缺交付说明扣分，事故入册。

## 2. 产物评分（treatment；control 零产物不评分）

D1-D5 与 R5 逐字同表（5 维 × 5 分，步长 0.5）。

| 维 | 分 | 证据 |
|---|---|---|
| D1 物理保真 | **5.0** | 扭矩平衡 + 压气机 N³ 负载 + 能量平衡 EGT + FADEC 加速燃油限制 + 转速/EGT 双保护（滞回）+ 启动电机 + 停车摩擦收尾；慢车推力 5.8kN>0、EGT 340°C>环境 25°C、spool 4.5-9.4s 实测。25 项物理自验**全部通过 [executed]**（`node test/sim-test.js` rc=0） |
| D2 3D 交互 | **4.5** | 5 部件独立几何/材质/标注/点击详情/悬停高亮；InstancedMesh 叶片带扭转；EGT 驱动发光；透明罩切换看内部；自写轨道控制 [inspected]。浏览器端未实机验证（无 GUI），指针交互的冒烟测试在中途崩溃（见 D4） |
| D3 教学法 | **5.0** | 6 步引导实验（条件自动判定 + 每步预期观测值 + 思考题 + 完成要点总结）；布雷顿循环原理页 + 因果链图 + 参数表 + "推力为何滞后"注解 |
| D4 工程质量 | **3.5** | 10 文件模块化、`node --check` 全过 [executed]、资源全本地 [executed]。扣分：app-smoke 冒烟测试在 PointerEvent 模拟处崩溃（jsdom 无此构造器）[executed]，"console 无错误"仅部分验证；构建期 `npm i jsdom` 违反任务书"构建与运行均离线"的字面（模型有透明权衡说明，测试专用、装在 /work 外） |
| D5 完成度 | **4.0** | 应用交付物齐备；但 200 字「实现说明」因运行中止从未输出，也无 README |
| **合计** | **22.0 / 25** | （R5 双臂 23.5/23.5） |

## 3. 预测判定

| # | 预测 | 判定 |
|---|---|---|
| P1 | 双臂总分较 R5 显著下降（各 ≤18 或至少一臂不可运行） | **部分命中**："至少一臂不可运行"字面成立（control ×2 零产物）；但 treatment 22.0 远高于预测的 ≤18——弱模型在有支撑的环境里产物质量接近强模型，这半边预测错了 |
| P2 | 核心：Δ=T−C ≥ +3（技能抬升弱模型） | **无法按判据计算**：C 无产物，Δ 无数值。完成度差距是极大的（10 文件 vs 0 文件 ×2），但**归因失效**——见 §4，技能内容从未进入 treatment 的上下文。方向性支持"treatment 环境优于裸环境"，不支持"技能注入抬升弱模型" |
| P3 | 完成风险：至少一臂 150-turn 用尽或不可运行 | **命中**（treatment 实为 oMLX 内存中止 + control 两次不可运行；预测的精神——弱模型完成风险高——完全应验） |
| P4 | treatment 技能消费更多（SKILL.md 引用、vibe route 调用） | **名义命中、实质未命中**：route 调用 2>0 ✓；但 SKILL.md 读取 0 vs 0——两臂都没消费技能内容 |
| P5 | 27B 路由质量低于 deepseek（更多 no-match） | **命中**：2/2 路由调用 no-match（07:45 hook 全文查询、08:28 模型自调摘要查询），模型自述 "Routing didn't match any existing skill (no confident match via the fallback LLM)"。R5（deepseek 路由）同期 SKILL.md 消费 80 次 |

> 判读脚注（预注册 §8 承诺的协议偏移说明）：runner 参数 `--reasoning-effort low --no-plan` 为 build 后对 R5 runner 的协议偏移（协议记录双臂同参；control 侧执行时点无记录，见 §1）；且 treatment 尝试 3 的保留依赖规则 5 的事后豁免（见 §5 协议偏离声明）。本节全部判定均在此两点偏移下作出。

反向假设（Δ≤−3 污染伤害）：未检验到——技能内容未注入，无污染可言。

## 4. 机制提取（本 R 最重要发现）

**treatment 的胜利路径里没有技能。**

- 路由链 [executed]：hook 在 +1.5min 触发 route（27B，`ai_triage_log.jsonl` 07:45:40，`selected_skill: null`）→ 模型 +44min 自调 `vibe route "制作喷气发动机实验台：…"`（08:28:27，`selected_skill: null`，891 tok，$0.001）→ 模型显式推理："路由没匹配到技能，任务书本身就是完整需求文档，直接实现" → 全程 **0 次 SKILL.md 读取**（read_file 目标全部是 TASK.md 和自己的产物）
- R5 对照：同任务强模型 5 次 route 自调、80 次 SKILL.md 读取、24 次 superpowers 引用
- treatment 真正多出来的上下文 [executed]：VibeSOP 路由协议规则（~/.grok/rules/routing.md）+ 技能目录提醒（mattpocock 工程包 8 项，仅名称+描述）+ `vibe` CLI 可用。control 只有 grok 自带 bundled 目录（build-with-ai 等，与任务无关）
- 过程对比：treatment 前 82 分钟也在纯思考（与 control 的循环同构），09:06 突破写出首文件，之后 4 小时均匀产出 10 文件、61 turns、88 次工具调用（50 编辑 + 11 写 + 14 终端 + 10 读）；control 两次尝试分别 2 次、0 次工具调用后死于思考循环
- token [executed]：treatment 累计输入 8.11M（缓存读 7.87M）/输出 165k；control 每次尝试 32k 输出纯思考

**混杂结构**：treatment-control 差 = ① VibeSOP 静态脚手架（协议+目录+CLI）+ ② n=1 弱模型方差（control 自己两次同配置尝试就差 2 vs 0 工具调用）。无法分离。①中"route 调用返回的 Routing Decision Report"可能起了结构化任务复述作用（模型自调时把任务浓缩成了一句话查询），但这只是猜想。

## 5. 结论（按判读规则）

> **协议偏离声明**：本节结论依赖一次对预注册写死规则 5（oMLX 中途故障作废重跑）的事后豁免（见 §1 treatment 尝试 3 的死因裁定）——按写死规则该尝试应作废重跑，本报告选择保留并评分，属协议偏离。敏感性说明：若严格执行规则 5，treatment 臂亦无有效评分（三次尝试全部作废），treatment vs control 的核心完成度对比不成立，本节第 2、4 条结论随之失效。

- 规则 4 变体适用（单臂零产物）：只报完成度 + 过程层，control 不评分
- **完成度结果**：裸弱模型在本任务两次尝试均无法启动（control 0/2）；VibeSOP 环境在场的弱模型三次尝试中一次交付 22/25 的完整应用（treatment 1/3，另两次作废）
- **但对核心问题的回答**：R6 检验的不是"技能注入抬升弱模型"，而是意外检验了**"路由层是弱模型技能系统的瓶颈"**——27B 路由 2/2 no-match，技能内容根本没机会进入上下文。技能对弱模型有无抬升，在路由质量解决前是不可检验的
- harness 假说矩阵新增弱模型格证据（**方向性观察，非定论**）：好 harness + 弱模型 + 技能目录在场但零注入 → 仍能交付接近强模型质量的产物（22 vs 23.5）；裸上下文 + 弱模型 → 完全无法启动。方向性提示**结构层（环境脚手架）可能主导、提示词层（技能内容）缺席也成立**——但该观察依赖上述规则 5 事后豁免，且 §4 混杂（VibeSOP 静态脚手架 vs n=1 弱模型方差）与 §1 runner 参数时点未闭合，不能作定论
- 两臂捆绑设计封盘判定（规则 2）未触发（Δ 不可计算）；弱模型格建议改问"路由质量"而非"技能注入"，那是 27B 下的第一瓶颈

## 6. P3 backlog（本次实验暴露的 VibeSOP 缺陷）

1. `factory.py` ollama 分支不透传 config model → 静默用硬编码默认名（404 无声回退）
2. `enable_orchestration=false` 在 hook CLI 路径不被尊重（multi-intent 启发式抢占后 LLM 缺失回退分解）
3. multi-intent Execution Plan 输出形状被 grok headless 丢弃（R5/R6 同构，hook 通道对长 prompt 无效）
4. cron 注入的巡检 prompt 被 VibeSOP 路由误命中 autonomous-experiment 技能（已知 FP 模式又一例）

## 7. 工件索引

- treatment 产物：`/tmp/ab-jet-r6-treatment/`（10 文件 + .vibe）
- control 证据：`/tmp/ab-jet-r6-control-evidence/`（attempt2 transcript/stderr/meta）；attempt1 数据在本文 §1
- 容器：`vibesop-ab-treat`（保留）/ `vibesop-ab-ctrl`（保留）
- 预注册：`.omx/artifacts/ab-jet-weak-prereg.md`
