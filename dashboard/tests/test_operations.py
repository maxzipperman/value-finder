"""Operational truth, overlap, missingness, provenance and read-only boundaries."""
import json
import os
import subprocess
import sys
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from conftest import write, make_store, Clock
from vfdash import operations as op, api, status_md, commands

NOW = datetime(2026, 10, 3, 18, tzinfo=timezone.utc)


def journal(home, root='a'*64, rid='b'*64, status='pilot_complete', attempt='completed', bill=30):
    p = home / 'Library/Application Support/ValueFinder/football-acquisition-state' / root / 'spending-ledger.json'
    d = {'bundle_root_sha256':root, 'status':status, 'attempts':{rid:{'status':attempt, 'reserved_credits':60,
         'billed_credits':bill, 'response_path':'DO_NOT_EXPOSE_PRIVATE_PATH', 'observed_billing_headers':{'apiKey':'DO_NOT_EXPOSE_SECRET'}}},
         'other_usage_reserved':500000, 'cache_reuse':{'c'*64: {'status':'completed'}}, 'probe_credits':1687}
    write(p, json.dumps(d));os.utime(p,(NOW.timestamp(),NOW.timestamp()))
    return p


def test_charges_are_not_reservations_carry_or_reuse(home):
    p = journal(home)
    before = p.read_bytes(), p.stat().st_mtime_ns
    out = op.acquisition(home,NOW,timezone.utc)
    assert out['total']['requests'] == 1 and out['total']['billed'] == 30
    assert out['batches'][0]['reserved'] == 60
    assert 'DO_NOT_EXPOSE' not in json.dumps(out)
    assert before == (p.read_bytes(),p.stat().st_mtime_ns)


def test_duplicate_ids_withhold_aggregate(home):
    journal(home);journal(home,root='c'*64)
    out=op.acquisition(home,NOW,timezone.utc)
    assert out['total'] is None
    assert any('overlap' in s for s in out['notes'])


def test_missing_and_corrupt_are_unknown(home):
    assert op.acquisition(home,NOW,timezone.utc)['total'] is None
    p=journal(home);p.write_text('{')
    assert op.acquisition(home,NOW,timezone.utc)['total'] is None


def test_pending_and_unknown_billing_not_complete_or_zero(home):
    journal(home,attempt='pending',bill=None)
    out=op.acquisition(home,NOW,timezone.utc)
    assert out['total']['unknown_bill']==1 and out['total']['pending']==1
    assert out['batches'][0]['state']=='unconfirmed'


def test_invalid_amount_withholds_totals(home):
    p=journal(home);d=json.loads(p.read_text());d['attempts']['b'*64]['reserved_credits']=-5;p.write_text(json.dumps(d))
    assert op.acquisition(home,NOW,timezone.utc)['total'] is None


def test_future_journal_withholds_totals(home):
    p=journal(home);os.utime(p,(NOW.timestamp()+3600,)*2)
    out=op.acquisition(home,NOW,timezone.utc)
    assert out['total'] is None and out['freshness']['state']=='future'


def test_symlinks_and_size_limit(home,tmp_path,monkeypatch):
    p=journal(home);target=tmp_path/'private.env';target.write_text('DO_NOT_READ')
    p.unlink();p.symlink_to(target)
    assert op.acquisition(home,NOW,timezone.utc)['total'] is None
    p.unlink();journal(home)
    monkeypatch.setattr(op,'MAX_BYTES',4)
    assert op.acquisition(home,NOW,timezone.utc)['total'] is None


def test_old_documents_do_not_become_fresh_after_checkout(tmp_path):
    p=tmp_path/'QUEUE.md';p.write_text('Updated October 1, 2026\n')
    os.utime(p,(NOW.timestamp(),)*2)
    _,fresh=op.document(p,'Plan',NOW,timezone.utc)
    assert fresh['state']=='stale'
    assert op.freshness('missing',None,NOW,timezone.utc)['state']=='unknown'


