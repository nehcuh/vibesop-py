"""Audit completeness and metering; no new model calls."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
out=[]
for root in sorted((ROOT/'runs').iterdir()):
 if not (root/'manifest.json').exists():continue
 manifest=json.loads((root/'manifest.json').read_text())
 checks=[];usage={'input':0,'cached':0,'output':0,'reasoning':0};statuses={};models=set();responses=0
 for name,digest in manifest['hashes'].items():
  p=root/'frozen-sources'/name
  checks.append({'name':'frozen:'+name,'passed':p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==digest})
 for t,a in manifest['assignments']:
  d=root/f'{t}-{a}';p=d/'result.json'
  if not p.exists():statuses['not_started']=statuses.get('not_started',0)+1;continue
  r=json.loads(p.read_text());statuses[r['status']]=statuses.get(r['status'],0)+1
  for response in d.glob('call-*-response.json'):
   x=json.loads(response.read_text());u=x['usage'];models.add(x['model']);responses+=1
   usage['input']+=u['prompt_tokens'];usage['output']+=u['completion_tokens'];usage['cached']+=u.get('prompt_cache_hit_tokens',0)
   usage['reasoning']+=(u.get('completion_tokens_details') or {}).get('reasoning_tokens',0) or 0
   checks.append({'name':str(response.relative_to(root))+':request','passed':response.with_name(response.name.replace('response','request')).exists()})
 cost=((usage['input']-usage['cached'])*.15+usage['cached']*.003+usage['output']*.6)/1e6
 row={'run':root.name,'allocated':len(manifest['assignments']),'statuses':statuses,'models':sorted(models),'responses':responses,'usage':usage,'estimated_usd_offpeak':cost,'price_source':'https://api-docs.deepseek.com/quick_start/pricing/','not_account_invoice':True,'checks':checks,'record_audit_passed':all(x['passed'] for x in checks),'all_allocations_finished':sum(statuses.get(k,0) for k in ('passed','failed','error'))==len(manifest['assignments'])}
 (root/'audit.json').write_text(json.dumps(row,ensure_ascii=False,indent=2));out.append(row)
 print(json.dumps({k:v for k,v in row.items() if k!='checks'},ensure_ascii=False))
(ROOT/'audit-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
