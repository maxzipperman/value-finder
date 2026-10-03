"""LOCAL-BECAUSE: hardware. Fresh matched Q4/Q8 synthetic edge-case tasks."""
import copy
import json
import math
import random
import re
import signal
import sys
from datetime import datetime, timezone, timedelta, tzinfo
from pathlib import Path
from expanded import BASE, ROOT, oracle as odds_oracle, validated, parse_json

CONTRACT = '''Write complete Python source defining select_books(rows, asof). rows is a list of potentially malformed records. Return dict book -> ORIGINAL selected row (identity matters), choosing separately for each book the latest ELIGIBLE observed_at, tie lexicographically smallest id, then first input row if both observed time and id tie. Fields: nonempty string book and id; odds finite int/float/numeric string with abs>=100, bool and other types invalid; observed_at/expires_at timezone-aware ISO strings, Z and offsets allowed. Skip malformed rows. Eligibility is observed_at <= asof < expires_at and observed_at < expires_at. Compare all clocks as UTC absolute instants; asof must be a datetime with non-None utcoffset or raise ValueError, even for empty rows. Future, expired or malformed later records MUST NOT suppress older eligible records for that book. Never mutate rows or row contents. Numeric conversions outside float range are malformed, not a reason to crash. Standard library math/datetime only, no I/O or tools. Return only source, no explanations.'''
REVIEW = '''1 from datetime import datetime
2 def choose_books(rows, asof):
3     latest = {}
4     for row in rows:
5         book = row['book']
6         if book not in latest or row['observed_at'] > latest[book]['observed_at']:
7             latest[book] = row
8     out = {}
9     for book, row in latest.items():
10         observed = datetime.fromisoformat(row['observed_at'])
11         expires = datetime.fromisoformat(row['expires_at'])
12         if observed <= asof <= expires:
13             probability = 100 / (abs(float(row['odds'])) + 100)
14             out[book] = {'row': row, 'probability': probability}
15     return out'''
TASKS = {
 'hard-selection': BASE + CONTRACT,
 'hard-review': BASE + '''Review this Python 3.14 code. Inputs are valid rows: book/id nonempty strings, finite int/float/numeric-string odds with abs>=100, valid aware ISO clocks with arbitrary offsets or Z and observed_at<expires_at; asof is an aware UTC datetime. Desired: for each book choose the latest ELIGIBLE observed_at (observed_at<=asof<expires_at); latest future/expired rows do not suppress eligible alternatives. Compare absolute instants, ties smallest id, identical instant/id ties first input row. Return dict book -> {'row': ORIGINAL selected row, 'probability': correct American-odds implied probability}, no input mutation. Find distinct defects, including interactions. Do not flag unsupported or out-of-contract inputs or speculate about concurrent mutation. Return only JSON list {line: integer, explanation: string}, one per independent cause. No patches.\n''' + REVIEW,
}

UTC=timezone.utc
NOW=datetime(2025,11,2,6,30,tzinfo=UTC)
def row(**kwargs):
 x=dict(book='A',id='a',odds=-110,observed_at='2025-11-02T06:00:00Z',expires_at='2025-11-02T07:00:00Z');x.update(kwargs);return x

def reference(rows, asof):
 if not isinstance(asof,datetime) or asof.utcoffset() is None:raise ValueError('asof')
 now=asof.astimezone(UTC);out={};keys={}
 for r in rows:
  try:
   if not isinstance(r,dict) or any(not isinstance(r.get(k),str) or not r[k] for k in ('book','id')):continue
   odds_oracle(r['odds'])
   a=datetime.fromisoformat(r['observed_at']).astimezone(UTC) if datetime.fromisoformat(r['observed_at']).utcoffset() is not None else None
   b=datetime.fromisoformat(r['expires_at']).astimezone(UTC) if datetime.fromisoformat(r['expires_at']).utcoffset() is not None else None
   if a is None or b is None or not(a<=now<b and a<b):continue
   key=(-a.timestamp(),r['id'])
   if r['book'] not in out or key<keys[r['book']]:out[r['book']]=r;keys[r['book']]=key
  except (ValueError,TypeError,KeyError,AttributeError,OverflowError):continue
 return out

class NoOffset(tzinfo):
 def utcoffset(self,dt):return None