def test_owner_actions_classified_only():
    text='## Waiting on you\n1. **[resolved] Backup.** Waived.\n2. **[reference] Installed.** Done.\n3. **[open] Choose plan.** Due Oct 20, 2026.\n4. **[review] Old deadline.** Due Oct 1, 2026.\n5. **Unclassified.** Unknown.\n'
    rows,unknown=op.owner_actions(text,NOW,timezone.utc)
    assert [r['title'] for r in rows]==['Choose plan','Old deadline','Unclassified'] and unknown==1
    assert rows[-1]['action_state']=='review'
    assert rows[1]['due_level']=='warn' and rows[1]['due_iso'] is None


def test_queue_only_adopted_status_table():
    text='## Paid data — sole current queue\n| Order | State / next action | Maximum new credits / authority |\n|---|---|---|\n| 1 | Finish actual successor | 66480 total cap, not remaining |\n| Held | CFB groups held | No bulk release |\n## Other\n| 2 | Wrong | Ignore |'
    rows=op.queue_rows(text)
    assert len(rows)==2 and rows[1]['state']=='blocked' and rows[0]['state']=='queued'
    assert 'not remaining' in rows[0]['cap']
    assert op.queue_rows('## Purchase sequence\n| Next | Old plan | 100 | Stale |')==[]


def test_later_variant_setup_not_silently_lost():
    assert status_md.variants('- **Variants:** old **288**.\n- Setup: adds **6 committed variants**, 288 + 6 = **294**.')==294


def test_seven_jobs_no_collector_success_from_exit_zero(root,home):
    store=make_store(root,home)
    snap=store.snapshot()
    for lbl in commands.JOB_LABELS[4:]:
        snap.launchctl.listed[lbl]={'pid':None,'status':0}
    rows=api.jobs(api.Screen(store))
    assert len(rows)==7
    assert all('Collection success is unverified' in j['result'] for j in rows[4:])
    assert all(j['level']=='warn' for j in rows[4:])


def test_nba_start_is_read_from_config(root,home):
    write(root/'sharp-markets/config/sports/nba.yaml','collector:\n  start: 2026-10-20 # from config\n  every_min: 5\n')
    store=make_store(root,home);snap=store.snapshot()
    snap.launchctl.listed['com.valuefinder.nbacollector']={'pid':None,'status':0}
    j=api.jobs(api.Screen(store))[-1]
    assert j['level']=='ok' and 'no collections expected yet' in j['result']


def test_operations_root_separate_from_live_data(root,home,tmp_path):
    review=tmp_path/'review';write(review/'STATUS.md','## Waiting on you\n1. **[open] Real decision.** Decide this.\n')
    store=make_store(root,home);store.cfg.operations_root=review
    d=api.home(store)
    assert d['waiting'][0]['title']=='Real decision'
    assert d['numbers']['games_on_board']==8


def test_rendered_downloads_and_home_order(root,home,tmp_path):
    from test_signals import draw, text
    journal(home)
    store=make_store(root,home,clock=Clock(NOW))
    page=text(draw(tmp_path,'#downloads',api.pull(store)))
    assert 'Downloads' in page and 'Recorded charges' in page and 'Plan and usable coverage' in page
    assert 'Thursday' not in page
    page=text(draw(tmp_path,'#home',api.home(store)))
    assert page.index('Needs attention') < page.index('Download progress') < page.index('signals are live') < page.index('Research progress')


def test_running_is_reported_not_confirmed(home):
    journal(home,status='running')
    row=op.acquisition(home,NOW,timezone.utc)['batches'][0]
    assert row['state']=='running (reported; liveness unverified)'


def test_bad_identity_and_many_batches_withhold_total(home,monkeypatch):
    p=journal(home);d=json.loads(p.read_text());d['bundle_root_sha256']='x';p.write_text(json.dumps(d))
    assert op.acquisition(home,NOW,timezone.utc)['total'] is None
    journal(home);journal(home,root='c'*64,rid='d'*64)
    monkeypatch.setattr(op,'MAX_BATCHES',1)
    assert op.acquisition(home,NOW,timezone.utc)['total'] is None


