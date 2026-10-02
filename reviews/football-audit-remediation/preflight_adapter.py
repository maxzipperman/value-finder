"""Outcome-blind acceptance preflight; no model, scores, keys or paid transport."""
import argparse,json,resource,sys,time,hashlib
from pathlib import Path

def guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Preflight network disabled')
    if event=='open' and isinstance(args[0],(str,bytes)):
        s=str(args[0])
        if Path(s).name.startswith('.env') or '/data/forward/' in s or s.endswith(('games.parquet','scores.parquet','pricing_cohort.json')):
            raise RuntimeError('Preflight credential/outcome/cohort read disabled')
sys.addaudithook(guard)
import dotenv
dotenv.load_dotenv=lambda *a,**k:False
from markets.research.price_engine import handoff,archive_adapter
p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
start=time.monotonic();root=archive_adapter.ACQUIRED_ROOT
ledger_before=archive_adapter.sha(a.runtime/'spending-ledger.json')
verified,sources=handoff._verify(a.bundle,root)
with handoff._bundle_code(a.bundle,sources):
    import importlib
    validator=importlib.import_module('validator');executor=importlib.import_module('executor')
    accepted=archive_adapter.build_handoff(a.bundle,root,a.runtime,verify=validator.verify,validate_response=executor.validate_response)
    cache=archive_adapter.ReadOnlyCache(accepted,a.runtime/'data/raw',a.bundle)
assert archive_adapter.sha(a.runtime/'spending-ledger.json')==ledger_before
handoff.verify_frozen(a.bundle,root)
peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform!='darwin':peak*=1024
out={'status':'passed','mode':'acceptance adapter only; registration/strategy runner never invoked','entries':len(accepted['entries']),
     'accepted_missing':sum(e.get('status')=='accepted_missing' for e in accepted['entries']),
     'canonical_provider_bindings':len(cache.canonical_event_map),'ambiguous_bindings':sum(v is None for v in cache.canonical_event_map.values()),
     'coverage_report_sha256':accepted['coverage_report_sha256'],'ledger_sha256':ledger_before,
     'elapsed_seconds':round(time.monotonic()-start,2),'peak_rss_bytes':peak,'memory_budget_bytes':2*1024**3,
     'outcomes_joined':False,'API_calls':0,'frozen_bundle_modified':False,'registration_root_still_unset':handoff.REGISTERED_ROOT is None}
assert peak<out['memory_budget_bytes'],out
assert out['registration_root_still_unset']
a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
