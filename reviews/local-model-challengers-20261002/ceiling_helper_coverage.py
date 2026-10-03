"""Declared exact-source helper coverage; original restrictions, default sandbox only."""
import hashlib,json,signal,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'ceiling'))
import harness
from ceiling_verify import verify
from ceiling_type_name_diagnostic import helper_checks

def main():
    if sys.argv[1:]:raise ValueError('No arbitrary candidates')
    verify()
    manifest=json.loads((ROOT/'ceiling-helper-coverage-freeze.json').read_text())
    for name,digest in manifest['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Supplemental freeze changed')
    reference=harness.load(harness.source_bundle(),return_modules=True)
    ref=helper_checks(reference)
    if len(ref)!=4 or not all(x['passed'] for x in ref):raise ValueError('Reference helper acceptance failed')
    class EmptyAccepts:
        def select(self,rows,event,asof):return {} if not rows else reference['quotes'].select(rows,event,asof)
        def reconcile(self,rows,asof):return {} if not rows else reference['runs'].reconcile(rows,asof)
    class RejectStrings:
        def select(self,rows,event,asof):
            if isinstance(asof,str):raise ValueError('deliberate string rejection')
            return reference['quotes'].select(rows,event,asof)
        def reconcile(self,rows,asof):
            if isinstance(asof,str):raise ValueError('deliberate string rejection')
            return reference['runs'].reconcile(rows,asof)
    controls=[]
    for name,wrapper,wanted in [('empty_invalid_accepted',EmptyAccepts(),[False,False,True,True]),('valid_ISO_rejected',RejectStrings(),[True,True,False,False])]:
        value=helper_checks(dict(quotes=wrapper,runs=wrapper))
        if [x['passed'] for x in value]!=wanted:raise ValueError('Faulty control not detected')
        controls.append(dict(name=name,checks=value))
    path=ROOT/'ceiling-space-bunny/implementation-response.txt'
    source=json.loads(path.read_text())
    results=helper_checks(harness.load(source,return_modules=True))
    report=dict(grading='supplemental author direct-helper coverage, post-observation, not independent or original197 grading',original_acceptance_preserved=True,source_sha256=manifest['sha256']['ceiling-space-bunny/implementation-response.txt'],reference_helper_checks=ref,trusted_faulty_controls=controls,checks=results,passed=sum(x['passed'] for x in results),cases=len(results),restrictions='Original AST/runtime-import restrictions unchanged; no type-name exception, feedback or source repair.',limitations='Four probes only, not exhaustive public-interface validation; separate denominator.')
    path.with_name('implementation-helper-coverage.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],cases=report['cases'])))

if __name__=='__main__':
    signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('15s helper diagnostic limit')))
    signal.alarm(15);main()
