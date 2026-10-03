"""Trusted synthetic integrated cases; never sent to a model."""
import ast
import copy
import hashlib
import json
import math
import signal
import types
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parent
NOW='2025-11-02T06:30:00Z'

def q(**kw):
    return dict(dict(id='a',book='A',event='E',observed_at='2025-11-02T06:00:00Z',expires_at='2025-11-02T07:00:00Z',last_update='2025-11-02T05:59:00Z',odds=-200),**kw)

def run(**kw):
    return dict(dict(run_id='r1',job='J',attempt=1,observed_at='2025-11-02T06:00:00Z',status='ok',downloaded_rows=3),**kw)

def fixtures():
    xs=[]
    def add(name,qs=None,rs=None,eq=None,er=None,**kw):
        xs.append(dict(name=name,qs=qs or [],rs=rs or [],eq=eq or {},er=er or {},event=kw.get('event','E'),asof=kw.get('asof',NOW),raises=kw.get('raises',False)))
    add('empty')
    add('basic and independent jobs',[q()],[run()],{'A':0},{'J':0})
    add('abs offset latest',[q(id='z',observed_at='2025-11-02T01:45:00-04:00',last_update='2025-11-02T05:40:00Z'),q(id='b',observed_at='2025-11-02T01:15:00-05:00')],eq={'A':1})
    add('absolute tie smallest id',[q(id='z'),q(id='a',observed_at='2025-11-02T01:00:00-05:00')],eq={'A':1})
    add('same instant/id first identity',[q(odds=-200),q(odds=300)],eq={'A':0})
    add('future cannot suppress',[q(),q(id='z',observed_at='2025-11-02T06:31:00Z')],eq={'A':0})
    add('expiry exact cannot suppress',[q(observed_at='2025-11-02T05:00:00Z',last_update='2025-11-02T04:59:00Z'),q(id='z',expires_at=NOW)],eq={'A':0})
    add('update vintage cannot suppress',[q(),q(id='z',observed_at='2025-11-02T06:20:00Z',last_update='2025-11-02T06:25:00Z')],eq={'A':0})
    add('other event isolated',[q(event='X'),q(book='B')],eq={'B':1})
    add('asof aware datetime',[q()],eq={'A':0},asof=datetime.fromisoformat(NOW))
    add('asof offset',[q()],eq={'A':0},asof='2025-11-02T01:30:00-05:00')
    add('exact observation/update',[q(observed_at=NOW,last_update=NOW)],eq={'A':0})
    add('quotes independent failed job',[q()],[run(status='failed',downloaded_rows=0)],{'A':0},{'J':0})
    add('whitespace identifiers',[q(id=' ',book=' ',event=' ')],eq={' ':0},event=' ')
    for key in ('id','book','event'):
        for bad in ('',None,False,2,[],{}):
            add('quote field '+key+' '+repr(bad),[q(**{key:bad}),q(book='B')],eq={'B':1})
    for key in ('observed_at','expires_at','last_update'):
        for bad in ('bad','2025-11-02T06:00:00',None,False,[],{}):
            add('quote time '+key+' '+repr(bad),[q(**{key:bad}),q(book='B')],eq={'B':1})
    for bad in (True,False,None,99,-99,0,'bad','nan','inf',10**1000,[],{},complex(100)):
        add('invalid odds '+repr(bad),[q(odds=bad),q(book='B')],eq={'B':1})
    for good in (100,-100,110,-110,' +250 ','-250','1e3',100.5,-100.5):
        add('valid odds '+repr(good),[q(odds=good)],eq={'A':0})
    add('malformed both lists',[None,[],{},q()],[None,[],{},run()],{'A':3},{'J':3})
    for bad in (None,False,7,'bad','2025-11-02T06:30:00',datetime(2025,11,2,6,30)):
        add('invalid asof '+repr(bad),asof=bad,raises=True)
    for bad in ('',None,False,[],2):
        add('invalid event '+repr(bad),event=bad,raises=True)
    for status,n in (('ok',3),('ok',0),('partial',2),('partial',0),('failed',0),('pending',0)):
        add('run status '+status+str(n),rs=[run(status=status,downloaded_rows=n)],er={'J':0})
    add('retry latest failed',[q()],[run(),run(run_id='r2',attempt=2,status='failed',downloaded_rows=0)],{'A':0},{'J':1})
    add('retry latest partial',rs=[run(downloaded_rows=50),run(run_id='r2',attempt=2,status='partial',downloaded_rows=4)],er={'J':1})
    add('retry latest pending',rs=[run(),run(run_id='r2',attempt=2,status='pending',downloaded_rows=0)],er={'J':1})
    add('stale failed last cannot overwrite',rs=[run(observed_at='2025-11-02T06:20:00Z'),run(run_id='r2',status='failed',downloaded_rows=0)],er={'J':0})
    add('numeric attempt10 beats2',rs=[run(attempt=2),run(run_id='r2',attempt=10)],er={'J':1})
    add('job tie lexical run id',rs=[run(run_id='z'),run(run_id='a',status='partial')],er={'J':1})
    add('run abs offset latest',rs=[run(run_id='z',observed_at='2025-11-02T01:45:00-04:00'),run(run_id='a',observed_at='2025-11-02T01:15:00-05:00')],er={'J':1})
    add('duplicate corrected job global',rs=[run(job='old'),run(job='new',observed_at='2025-11-02T06:10:00Z')],er={'new':1})
    add('same run id time tie first',rs=[run(),run(status='failed',downloaded_rows=0)],er={'J':0})
    add('future dup cannot suppress',rs=[run(),run(job='new',observed_at='2025-11-02T06:31:00Z')],er={'J':0})
    add('invalid dup cannot suppress',rs=[run(),run(job='new',downloaded_rows=-1,observed_at='2025-11-02T06:10:00Z')],er={'J':0})
    add('latest observed dup not largest attempt',rs=[run(attempt=8),run(attempt=2,observed_at='2025-11-02T06:10:00Z')],er={'J':1})
    for key in ('run_id','job'):
        for bad in ('',None,False,2,[],{}):
            add('run id '+key+' '+repr(bad),rs=[run(**{key:bad}),run(run_id='r2',job='K')],er={'K':1})
    for key in ('attempt','downloaded_rows'):
        for bad in (True,False,-1,'2',2.0,None,[],{}):
            add('run number '+key+' '+repr(bad),rs=[run(**{key:bad}),run(run_id='r2',job='K')],er={'K':1})
    for key,bad in (('attempt',0),('status','unknown'),('status',[]),('status',True),('observed_at',None),('observed_at','bad'),('observed_at','2025-11-02T06:00:00')):
        add('run malformed '+key+repr(bad),rs=[run(**{key:bad}),run(run_id='r2',job='K')],er={'K':1})
    for status in ('failed','pending'):
        add('nonzero bad '+status,rs=[run(status=status),run(run_id='r2',job='K')],er={'K':1})
    add('sorted failed partial unknown controls',rs=[run(run_id='z',job='Z',status='failed',downloaded_rows=0),run(run_id='a',job='A',status='failed',downloaded_rows=0),run(run_id='p',job='P',status='pending',downloaded_rows=0),run(run_id='b',job='B',status='partial',downloaded_rows=7)],er={'Z':0,'A':1,'P':2,'B':3})
    add('all quote timestamp objects',[q(observed_at=datetime.fromisoformat('2025-11-02T06:00:00Z'),expires_at=datetime.fromisoformat('2025-11-02T07:00:00Z'),last_update=datetime.fromisoformat('2025-11-02T05:59:00Z'))],eq={'A':0})
    add('run timestamp object',rs=[run(observed_at=datetime.fromisoformat('2025-11-02T06:00:00Z'))],er={'J':0})
    add('extra nested fields preserved',[q(extra={'a':[1,2]})],[run(extra={'a':[3]})],{'A':0},{'J':0})
    add('first invalid quote tie skipped',[q(last_update='2025-11-02T06:01:00Z'),q()],eq={'A':1})
    # Explicit cross-module expected selections, no reference-generated answer keys.
    for kind in ('future','expiry','vintage','other'):
        for latest_status in ('ok','partial','failed','pending'):
            for offset in (0,-5):
                qs=[q(),q(book='B',odds=250),q(id='z',observed_at='2025-11-02T06:20:00Z')]
                qs[2].update({'observed_at':'2025-11-02T06:31:00Z'} if kind=='future' else {'expires_at':NOW} if kind=='expiry' else {'last_update':'2025-11-02T06:25:00Z'} if kind=='vintage' else {'event':'X'})
                rs=[run(downloaded_rows=99),run(run_id='r2',attempt=2,status=latest_status,downloaded_rows=4 if latest_status in ('ok','partial') else 0),run(run_id='k',job='K',status='partial',downloaded_rows=2)]
                rs += [rs[1],rs[2],run(run_id='r2',job='future',attempt=3,observed_at='2025-11-02T06:31:00Z')]
                at=datetime.fromisoformat(NOW).astimezone(timezone(timedelta(hours=offset)))
                add('interaction '+kind+latest_status+str(offset),qs,rs,{'A':0,'B':1},{'J':1,'K':2},asof=at)
    # Reordered distinct ranks and duplicate replay, respecting explicit first-tie exception.
    qs=[q(id='old'),q(id='new',observed_at='2025-11-02T06:20:00Z'),q(book='B')]
    rs=[run(),run(run_id='r2',attempt=2,status='partial'),run(run_id='k',job='K')]
    for reverse in (False,True):
        a=list(reversed(qs)) if reverse else qs[:];b=list(reversed(rs)) if reverse else rs[:]
        eq={'A':a.index(qs[1]),'B':a.index(qs[2])};er={'J':b.index(rs[1]),'K':b.index(rs[2])}
        for copies in (1,2,5):add('permutation/replay '+str(reverse)+str(copies),a*copies,b*copies,eq,er)
    return xs


