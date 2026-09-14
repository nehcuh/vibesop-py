"""Regenerate a partial or final calibration report from persisted run records."""
import json,sys
from pathlib import Path
from collections import Counter
root=Path(sys.argv[1]) if len(sys.argv)>1 else sorted((Path(__file__).parent/'runs').iterdir())[-1]
rows=[json.loads(p.read_text()) for p in sorted(root.glob('*/result.json'))]
lines=['# 多专家校准运行结果','',f'运行目录：`{root.name}`。以下为流程校准，不能据此比较组织效果。','', '| 组 | 已记录 | 通过 | 验收失败 | 运行错误 | 运行中 | 输入 tokens | 输出 tokens |','|---|---:|---:|---:|---:|---:|---:|---:|']
for a in 'ABCDE':
 r=[x for x in rows if x['arm']==a];c=Counter(x['status'] for x in r)
 lines.append(f"| {a} | {len(r)} | {c['passed']} | {c['failed']} | {c['error']} | {c['running']} | {sum(x.get('input_tokens',0) for x in r)} | {sum(x.get('output_tokens',0) for x in r)} |")
lines+=['','## 逐次结果','']
for x in rows:
 ident=x['task_id']+'-'+x['arm']
 lines.append(f"- [{ident}]({ident}/result.json)：{x['status']}"+('；'+x.get('error','') if x.get('error') else ''))
lines+=['','## 解释边界','','这批使用受约束的文件交付协议和专门构造的小型 CLI 夹具。尚无交互工具回路，不是完整生产仓库开发；B 使用显式重传的阶段上下文，C/D 的交流执行串行但读取相同冻结报告，E 工人提交代码文本供整合者集成。正式实验必须先审计这些实现与协议的一致性。模型别名、隐藏推理 token 与输出截断均须检查。','', '真实货币费用尚未计算；报告 token 用量，不将相同上限宣称为相同实际费用。失败没有删除或替换。']
(root/'report.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines[:11]))
