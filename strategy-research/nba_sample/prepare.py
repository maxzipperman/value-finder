"""Free outcome-blind NBA sample metadata; never loads Odds API credentials or outcomes."""
from collections import defaultdict
from datetime import datetime,timedelta,timezone
import hashlib,json
from pathlib import Path
import re,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sharp-markets/src'))
from markets.cache import RawCache
from markets.kalshi.client import KalshiClient
from markets.oddsapi.schedule import plan_snapshots
from markets.settings import parse_ts

def prepare():
    assert not (ROOT/'sharp-markets/.env').exists(), 'No credentials permitted in this prep checkout'
    cache=RawCache(ROOT/'sharp-markets/data/raw')
    client=KalshiClient('nba',cache)
    rows=client._paginate('/historical/markets','markets',{'series_ticker':'KXNBAGAME','limit':1000},source='kalshi_markets_hist',data_date='2026-10-02',key_extra={'as_of':'nba-sample-2026-10-02'},max_pages=20)
    grouped=defaultdict(list)
    wanted=re.compile(r'^KXNBAGAME-26JAN(0[5-9]|1[01])[A-Z]+$')
    fields=('event_ticker','ticker','title','open_time','close_time','expected_expiration_time')
    for raw in rows:
        ticker=raw.get('event_ticker','')
        if wanted.fullmatch(ticker):
            grouped[ticker].append({k:raw.get(k) for k in fields})
    games=[];problems=[]
    for event,markets in sorted(grouped.items()):
        exp={m['expected_expiration_time'] for m in markets};opened={m['open_time'] for m in markets}
        if len(markets)!=2 or None in exp or None in opened or len(exp)!=1:
            problems.append({'event_ticker':event,'reason':'missing_or_ambiguous_timing_or_market_pair'})
            continue
        tip=parse_ts(next(iter(exp)))-timedelta(hours=3)
        op=min(parse_ts(x) for x in opened)
        games.append({'event_ticker':event,'tip_proxy_utc':tip.isoformat(),'open_utc':op.isoformat(),'markets':markets})
    times=plan_snapshots([(parse_ts(g['tip_proxy_utc']),parse_ts(g['open_utc'])) for g in games],'A')
    out={'scope':'NBA2025-26; Jan5-11,2026ET; scheduleA','games':games,'problems':problems,'requested_utc':[x.isoformat() for x in times],'snapshot_count':len(times),'unreconciled_credit_upper_bound':10*len(times),'bookmakers':['pinnacle','lowvig','betonlineag'],'markets':'h2h','actual_play_certified':False,'outcomes_inspected':False,'sealed_2026_27_inspected':False,'paid_calls':0,'free_http_calls':cache.http_requests,'settlement_based_exclusions':False,'eligible_for_paid_execution':False}
    (ROOT/'sharp-markets/data').mkdir(exist_ok=True)
    target=ROOT/'sharp-markets/data/nba-sample-metadata.json';target.write_text(json.dumps(out,sort_keys=True,separators=(',',':'))+'\n')
    print(json.dumps({'games':len(games),'problems':len(problems),'snapshots':len(times),'unreconciled_credits':10*len(times),'free_http_calls':cache.http_requests,'paid_calls':0,'metadata_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))

if __name__=='__main__':
    try:prepare()
    except Exception:raise SystemExit('NBA free metadata preparation stopped; no paid call made') from None
