"""Purchase-loop preparation over captured primitives; no public paid entrypoint.

Caller MUST hold the shared lock before ledger creation, authenticate complete
baseline/cache union and packet, and verify live authority before credential access.
The guard callbacks below must be the captured authority/inventory checks, never
user-supplied callbacks in a production CLI. Until that wiring is independently
reviewed, runner remains offline-only. Tests use temporary ledgers and fake HTTP.
"""
import os
import time
import capture
import evidence
import receipts
import transport


def prepared_loop(*, base, ledger, rows, policy, raw_cache, fetched_type, http_session,
                  authorize_live, verify_unchanged, credential, checkpoint=lambda _:None, pause_after=None):
    """Run exact untouched rows; stopped/pending attempts never auto-recover.

    Ledger and cache are explicit, already initialized under the outer shared lock.
    Returned completion is acquisition-only, not a final statistical look or release.
    """
    if pause_after is not None and (type(pause_after) is not int or pause_after<1):
        raise ValueError("positive clean-pause count required")
    receipts.validate_policy(rows,policy)
    if (ledger.state.get('status')=='pilot_complete' or ledger.state.get('pending')
            or ledger.state.get('stopped') or ledger.state.get('free_account_attempt',{}).get('status') in {'started','received'}):
        raise ValueError('exhausted or unresolved epoch; never resend')
    evidence.captured_receipts(ledger.folder,rows,ledger.state,policy)
    authorize_live();verify_unchanged()
    if not isinstance(credential,str) or len(credential)<8:raise ValueError("explicit authorized credential required")
    ledger.checkpoint=checkpoint
    session=transport.guarded_session(base,authorize_live,verify_unchanged)(http_session,ledger,rows)
    session.ledger_key=credential
    try:
        response=session.get('https://api.the-odds-api.com/v4/sports',params={},timeout=30)
        if response.status_code!=200:raise ValueError('free account check failed')
        ledger.account(receipts.integer(response.headers.get('x-requests-used')),receipts.integer(response.headers.get('x-requests-remaining')))
        completed_here=0
        for row in rows:
            if row['request_id'] in ledger.state['attempts']:continue
            if raw_cache.lookup(row['sport'],row['source'],row['cache_key']) is not None:
                raise ValueError('unreconciled own cache; never repurchase')
            # Revalidate live approval before stranding a new reservation.
            authorize_live();verify_unchanged()
            ledger.reserve(row);checkpoint('after_reservation')
            def fetch():
                response=session.get(row['url'],params=row['params'],timeout=30)
                return fetched_type(response.status_code,dict(response.headers),response.text)
            record=raw_cache.get_or_fetch(sport=row['sport'],source=row['source'],data_date=row['requested_utc'][:10],url=row['url'],params=row['params'],fetch=fetch,cache_statuses=tuple(range(100,600)))
            checkpoint('after_transport')
            path=raw_cache.lookup(row['sport'],row['source'],row['cache_key'])
            if path is None:raise ValueError('saved response absent')
            with path.open('rb') as f:os.fsync(f.fileno())
            base.durable_directory(path.parent);checkpoint('after_cache')
            ledger.complete(row,record,path);checkpoint('after_completion')
            completed_here+=1
            if pause_after is not None and completed_here>=pause_after:
                proof=evidence.captured_receipts(ledger.folder,rows,ledger.state,policy)
                if proof['untouched_ids']:
                    verify_unchanged();ledger.state['status']='pilot_clean_pause';ledger.save()
                    return dict(proof,status='pilot_clean_pause',next_stage_authorized=False)
            time.sleep(.25)  # fixed4RPS ceiling; no automatic retry
        proof=evidence.captured_receipts(ledger.folder,rows,ledger.state,policy)
        if proof['untouched_ids']:raise ValueError('terminal scope incomplete')
        verify_unchanged()
        ledger.state['status']='pilot_complete';ledger.save()
        return dict(proof,status='pilot_complete',next_stage_authorized=False)
    except BaseException:
        ledger.halt('Pilot halted; retain reservations; no automatic recovery or resend')
        raise
    finally:session.close()
