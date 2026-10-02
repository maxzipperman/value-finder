"""LOCAL-BECAUSE: hardware: bounded local inference, synthetic coding tests only."""
import ast
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
words = (REPO / 'dashboard/vfdash/words.py').read_text()

def extract(name):
    tree = ast.parse(words)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return '\n'.join(words.splitlines()[node.lineno-1:node.end_lineno])

prefix = 'Value Finder is paper-only research. This is an isolated synthetic coding test. Use Python standard library only; do not read files, use network, execute commands, or access real data. Return only complete executable Python source, without markdown. Include needed imports. '
TASKS = [
    ('schedule', prefix + 'Repair the following dashboard helper. Contract: return the first daily scheduled run STRICTLY AFTER aware now, in the provided timezone; accept unsorted times, empty list returns None. Preserve signature.\n' + extract('next_run').replace('if t > now:', 'if t >= now:')),
    ('scrub', prefix + 'Repair the following deliberately damaged dashboard secret scrubber. Preserve line breaks and non-secret text. Redact ENV_NAMES assignments, api-key/token/password/authorization-style fields, and standalone Bearer tokens. Preserve already-redacted values. Preserve signature scrub(text).\n' + words[words.index('_VALUE ='):words.index('\ndef missing_columns')].replace('return BEARER.sub(lambda m: blank(m, mid=False), text)', 'return text')),
    ('quotes', prefix + '''Implement select_quote(rows, decision, kickoff). rows is a list of dicts with id, snapshot_utc, last_update_utc (ISO timestamp strings), and price (American odds). decision and kickoff are aware datetime objects. Return the original dict for the eligible row with the latest snapshot, or None. A row is eligible only when BOTH clocks are timezone-aware, both are at or before decision, both are strictly before kickoff, and last_update_utc is at or before snapshot_utc. Reject missing/malformed clocks, naive clocks, missing/non-numeric/non-finite prices, booleans as prices, and American odds whose absolute value is below 100. Numeric strings are accepted. For equal snapshots choose the lexicographically smallest id. Never mutate input. No external dependencies.'''),
]

CASES = []
def case(name, task, fn): CASES.append((name, task, fn))
def dt(s): return datetime.fromisoformat(s.replace('Z', '+00:00'))
UTC = timezone.utc
TZ = ZoneInfo('America/Los_Angeles')
case('exact scheduled time moves to next', 'schedule', lambda ns: ns['next_run']([(16,30),(7,30),(10,30)], dt('2026-10-02T10:30:00-07:00'), TZ) == dt('2026-10-02T16:30:00-07:00'))
case('last slot moves to tomorrow', 'schedule', lambda ns: ns['next_run']([(23,30)], dt('2026-10-02T23:30:00-07:00'), TZ) == dt('2026-10-03T23:30:00-07:00'))
case('empty schedule', 'schedule', lambda ns: ns['next_run']([], dt('2026-10-02T12:00:00Z'), TZ) is None)
case('UTC input local output', 'schedule', lambda ns: ns['next_run']([(7,30)], dt('2026-10-02T14:00:00Z'), TZ) == dt('2026-10-02T14:30:00Z'))
case('DST following day offset', 'schedule', lambda ns: ns['next_run']([(7,30)], dt('2026-10-31T08:00:00-07:00'), TZ) == dt('2026-11-01T07:30:00-08:00'))
for name, before, after in [
 ('standalone bearer','Failed Bearer syntheticABC!','Failed Bearer ***'),
 ('API key URL','https://example.invalid?apiKey=syntheticABC&sport=nfl','https://example.invalid?apiKey=***&sport=nfl'),
 ('environment topic','NTFY_TOPIC => syntheticABC','NTFY_TOPIC => ***'),
 ('preserve multiline','token=syntheticABC\nnext line','token=***\nnext line'),
 ('leave ordinary words','monkey=banana keyword=hello KeyError','monkey=banana keyword=hello KeyError'),
 ('idempotent','apiKey=***','apiKey=***'),
 ('authorization','Authorization: Bearer syntheticABC','Authorization: Bearer ***'),
]: case(name, 'scrub', lambda ns,b=before,a=after: ns['scrub'](b)==a)
D=dt('2025-10-01T12:00:00Z'); K=dt('2025-10-01T13:00:00Z')
def row(id='a', snapshot='2025-10-01T11:00:00Z', update='2025-10-01T10:59:00Z', price=-110):
 return dict(id=id,snapshot_utc=snapshot,last_update_utc=update,price=price)

def check_quote(ns, rows, expected, decision=D, kickoff=K):
 before=json.dumps(rows,sort_keys=True,allow_nan=True)
 result=ns['select_quote'](rows,decision,kickoff)
 return (None if result is None else result['id'])==expected and json.dumps(rows,sort_keys=True,allow_nan=True)==before and (result is None or any(result is x for x in rows))