def test_newer_journal_flags_plan_and_updates_header(root,home):
    journal(home)
    write(root/op.QUEUE,'Updated October 2, 2026\n\n## Paid data — sole current queue\n| Order | State / next action | Maximum new credits / authority |\n|---|---|---|\n| 1 | Props | 60; Held |\n')
    store=make_store(root,home,clock=Clock(NOW))
    data=api.pull(store)
    assert data['operations']['plan_freshness']['state']=='stale'
    assert data['header']['last_written'].startswith('Last acquisition record')
    assert 'nothing recorded' not in data['header']['last_written']


ADOPTED = Path(__file__).parent / 'fixtures/status-adopted-11474c6.md'


def test_real_adopted_status_keeps_every_current_choice(root,home):
    text = ADOPTED.read_text()
    write(root/'STATUS.md',text)
    # A historical plan must never override the adopted queue.
    write(root/'sharp-markets/docs/OCTOBER_2026_QUEUE.md','## Purchase sequence\n| Next | WRONG HISTORICAL | 999 | Wrong |')
    store=make_store(root,home,clock=Clock(NOW));data=api.home(store)
    assert [x['n'] for x in data['waiting']]==[0,2,4,8,11]
    assert all(x['action_state']=='review' for x in data['waiting'])
    assert data['variants']==294
    queue=data['operations']['queue']
    assert len(queue)==4 and queue[-1]['state']=='blocked'
    assert 'finish or reconcile' in queue[0]['name']
    assert 'not a fresh remaining balance' in queue[0]['cap']
    assert 'CFB2021–22' in queue[-1]['name'] and 'own gates' in queue[-1]['name']
    assert data['operations']['queue_source']=='STATUS.md'
    assert data['operations']['queue_url'].endswith('STATUS.md#paid-data--sole-current-queue')
    assert 'WRONG HISTORICAL' not in json.dumps(data)


def test_mixed_resolved_history_retains_explicit_child_decisions():
    text = """## Waiting on you
0. **[resolved] Backup and current plan.** Waived and purchased.
   - **[open] Credit reset date.** Confirm the date, not a new purchase.
   - **[open] Post-month plan.** Choose by October 25; no automatic renewal.
7. **[reference] Earlier review.** Historical results only.
   - **[review] Future paper-to-money discussion.** Paper-only remains in force; no betting authority.
"""
    rows,unknown=op.owner_actions(text,NOW,timezone.utc)
    assert [r['n'] for r in rows]==['0.1','0.2','7.1'] and unknown==0
    assert [r['title'] for r in rows]==['Credit reset date','Post-month plan','Future paper-to-money discussion']
    assert 'no betting authority' in rows[-1]['detail']


def test_current_source_split_choices_and_paper_only():
    text=(Path(__file__).resolve().parents[2]/'STATUS.md').read_text()
    rows,_=op.owner_actions(text,NOW,timezone.utc)
    ids={x['n']:x for x in rows}
    assert {0,2,4,8,11,12,13} <= set(ids)
    assert 'reset date' in ids[0]['title'].lower()
    assert ids[12]['action_state']=='open' and 'no renewal' in ids[12]['detail'].lower()
    assert ids[13]['action_state']=='review' and 'project remains paper-only' in ids[13]['detail']


def test_fifo_journal_returns_without_writer(tmp_path):
    path=tmp_path.resolve()/'spending-ledger.json'
    os.mkfifo(path)
    script='from pathlib import Path; from vfdash.operations import bounded; import sys; r=bounded(Path(sys.argv[1])); assert r.data is None and "Nonregular" in r.note'
    subprocess.run([sys.executable,'-B','-c',script,str(path)],check=True,timeout=2)


