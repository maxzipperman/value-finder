"""Reuse only focused synthetic receipt/provenance helper checks, no live cache."""
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parent/'coverage-pilot-v1'))
from test_binding import BindingTests
from test_integration import IntegrationTests, loader

class ProbeRefusal(unittest.TestCase):
    def test_unbound_probe_claim_refused_before_payload(self):
        evidence=loader()('evidence')
        claim=dict(kind='frozen_probe',source_bundle_root='4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d',request_id='fake',cache_source='reuse/fake',cache_sha256='0'*64,request_manifest_sha256='0'*64,probe_ledger_sha256='0'*64,probe_attempt_sha256='0'*64)
        with self.assertRaises(ValueError):evidence.frozen_probe_record(claim,{'freeze':b'{"bundle_root_sha256":"fake","file_sha256":{}}','files':{}})

if __name__=='__main__':
    suite=unittest.TestSuite([BindingTests('test_reuse_authenticated_cells_and_wrong_pin_or_extra_cell'),IntegrationTests('test_actual_parquet_receipt_validation_and_tamper'),IntegrationTests('test_shared_request_dedup_and_zero_denominator'),ProbeRefusal('test_unbound_probe_claim_refused_before_payload')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
