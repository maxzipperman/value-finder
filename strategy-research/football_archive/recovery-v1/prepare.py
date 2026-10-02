"""Preview one pinned offline transition and freeze exact continuation; never mutate runtime."""
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import epoch
import missing
import plan


def prepare():
    here=Path(__file__).parent;bundle=here.parent/'acquisition/football-archive-v4';packet=here/'F2-continuation'
    if (packet/'FREEZE.json').exists():
        root=json.loads((packet/'FREEZE.json').read_text())['root']
        if (epoch.ROOT_BASE/root).exists():raise ValueError('Cannot regenerate registered continuation')
    cert,post,_,rows=missing.preview(bundle)
    _,m,_=missing.original()
    ops=json.loads((here.parent/'execution-v1/F2/opportunities.json').read_text())
    for row in rows:
        attempt=post['attempts'].get(row['request_id'])
        if attempt:
            row.update(max_new_credits=0,cache_source=attempt['response_path'],cache_sha256=attempt['response_sha256'])
    m['stage']='F2-continuation';m['cache_reconciliation']='completed predecessor reuse plus exact no-resend missing; fresh exact-key cross-store check'
    m=plan.write_packet(packet,m,rows,ops)
    raw_roots=json.loads((here.parent/'execution-v1/F2/cache-reconciliation.json').read_text())['raw_roots']
    # New exact rows must be absent from all known stores, including original root.
    raw_roots=sorted(set(raw_roots+[str(epoch.ROOT_BASE/missing.ORIGINAL_ROOT/'data/raw')]))
    for row in rows:
        hits=[]
        for raw in raw_roots:
            hits.extend((Path(raw)/row['sport']/row['source']).glob('*/'+row['cache_key']+'.parquet'))
        if row['max_new_credits'] and hits:raise ValueError('New overlapping cache; review instead of repurchase')
        if not row['max_new_credits']:
            if not hits or any(plan.sha(p)!=row['cache_sha256'] for p in hits):raise ValueError('Reused cache missing/conflicting')
    seed={'root':missing.ORIGINAL_ROOT,'ledger_path':str(epoch.ROOT_BASE/missing.ORIGINAL_ROOT/'spending-ledger.json'),
        'ledger_sha256':cert['post_ledger_sha256'],'probe_credits':1687,
        'cumulative_debit_without_probe':post['other_usage_reserved']+sum(a['reserved_credits'] for a in post['attempts'].values())}
    packet.mkdir(exist_ok=True)
    for name,obj in [('missing-certificate.json',cert),('seed.json',seed),('cache-reconciliation.json',
        {'status':'reconciled','raw_roots':raw_roots,'request_set_sha256':m['request_set_sha256'],
         'reused':[{'request_id':r['request_id'],'sha256':r['cache_sha256'],'paths':[r['cache_source']]} for r in rows if not r['max_new_credits']],
         'paid_count':1307,'new_credits':26140})]:
        (packet/name).write_bytes(plan.canonical(obj)+b'\n')
    root=epoch.freeze(packet);epoch.verify_packet(packet,root);epoch.verify_source_plan(packet,bundle,m,rows)
    print(json.dumps({'root':root,'proposal_sha256':cert['proposal_sha256'],'post_ledger_sha256':cert['post_ledger_sha256'],
        'request_count':len(rows),'new_calls':sum(bool(r['max_new_credits']) for r in rows),'new_credits':m['new_credits'],
        'request_list_sha256':m['request_list_sha256'],'request_set_sha256':m['request_set_sha256'],
        'predecessor_cumulative_reserved':1687+seed['cumulative_debit_without_probe'],'paid_calls':0},indent=2))


if __name__=='__main__':prepare()