def test_replaced_fifo_at_open_is_still_nonblocking(tmp_path):
    path=tmp_path.resolve()/'spending-ledger.json';path.write_text('{}')
    script="""from pathlib import Path
import os,sys
from vfdash import operations as op
p=Path(sys.argv[1]);original=op.os.open
def swapped(path,flags):
    assert flags & os.O_NONBLOCK and flags & os.O_NOFOLLOW
    p.unlink();os.mkfifo(p)
    return original(path,flags)
op.os.open=swapped
r=op.bounded(p)
assert r.data is None and 'Nonregular' in r.note
"""
    subprocess.run([sys.executable,'-B','-c',script,str(path)],check=True,timeout=2)


def test_directory_and_socket_are_not_read(tmp_path):
    import socket
    folder=tmp_path.resolve()
    assert op.bounded(folder).data is None
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        # Short path avoids macOS AF_UNIX path-length limit in pytest folders.
        import tempfile
        with tempfile.TemporaryDirectory(dir='/tmp') as d:
            p=Path(d).resolve()/'s';sock.bind(str(p))
            assert op.bounded(p).data is None


@pytest.mark.parametrize('state', ['event_epoch_complete', 'pilot_complete',
    'recent_complete_stopped_before_older', 'older_epoch_complete', 'metadata_complete'])
@pytest.mark.parametrize('attempt,expected', [('completed', 'completed'), ('missing', 'completed'), ('pending', 'unconfirmed')])
def test_emitted_terminal_states_preserve_missing_and_pending(home, state, attempt, expected):
    journal(home, status=state, attempt=attempt)
    row = op.acquisition(home, NOW, timezone.utc)['batches'][0]
    assert row['state'] == expected
    assert row['recorded_state'] == state
    assert row[attempt] == 1
    assert row['completed'] == int(attempt == 'completed')


@pytest.mark.parametrize('state', ['older_epoch_complete', 'metadata_complete'])
def test_new_terminal_states_with_top_level_pending_remain_unconfirmed(home, state):
    p = journal(home, status=state)
    data = json.loads(p.read_text()); data['pending'] = ['b'*64]
    p.write_text(json.dumps(data))
    assert op.acquisition(home, NOW, timezone.utc)['batches'][0]['state'] == 'unconfirmed'


def test_nba_run_log_metadata_visible_without_collection_success(root, home):
    p = root / 'sharp-markets/data/collector/nba/runs.csv'
    write(p, 'PRIVATE_BODY_NOT_PARSED')
    os.utime(p, (NOW.timestamp(), NOW.timestamp()))
    store = make_store(root, home, clock=Clock(NOW))
    store.snapshot().launchctl.listed['com.valuefinder.nbacollector'] = {'pid':None, 'status':0}
    row = api.jobs(api.Screen(store))[-1]
    assert op.collector_outputs(root)['com.valuefinder.nbacollector'] == NOW.timestamp()
    assert 'Last output file update: Not verified' not in row['result']
    assert 'Collection success is unverified' in row['result'] and row['level'] == 'warn'
    assert not row['running'] and 'PRIVATE_BODY' not in json.dumps(row)
    p.unlink()
    assert op.collector_outputs(root)['com.valuefinder.nbacollector'] is None
    target = root / 'private-log'; write(target, 'private')
    p.symlink_to(target)
    assert op.collector_outputs(root)['com.valuefinder.nbacollector'] is None


def receipt(home, name='propslog', **changes):
    d = dict(version=1,label='com.valuefinder.'+name,recorded_utc='2026-10-03T18:00:00Z',
             state='collected',last_attempt_utc='2026-10-03T17:59:00Z',
             last_success_utc='2026-10-03T17:59:00Z',next_expected_utc=None,
             missed_windows=None,window_start_utc=None,window_end_utc=None)
    d.update(changes)
    p = home/'Library/Application Support/ValueFinder/collector-status'/f'{name}.json'
    write(p,json.dumps(d))
    return p


