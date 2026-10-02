"""Offline exact F3a preparation; final certificate only after this exact F2 union completes."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import epoch
import plan
import union
import f3a_missing


def prepare(candidate=False,continuation_authorization=None,expected_ledger_sha256=None):
    here=Path(__file__).resolve().parent;packet=here/'F3a';bundle=here.parent/'acquisition/football-archive-v4'
    if (packet/'FREEZE.json').exists():
        root=json.loads((packet/'FREEZE.json').read_text())['root']
        if (epoch.ROOT_BASE/root).exists():raise ValueError('Registered F3a packet cannot be regenerated')
    if candidate:
        cert={'status':'candidate_only_requires_exact_completed_F2_union'};coverage={'status':'not_evaluated_until_completion'}
        auth={'status':'candidate_only'};seed={'status':'no_completed_predecessor_yet'}
    else:
        if not continuation_authorization:raise ValueError('Exact non-secret continuation paid authorization JSON required')
        auth=union.json_file(Path(continuation_authorization));cert,coverage=union.validate(auth,expected_ledger_sha256=expected_ledger_sha256,authenticate=True)
        seed={'root':union.CONTINUATION_ROOT,'ledger_path':str(epoch.ROOT_BASE/union.CONTINUATION_ROOT/'spending-ledger.json'),
            'ledger_sha256':cert['continuation_ledger_sha256'],'probe_credits':1687,
            'cumulative_debit_without_probe':cert['cumulative_debit_without_probe']}
    epoch.source_executor(bundle)
    plan.build(bundle,packet,'F3a')
    m=json.loads((packet/'manifest.json').read_text());rows=json.loads((packet/'requests.json').read_text());ops=json.loads((packet/'opportunities.json').read_text())
    raw_roots=epoch.known_raw_roots()
    _,read_record,*_=epoch.source_executor(bundle).vendor_imports(bundle,packet)
    base=epoch.source_executor(bundle);protocol=json.loads((bundle/'protocol.json').read_text());reused=[]
    for row in rows:
        hits=epoch.matches(row,raw_roots)
        if hits:
            hashes={plan.sha(p) for p in hits}
            if len(hashes)!=1:raise ValueError('Conflicting exact F3a cache copies')
            epoch.event_valid(row,read_record(hits[0]),base,protocol)
            row.update(max_new_credits=0,cache_source=str(hits[0]),cache_sha256=next(iter(hashes)))
            reused.append({'request_id':row['request_id'],'paths':[str(p) for p in hits],'sha256':row['cache_sha256']})
    missing_policy=f3a_missing.expected(rows,ops)
    m['f3a_exact_missing_policy_sha256']=f3a_missing.sha(missing_policy)
    m['stage']='candidate' if candidate else 'F3a-from-F2-union'
    m['f2_union_certificate_sha256']=union.digest(plan.canonical(cert))
    m=plan.write_packet(packet,m,rows,ops)
    for name,obj in [('exact-missing-policy.json',missing_policy),('seed.json',seed),('union-certificate.json',cert),('union-coverage.json',coverage),('continuation-authorization.json',auth),
        ('cache-reconciliation.json',{'status':'reconciled','raw_roots':sorted(str(Path(p).resolve()) for p in raw_roots),
            'request_set_sha256':m['request_set_sha256'],'reused':reused,'paid_count':sum(bool(r['max_new_credits']) for r in rows),'new_credits':m['new_credits']})]:
        (packet/name).write_bytes(plan.canonical(obj)+b'\n')
    root=epoch.freeze(packet);epoch.verify_packet(packet,root);epoch.verify_source_plan(packet,bundle,m,rows)
    if not candidate:
        epoch.seed_state(seed,rows);epoch.stage_guard(packet,m,seed,rows,bundle,authenticate=False)
    print(json.dumps({'root':root,'stage':m['stage'],'requests':len(rows),'new_calls':sum(bool(r['max_new_credits']) for r in rows),
        'new_credits':m['new_credits'],'request_list_sha256':m['request_list_sha256'],'request_set_sha256':m['request_set_sha256'],
        'sealed_reads':False,'outcomes_joined':False,'paid_calls':0,'strategy_grading_enabled':False},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',action='store_true');p.add_argument('--continuation-authorization',type=Path);p.add_argument('--expected-ledger-sha256')
    a=p.parse_args();prepare(a.candidate,a.continuation_authorization,a.expected_ledger_sha256)