def checks(candidate):
    results=[]
    for spec in fixtures():
        qs=copy.deepcopy(spec['qs']);rs=copy.deepcopy(spec['rs']);before=repr((qs,rs))
        try:
            out=candidate(qs,rs,spec['event'],spec['asof'])
            if spec['raises']:
                raise AssertionError('invalid argument accepted')
            assert isinstance(out,dict) and set(out)=={'quotes','runs','successful_rows','failures','partial_jobs','unknown_jobs'}
            assert set(out['quotes'])==set(spec['eq']) and set(out['runs'])==set(spec['er'])
            for book,index in spec['eq'].items():
                chosen=out['quotes'][book];assert set(chosen)=={'row','probability'} and chosen['row'] is qs[index]
                v=float(qs[index]['odds']);p=100/(v+100) if v>0 else -v/(-v+100)
                assert isinstance(chosen['probability'],float) and math.isclose(chosen['probability'],p,rel_tol=1e-12)
            expected={job:rs[i] for job,i in spec['er'].items()}
            assert all(out['runs'][job] is row for job,row in expected.items())
            assert type(out['successful_rows']) is int and out['successful_rows']==sum(row['downloaded_rows'] for row in expected.values() if row['status'] in ('ok','partial'))
            for field,status in (('failures','failed'),('partial_jobs','partial'),('unknown_jobs','pending')):
                assert out[field]==sorted(job for job,row in expected.items() if row['status']==status)
            assert repr((qs,rs))==before
            results.append(dict(case=spec['name'],passed=True))
        except Exception as exc:
            good=spec['raises'] and isinstance(exc,ValueError) and repr((qs,rs))==before
            results.append(dict(case=spec['name'],passed=good,error=None if good else type(exc).__name__+': '+str(exc)))
    return results