def test_deployment_pending_has_owner_and_action():
    d=op.collector_display('com.valuefinder.propslog',False,False,None,{'available':False})
    assert d['state']=='deployment_pending' and d['owner']=='Hub'
    assert '/pull/125' in d['tracking_url'] and 'first eligible' in d['next_action']


def test_future_nba_not_an_attention_failure_but_still_needs_installation():
    d=op.collector_display('com.valuefinder.nbacollector',False,False,None,{},'2026-10-20')
    assert d['state']=='scheduled' and not d['attention'] and d['level']=='ok'
    assert 'not loaded' in d['text'] and 'before 2026-10-20' in d['next_action']


def test_launchctl_unknown_or_failure_not_hidden_by_future_start_or_receipt():
    d=op.collector_display('com.valuefinder.nbacollector',None,False,None,{},'2026-10-20')
    assert d['state']=='process_unknown' and d['attention']
    d=op.collector_display('com.valuefinder.nbacollector',True,False,1,{'available':True,'state':'collected'},'2026-10-20')
    assert d['state']=='process_failed' and d['level']=='fail'


def test_collection_receipts_report_success_and_unknown_misses_separately(home):
    p=receipt(home);before=p.read_bytes(),p.stat().st_mtime_ns
    r=op.collector_receipts(home,NOW)['com.valuefinder.propslog']
    assert r['available'] and r['state']=='collected' and r['missed_windows'] is None
    assert before==(p.read_bytes(),p.stat().st_mtime_ns)
    d=op.collector_display('com.valuefinder.propslog',True,False,0,r)
    assert 'reports a successful' in d['text']
    assert op.collector_display('com.valuefinder.propslog',False,False,None,r)['state']=='deployment_pending'


@pytest.mark.parametrize('changes',[
    {'version':True}, {'label':'com.valuefinder.triggerpoll'}, {'state':'other'},
    {'recorded_utc':'2026-10-03T19:00:00Z'}, {'recorded_utc':'2026-10-03'},
    {'last_success_utc':'2026-10-03T18:01:00Z'}, {'last_attempt_utc':None},
    {'missed_windows':0}, {'missed_windows':True}, {'missed_windows':-1},
    {'window_start_utc':'2026-10-03T17:00:00Z'},
    {'state':'collected','last_success_utc':None}, {'private_key':'DO_NOT_EXPOSE'},
])
def test_invalid_collection_receipt_is_unknown(home,changes):
    receipt(home,**changes)
    r=op.collector_receipts(home,NOW)['com.valuefinder.propslog']
    assert not r['available'] and 'DO_NOT_EXPOSE' not in json.dumps(r)


def test_collection_receipt_bounded_no_links_duplicate_fields_or_pipes(home,tmp_path):
    p=receipt(home)
    p.write_text('{"version":1,"version":1}')
    assert not op.collector_receipts(home,NOW)['com.valuefinder.propslog']['available']
    p.write_text(' '*16385)
    assert not op.collector_receipts(home,NOW)['com.valuefinder.propslog']['available']
    p.unlink();target=tmp_path/'private.env';target.write_text('DO_NOT_READ');p.symlink_to(target)
    assert not op.collector_receipts(home,NOW)['com.valuefinder.propslog']['available']
    p.unlink();os.mkfifo(p)
    assert not op.collector_receipts(home,NOW)['com.valuefinder.propslog']['available']


def test_stale_receipt_not_current_success_and_misses_have_window(home):
    receipt(home,recorded_utc='2026-10-03T16:00:00Z',last_attempt_utc='2026-10-03T15:59:00Z',last_success_utc='2026-10-03T15:59:00Z')
    r=op.collector_receipts(home,NOW)['com.valuefinder.propslog']
    assert r['stale']
    assert op.collector_display('com.valuefinder.propslog',True,False,0,r)['state']=='collection_unverified'
    receipt(home,missed_windows=2,window_start_utc='2026-10-02T18:00:00Z',window_end_utc='2026-10-03T18:00:00Z')
    r=op.collector_receipts(home,NOW)['com.valuefinder.propslog']
    assert r['missed_windows']==2
    d=op.collector_display('com.valuefinder.propslog',True,False,0,r)
    assert d['attention'] and d['level']=='warn'


