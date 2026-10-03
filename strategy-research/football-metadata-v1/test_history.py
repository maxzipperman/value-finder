"""Synthetic response/certification regressions. No actual runtime or provider reads."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_metadata


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_metadata.MetadataTests.setUpClass()
        cls.history=test_metadata.MetadataTests.load('history')
        cls.capture=test_metadata.MetadataTests.load('capture')
        cls.engine=test_metadata.MetadataTests.engine

    def evidence(self,folder):
        import pyarrow as pa
        import pyarrow.parquet as pq
        params={'date':'2025-10-01T06:00:00Z'}
        ident={'source':'oddsapi/hist_odds','url':'https://api.the-odds-api.com/v4/historical/sports/americanfootball_nfl/odds','params':params}
        rid=self.capture.identity(ident)
        key=__import__('hashlib').sha1(json.dumps(ident,sort_keys=True,default=str).encode()).hexdigest()[:20]
        headers={'x-requests-last':'30','x-requests-used':'30','x-requests-remaining':'4999970'}
        body={'timestamp':params['date'],'previous_timestamp':'2025-10-01T05:55:00Z','next_timestamp':'2025-10-01T06:05:00Z','data':[]}
        rec=dict(ident,params_json=json.dumps(params),cache_key=key,sport='americanfootball_nfl',http_status=200,body=json.dumps(body),headers_json=json.dumps(headers));rec.pop('params')
        cache=folder/'record.parquet';pq.write_table(pa.Table.from_pylist([rec]),cache)
        proof={'request_id':rid,'cache_key':key,'record_sha256':self.capture.sha(cache),'record':rec,'headers':headers}
        receipt=folder/'receipts'/(rid+'.json');receipt.parent.mkdir();receipt.write_text(json.dumps(proof))
        attempt={'status':'completed','reserved_credits':30,'billed_credits':30,'send_started':True,'response_path':str(cache),
                 'response_sha256':self.capture.sha(cache),'receipt_sha256':self.capture.sha(receipt)}
        return rid,attempt,proof,receipt,cache

    def test_complete_response_and_exact_billing_positive(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            rid,a,_,_,_=self.evidence(Path(d));self.history.response_evidence(rid,a,Path(d))
            self.assertEqual(a['reserved_credits'],30)

    def test_completed_receipt_without_response_rejected(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            folder=Path(d);rid,a,_,receipt,_=self.evidence(folder)
            receipt.write_text(json.dumps({'request_id':rid}));a['receipt_sha256']=self.capture.sha(receipt)
            a.pop('response_path');a.pop('response_sha256')
            with self.assertRaisesRegex(ValueError,'response bytes absent'):self.history.response_evidence(rid,a,folder)

    def test_response_and_classification_adverse_paths(self):
        for change in ('delete_cache','changed_cache','receipt_record','bill','classification','missing_without_policy'):
            with self.subTest(change=change),tempfile.TemporaryDirectory(dir='/private/tmp') as d:
                folder=Path(d);rid,a,proof,receipt,cache=self.evidence(folder)
                if change=='delete_cache':cache.unlink()
                elif change=='changed_cache':cache.write_bytes(b'changed')
                elif change=='receipt_record':proof['record']['body']='{}'
                elif change=='bill':a['billed_credits']=0
                elif change=='classification':proof['status']='missing'
                else:a['status']='missing'
                receipt.write_text(json.dumps(proof));a['receipt_sha256']=self.capture.sha(receipt)
                with self.assertRaises((ValueError,FileNotFoundError)):self.history.response_evidence(rid,a,folder)
                self.assertEqual(a['reserved_credits'],30)

    def test_unknown_partial_family_rejected_even_without_receipt_scan(self):
        for status in ('event_epoch_partial_reconciled','older_epoch_partial_reconciled'):
            for full in (True,False):
                with self.subTest(status=status,full=full),self.assertRaisesRegex(ValueError,'Unknown'):
                    self.history.certified_partials({'a'*64:{'status':status}},{},full)

    def test_known_partial_routes_to_deep_authenticated_union(self):
        h=self.history;gate=h.f2_gate
        states={r:{'status':'event_epoch_partial_reconciled' if r in h.PARTIAL_ROOTS else 'event_epoch_complete'} for r in h.F2_ROOTS}
        paths={r:Path('/synthetic')/r/'spending-ledger.json' for r in states}
        with patch.object(gate,'verify_partial') as partial,patch.object(h.capture,'sha',return_value='a'*64),patch.object(gate,'verify_full_union') as deep:
            h.certified_partials(states,paths)
            self.assertEqual(partial.call_count,2);deep.assert_called_once_with(paths[gate.FINAL_ROOT])
            deep.side_effect=ValueError('certificate/stopped backup/auth/run evidence absent')
            with self.assertRaisesRegex(ValueError,'certificate'):h.certified_partials(states,paths)

    def test_f2_status_relabel_cannot_skip_certificate_verification(self):
        h=self.history
        states={r:{'status':'event_epoch_complete'} for r in h.F2_ROOTS}
        with self.assertRaisesRegex(ValueError,'incomplete certified'):
            h.certified_partials(states,{})

    def test_exact_partial_pin_rejects_fabricated_status(self):
        gate=self.history.f2_gate
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            path=Path(d)/'spending-ledger.json';path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Uncertified'):
                gate.verify_partial(gate.FIRST_ROOT,path,{'status':'event_epoch_partial_reconciled'},self.capture.sha(path))

    def test_reviewed_deep_certificate_positive_and_missing_preserved_evidence(self):
        module=self.history.f2_gate.verified_union_module()
        for fault in (None,'backup_absent','backup_changed','approval_absent','approval_commit','certificate'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(dir='/private/tmp') as d:
                root='a'*64;folder=Path(d)/root;folder.mkdir();path=folder/'spending-ledger.json'
                stopped={'pending':'b'*64,'attempts':{'b'*64:{'reserved_credits':20}}}
                stopped_bytes=self.capture.canonical(stopped);stopped_sha=self.capture.digest(stopped_bytes)
                proposal={'original_root':root,'prior_ledger_sha256':stopped_sha,'request_id':'b'*64,'response_sha256':'c'*64,
                          'reserved_credits':20,'billed_credits':0}
                psha=self.capture.identity(proposal)
                state={'status':'event_epoch_partial_reconciled','missing_resolution':{'proposal_sha256':psha}}
                path.write_bytes(self.capture.canonical(state));post=self.capture.sha(path)
                cert={'proposal':proposal,'proposal_sha256':psha,'post_ledger_sha256':post}
                backup=folder/'recovery'/('original-ledger-'+stopped_sha+'.json');backup.parent.mkdir();backup.write_bytes(stopped_bytes)
                commit='d'*40
                line=f'APPROVED offline missing: proposal {psha}, ledger {stopped_sha}, request {"b"*64}, response {"c"*64}, commit {commit}'
                auth={'status':'approved','execution_commit':commit,'proposal_sha256':psha,'prior_ledger_sha256':stopped_sha,
                      'request_id':'b'*64,'response_sha256':'c'*64,'hub_go_ahead':{
                      'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1','comment_body':line}}
                approval=folder/('missing-approval-'+psha+'.json');approval.write_text(json.dumps(auth))
                if fault=='backup_absent':backup.unlink()
                elif fault=='backup_changed':backup.write_text('{}')
                elif fault=='approval_absent':approval.unlink()
                elif fault=='approval_commit':auth['execution_commit']='e'*40;approval.write_text(json.dumps(auth))
                elif fault=='certificate':cert['proposal']['billed_credits']=1
                live={'html_url':auth['hub_go_ahead']['comment_url'],'body':line,'user':{'login':'maxzipperman'}}
                with patch.object(module.subprocess,'check_output',return_value=json.dumps(live)):
                    def checked():return module.check_partial(state,path,cert,root,stopped_sha,post,'b'*64,'c'*64,commit,True)
                    if fault is None:self.assertEqual(checked(),self.capture.sha(approval))
                    else:
                        with self.assertRaises((ValueError,FileNotFoundError)):checked()

    def test_uncached_observed_5xx_requires_exact_approved_attempt(self):
        h=self.history
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            folder=Path(d);rid,a,old,receipt,cache=self.evidence(folder)
            pending={'reserved_credits':30,'status':'pending','cache_key':old['cache_key'],'send_started':True,
                     'observed_http_status':503,'observed_billing_headers':old['headers']}
            a=dict(pending,status='missing',missing_reason='http_5xx',billed_credits=30,
                   response_path=None,response_sha256=None)
            commit='1'*40;prior='2'*64
            line=f'APPROVED missing response: root {folder.name}, request {rid}, ledger {prior}, commit {commit}, reason http_5xx'
            resolution={'request_id':rid,'reason':'http_5xx','owner_note':'synthetic','attempt_sha256':self.capture.identity(pending),
                        'hub_go_ahead':{'status':'approved','commit':commit,'comment_body':line,'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1'}}
            recn={'status':'approved','bundle_root_sha256':folder.name,'prior_ledger_sha256':prior,'missing_response_resolution':resolution}
            proof={'request_id':rid,'status':'accepted_missing','reason':'http_5xx','response_sha256':None,
                   'observed_billing_headers':old['headers'],'reconciliation':recn}
            cache.unlink();receipt.write_text(json.dumps(proof));a['receipt_sha256']=self.capture.sha(receipt)
            h.response_evidence(rid,a,folder,original=True)
            a['observed_http_status']=500
            with self.assertRaisesRegex(ValueError,'attempt proof'):h.response_evidence(rid,a,folder,original=True)
            a['observed_http_status']=503;a['status']='completed'
            with self.assertRaisesRegex(ValueError,'response bytes absent'):h.response_evidence(rid,a,folder,original=True)

    def test_original_approved_cached_missing_positive_and_rejected_tamper(self):
        h=self.history
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            folder=Path(d);rid,a,proof,receipt,cache=self.evidence(folder)
            import pyarrow as pa
            import pyarrow.parquet as pq
            rec=proof['record'];rec['http_status']=404;rec['body']='{}'
            pq.write_table(pa.Table.from_pylist([rec]),cache)
            digest=self.capture.sha(cache);commit='1'*40;prior='2'*64
            line=f'APPROVED missing response: root {folder.name}, request {rid}, ledger {prior}, commit {commit}, reason http_404'
            resolution={'request_id':rid,'reason':'http_404','owner_note':'synthetic','response_sha256':digest,
                        'hub_go_ahead':{'status':'approved','commit':commit,'comment_body':line,'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1'}}
            recn={'status':'approved','bundle_root_sha256':folder.name,'prior_ledger_sha256':prior,'missing_response_resolution':resolution}
            proof={'request_id':rid,'status':'accepted_missing','reason':'http_404','response_sha256':digest,
                   'observed_billing_headers':json.loads(rec['headers_json']),'reconciliation':recn}
            receipt.write_text(json.dumps(proof));a.update(status='missing',missing_reason='http_404',response_sha256=digest,receipt_sha256=self.capture.sha(receipt))
            h.response_evidence(rid,a,folder,original=True)
            proof['reconciliation']['missing_response_resolution']['response_sha256']='3'*64
            receipt.write_text(json.dumps(proof));a['receipt_sha256']=self.capture.sha(receipt)
            with self.assertRaisesRegex(ValueError,'approval response'):h.response_evidence(rid,a,folder,original=True)


if __name__=='__main__':unittest.main()