case('empty quote list','quotes',lambda ns: check_quote(ns,[],None))
case('latest eligible snapshot','quotes',lambda ns: check_quote(ns,[row('b'),row('a','2025-10-01T11:30:00Z')],'a'))
case('snapshot at decision permitted','quotes',lambda ns: check_quote(ns,[row('a','2025-10-01T12:00:00Z')],'a'))
case('future snapshot excluded','quotes',lambda ns: check_quote(ns,[row('a','2025-10-01T12:00:01Z')],None))
case('future update excluded','quotes',lambda ns: check_quote(ns,[row('a',update='2025-10-01T12:01:00Z')],None))
case('update after snapshot excluded','quotes',lambda ns: check_quote(ns,[row('a',update='2025-10-01T11:01:00Z')],None))
case('at kickoff excluded','quotes',lambda ns: check_quote(ns,[row('a','2025-10-01T13:00:00Z')],None,dt('2025-10-01T14:00:00Z')))
case('tie broken by id','quotes',lambda ns: check_quote(ns,[row('z'),row('a')],'a'))
case('offset normalized','quotes',lambda ns: check_quote(ns,[row('a','2025-10-01T07:00:00-04:00','2025-10-01T06:59:00-04:00')],'a'))
for field in ('snapshot_utc','last_update_utc'):
 for label,value in [('missing',None),('bad','garbage'),('naive','2025-10-01T10:00:00')]:
  case(field+' '+label,'quotes',lambda ns,f=field,v=value: check_quote(ns,[dict(row(),**{f:v})],None))
for label,value in [('low',-99),('nan',float('nan')),('inf',float('inf')),('bool',True),('bad','oops'),('missing',None)]:
 case('price '+label,'quotes',lambda ns,v=value: check_quote(ns,[row(price=v)],None))
case('numeric string price','quotes',lambda ns: check_quote(ns,[row(price='-110')],'a'))

if sys.argv[1]=='generate':
 model=sys.argv[2]
 out=ROOT/(model.replace(':','-') + os.environ.get('EVAL_LABEL','') + ('-repair' if len(sys.argv)>3 else ''));out.mkdir(exist_ok=True)
 for task,prompt in TASKS:
  (out/(task+'-prompt.txt')).write_text(prompt)
  messages=[dict(role='user',content=prompt)]
  if len(sys.argv)>3:
   prior=ROOT/(model.replace(':','-') + os.environ.get('EVAL_LABEL',''))
   failures=[r for r in json.loads((prior/'acceptance.json').read_text()) if r['task']==task and not r['passed']]
   if not failures: continue
   messages += [dict(role='assistant',content=(prior/(task+'-response.txt')).read_text()),dict(role='user',content='Your code failed these acceptance checks. Fix the implementation and return complete Python source only. '+json.dumps(failures))]
  body=dict(model=model,messages=messages,stream=False,keep_alive='5m',options=dict(temperature=0,num_ctx=8192,num_predict=2400,seed=42))
  if os.environ.get('EVAL_THINK') in ('false','true'): body['think']=os.environ['EVAL_THINK']=='true'
  if os.environ.get('EVAL_TOKEN_BUDGET'): body['options']['num_predict']=int(os.environ['EVAL_TOKEN_BUDGET'])
  if os.environ.get('EVAL_SAMPLING')=='default': body['options'].pop('temperature',None)
  (out/(task+'-request-settings.json')).write_text(json.dumps({k:v for k,v in body.items() if k!='messages'},indent=2))
  started=time.monotonic()
  try:
   req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=360) as r: result=json.load(r)
   result['wall_seconds']=time.monotonic()-started
   response=result.get('message',{}).get('content','')
   (out/(task+'-thinking.txt')).write_text(result.get('message',{}).get('thinking',''))
   (out/(task+'-response.txt')).write_text(response)
   blocks=re.findall(r'```(?:python)?\s*\n(.*?)```',response,re.S)
   code='\n'.join(blocks) if blocks else response
   (out/(task+'.py')).write_text(code)
   (out/(task+'-metrics.json')).write_text(json.dumps({k:v for k,v in result.items() if k!='message'},indent=2))
   print(json.dumps(dict(task=task,model=model,wall_seconds=result['wall_seconds'],tokens=result.get('eval_count'),tokens_per_second=result.get('eval_count',0)/(result.get('eval_duration',1)/1e9))),flush=True)
  except Exception as e:
   (out/(task+'-error.txt')).write_text(str(e));print(task,type(e).__name__,str(e),flush=True)
else:
 model=sys.argv[2];out=ROOT/(model.replace(':','-') + os.environ.get('EVAL_LABEL','') + ('-repair' if len(sys.argv)>3 else ''));results=[]
 for task,_ in TASKS:
  try:
   source_path=out/(task+'.py')
   if not source_path.exists() and len(sys.argv)>3: source_path=ROOT/(model.replace(':','-') + os.environ.get('EVAL_LABEL',''))/(task+'.py')
   source=source_path.read_text();tree=ast.parse(source)
   for node in ast.walk(tree):
    if isinstance(node,(ast.Import,ast.ImportFrom)):
     names=[a.name.split('.')[0] for a in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
     if any(n not in ('datetime','zoneinfo','re','math','typing') for n in names): raise ValueError('Disallowed import')
    if isinstance(node,ast.Name) and node.id in ('open','eval','exec','compile','__import__','breakpoint'): raise ValueError('Disallowed operation')
    if isinstance(node,ast.Attribute) and node.attr.startswith('__'): raise ValueError('Disallowed attribute')
   ns={};exec(compile(tree,str(out/(task+'.py')),'exec'),ns)
   for name,t,fn in CASES:
    if t!=task:continue
    try: passed=bool(fn(ns));error=None
    except Exception as e: passed=False;error=str(e)
    results.append(dict(task=t,case=name,passed=passed,error=error))
  except Exception as e:
   results.extend(dict(task=t,case=name,passed=False,error=str(e)) for name,t,fn in CASES if t==task)
 (out/'acceptance.json').write_text(json.dumps(results,indent=2))
 print(json.dumps(dict(model=model,passed=sum(r['passed'] for r in results),total=len(results),failures=[r for r in results if not r['passed']]),indent=2))
