"""Prospective exact-source MiMo diagnostic, ordinary restricted sandbox only."""
import ast,copy,hashlib,json,signal,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'ceiling'))
import harness,grade
from ceiling_verify import verify
from ceiling_type_name_diagnostic import helper_checks
ORIGINAL_VALIDATE=harness.validate

def compatible_validate(source,allowed):
    tree=ast.parse(source);checked=copy.deepcopy(tree);exports=0
    for i,node in enumerate(checked.body):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='__all__':
            if not isinstance(node.value,ast.List) or not node.value.elts or not all(isinstance(x,ast.Constant) and isinstance(x.value,str) and x.value and not x.value.startswith('_') for x in node.value.elts):
                raise ValueError('only static literal export list permitted')
            exports+=1
            if exports>1:raise ValueError('multiple export declarations')
            checked.body[i]=ast.Pass()
    for node in ast.walk(checked):
        if isinstance(node,ast.Name) and node.id=='type' and isinstance(node.ctx,ast.Store):raise ValueError('shadowed type binding')
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name=='type':raise ValueError('shadowed type binding')
        if isinstance(node,ast.arg) and node.arg=='type':raise ValueError('shadowed type argument')
        if isinstance(node,ast.alias) and (node.asname=='type' or node.name=='type'):raise ValueError('shadowed type import')
        if isinstance(node,ast.ExceptHandler) and node.name=='type':raise ValueError('shadowed type exception')
        if isinstance(node,ast.Attribute) and node.attr=='__name__':
            v=node.value
            if not (isinstance(v,ast.Call) and isinstance(v.func,ast.Name) and v.func.id=='type' and len(v.args)==1 and isinstance(v.args[0],ast.Name) and not v.keywords):raise ValueError('only exact type(NAME).__name__ permitted')
            node.attr='diagnostic_type_name'
    ORIGINAL_VALIDATE(ast.unparse(checked),allowed)
    return compile(tree,'exact_inspected_mimo_candidate','exec')

def main():
    if sys.argv[1:]:raise ValueError('No arbitrary candidates')
    verify()
    manifest=json.loads((ROOT/'ceiling-mimo-diagnostic-freeze.json').read_text())
    for name,digest in manifest['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Supplemental freeze changed')
    path=ROOT/'openrouter-ceiling/xiaomi--mimo-v2.6-flash/implementation-response.txt'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=RESPONSE_SHA:raise ValueError('Exact inspected source required')
    safety=[]
    negatives=('x=value.__name__','x=globals()','x=open("x")','import os','type=str\nx=type(value).__name__','__all__=list(value)','__all__=["instant"]\nx=__all__')
    for source in negatives:
        try:compatible_validate(source,{'math'})
        except ValueError:safety.append(dict(source=source,rejected=True))
        else:raise AssertionError('Unsafe filter case accepted')
    compatible_validate('__all__=["instant"]\ndef instant(value): return type(value).__name__',set())
    harness.validate=compatible_validate
    try:
        reference=harness.source_bundle();ref=grade.grade('implementation',json.dumps(reference));ref_helpers=helper_checks(harness.load(reference,return_modules=True))
        if len(ref)!=197 or len(ref_helpers)!=4 or not all(x['passed'] for x in ref+ref_helpers):raise ValueError('Reference acceptance failed')
        checks=grade.grade('implementation',path.read_text());helpers=helper_checks(harness.load(json.loads(path.read_text()),return_modules=True))
    finally:harness.validate=ORIGINAL_VALIDATE
    out=dict(grading='supplemental author exact-source compatibility diagnostic, post-observation, not independent/blinded initial grading',original_acceptance_preserved=True,source_sha256=RESPONSE_SHA,safety=safety,reference_checks=dict(passed=197,cases=197),reference_helper_checks=ref_helpers,original_197_checks=dict(passed=sum(x['passed'] for x in checks),cases=len(checks),checks=checks),extra_helper_checks=helpers,limitations='Only static module export-list and exact unshadowed type(NAME).__name__ permitted; all other AST/runtime bans retained, default restricted15s/no network/credentials. Four extra probes separate, not exhaustive/full-contract proof or causal ranking; no source changes/model feedback/inference.')
    path.with_name('implementation-type-name-diagnostic.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(original197_passed=sum(x['passed'] for x in checks),extra4_passed=sum(x['passed'] for x in helpers))))

RESPONSE_SHA='f22d55a920f335bcaf9588dd57edd0615ac7d414c6c4991ce11843c1353102d4'
if __name__=='__main__':
    signal.signal(signal.SIGALRM,lambda *a:(_ for _ in ()).throw(TimeoutError('15s whole diagnostic')))
    signal.alarm(15);main()
