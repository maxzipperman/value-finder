"""Download only free, decision-time Kalshi price inputs for the fixed NBA sample."""
import json,sys,math
from datetime import timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'sharp-markets/src'))
from markets.cache import RawCache
from markets.kalshi.client import KalshiClient
from markets.kalshi.ingest import candle_windows
from markets.settings import parse_ts

def pull():
    assert not (ROOT/'sharp-markets/.env').exists()
    data=json.loads((ROOT/'sharp-markets/data/nba-sample-metadata.json').read_text())
    cache=RawCache(ROOT/'sharp-markets/data/raw');client=KalshiClient('nba',cache,rate_per_sec=4)
    count=windows=markets=0
    for game in data['games']:
        end_limit=parse_ts(game['tip_proxy_utc'])+timedelta(minutes=15)
        for market in game['markets']:
            start=int(parse_ts(market['open_time']).timestamp())//60*60
            end=math.ceil(min(parse_ts(market['close_time']),end_limit).timestamp()/60)*60
            for a,b in candle_windows(start,end,1):
                candles=client.candles(market_ticker=market['ticker'],series_ticker='KXNBAGAME',start_ts=a,end_ts=b,period_min=1,historical=True,data_date='2026-01-'+game['event_ticker'][15:17])
                count+=len(candles);windows+=1
            markets+=1
            if markets%20==0:print(json.dumps({'markets_completed':markets,'cached_price_minutes':count,'paid_calls':0}),flush=True)
    report={'games':len(data['games']),'markets_completed':markets,'price_minutes_cached':count,'windows':windows,'new_free_http_calls':cache.http_requests,'paid_calls':0,'odds_api_credits':0,'strategy_results_computed':False,'game_outcomes_inspected':False,'sealed_2026_27_inspected':False,'use_after_tip':'descriptive_only; entries must be independently pregame'}
    (ROOT/'sharp-markets/data/nba-free-candles.json').write_text(json.dumps(report,sort_keys=True)+'\n');print(json.dumps(report))
if __name__=='__main__':
    try:pull()
    except Exception:raise SystemExit('Free candle pull stopped; cached inputs retained; no Odds API credits spent') from None
