"""Hub-only bulk orchestration under the fixed shared lock. Never invoked on import.

No CLI, seed generator, list planner, retries or automatic recovery. Requires a
fully frozen reviewed-for-execution packet and exact live authority. Current draft
packets remain offline/not-ready; this source needs independent execution review.
"""
import fcntl
import json
import os
from pathlib import Path
import capture
import bootstrap
import baseline
import evidence
import authority
import execution
import overlap
import transport
import runner


def remaining_checks(ledger,cap):
    """Budget adds untouched reservations; floor includes unpaid pending exposure."""
    untouched=cap-ledger.reserved()
    if untouched<0:raise ValueError('reserved cost exceeds exact cap')
    pending=0
    for attempt in ledger.state['attempts'].values():
        if attempt['status']=='pending':pending+=attempt['reserved_credits']
        elif attempt['status'] not in {'completed','missing'}:raise ValueError('uncertain exposure state')
    # Existing reserved credits already enter cumulative debit; do not add them twice.
    ledger.budget_check(untouched,check_floor=False)
    # conservative_remaining already deducts completed billing (including counter lag).
    # Only pending+untouched are future costs; terminal unused reservations are not bills.
    exposure=untouched+pending
    if ledger.state['provider_remaining'] is not None and ledger.conservative_remaining()-exposure<ledger.protocol['budgets']['account_reserve_floor']:
        raise ValueError('full pending and untouched purchase would breach reserve')
    return dict(untouched=untouched,pending_unpaid=pending,future_exposure=exposure)


