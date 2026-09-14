"""Write the calibration checkpoint with exact observed counts, never pooled scores."""
import json
from pathlib import Path
P=Path(__file__).resolve().parent
runs=[p for p in sorted((P/'runs').iterdir()) if (p/'manifest.json').exists()]
lines=['# 多专家实验：校准阶段记录','', '正式 360 次实验尚未开始。本页记录执行器校准及其门槛，不能作为多专家体系的有效性结论。','', '## 已完成的基础设施','', '- 三个独立 CLI 校准任务：意图路由、配置路径生成与读取、下一根行情撮合。共 77 项行为验收。','- 隐藏验收器的正确实现、初始脚手架、业务错误变体及超时/输出异常处理自检通过。所有模型代码只在隔离 Docker 环境运行。','- 五组调用流程、随机分配、阶段及累计输出上限、逐调用原始请求/响应、模型标识、token 账本、源码哈希和失败产物均保留。','', '## 校准批次','', '| 批次 | 已结束 / 分配 | 验收通过 | 验收失败 | 运行错误 | 用途 |','|---|---:|---:|---:|---:|---|']
notes=['识别默认推理消耗与截断','关闭推理后识别内部报告被过早终止','保留内部截断报告，继续完整流程']
for i,r in enumerate(runs):
 a=json.loads((r/'audit.json').read_text());s=a['statuses'];done=sum(s.get(k,0) for k in ['passed','failed','error'])
 lines.append(f"| [{r.name}](runs/{r.name}/report.md) | {done} / {a['allocated']} | {s.get('passed',0)} | {s.get('failed',0)} | {s.get('error',0)} | {notes[i] if i<len(notes) else '另见清单'} |")
lines+=['','每次校准都是整批重新分配，未仅补跑失败组，未合并成 45 个独立正式样本。第一、二批保留原始错误判定，后续解释单列。','', '## 目前能够说什么','', '执行器的默认参数和失败判定足以制造“委员会更差”的假象，必须先排除。真实入口验收也确实捕捉到了代码契约错误：分工组有一次把明确规定为 0 的错误处理退出码改成了 1，另有运行出现舍入契约问题或交付 JSON 不合法。见[中间观察与证据链](observations.md)。','', '目前不能说委员会优于或劣于单体。只有三个校准任务，每组每批一次；执行器版本发生变化，且工具回路、完整上下文和实际可用预算尚未满足正式协议。','', '## 正式阶段的未完成项','', '1. 为所有组补齐相同的可见文件/测试工具回路及修复机会，保持角色和阶段上下文。','2. 修正预算分配使单体能使用完整总额度，并明确工人写入边界和依赖；重新做流程校准。','3. 制作并冻结十二个正式任务、完整/简略两版需求及共同澄清接口，独立核验隐藏标准。','4. 通过[协议一致性审查](protocol-fidelity-review.md)后再分配正式样本。强规划/弱执行扩展仍另依赖 R8 结算。','', '## 记录在哪里','', '每个运行目录的 manifest.json 是分配和冻结清单；frozen-sources 保存当轮源码；每次运行子目录包含 call-*-request.json、call-*-response.json、result.json 和 workspace；audit.json 校验记录与用量。错误响应也保留。来源代码或模型未运行时不伪造轨迹。','']
if all((r/'audit.json').exists() for r in runs):
 total=sum(json.loads((r/'audit.json').read_text())['estimated_usd_offpeak'] for r in runs)
 lines+= [f'三批任务 API 调用按实际 usage 与当日非高峰牌价估算合计约 **${total:.4f}**（不含预检、编写/审查工具的辅助调用和本地算力，不是账户账单）。[费率来源](https://api-docs.deepseek.com/quick_start/pricing/)。','']
(P/'RESULTS.md').write_text('\n'.join(lines))
print(P/'RESULTS.md')