def validate(source,allowed):
    tree=ast.parse(source)
    forbidden={'open','eval','exec','compile','__import__','breakpoint','getattr','setattr','delattr','globals','locals','vars','input','dir','help','exit','quit'}
    for node in ast.walk(tree):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            names=[a.name.split('.')[0] for a in node.names] if isinstance(node,ast.Import) else [(node.module or '').split('.')[0]]
            if any(n not in allowed for n in names) or isinstance(node,ast.ImportFrom) and node.level:
                raise ValueError('disallowed import')
        if isinstance(node,ast.Name) and (node.id in forbidden or node.id.startswith('__')):
            raise ValueError('disallowed name')
        if isinstance(node,ast.Attribute) and (node.attr.startswith('__') or node.attr in ('mro','subclasses','now','utcnow','today','fromtimestamp')):
            raise ValueError('disallowed operation')
    return compile(tree,'candidate','exec')


def load(sources,restricted=True,return_modules=False):
    modules={name:types.ModuleType(name) for name in ('times','quotes','runs','pipeline')}
    real_import=__import__
    def local_import(name,globals=None,locals=None,fromlist=(),level=0):
        if name in modules:return modules[name]
        if name not in {'datetime','math','copy','json','typing'} or level:raise ValueError('disallowed runtime import')
        return real_import(name,globals,locals,fromlist,level)
    for name,module in modules.items():
        source=sources[name+'.py'];builtins=dict(vars(__import__('builtins')));builtins['__import__']=local_import;module.__dict__['__builtins__']=builtins
        code=validate(source,set(modules)|{'datetime','math','copy','json','typing'}) if restricted else compile(source,name,'exec')
        exec(code,module.__dict__)
    return modules if return_modules else modules['pipeline'].snapshot


