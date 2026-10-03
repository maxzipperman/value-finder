"""Synthetic-only account fixture. Never imported by production or installers.

Replaces the unconditional hold ONLY inside a scoped test patch. No key lookup,
provider access or runtime baseline bootstrap. Temporary journal and lock only.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from ops import collector_guard as guard


@contextmanager
def synthetic_account(root, key, params, *, ceiling=900):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    journal = root / 'journal.json'
    config = root / 'authority.json'
    now = datetime.now(timezone.utc)
    authority = dict(version=2, source_sha='a'*40, approval='SYNTHETIC ONLY',
                     month=now.strftime('%Y-%m'), valid_until_utc=(now+timedelta(hours=1)).isoformat(),
                     account_fingerprint=guard.digest(key.encode())[:12], account_ceiling=ceiling,
                     plan_credits=50000, reserve_floor=100, ledger=str(journal),
                     shared_writers=sorted(guard.LABELS), roles={
                         label:dict(cap=50,path_pattern=guard.ROLE_PATHS[label],params=params)
                         for label in guard.LABELS})
    config.write_text(json.dumps(authority))
    identity=guard.digest(config.read_bytes())
    journal.write_text(json.dumps(dict(version=2,envelope_sha256=identity,baseline_used=100,
                                      external_reserved=0,external_state='ready',attempts={})))
    journal.with_suffix('.json.lock').touch()
    def state():return json.loads(journal.read_text())
    class FakeSession:
        calls=[]
        failure=None
        body="[]"
        def get_adapter(self,url):return SimpleNamespace(max_retries=SimpleNamespace(total=0))
        def get(self,url,**kwargs):
            attempts=state()['attempts']
            assert any(a['state']=='pending' for a in attempts.values())
            assert kwargs['allow_redirects'] is False
            self.calls.append((url,kwargs))
            if self.failure:raise self.failure
            used=100+sum(a['reserved'] for a in attempts.values())
            pending=next(a for a in attempts.values() if a['state']=='pending')
            return SimpleNamespace(status_code=200,text=self.body,headers={
                'x-requests-last':str(pending['reserved']),
                'x-requests-used':str(used),'x-requests-remaining':str(50000-used)})
    session=FakeSession()
    with patch.dict(os.environ,VF_COLLECTOR_ENVELOPE=str(config),VF_COLLECTOR_ENVELOPE_SHA256=identity), \
         patch.object(guard,'ACCOUNT_LEDGER',journal), \
         patch.object(guard,'source_sha',return_value='a'*40), \
         patch.object(guard,'require_bridge',return_value=None):
        yield session,state