def run(packet_path,root,bundle,auth,*,key_factory,http_factory):
    runner,base,data,source,load=bootstrap.verified(packet_path,root,bundle)
    runner.packet(data,source)
    protocol=json.loads(data['protocol.json'])
    if protocol.get('execution_status')!='reviewed_for_execution':
        raise ValueError('packet is preparation only')
    commit=base.checkout_commit(packet_path);runtime=base.runtime_path(root)
    base.execution_context(packet_path,root,runtime)
    manifest=json.loads(data['manifest.json']);rows=json.loads(data['requests.json']);policy=json.loads(data['policy.json'])
    bindings=json.loads(data['baseline.json']);cache_plan=json.loads(data['overlap.json'])
    # Priority1 is the ledger transport class explicitly bound by the prospective
    # combined-stage amendment; it does not reclassify original older priority2.
    effective=[dict(r,path=r['url'].removeprefix('https://api.the-odds-api.com/v4'),priority=1,max_credits=r['max_new_credits']) for r in rows]
    bridge=dict(manifest,requests=effective,new_credits_by_priority={'1':manifest['max_new_credits']})
    context={'policy_sha256':capture.identity(policy),'plan_sha256':root,
             'global_snapshot_sha256':capture.identity(bindings['expected_global_snapshot']),
             'historical_bindings_sha256':capture.identity(bindings),
             'cache_union_sha256':capture.identity(cache_plan),
             'captured_closure_sha256':capture.identity({n:capture.digest(v) for n,v in data.items() if n.startswith('code/')})}
    def auth_check():authority.check(base,auth,bridge,root,commit,context)
    auth_check()
    if base.current_runtime()!=json.loads(source['runtime-lock.json']):raise ValueError('reviewed runtime differs')
    root_base=base.RUNTIME_BASE
    with (root_base/'followup-purchase.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def source_check():
            _,_,now,shared,_=bootstrap.verified(packet_path,root,bundle)
            if now!=data or shared!=source:raise ValueError('captured packet/source changed')
        source_check();auth_check()
        def base_check(ledgers,markers):
            return baseline.verify_base(ledgers,markers,bindings['base_snapshot'],source['request-manifest.json'],bindings['historical_bindings'])
        # Verify current epoch explicitly; only this exact authorized root can be
        # removed from the predecessor inventory being authenticated below.
        existing=runtime/'spending-ledger.json'
        own_marker=root_base/'registrations'/(root+'.json')
        own_init=runtime/'INITIALIZED.json'
        own_auth=capture.identity(auth)
        def current_check(allow_pending=False, allow_complete=False):
            if not existing.exists():
                if own_marker.exists() or own_init.exists() or any((runtime/'data/raw').rglob('*.parquet')):raise ValueError('lost current epoch ledger/unledgered cache')
                return
            state=capture.read(existing)
            if (capture.read(own_init)!={'bundle_root_sha256':root,'probe_credits':1687}
                    or capture.read(own_marker)!={'bundle_root_sha256':root,'authorization_sha256':own_auth,'runtime_path':str(runtime.resolve())}
                    or state.get('bundle_root_sha256')!=root or state.get('authorization_sha256')!=own_auth
                    or state.get('pilot_plan_sha256')!=root or (state.get('status')=='pilot_complete' and not allow_complete)
                    or state.get('status') not in {'prepared','running','pilot_clean_pause','pilot_complete'}
                    or state.get('stopped') or (state.get('pending') and not allow_pending)
                    or (not allow_pending and state.get('free_account_attempt',{}).get('status') in {'started','received'})):
                raise ValueError('current epoch identity/unresolved/exhausted state differs')
            if not allow_pending:
                evidence.captured_receipts(runtime,effective,state,policy)
                by_id={r['request_id']:r for r in rows}
                expected_cache={runtime/'data/raw'/by_id[rid]['sport']/by_id[rid]['source']/by_id[rid]['requested_utc'][:10]/(by_id[rid]['cache_key']+'.parquet') for rid in state['attempts']}
                if set((runtime/'data/raw').rglob('*.parquet'))!=expected_cache:raise ValueError('unledgered current cache; never repurchase')
        current_check()
        # Global verifier understands the exact active root, never arbitrary exclusions.
        global_snapshot,carry=evidence.global_union(root_base,bindings['base_snapshot'],bindings['pilot_bindings'],base_check,
                                                   active_root=root if existing.exists() else None,active_verifier=current_check)
        if global_snapshot!=bindings['expected_global_snapshot']:raise ValueError('approved global snapshot differs')
        if carry['conservative_debit']!=208106:raise ValueError('exact saved conservative carry changed')
        runner.residual(data,source,load,root_base,global_snapshot)
        retirement=root_base/json.loads(data['recovery/certificate.json'])['source_root']/'authority-timeout-retirement'
        adoption={n:capture.regular(retirement/n) for n in ('certificate.json','approval.json')}
        evidence.authenticate_reuse(root_base,global_snapshot,json.loads(data['mappings.json']),frozen_source={'freeze':data['source/FREEZE.json'],'files':source})
        # Missing/uncertain attempts cannot escape via another grouping or root.
        historical_ids=set()
        for old in global_snapshot['ledgers']:
            historical_ids.update(capture.read(root_base/old/'spending-ledger.json')['attempts'])
        if historical_ids & {r['request_id'] for r in rows}:raise ValueError('prior attempted request ID in new list')
        expected_roots={str((root_base/r/'data/raw').absolute()) for r in global_snapshot['ledgers']}
        expected_roots.add(str((Path.home()/'code/value-finder/sharp-markets/data/raw').absolute()))
        probe=Path(cache_plan['probe_bundle_root'])
        for item in json.loads(source['input-provenance.json'])['raw_probe_sources']:
            suffix=item['path'].removeprefix('local://football-probe-v1/')
            if suffix==item['path'] or capture.sha(probe/suffix)!=item['sha256']:raise ValueError('probe evidence changed')
        expected_roots.add(str((probe/'data/raw').absolute()))
        if set(cache_plan['raw_roots'])!=expected_roots:raise ValueError('complete raw-root inventory required')
        overlap.check(rows,cache_plan['raw_roots'],expected_inventory_sha256=cache_plan['inventory_sha256'])
        auth_check();source_check()
        base.register_runtime(runtime,root,auth)
        ledger=transport.pilot_ledger(base,policy)(runtime,json.loads(data['execution-protocol.json']),bridge,root,auth,json.loads(source['probe-spending-ledger.json']))
        try:
            if ledger.state.get('predecessor_snapshot') not in (None,capture.identity(global_snapshot)):
                raise ValueError('current predecessor changed')
            ledger.state.update(predecessor_snapshot=capture.identity(global_snapshot),pilot_plan_sha256=root)
            ledger.state['other_usage_reserved']=max(ledger.state['other_usage_reserved'],carry['conservative_debit']-1687)
            ledger.save();ledger.budget_check(0)
            # Reserve headroom for ALL remaining calls before accessing a key.
            if 1687+ledger.state['other_usage_reserved']+manifest['max_new_credits']>274686:raise ValueError('full remaining purchase exceeds prospective ceiling')
            def unchanged():
                source_check()
                if any(capture.regular(retirement/n)!=raw for n,raw in adoption.items()):raise ValueError('installed exact retirement changed')
                # Authenticated historical receipts remain pinned by ledger/marker
                # identities; recheck full receipts at completion below.
                expected=set(global_snapshot['ledgers'])|{root}
                if ({p.parent.name for p in root_base.glob('*/spending-ledger.json')}!=expected
                        or {p.stem for p in (root_base/'registrations').glob('*.json')}!=expected
                        or {p.parent.name for p in root_base.glob('*/INITIALIZED.json')}!=expected):
                    raise ValueError('shared inventory changed')
                for old in global_snapshot['ledgers']:
                    if capture.sha(root_base/old/'spending-ledger.json')!=global_snapshot['ledgers'][old] or capture.sha(root_base/'registrations'/(old+'.json'))!=global_snapshot['registrations'][old]:
                        raise ValueError('historical ledger/registration changed')
                current_check(allow_pending=True)
                remaining_checks(ledger,manifest['max_new_credits'])
            unchanged();auth_check()
            if (runtime/'.env').exists():raise ValueError('implicit runtime credential file forbidden')
            os.environ.update(MARKETS_ROOT=str(runtime),MARKETS_DATA_DIR=str(runtime/'data'),MARKETS_REPORTS_DIR=str(runtime/'reports'))
            cachemod=load('archive_markets.cache')
            secret=key_factory()  # first credential access, after all protected checks
            http=http_factory()
            result=execution.prepared_loop(base=base,ledger=ledger,rows=effective,policy=policy,
                raw_cache=cachemod.RawCache(runtime/'data/raw'),fetched_type=cachemod.Fetched,http_session=http,
                authorize_live=auth_check,verify_unchanged=unchanged,credential=secret)
            # Source/old receipt verification after the one-time purchase; no gate release.
            evidence.global_union(root_base,bindings['base_snapshot'],bindings['pilot_bindings'],base_check,
                                  active_root=root,active_verifier=lambda:current_check(allow_complete=True))
            missing=[m['game_id'] for m in json.loads(data['mappings.json']) if m.get('certified_unavailable_request_ids')]
            return dict(result,original_attempted_excluded=12,prior_completed_reused=11,certified_unavailable_request_ids=[json.loads(data['recovery/certificate.json'])['quarantined_request_id']],certified_unavailable_game_ids=missing,original_denominator_sha256=capture.digest(data['denominators.json']),no_new_statistical_look=True)
        except BaseException:
            ledger.halt('Pilot stopped; reservations retained; no automatic retry or recovery')
            raise base.Halt('Pilot stopped; inspect retained local evidence; never retry automatically') from None
        finally:ledger.close()