def source_bundle():return {p.name:p.read_text() for p in (ROOT/'reference').glob('*.py')}

# Single independent substitutions. Each must be killed by trusted checks before inference.
MUTATIONS={
 'inclusive_expiry':('quotes.py','at<expiry','at<=expiry'),
 'ignore_update_vintage':('quotes.py','and update<=observed',''),
 'future_quotes':('quotes.py','observed<=at<expiry','at<expiry'),
 'oldest_quote':('quotes.py','observed>old[0]','observed<old[0]'),
 'largest_quote_id':('quotes.py',"row['id']<old[1]","row['id']>old[1]"),
 'last_quote_tie':('quotes.py',"row['id']<old[1]","row['id']<=old[1]"),
 'copied_quote':('quotes.py',"{'row':row,'probability':p}","{'row':dict(row),'probability':p}"),
 'negative_probability':('quotes.py','(-v)/((-v)+100)','100/((-v)+100)'),
 'future_runs':('runs.py','if observed>at:','if False:'),
 'run_duplicate_last_wins':('runs.py','observed>stamps[identity]','observed>=stamps[identity]'),
 'oldest_run_retry':('runs.py','rank[0]>old[0]','rank[0]<old[0]'),
 'stale_job_overwrite':('runs.py',"if old is None or rank[0]>old[0] or (rank[0]==old[0] and (rank[1]>old[1] or (rank[1]==old[1] and rank[2]<old[2]))):","if True:"),
 'duplicate_job_scope':('runs.py',"identity=row['run_id']","identity=row['job']+row['run_id']"),
 'partial_rows_dropped':('pipeline.py',"row['status'] in ('ok','partial')","row['status']=='ok'"),
 'pending_reported_failed':('pipeline.py',"row['status']=='failed'","row['status'] in ('failed','pending')"),
 'copied_run':('runs.py','picked[key]=row;','picked[key]=dict(row);'),
}

def mutants():
    base=source_bundle();out={}
    for name,(file,old,new) in MUTATIONS.items():
        assert base[file].count(old)==1,(name,'nonunique mutation')
        bundle=base|{file:base[file].replace(old,new)};out[name]=load(bundle)
    return out


def selfcheck():
    reference=load(source_bundle());cs=checks(reference);failed=[c for c in cs if not c['passed']];assert not failed,failed
    kills={name:[c['case'] for c in checks(f) if not c['passed']] for name,f in mutants().items()};assert all(kills.values()),kills
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'CONTRACT.md',ROOT/'harness.py',*sorted((ROOT/'reference').glob('*.py'))]}
    result=dict(cases=len(cs),oracle_passed=len(cs),mutants=len(kills),mutant_failures=kills,sha256=hashes,review='author harness validation; not independent signoff')
    (ROOT/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('cases','oracle_passed','mutants')}))

if __name__=='__main__':
    signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('15s candidate limit')));signal.alarm(15);selfcheck()