def cases():
 xs=[('empty',[],NOW),('negative', [row()],NOW),('future does not suppress',[row(),row(id='z',observed_at='2025-11-02T06:31:00Z')],NOW),('expired later does not suppress',[row(observed_at='2025-11-02T05:00:00Z'),row(id='z',expires_at='2025-11-02T06:30:00Z')],NOW),('independent books',[row(),row(book='B',odds='+250'),row(book='B',id='new',observed_at='2025-11-02T06:20:00Z')],NOW),('absolute offset order',[row(id='z',observed_at='2025-11-02T01:45:00-04:00'),row(id='a',observed_at='2025-11-02T01:15:00-05:00')],NOW),('offset instant tie id',[row(id='z'),row(id='a',observed_at='2025-11-02T01:00:00-05:00')],NOW),('same id first identity',[row(),row(odds=250)],NOW),('exact observation',[row(observed_at=NOW.isoformat())],NOW),('exact expiry',[row(expires_at=NOW.isoformat())],NOW),('nonutc asof',[row()],NOW.astimezone(timezone(timedelta(hours=-5))))]
 for k,v in [('odds',True),('odds',float('nan')),('odds',float('inf')),('odds',10**1000),('odds','oops'),('odds',99),('book',''),('book',None),('id',''),('id',3),('observed_at',None),('observed_at','2025-11-02T06:00:00'),('expires_at','bad'),('expires_at',3),('expires_at','2025-11-02T05:00:00Z')]:
  xs.append((k+' malformed plus eligible',[row(**{k:v}),row(id='b')],NOW))
 for bad in [None,'2025-11-02T06:30:00Z',datetime(2025,11,2,6,30),datetime(2025,11,2,6,30,tzinfo=NoOffset())]:xs.append(('invalid asof '+repr(bad),[],bad))
 rng=random.Random(971)
 for i in range(48):
  rs=[]
  for j in range(24):
   offset=timezone(timedelta(hours=rng.choice([-5,-4,0,2,9])))
   obs=NOW+timedelta(minutes=rng.choice([-90,-30,-1,0,1,30]))
   exp=obs+timedelta(minutes=rng.choice([0,15,60,180]))
   rs.append(row(book=rng.choice(['A','B','C']),id=rng.choice(['a','b','z']),odds=rng.choice([-250,-110,' 250 ',True,99]),observed_at=obs.astimezone(offset).isoformat(),expires_at=exp.astimezone(offset).isoformat()))
  rs.extend([None,{},[]]);rng.shuffle(rs);xs.append((f'mixed {i}',rs,NOW))
 return xs

def checks(f):
 out=[]
 for name,rows,asof in cases():
  before=repr(rows)
  try:expected=reference(rows,asof);invalid=False
  except ValueError:expected=None;invalid=True
  try:
   got=f(rows,asof)
   good=not invalid and isinstance(got,dict) and set(got)==set(expected) and all(got[k] is expected[k] for k in expected) and before==repr(rows);error=None
  except ValueError:good=invalid;error=None if invalid else 'unexpected ValueError'
  except Exception as e:good=False;error=f'{type(e).__name__}: {e}'
  out.append(dict(case=name,passed=good,error=error))
 return out

def wrong_order(rows, asof, lexical=False, prefilter=False, ignore_tie=False):
 # Deliberate harness mutants, never shown to candidates.
 reference([],asof)
 selected={};keys={}
 for r in rows:
  try:
   if not isinstance(r,dict):continue
   if not prefilter and not reference([r],asof):continue
   book=r['book'];stamp=r['observed_at'] if lexical else datetime.fromisoformat(r['observed_at']).astimezone(UTC)
   if book not in selected or stamp>keys[book][0] or (not ignore_tie and stamp==keys[book][0] and r['id']<keys[book][1]):selected[book]=r;keys[book]=(stamp,r['id'])
  except (ValueError,TypeError,KeyError,AttributeError):continue
 return reference(list(selected.values()),asof) if prefilter else selected

def changes_input(rows, asof):
 out=reference(rows,asof)
 for r in out.values():r['_model_added']=True
 return out

def grade(task,text):
 if task=='hard-selection':
  blocks=re.findall(r'```(?:python)?\s*\n(.*?)```',text,re.S);ns={};exec(validated('\n'.join(blocks) if blocks else text,{'math','datetime'}),ns);return checks(ns['select_books'])
 findings=parse_json(text)
 if not isinstance(findings,list) or any(not isinstance(x,dict) or set(x)!={'line','explanation'} or type(x['line']) is not int or not isinstance(x['explanation'],str) for x in findings):raise ValueError('schema')
 return [dict(case='line localization only; manual explanation review required',passed=True,findings=findings)]

if __name__=='__main__':
 signal.signal(signal.SIGALRM,lambda *a:(_ for _ in ()).throw(TimeoutError('15 second deadline')))
 if sys.argv[1]=='selfcheck':
  cs=checks(reference);assert all(c['passed'] for c in cs)
  import inspect
  source=inspect.getsource(reference).replace('a<=now<b','a<=now<=b')
  namespace=dict(globals());exec(source,namespace);inclusive=namespace['reference']
  mutants={'last_input_wins':lambda rs,t:{r['book']:r for r in rs if isinstance(r,dict) and 'book' in r},'drops_all':lambda rs,t:{},'copies_rows':lambda rs,t:{k:dict(v) for k,v in reference(rs,t).items()},'lexical_offsets':lambda rs,t:wrong_order(rs,t,lexical=True),'filter_after_latest':lambda rs,t:wrong_order(rs,t,prefilter=True),'ignore_id_tie':lambda rs,t:wrong_order(rs,t,ignore_tie=True),'inclusive_expiry':inclusive,'input_mutation':changes_input}
  killed={k:any(not c['passed'] for c in checks(f)) for k,f in mutants.items()};assert all(killed.values());x=dict(cases=len(cs),oracle_passed=True,smoke_mutants=killed);(ROOT/'hard-pair-harness-validation.json').write_text(json.dumps(x,indent=2));print(x)
 else:
  folder=ROOT/sys.argv[2];out={}
  for task in TASKS:
   try:signal.alarm(15);out[task]=grade(task,(folder/(task+'-response.txt')).read_text())
   except Exception as e:out[task]=[dict(case='candidate completion/loading',passed=False,error=f'{type(e).__name__}: {e}')]
   finally:signal.alarm(0)
  (folder/'hard-acceptance.json').write_text(json.dumps(out,indent=2));print(json.dumps({t:(sum(c['passed'] for c in cs),len(cs)) for t,cs in out.items()}))