def test_explicit_disable_never_runs_or_reuses_scorers(root,home):
    from vfdash.data import Scored
    store=make_store(root,home)
    store.cfg.disable_scorers=True
    store._scores['nfl-weather']=Scored('nfl-weather','ok',text='old cached result',ran_at=store.clock())
    def forbidden(*a,**kw):
        raise AssertionError('Scorer execution forbidden')
    store._run=forbidden
    for project in ('nfl-weather','cfb-weather'):
        assert store.scorer(project).status=='disabled'
        assert store.scorer(project,wait=False).status=='disabled'
        assert store._score(project).status=='disabled'


def test_render_actionable_status_and_disabled_mode(root,home,tmp_path):
    from test_signals import draw,text
    store=make_store(root,home,clock=Clock(NOW));store.cfg.disable_scorers=True
    data=api.home(store)
    rendered=text(draw(tmp_path,'#home',data))
    assert 'Scoring disabled for this dashboard' in rendered
    assert 'Owner: Hub' in rendered and 'Next action:' in rendered
    assert 'Missed windows: Unknown' in rendered and 'Last successful collection: Not verified' in rendered
    assert 'Dashboard version and status source' in rendered


def test_deployment_record_binds_status_without_paths_or_false_freshness(root,home,tmp_path):
    import hashlib
    store=make_store(root,home);store.cfg.content=tmp_path/'release/dashboard/content'
    status='Updated October 3, 2026\n'
    p=tmp_path/'release/DEPLOYMENT.json'
    d=dict(version=1,commit='a'*40,deployed_utc='2026-10-03T17:00:00Z',status_sha256=hashlib.sha256(status.encode()).hexdigest())
    write(p,json.dumps(d))
    result=op.deployment_provenance(store.cfg,status,NOW)
    assert result['available'] and result['status_matches'] and '/'+ 'a'*40+'/' in result['source_url']
    result=op.deployment_provenance(store.cfg,status+'changed',NOW)
    assert not result['status_matches'] and result['source_url'] is None
    d['commit']='javascript:DO_NOT_EXPOSE';write(p,json.dumps(d))
    assert not op.deployment_provenance(store.cfg,status,NOW)['available']


@pytest.mark.parametrize('state,expected_level', [
    ('failed', 'fail'), ('blocked', 'warn'), ('waiting', 'warn'), ('collected', 'warn'),
])
def test_reported_misses_preserve_failure_severity_and_recovery_action(home,state,expected_level):
    label = 'com.valuefinder.propslog'
    receipt(home,state=state,missed_windows=0,
            window_start_utc='2026-10-02T18:00:00Z',window_end_utc='2026-10-03T18:00:00Z')
    baseline_receipt = op.collector_receipts(home,NOW)[label]
    assert baseline_receipt['available'] and not baseline_receipt['stale']
    baseline = op.collector_display(label,True,False,0,baseline_receipt)
    receipt(home,state=state,missed_windows=2,
            window_start_utc='2026-10-02T18:00:00Z',window_end_utc='2026-10-03T18:00:00Z')
    parsed = op.collector_receipts(home,NOW)[label]
    assert parsed['available'] and parsed['missed_windows'] == 2
    display = op.collector_display(label,True,False,0,parsed)
    assert display['state'] == state and display['level'] == expected_level
    assert display['attention']
    assert baseline['next_action'] in display['next_action']
    assert 'Reconcile the reported missed windows' in display['next_action']
    if state == 'failed':
        assert 'Resolve the collection failure' in display['next_action']
