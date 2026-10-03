"""Run only after complete manual source inspection, ordinary restricted sandbox."""
import ast
import json
import math
import signal
import sys
from datetime import datetime,timezone
from pathlib import Path
from harness import validate,load,source_bundle,checks,mutants,ROOT


def support_checks(modules):
    out=[]
    def put(case,fn):
        try:assert fn();out.append(dict(case=case,passed=True))
        except Exception as exc:out.append(dict(case=case,passed=False,error=type(exc).__name__+': '+str(exc)))
    for value in (-100,100,-200,250,' -250 ',100.5):
        v=float(value);expected=100/(v+100) if v>0 else -v/(-v+100)
        put('public probability '+str(value),lambda value=value,expected=expected:math.isclose(modules['quotes'].probability(value),expected,rel_tol=1e-12))
    for value in (True,None,99,'nan',float('inf'),10**1000,[]):
        def rejects(value=value):
            try:modules['quotes'].probability(value)
            except ValueError:return True
            return False
        put('public probability invalid '+str(type(value)),rejects)
    put('public instant normalized',lambda: modules['times'].instant('2025-11-02T01:00:00-05:00')==datetime(2025,11,2,6,tzinfo=timezone.utc) and modules['times'].instant('2025-11-02T01:00:00-05:00').tzinfo is timezone.utc)
    return out


def grade(task,text):
    obj=json.loads(text)
    if task=='implementation':
        if not isinstance(obj,dict) or set(obj)!={'times.py','quotes.py','runs.py','pipeline.py'} or not all(isinstance(v,str) for v in obj.values()):raise ValueError('four source files required')
        # Preserve module/interface differences in packaging checks; semantic checks separate.
        modules=load(obj,return_modules=True)
        result=checks(modules['pipeline'].snapshot)+support_checks(modules)
        tree=ast.parse(obj['pipeline.py']);imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}|{a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
        result.append(dict(case='entry point imports all supporting modules (manual invocation review also required)',passed={'times','quotes','runs'}<=imports))
        return result
    if task=='regression':
        if not isinstance(obj,dict) or set(obj)!={'tests.py'} or not isinstance(obj['tests.py'],str):raise ValueError('tests.py JSON source required')
        code=validate(obj['tests.py'],{'datetime','math','copy','json'});ns={};exec(code,ns);f=ns['run_tests']
        try:f(load(source_bundle()))
        except Exception as exc:return [dict(case='correct oracle accepted',passed=False,error=type(exc).__name__+': '+str(exc),note='No mutation credit')]
        out=[dict(case='correct oracle accepted',passed=True)]
        for name,mutant in mutants().items():
            try:f(mutant);out.append(dict(case=name,passed=False,catch='none'))
            except AssertionError as exc:out.append(dict(case=name,passed=True,catch='assertion',error=str(exc)))
            except Exception as exc:out.append(dict(case=name,passed=True,catch='exception',error=type(exc).__name__+': '+str(exc)))
        return out
    if task=='review':
        if not isinstance(obj,list) or any(not isinstance(f,dict) or set(f)!={'file','line','explanation'} or f['file'] not in ('times.py','quotes.py','runs.py','pipeline.py') or type(f['line']) is not int or not isinstance(f['explanation'],str) for f in obj):raise ValueError('invalid review schema')
        return [dict(case='schema only; each cause/false/duplicate finding requires manual semantic review',passed=True,findings=obj)]
    raise ValueError('unknown task')

if __name__=='__main__':
    signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('15s candidate limit')))
    task,path=sys.argv[1:];signal.alarm(15)
    try:result=grade(task,Path(path).read_text())
    except Exception as exc:result=[dict(case='candidate completion/loading',passed=False,error=type(exc).__name__+': '+str(exc))]
    finally:signal.alarm(0)
    Path(path).with_name(task+'-acceptance.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'passed':sum(c['passed'] for c in result),'cases':len(result)}))
