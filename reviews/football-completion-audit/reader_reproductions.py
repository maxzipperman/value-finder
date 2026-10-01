"""Synthetic-only reproductions against the real reader; no outcome model or scoring."""
import sys,json
from pathlib import Path
from collections import Counter
from datetime import date

def guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Network forbidden')
    if event=='open' and isinstance(args[0],(str,bytes)):
        s=str(args[0])
        if Path(s).name.startswith('.env') or '/data/forward/' in s or s.endswith(('games.parquet','scores.parquet','pricing_cohort.json')):raise RuntimeError('Data/credential read forbidden')
sys.addaudithook(guard)
import dotenv
dotenv.load_dotenv=lambda *a,**kw:False
import pandas as pd
from markets.research.price_engine import quotes,engine,handoff
NFL='americanfootball_nfl'
cfg={'sports':{NFL:{'windows':[{'from':date(2024,1,1),'to':date(2024,12,31),'label':'2024','sealed':False}]}}}
def rows(eid,snap,kick,home='H',away='A',market='totals',upd=None):
    names=('Over','Under') if market=='totals' else (home,away)
    return [{'sport':NFL,'odds_event_id':eid,'snapshot_ts':snap,'commence_time':kick,'home_team':home,'away_team':away,'bookmaker':'draftkings','market_key':market,'market_last_update':upd or snap,'book_last_update':upd or snap,'outcome_name':n,'point':44.5 if market=='totals' else None,'price_decimal':1.91} for n in names]
def load(batch):
    old=quotes.bulk.load_rows
    try:
        quotes.bulk.load_rows=lambda *a,**k:batch
        return quotes.load_quotes(cfg,[object()],None)[0]
    finally:quotes.bulk.load_rows=old
v=next(v for v in engine.VARIANTS if v.sport==NFL and v.market=='totals' and v.primary)
def entries(q):
    return engine.entries(q.assign(side='under',dec=1.91,ev_pinnacle=.03,ev_blend=.03,pin_line=44.5),v)
early=rows('e','2024-09-01T16:00:00Z','2024-09-09T16:00:00Z')
late=rows('e','2024-09-02T16:00:00Z','2024-09-07T16:00:00Z')
base=load(early);revised=load(early+late);e=entries(revised)
assert base.empty and str(e.iloc[0]['snap'])=='2024-09-01 16:00:00+00:00'
# Known safety guard passes: a later delay cannot admit a quote inside the original one-hour cutoff.
guard_q=load(rows('e','2024-09-08T16:30:00Z','2024-09-08T17:00:00Z')+rows('e','2024-09-08T18:00:00Z','2024-09-08T20:00:00Z'))
assert not (entries(guard_q)['snap']==pd.Timestamp('2024-09-08T16:30:00Z')).any()
q=load(rows('swap','2024-09-07T16:00:00Z','2024-09-08T19:00:00Z',market='h2h')+rows('swap','2024-09-08T18:55:00Z','2024-09-08T19:00:00Z',home='A',away='H',market='h2h'))
c=engine.closes(q);assert q.iloc[0]['home']=='H' and q.iloc[-1]['home']=='A' and c.iloc[0]['c_snap']==q.iloc[-1]['snap']
assert 'home' not in c.columns
dup=load(rows('id1','2024-09-07T16:00:00Z','2024-09-08T19:00:00Z')+rows('id2','2024-09-07T16:00:00Z','2024-09-08T19:00:00Z'));assert len(entries(dup))==2
stale=load(rows('stale','2024-09-07T16:00:00Z','2024-09-08T19:00:00Z',upd='2024-09-06T16:00:00Z'));assert len(entries(stale))==1
try:handoff._check_registered('4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d')
except handoff.HandoffRefused:registration_refused=True
else:registration_refused=False
assert registration_refused
out={'synthetic_checks':6,'later_kickoff_delay_cutoff_guard':'passes','later_earlier_kickoff_admits_previously_outside_7_day_row':{'baseline_rows':len(base),'revised_first_entry':str(e.iloc[0]['snap']),'decision_time_lead_days':8,'latest_kickoff_lead_days':6},'home_away_swap_retained':{'entry_home':'H','close_home':'A','rows_retained':len(q)},'duplicate_ids_for_same_teams_and_kickoff':{'entries':len(entries(dup))},'24_hour_old_quote_retained':{'entries':len(entries(stale))},'unregistered_handoff_refused':registration_refused,'trial_count_in_engine':engine.RUNNING_COUNT,'variants':len(engine.VARIANTS),'primary_variants':sum(v.primary for v in engine.VARIANTS)}
print(json.dumps(out,indent=2))
