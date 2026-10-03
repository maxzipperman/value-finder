"""Offline reservation/audit controls, synthetic ledgers only."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from openrouter_budget import totals, reserve_ok, audited_terminal

class BudgetChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
    def write(self,name,data):
        p=self.root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(data)); return p
    def attempt(self,n,status='completed',**kw):
        return dict(model='m',task='t',status=status,maximum_estimate_usd=n,accounted_usd=n,**kw)
    def test_combined_unknown_reservation(self):
        self.write('openrouter-paid/billing.json',{'attempts':[self.attempt(.40,'stopped')]})
        self.write('openrouter-paid32k/billing.json',{'attempts':[self.attempt(.35)]})
        self.write('openrouter-ceiling/billing.json',{'attempts':[self.attempt(.20)]})
        self.assertAlmostEqual(totals(self.root),.95)
        reserve_ok(self.root,.04)
        with self.assertRaises(RuntimeError):reserve_ok(self.root,.06)
    def test_invalid_values(self):
        for n in (True,float('nan'),float('inf'),-1):
            self.write('openrouter-paid/billing.json',{'attempts':[self.attempt(n)]})
            with self.assertRaises(RuntimeError):totals(self.root)
    def test_underreservation_and_duplicates(self):
        a=self.attempt(.2);a['accounted_usd']=.1
        self.write('openrouter-paid/billing.json',{'attempts':[a]})
        with self.assertRaises(RuntimeError):totals(self.root)
        self.write('openrouter-paid/billing.json',{'attempts':[self.attempt(.2),self.attempt(.2)]})
        with self.assertRaises(RuntimeError):totals(self.root)
    def test_error_audit_is_digest_bound(self):
        ledger={'attempts':[self.attempt(.2,'stopped')]}
        self.assertFalse(audited_terminal(self.root,ledger))
        p=self.write('openrouter-paid/m/t-error.json',{'http_status':520})
        self.write('openrouter-error-audit.json',{'m|t':{'continue_distinct_missing_only':True,'reason':'No repeat; retain reservation','error_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}})
        self.assertTrue(audited_terminal(self.root,ledger))
        p.write_text('{}');self.assertFalse(audited_terminal(self.root,ledger))
        ledger['attempts'][0]['status']='reserved';self.assertFalse(audited_terminal(self.root,ledger))

if __name__=='__main__':unittest.main()
