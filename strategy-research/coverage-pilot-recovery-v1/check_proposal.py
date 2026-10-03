"""Read-only exact halt replay; virtual receipt/ledger only, no install or sends."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import recovery


def check(repo,packet,proposal):
    cert=json.loads(recovery.regular(proposal/'certificate.json'))
    build,boot,load,source,bundle,paths,inventory=recovery.loader(repo,cert['code_inventory'])
    q=load('quarantine');base=load('executor');capture=load('capture')
    runtime=base.RUNTIME_BASE/q.ROOT;ledger=runtime/'spending-ledger.json'
    before=capture.regular(ledger)
    if recovery.sha(before)!=q.BEFORE:raise ValueError('live halted ledger differs')
    data,_=recovery.old_data(packet,boot,q.ROOT);rows=json.loads(data['requests.json']);policy=json.loads(data['policy.json']);state=json.loads(before)
    row=next(r for r in rows if r['request_id']==q.RID)
    raw=capture.regular(cert['cache_path'])
    if recovery.sha(raw)!=q.RAW:raise ValueError('cache differs')
    import pyarrow as pa
    import pyarrow.parquet as pq
    record=pq.read_table(pa.BufferReader(raw)).to_pylist()[0]
    after,receipt=q.transition(state,row,record,policy,base,json.loads(source['protocol.json']),cert['cache_path'])
    if recovery.sha(base.canonical(after)+b'\n')!=cert['after_ledger_sha256'] or recovery.sha(receipt)!=cert['receipt_sha256']:raise ValueError('proposal transition differs')
    if recovery.regular(proposal/'after-ledger.json')!=base.canonical(after)+b'\n':raise ValueError('proposal after bytes differ')
    untouched=[r for r in rows if r['request_id'] not in state['attempts']]
    if recovery.regular(proposal/'untouched-requests.json')!=recovery.canonical(untouched) or len(untouched)!=729 or sum(r['max_new_credits'] for r in untouched)!=36810:raise ValueError('residual differs')
    original_sha=capture.sha;original_regular=capture.regular;receipt_path=runtime/'receipts'/(q.RID+'.json')
    def read(path):
        p=Path(path)
        if p==ledger:return base.canonical(after)+b'\n'
        if p==receipt_path:return receipt
        return original_regular(path)
    def hashed(path):return recovery.sha(read(path))
    with patch.object(capture,'regular',side_effect=read),patch.object(capture,'sha',side_effect=hashed):
        proof=q.verify_partial(runtime,rows,after,policy,cert)
        for change in ('status','billed_credits','reserved_credits','receipt_sha256'):
            bad=copy.deepcopy(after);bad['attempts'][q.RID][change]=None
            try:q.verify_partial(runtime,rows,bad,policy,cert)
            except (ValueError,TypeError):pass
            else:raise ValueError('altered quarantine attempt accepted')
        changed=dict(cert,after_ledger_sha256='0'*64)
        try:q.verify_partial(runtime,rows,after,policy,changed)
        except ValueError:pass
        else:raise ValueError('altered certificate accepted')
    if original_sha(ledger)!=q.BEFORE or original_sha(cert['cache_path'])!=q.RAW or receipt_path.exists():raise ValueError('runtime changed during read-only check')
    return dict(passed=True,certificate_sha256=capture.identity(cert),after_ledger_sha256=cert['after_ledger_sha256'],receipt_sha256=cert['receipt_sha256'],six_original_receipts_verified=True,untouched_count=len(proof['untouched_ids']),untouched_cap=36810,observed_charges=210,reserved=270,conservative_carry=170576,paid_calls=0,runtime_modified=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--old-packet',type=Path,required=True);p.add_argument('--proposal',type=Path,required=True);a=p.parse_args()
    print(json.dumps(check(a.repo,a.old_packet,a.proposal),sort_keys=True))
