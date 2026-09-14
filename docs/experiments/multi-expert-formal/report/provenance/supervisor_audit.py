"""Independent outcome/ledger audit; does not modify participant artifacts."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib, json, random, sys
root = Path(sys.argv[1])
high = sys.argv[2] if len(sys.argv) > 2 else 'D'
manifest = json.loads((root/'manifest.json').read_text())
assignments = manifest['assignments']
issues, rows, models = [], [], Counter()
interruption_unknowns = []
call_count = 0
for a in assignments:
    dest = root / a['allocation_id']
    d = json.loads((dest/'result.json').read_text())
    rows.append(d)
    if d.get('status') not in {'passed','failed','error','interrupted'}:
        issues.append([a['allocation_id'],'not_terminal'])
    for k in ['task_id','arm','spec_variant','repeat']:
        if d.get(k) != a.get(k): issues.append([a['allocation_id'],'metadata_'+k])
    requests = sorted(dest.glob('call-*-request.json'))
    ids = [int(p.name.split('-')[1]) for p in requests]
    if ids != list(range(len(ids))): issues.append([a['allocation_id'],'call_sequence'])
    totals = Counter()
    for q in requests:
        r = q.with_name(q.name.replace('-request','-response'))
        e = q.with_name(q.name.replace('-request','-error'))
        if int(r.exists()) + int(e.exists()) != 1:
            if d['status']=='interrupted' and not r.exists() and not e.exists(): interruption_unknowns.append({'allocation_id':a['allocation_id'],'request':q.name,'kind':'response_and_billed_usage_unknown'})
            else: issues.append([a['allocation_id'],'call_pair',q.name])
        req = json.loads(q.read_text())
        if req.get('temperature') != 0 or req.get('thinking') != {'type':'disabled'} or req.get('sdk_max_retries') != 0:
            issues.append([a['allocation_id'],'request_parameters',q.name])
        if r.exists():
            response = json.loads(r.read_text()); u = response.get('usage') or {}
            models[response.get('model')] += 1
            for name,key in [('used_i','prompt_tokens'),('used_t','completion_tokens'),('cache_hit','prompt_cache_hit_tokens')]: totals[name] += int(u.get(key) or 0)
            totals['reasoning'] += int((u.get('completion_tokens_details') or {}).get('reasoning_tokens') or 0)
    call_count += len(requests)
    led = d.get('ledger') or {}
    for k in ['used_i','used_t','cache_hit','reasoning']:
        if d['status']!='interrupted' and led.get(k) != totals[k]: issues.append([a['allocation_id'],'usage_'+k,led.get(k),totals[k]])
    events = [json.loads(l) for l in (dest/'tools.jsonl').read_text().splitlines()] if (dest/'tools.jsonl').exists() else []
    executed = [e for e in events if e.get('executed') is not False]
    if d['status']!='interrupted' and len(executed) != led.get('used_k'): issues.append([a['allocation_id'],'tool_ledger',len(executed),led.get('used_k')])
    if d['status']=='interrupted':
        d['ledger']={**totals,'used_k':len(executed),'origin':'derived_known_usage_lower_bound_from_persisted_files'}
    if [e.get('seq') for e in events] != list(range(len(events))): issues.append([a['allocation_id'],'tool_sequence'])
    if d['status']=='passed':
        notes=d.get('notes') or {}; ev=d.get('evaluation') or {}
        if not ev.get('passed') or not all(x['passed'] for x in ev.get('checks',[])) or not notes.get('delivered') or notes.get('conflicts') or notes.get('violations'):
            issues.append([a['allocation_id'],'success_contract'])
        violations=[e for e in executed if 'ownership_violation' in str(e.get('result')) or 'invalid_path' in str(e.get('error')) or 'path_escapes_workspace' in str(e.get('error'))]
        if violations: issues.append([a['allocation_id'],'success_path_review',violations])
    if d.get('task_hash') != (manifest.get('task_hashes') or {}).get(a['task_id']): issues.append([a['allocation_id'],'task_hash'])
by_arm=defaultdict(list)
paired=defaultdict(dict)
for d in rows:
    by_arm[d['arm']].append(d)
    paired[(d['task_id'],d['spec_variant'],d['repeat'])][d['arm']] = float(d['status']=='passed')
means=defaultdict(list)
for (task,spec,rep), arms in paired.items():
    if high in arms and 'A' in arms: means[task].append(arms[high]-arms['A'])
if len(means)!=12 or any(len(v)!=6 for v in means.values()): issues.append(['cluster_multiplicity'])
values = [sum(means[t])/len(means[t]) for t in sorted(means)]
rng = random.Random(20260913)
samples = sorted(sum(values[rng.randrange(len(values))] for _ in values)/len(values) for _ in range(20000))
def quant(p):
    x=(len(samples)-1)*p; i=int(x); f=x-i
    return samples[i]*(1-f)+samples[min(i+1,len(samples)-1)]*f
out={'cohort':root.name,'n':len(rows),'unique':len({a['allocation_id'] for a in assignments}),'manifest_sha256':hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),'calls':call_count,'models':dict(models),'issues':issues,'interruption_unknowns':interruption_unknowns,'usage_scope':'Known persisted usage only; interrupted pending calls may incur additional unknown billing','arms':{a:{'n':len(ds),'passed':sum(d['status']=='passed' for d in ds),'interrupted':sum(d['status']=='interrupted' for d in ds),'hidden_evaluated':sum('evaluation' in d for d in ds),'errors':dict(Counter(d.get('error','hidden_checks') for d in ds if d['status']!='passed')),'input':sum(d['ledger']['used_i'] for d in ds),'output':sum(d['ledger']['used_t'] for d in ds),'cache':sum(d['ledger']['cache_hit'] for d in ds)} for a,ds in by_arm.items()},'comparison':high+'-A','point':sum(values)/len(values),'ci95':[quant(.025),quant(.975)],'task_means':{t:sum(v)/len(v) for t,v in means.items()}}
n_hi=len(by_arm[high]); n_a=len(by_arm['A']); mi_hi=sum(d['status']=='interrupted' for d in by_arm[high]);mi_a=sum(d['status']=='interrupted' for d in by_arm['A']);out['interruption_point_bounds']=[out['point']-mi_a/n_a,out['point']+mi_hi/n_hi]
outpath=Path('.experiment')/('supervisor-final-'+root.name+'.json');outpath.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
