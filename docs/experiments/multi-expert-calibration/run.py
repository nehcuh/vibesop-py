"""Calibration only: bounded model calls, immutable attempts, isolated external checks."""
import concurrent.futures, hashlib, json, random, time, traceback, subprocess
from pathlib import Path
from datetime import datetime, timezone
from openai import OpenAI
from vibesop.core.llm_config import VibeSOPConfigManager
from tasks import TASKS, evaluate, self_check
ROOT=Path(__file__).resolve().parent
MODEL='deepseek-v4-flash'
def save(p,x):
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str))
def run(task_id,arm,root):
    d=root/f'{task_id}-{arm}';d.mkdir();w=d/'workspace';w.mkdir()
    task=TASKS[task_id]
    for name,content in task['files'].items():
        p=w/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
    base=task['spec']+'\nInitial files:\n'+json.dumps(task['files'],ensure_ascii=False)
    config=VibeSOPConfigManager.get_llm_config()
    client=OpenAI(api_key=config.api_key,base_url=config.api_base or 'https://api.deepseek.com',max_retries=0,timeout=120)
    used=0;inputs=0;calls=[]
    def call(stage,request,cap):
        nonlocal used,inputs
        messages=[{'role':'system','content':'You are participating in a coding experiment. Follow the supplied task. Do not assume any external files, tools or prior memory. Python standard library only.'},{'role':'user','content':request}]
        bound=len(json.dumps(messages,ensure_ascii=False).encode())+100
        if inputs+bound>100000 or used>=12000:raise RuntimeError('budget_exhausted')
        cap=min(cap,12000-used,6000)
        record={'stage':stage,'messages':messages,'max_tokens':cap,'model':MODEL,'temperature':0,'started_at':datetime.now(timezone.utc).isoformat()}
        n=len(calls);calls.append(record);save(d/f'call-{n:02d}-request.json',record)
        try:
            response=client.chat.completions.create(model=MODEL,messages=messages,temperature=0,max_tokens=cap)
            data=response.model_dump();save(d/f'call-{n:02d}-response.json',data)
            if response.usage is None:raise RuntimeError('missing_usage')
            used+=response.usage.completion_tokens;inputs+=response.usage.prompt_tokens
            record.update(input_tokens=response.usage.prompt_tokens,output_tokens=response.usage.completion_tokens,returned_model=response.model)
            if inputs>100000 or used>12000:raise RuntimeError('reported_budget_exceeded')
            if response.choices[0].finish_reason!='stop':raise RuntimeError('incomplete_response:'+str(response.choices[0].finish_reason))
            return response.choices[0].message.content or ''
        except Exception as exc:
            save(d/f'call-{n:02d}-error.json',{'type':type(exc).__name__,'message':str(exc)[:1500]});raise
    result={'task_id':task_id,'arm':arm,'phase':'calibration','status':'running','started_at':datetime.now(timezone.utc).isoformat()}
    save(d/'result.json',result)
    try:
        notes=''
        if arm=='B':
            notes=call('plan',base+'\nPlan implementation and checks. Do not produce code yet.',1800)
        elif arm in ('C','D'):
            reports=[]
            for i,role in enumerate(['architecture','implementation','quality']):
                identity=f'You are the {role} expert; focus on {role}.' if arm=='D' else 'Analyze independently without an assigned expert role.'
                reports.append(call('independent-'+str(i),base+'\n'+identity+' Return a concise analysis, no code.',1200))
            # A single round, all members see the same frozen reports; member 0 integrates.
            exchange=[]
            for i in range(3):
                exchange.append(call('exchange-'+str(i),base+'\nYour initial report:\n'+reports[i]+'\nAll initial reports:\n'+json.dumps(reports)+'\nGive a short correction or agreement based on evidence.',400))
            notes=json.dumps({'initial':reports,'exchange':exchange})
        elif arm=='E':
            plan=call('decompose',base+'\nDivide work into exactly two subtasks with explicit interfaces, file ownership, dependencies and acceptance. Return the plan, no code.',2400)
            workers=[]
            for i in range(2):
                workers.append(call('worker-'+str(i),base+'\nShared plan:\n'+plan+'\nImplement subtask '+str(i+1)+'. Return proposed code and integration notes. Earlier worker output if dependency exists:\n'+json.dumps(workers),3000))
            notes=json.dumps({'plan':plan,'workers':workers})
        code=call('deliver',base+'\nPrior work:\n'+notes+'\nImplement and check mentally, then deliver ALL required files. Return only a JSON object {"files":{"relative_path":"full file contents"}}. No markdown fences. No external tools are available in this calibration.',(4200 if arm=='B' else 6000) if arm!='E' else 3600)
        if arm=='B':
            code=call('check',base+'\nYour plan:\n'+notes+'\nYour implementation:\n'+code+'\nReview the implementation against the spec and return the complete corrected files as JSON {\"files\":{\"relative_path\":\"full contents\"}}. No markdown fences.',6000)
        obj=json.loads(code);files=obj['files']
        if not isinstance(files,dict) or not files:raise ValueError('invalid_files')
        for name,content in files.items():
            p=w/name
            if Path(name).is_absolute() or '..' in Path(name).parts or not isinstance(content,str):raise ValueError('invalid_path_or_content')
            p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
        result['evaluation']=evaluate(task_id,w)
        result['status']='passed' if result['evaluation']['passed'] else 'failed'
    except Exception as exc:
        result.update(status='error',error_type=type(exc).__name__,error=str(exc)[:1500])
    result.update(input_tokens=inputs,output_tokens=used,calls=len(calls),finished_at=datetime.now(timezone.utc).isoformat())
    save(d/'result.json',result)
    print(json.dumps({k:result[k] for k in ['task_id','arm','status','input_tokens','output_tokens']},ensure_ascii=False),flush=True)
    return result
if __name__=='__main__':
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root=ROOT/'runs'/stamp;root.mkdir(parents=True)
    check=self_check()
    save(root/'self-check.json',check)
    if not isinstance(check,dict) or check.get('passed') is not True:raise RuntimeError('self_check_failed')
    assignments=[(task,arm) for task in TASKS for arm in 'ABCDE'];random.Random(913).shuffle(assignments)
    save(root/'manifest.json',{'phase':'calibration','model':MODEL,'temperature':0,'max_output_total':12000,'max_input_total':100000,'sdk_retries':0,'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'docker_image_id':subprocess.check_output(['docker','image','inspect','python:3.12-slim','--format','{{.Id}}'],text=True).strip(),'assignments':assignments,'hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'tasks.py',ROOT/'README.md']}})
    print('RUN_ROOT='+str(root),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(run,t,a,root) for t,a in assignments]
        results=[f.result() for f in futures]
    save(root/'summary.json',results)
    print('COMPLETE '+str(root),flush=True)
