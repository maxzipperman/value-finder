"""Synthetic failure tests; exact local halt replay is a separate read-only check."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
REPO=HERE.parent.parent
sys.path.insert(0,str(HERE))
import recovery
sys.path.insert(0,str(HERE.parent/'coverage-pilot-v1'))
from test_integration import loader

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.load=staticmethod(loader());cls.receipts=cls.load('receipts');cls.q=cls.load('quarantine')

    def event(self,price=1.0):
        return {'bookmakers':[{'key':'draftkings','markets':[{'key':'totals','outcomes':[{'name':'Over','price':price,'point':44}]}]}]}

    def test_one_requires_explicit_policy_and_is_counted(self):
        with self.assertRaisesRegex(ValueError,'invalid decimal price'):self.receipts.odds_shape(self.event())
        self.assertEqual(self.receipts.odds_shape(self.event(),allow_decimal_one=True),1)
        self.assertEqual(self.receipts.odds_shape(self.event(1.91)),0)

    def test_amendment_never_normalizes_other_bad_quotes(self):
        for price in (0,.99,-1,True,'1.0',None,float('inf'),float('nan')):
            with self.subTest(price=price),self.assertRaises(ValueError):self.receipts.odds_shape(self.event(price),allow_decimal_one=True)
        for event in ({'bookmakers':[{'key':'x','markets':[]},{'key':'x','markets':[]}]}, {'bookmakers':[{'key':'x','markets':[{'key':'x','outcomes':[{'name':'','price':1}]}]}]}):
            with self.assertRaises(ValueError):self.receipts.odds_shape(event,allow_decimal_one=True)

    def test_literal_one_cannot_form_two_sided_pair(self):
        classifier=self.load('classifier')
        at='2020-10-02T15:50:00Z';kick='2020-10-02T16:00:00Z'
        body=dict(timestamp=at,previous_timestamp='2020-10-02T15:45:00Z',next_timestamp='2020-10-02T15:55:00Z',data=dict(id='e',commence_time=kick,home_team='A',away_team='B',bookmakers=[dict(key='draftkings',last_update=at,markets=[dict(key='totals',outcomes=[dict(name='Over',point=44,price=1),dict(name='Under',point=44,price=1.91)])])]))
        binding=dict(status='bound',event_id='e',provider_kickoff_utc=kick,binding_observed_utc=at,home_team='A',away_team='B')
        result=classifier.slot_pairs(body,requested=at,execution=at,binding=binding,independent_kickoff=kick,slot='CLOSE_T10',candidate_books=['draftkings'],markets=['totals'])
        self.assertEqual(result['pairs'],set());self.assertIn('invalid_quote',result['reasons'])

    def test_quarantined_selected_success_rejected(self):
        evidence=self.load('evidence');args=dict(frame_sha256='a'*64,protocol_sha256='b'*64,draw_sha256='c'*64,evidence_sha256='d'*64,selected_ids=['g'],classifications={'g':True},saved_bounds={},mappings=[dict(game_id='g',coverage_disposition=dict(classification='failure'))])
        with self.assertRaises(ValueError):evidence.final_record(**args)
        args['classifications']={'g':False}
        self.assertFalse(evidence.final_record(**args)['next_purchase_authorized'])

    def test_bad_builder_rejected_before_execution(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            repo=Path(d);p=repo/'strategy-research/coverage-pilot-packet-v1/build.py';p.parent.mkdir(parents=True);sentinel=repo/'executed'
            p.write_text(f"open({str(sentinel)!r},'w').write('bad')")
            with self.assertRaisesRegex(ValueError,'before execution'):recovery.packet_builder(repo,{'packet_builder':'0'*64,'recovery_builder':'0'*64})
            self.assertFalse(sentinel.exists())

    def test_bad_bootstrap_rejected_before_execution(self):
        build=recovery.packet_builder(REPO)
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            repo=Path(d);p=repo/'strategy-research/coverage-pilot-v1/bootstrap.py';p.parent.mkdir(parents=True);sentinel=repo/'executed'
            p.write_text(f"open({str(sentinel)!r},'w').write('bad')")
            with patch.object(recovery,'packet_builder',return_value=build),self.assertRaises(ValueError):recovery.loader(repo,{'bootstrap':'0'*64})
            self.assertFalse(sentinel.exists())

    def test_live_approval_revocation_and_exact_certificate(self):
        cert=dict(after_ledger_sha256='a'*64,receipt_sha256='b'*64);pin=self.load('capture').identity(cert)
        line=f"APPROVED offline reconciliation: certificate {pin}, before-ledger {self.q.BEFORE}, after-ledger {'a'*64}, receipt {'b'*64}, no resend"
        url='https://github.com/maxzipperman/value-finder/pull/1#issuecomment-2'
        binding=dict(certificate=cert,certificate_sha256=pin,approval=dict(comment_url=url,comment_body=line))
        live=dict(html_url=url,body=line,user=dict(login='maxzipperman'))
        self.assertEqual(self.q.verify_approval(binding,fetch=lambda _:live),cert)
        for changed in (dict(live,body='HALTED'),dict(live,user=dict(login='other')),dict(live,html_url=url+'0')):
            with self.assertRaises(ValueError):self.q.verify_approval(binding,fetch=lambda _:changed)
        binding['certificate_sha256']='0'*64
        with self.assertRaises(ValueError):self.q.verify_approval(binding,fetch=lambda _:live)

    def test_exact_transition_retains_reservations_and_does_not_mutate_input(self):
        from types import SimpleNamespace
        attempts={str(i):dict(status='completed',reserved_credits=40,billed_credits=30) for i in range(6)}
        headers={'x-requests-last':'30','x-requests-used':'167405','x-requests-remaining':'4832595'}
        attempts[self.q.RID]=dict(status='pending',send_started=True,reserved_credits=30,observed_http_status=200,observed_billing_headers=headers)
        state=dict(bundle_root_sha256=self.q.ROOT,pending=self.q.RID,status='halted',attempts=attempts,epoch={'start_billed':0},probe_credits=1687)
        original=copy.deepcopy(state);record=dict(headers_json=json.dumps(headers),http_status=200)
        class Ledger:
            def billed(self):return sum(a.get('billed_credits',0) for a in self.state['attempts'].values())
            def reserved(self):return sum(a['reserved_credits'] for a in self.state['attempts'].values())
            def measure_counters(self,used,left,billed):
                if (used,left,billed)!=(167405,4832595,210):raise ValueError('counter mismatch')
                self.save()
        base=SimpleNamespace(Ledger=Ledger,canonical=recovery.canonical)
        def classify(row,rec,policy):
            if 'quote_policy' not in policy:raise ValueError('invalid decimal price')
            return dict(status='completed',bill=30,used=167405,remaining=4832595,ineligible_quote_counts={'decimal_one':1})
        with patch.object(self.q.receipts,'classify',side_effect=classify):
            after,receipt=self.q.transition(state,{'request_id':self.q.RID},record,{},base,{},'/private/tmp/cache')
            self.assertEqual(state,original);self.assertEqual(after['status'],'pilot_partial_reconciled')
            self.assertFalse(json.loads(receipt)['classification']['usable_quote'])
            for field,value in [('bundle_root_sha256','x'),('pending',None),('status','pilot_complete')]:
                changed=copy.deepcopy(state);changed[field]=value
                with self.assertRaises(ValueError):self.q.transition(changed,{'request_id':self.q.RID},record,{},base,{},'/private/tmp/cache')
            for field,value in [('reserved_credits',0),('send_started',False),('observed_http_status',429)]:
                changed=copy.deepcopy(state);changed['attempts'][self.q.RID][field]=value
                with self.assertRaises(ValueError):self.q.transition(changed,{'request_id':self.q.RID},record,{},base,{},'/private/tmp/cache')

    def test_installer_revoked_last_approval_writes_nothing(self):
        from types import SimpleNamespace
        import pyarrow as pa
        import pyarrow.parquet as pq
        output=pa.BufferOutputStream();pq.write_table(pa.Table.from_pylist([{'http_status':200}]),output);raw=output.getvalue().to_pybytes()
        q=self.q;after={'attempts':{}};receipt=b'{}\n';before={'attempts':{q.RID:{},**{str(i):{} for i in range(6)}}}
        cert=dict(code_inventory={},marker_sha256='marker',initialization_sha256='init',cache_path='synthetic',after_ledger_sha256=recovery.sha(recovery.canonical(after)+b'\n'),receipt_sha256=recovery.sha(receipt))
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            root=Path(d);runtime=root/q.ROOT;runtime.mkdir();(root/'followup-purchase.lock').touch();(runtime/'acquisition.lock').touch()
            certificate=root/'certificate.json';certificate.write_bytes(recovery.canonical(cert))
            mutations=[];proofs=[];base=SimpleNamespace(RUNTIME_BASE=root,canonical=recovery.canonical,atomic=lambda *a:mutations.append(a))
            capture=SimpleNamespace(sha=lambda p: ('marker' if Path(p).parent.name=='registrations' else 'init' if Path(p).name=='INITIALIZED.json' else q.BEFORE),regular=lambda p:raw,read=lambda p:copy.deepcopy(before))
            evidence=SimpleNamespace(captured_receipts=lambda *a:proofs.append(a))
            load=lambda n:{'quarantine':q,'executor':base,'capture':capture,'evidence':evidence}[n]
            boot=SimpleNamespace(regular=lambda p:b'{}')
            data={'requests.json':recovery.canonical([{'request_id':q.RID}]),'policy.json':b'{}'}
            args=SimpleNamespace(certificate=certificate,certificate_sha256=recovery.sha(certificate.read_bytes()),repo=root,approval=root/'approval',old_packet=root)
            with patch.object(recovery,'loader',return_value=(None,boot,load,{'protocol.json':b'{}'},None,None,{})),patch.object(recovery,'old_data',return_value=(data,{})),patch.object(q,'RAW',recovery.sha(raw)),patch.object(q,'transition',return_value=(after,receipt)),patch.object(q,'verify_approval',side_effect=[cert,ValueError('revoked')]):
                with self.assertRaisesRegex(ValueError,'revoked'):recovery.install(args)
            self.assertEqual(mutations,[]);self.assertEqual(len(proofs),1)
            self.assertEqual(len(proofs[0][2]['attempts']),6)

    def test_output_rejects_live_runtime_traversal_existing_and_symlink(self):
        build=recovery.packet_builder(REPO)
        for out in (REPO,REPO/'STATUS.md',REPO/'..'/'escape',Path.home()/'code/value-finder/new',Path.home()/'Library/Application Support/ValueFinder/football-acquisition-state/new'):
            with self.subTest(out=out),self.assertRaises(ValueError):build.validate_output(REPO,out)
        with tempfile.TemporaryDirectory(dir=REPO) as d:
            link=Path(d)/'link';link.symlink_to('/private/tmp')
            with self.assertRaises(ValueError):build.validate_output(REPO,link/'new')

if __name__=='__main__':unittest.main()
