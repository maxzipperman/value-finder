"""Prospective adapters over captured v4 primitives; no runnable paid entrypoint.

Bootstrap must verify code/runtime, exact policy/list/account authority and entire
inventory under shared lock BEFORE initializing these factories or loading a key.
"""
import json
from pathlib import Path
import capture
from receipts import classify, receipt_union


def guarded_session(base, authorize_live, verify_unchanged):
    class PilotSession(base.GuardedSession):
        def get(self,url,**kwargs):
            authorize_live()  # must authenticate exact current hub comment each GET
            verify_unchanged()  # captured content + shared ledger/marker pins
            return super().get(url,**kwargs)
    return PilotSession


def pilot_ledger(base, policy):
    class PilotLedger(base.Ledger):
        def complete(self,row,record,path):
            rid = row['request_id']
            if self.state['pending'] != rid or self.state['attempts'][rid].get('send_started') is not True:
                raise ValueError('durable started reservation required')
            result = classify(row,record,policy)
            if result['reason']:
                prior = sum(a.get('missing_reason') == result['reason'] for a in self.state['attempts'].values())
                if prior >= policy['max_missing'][result['reason']]:
                    raise ValueError('finite missing policy exhausted')
            self.measure_counters(result['used'],result['remaining'],self.billed()-self.state['epoch']['start_billed']+result['bill'])
            proof = {'request_id':rid,'response_sha256':capture.sha(path),'record':record,'classification':result}
            receipt = self.folder/'receipts'/(rid+'.json')
            base.atomic(receipt,proof)
            getattr(self,'checkpoint',lambda _:None)('after_receipt')
            self.state['attempts'][rid].update(status=result['status'],missing_reason=result['reason'],
                billed_credits=result['bill'],response_path=str(Path(path).absolute()),
                response_sha256=capture.sha(path),receipt_sha256=capture.sha(receipt))
            self.state['pending']=None
            self.save()
    return PilotLedger
