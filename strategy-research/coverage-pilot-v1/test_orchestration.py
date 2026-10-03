"""Synthetic orchestration with real ledger/cache/lock/transport primitives.

Historical baseline/source authority adapters are synthetic fixtures here; their
real read-only proof is separate. No provider call or actual credential is used.
"""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_integration import loader, BUNDLE


class OrchestrationTests(unittest.TestCase):
    def test_locked_complete_and_resume_exhaustion(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            folder=Path(d)
            with patch.dict(os.environ,{'MARKETS_ROOT':str(folder),'MARKETS_DATA_DIR':str(folder/'data')}):
                load=loader();m=load('orchestration');base=load('executor');capture=load('capture');plan=load('plan')
                base.RUNTIME_BASE=folder/'state';base.RUNTIME_BASE.mkdir();(base.RUNTIME_BASE/'registrations').mkdir()
                old=base.RUNTIME_BASE/'base';old.mkdir();(old/'spending-ledger.json').write_text(json.dumps({'attempts':{}}));(old/'INITIALIZED.json').write_text('{}')
                (base.RUNTIME_BASE/'registrations/base.json').write_text('{}')
                snapshot={'ledgers':{'base':capture.sha(old/'spending-ledger.json')},'registrations':{'base':capture.sha(base.RUNTIME_BASE/'registrations/base.json')}}
                row=plan.make_request('odds',plan.ts('2025-10-01T06:00:00Z'),books=['draftkings'],markets=['player_pass_yds'],event_id='abc')
                root='a'*64;commit='b'*40;runtime=base.runtime_path(root)
                rawroots={str((old/'data/raw').absolute()),str((Path.home()/'code/value-finder/sharp-markets/data/raw').absolute()),str((folder/'probe/data/raw').absolute())}
                # Overlap adapter is replaced below, so no live checkout cache is inspected.
                bindings={'base_snapshot':snapshot,'expected_global_snapshot':snapshot,'historical_bindings':{},'pilot_bindings':{}}
                cacheplan={'raw_roots':sorted(rawroots),'probe_bundle_root':str(folder/'probe'),'inventory_sha256':'f'*64}
                manifest={'request_count':1,'max_new_credits':10,'request_list_sha256':'c'*64,'request_set_sha256':'d'*64}
                policy={'snapshot_lag_ids':[row['request_id']],'event_not_found_ids':[row['request_id']],'max_missing':{'snapshot_lag':1,'event_not_found':1}}
                data={k:json.dumps(v).encode() for k,v in {'manifest.json':manifest,'requests.json':[row],'policy.json':policy,'protocol.json':{'execution_status':'reviewed_for_execution'},'baseline.json':bindings,'overlap.json':cacheplan,'mappings.json':[]}.items()}
                source={n:(BUNDLE/n).read_bytes() for n in ('runtime-lock.json','protocol.json','probe-spending-ledger.json','request-manifest.json')};source['input-provenance.json']=b'{"raw_probe_sources":[]}'
                rec={'status':'approved','bundle_root_sha256':root,'baseline_mode':'capture_first_free_check','reason':'synthetic','owner_note':'synthetic','max_baseline_used':0,'billing_period_utc':base.datetime.now(base.timezone.utc).strftime('%Y-%m')}
                hub=dict(status='approved',bundle_root_sha256=root,request_set_sha256=manifest['request_set_sha256'],request_list_sha256=manifest['request_list_sha256'],budget_credits=10,commit=commit,comment_url='https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1',comment_body=f"APPROVED paid run: list {manifest['request_list_sha256']}, request-set {manifest['request_set_sha256']}, budget 10 credits, commit {commit}")
                auth=dict(status='approved',bundle_root_sha256=root,priority=1,max_new_credits=10,human_authorization_evidence='synthetic',execution_commit=commit,account_reconciliation=rec,hub_go_ahead=hub)
                calls=[];keys=[];checks=[]
                def authority(*args):checks.append('authority')
                def baseline(*args):return snapshot,{'cumulative_debit_without_probe':100}
                def verified(*args):return SimpleNamespace(packet=lambda *a:None),base,data,source,load
                def http():
                    def get(url,**kw):
                        calls.append(url)
                        if url.endswith('/sports'):return SimpleNamespace(status_code=200,text='[]',headers={'x-requests-last':'0','x-requests-used':'0','x-requests-remaining':'5000000'})
                        body={'timestamp':row['requested_utc'],'previous_timestamp':'2025-10-01T05:55:00Z','next_timestamp':'2025-10-01T06:05:00Z','data':{'id':'abc','sport_key':row['sport'],'commence_time':'2025-10-02T06:00:00Z','bookmakers':[]}}
                        return SimpleNamespace(status_code=200,text=json.dumps(body),headers={'x-requests-last':'10','x-requests-used':'10','x-requests-remaining':'4999990'})
                    return SimpleNamespace(adapters={'https':SimpleNamespace(max_retries=SimpleNamespace(total=0))},get=get,close=lambda:None)
                def key():keys.append(len(checks));return 'synthetic-test-secret'
                with patch.object(m.bootstrap,'verified',verified),patch.object(base,'checkout_commit',lambda _:commit),patch.object(base,'execution_context',lambda *a:None),patch.object(base,'current_runtime',lambda:json.loads(source['runtime-lock.json'])),patch.object(m.authority,'check',authority),patch.object(m.baseline,'verify_base',baseline),patch.object(m.overlap,'check',lambda *a,**kw:None):
                    result=m.run(folder/'packet',root,BUNDLE,auth,key_factory=key,http_factory=http)
                    self.assertEqual(result['status'],'pilot_complete');self.assertEqual(len(calls),2)
                    self.assertGreaterEqual(keys[0],3)
                    saved=json.loads((runtime/'spending-ledger.json').read_text())
                    self.assertEqual(saved['probe_credits'],1687);self.assertEqual(saved['other_usage_reserved'],100)
                    with self.assertRaises(ValueError):m.run(folder/'packet',root,BUNDLE,auth,key_factory=key,http_factory=http)
                    self.assertEqual(len(calls),2);self.assertEqual(len(keys),1)

    def test_preparation_packet_stops_before_key_or_http(self):
        load=loader();m=load('orchestration');calls=[]
        v=lambda *a:(SimpleNamespace(packet=lambda *a:None),None,{'protocol.json':b'{"execution_status":"draft"}'},None,None)
        with patch.object(m.bootstrap,'verified',v):
            with self.assertRaises(ValueError):m.run('unused','unused','unused',{},key_factory=lambda:calls.append('key'),http_factory=lambda:calls.append('http'))
        self.assertEqual(calls,[])
