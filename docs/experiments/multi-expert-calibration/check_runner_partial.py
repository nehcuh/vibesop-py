"""Offline harness checks only; no model result is produced."""
import importlib.util,json,sys,tempfile,types
from pathlib import Path
from unittest.mock import patch
path=Path(__file__).with_name('run_partial_reports.py')
fake=types.ModuleType('tasks');fake.TASKS={'dummy':{'spec':'dummy','files':{}}};fake.evaluate=lambda *a:{'passed':True,'checks':[]};fake.self_check=lambda:{'passed':True}
with patch.dict(sys.modules,{'tasks':fake}):
 spec=importlib.util.spec_from_file_location('calibration_runner',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Response:
 def __init__(self,finish='stop'):
  self.usage=types.SimpleNamespace(prompt_tokens=20,completion_tokens=20)
  self.model='offline-test';self.choices=[types.SimpleNamespace(finish_reason=finish,message=types.SimpleNamespace(content='{"files":{"app.py":"print(1)"}}'))]
 def model_dump(self):return {'offline_test':True,'finish':self.choices[0].finish_reason}
class Client:
 finish='stop'
 def __init__(self,**kwargs):self.chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda **k:Response(self.finish)))
m.OpenAI=Client;m.VibeSOPConfigManager=types.SimpleNamespace(get_llm_config=lambda:types.SimpleNamespace(api_key='offline-test',api_base=''))
checks=[]
with tempfile.TemporaryDirectory() as temp:
 for arm,count in zip('ABCDE',[1,3,7,7,4]):
  r=m.run('dummy',arm,Path(temp));assert r['status']=='passed' and r['calls']==count,r
  assert len(list((Path(temp)/('dummy-'+arm)).glob('call-*-response.json')))==count
  checks.append({'name':'flow_and_logging_'+arm,'passed':True})
with tempfile.TemporaryDirectory() as temp:
 Client.finish='length';r=m.run('dummy','A',Path(temp));assert r['status']=='error' and 'incomplete_response' in r['error'];assert r['output_tokens']==20
 checks.append({'name':'truncated_response_retained_with_usage','passed':True})
Path(__file__).with_name('runner-partial-self-check.json').write_text(json.dumps({'offline_only':True,'passed':True,'checks':checks},indent=2))
with tempfile.TemporaryDirectory() as temp:
 r=m.run('dummy','C',Path(temp));assert r['status']=='error' and r['calls']==7
 assert len(r['partial_internal_stages'])==6
print('Offline revised runner checks passed; six partial reports continue, final truncation fails.')
