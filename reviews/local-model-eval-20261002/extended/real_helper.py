"""LOCAL-BECAUSE: hardware: actual dashboard helper regression-test draft trial."""
import ast
import json
import re
import signal
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from expanded import BASE, ROOT, validated

REPO=ROOT.parents[2]
source=(REPO/'dashboard/vfdash/words.py').read_text()
tree=ast.parse(source);parts=[]
for node in tree.body:
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_UTC_FORMATS' for t in node.targets) or isinstance(node,ast.FunctionDef) and node.name=='parse_utc':
  parts.append('\n'.join(source.splitlines()[node.lineno-1:node.end_lineno]))
reference='from datetime import datetime, timezone\nUTC=timezone.utc\n'+'\n\n'.join(parts)
ns={};exec(reference,ns);oracle=ns['parse_utc']
PROMPT=BASE+'''Write regression tests for this ACTUAL dashboard helper. Return complete Python source defining run_tests(candidate), with imports from datetime/math only. candidate is parse_utc supplied by evaluator, not the implementation below. Contract: None/blank/invalid input returns None; strip outer whitespace; accept ordinary ISO Z, explicit offsets, compact UTC HHMMZ, naive ISO interpreted as UTC; return aware UTC normalized absolute instants, preserve ISO fractional seconds. Successful completion means all assertions passed; otherwise raise AssertionError. Test behavioral edge cases; never inspect candidate source/name/attributes. Avoid printing.\nReference implementation:\n'''+reference
def invalid_raises(x):
 r=oracle(x)
 if r is None:raise ValueError('bad timestamp')
 return r
def no_offset_conversion(x):
 if isinstance(x,str) and x.endswith('-04:00'):return datetime.fromisoformat(x).replace(tzinfo=timezone.utc)
 return oracle(x)
MUTANTS={
 'none_raises':lambda x: (_ for _ in ()).throw(TypeError()) if x is None else oracle(x),
 'no_whitespace_strip':lambda x: None if isinstance(x,str) and x!=x.strip() else oracle(x),
 'compact_unsupported':lambda x: None if isinstance(x,str) and re.search(r'T\d{4}Z$',x) else oracle(x),
 'offset_relabelled':no_offset_conversion,
 'invalid_raises':invalid_raises,
 'fractional_seconds_lost':lambda x: None if oracle(x) is None else oracle(x).replace(microsecond=0),
}
if __name__=='__main__':
 mode=sys.argv[1]
 if mode=='selfcheck':
  cases=[None,'bad',' 2025-01-01T11:00:00Z ','2025-01-01T1100Z','2025-01-01T07:00:00-04:00','2025-01-01T11:00:00.123456Z']
  detected={k:any(oracle(x)!=f(x) for x in cases) for k,f in []}
  detected={}
  for k,f in MUTANTS.items():
   detected[k]=False
   for x in cases:
    try:different=oracle(x)!=f(x)
    except Exception:different=True
    detected[k]|=different
  assert all(detected.values())
  (ROOT/'real-helper-harness-validation.json').write_text(json.dumps(detected,indent=2));print(detected);sys.exit()
 model=sys.argv[2];out=ROOT/model.replace(':','-');out.mkdir(exist_ok=True)
 if mode=='generate':
  body=dict(model=model,messages=[dict(role='user',content=PROMPT)],stream=False,keep_alive='5m',think=False,options=dict(temperature=0,seed=42,num_ctx=16384,num_predict=3500))
  (out/'real-helper-request.json').write_text(json.dumps(body,indent=2));start=time.monotonic()
  req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=240) as r:result=json.load(r)
  result['wall_seconds']=time.monotonic()-start
  (out/'real-helper-result.json').write_text(json.dumps(result,indent=2));(out/'real-helper-response.txt').write_text(result.get('message',{}).get('content',''))
  print(dict(model=model,seconds=result['wall_seconds'],done_reason=result.get('done_reason')),flush=True)
 else:
  def deadline(*args):raise TimeoutError('15-second candidate deadline')
  signal.signal(signal.SIGALRM,deadline);signal.alarm(15)
  try:
   response=(out/'real-helper-response.txt').read_text();blocks=re.findall(r'```(?:python)?\s*\n(.*?)```',response,re.S);namespace={}
   exec(validated('\n'.join(blocks) if blocks else response,{'datetime','math'}),namespace)
   suite=namespace['run_tests'];suite(oracle);results=[dict(case='actual helper accepted',passed=True)]
   for name,f in MUTANTS.items():
    try:suite(f);good=False;error=None
    except Exception as e:good=True;error=f'{type(e).__name__}: {e}'
    results.append(dict(case=name,passed=good,error=error))
  except Exception as e:results=[dict(case='candidate completion/loading',passed=False,error=f'{type(e).__name__}: {e}')]
  finally:signal.alarm(0)
  (out/'real-helper-acceptance.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
