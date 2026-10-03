"""Descriptive cache coverage only: no outcomes, selection or statistical tests."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import pyarrow.parquet as pq
import plan


def pairs(market, book, snapshot, decision):
    grouped = defaultdict(dict)
    reasons = Counter()
    update = market.get('last_update') or book.get('last_update')
    try:
        quote_time = plan.ts(update)
        age_snapshot = (snapshot-quote_time).total_seconds()
        age_decision = (decision-quote_time).total_seconds()
        fresh = 0 <= age_snapshot <= 900 and 0 <= age_decision <= 1500
        if age_snapshot < 0: reasons['future_quote_timestamp'] += 1
        elif not fresh: reasons['stale_quote_timestamp'] += 1
    except (ValueError, TypeError, AttributeError):
        fresh = False
        reasons['missing_or_invalid_quote_timestamp'] += 1
    for outcome in market.get('outcomes', []):
        if outcome.get('name') not in ('Over', 'Under'):
            reasons['non_OU_selection'] += 1
            continue
        try:
            point = Decimal(str(outcome['point']))
            price = Decimal(str(outcome['price']))
            if not point.is_finite() or not price.is_finite() or price <= 1:
                raise ValueError('Invalid line/decimal odds')
        except (InvalidOperation, KeyError, ValueError):
            reasons['invalid_line_or_price'] += 1
            continue
        player = outcome.get('description')
        if not isinstance(player, str) or not player.strip():
            reasons['missing_player_label'] += 1
            continue
        key = (player.strip(), str(point.normalize()))
        side = outcome['name']
        if side in grouped[key]:
            reasons['duplicate_side'] += 1
            grouped[key][side] = None
        else:
            grouped[key][side] = price
    complete = sum(set(sides) == {'Over','Under'} and all(v is not None for v in sides.values()) for sides in grouped.values())
    return {'OU_pairs': complete, 'fresh_OU_pairs': complete if fresh else 0,
            'incomplete_or_duplicate_pairs': len(grouped)-complete, 'reasons': dict(reasons)}


def report(inventory, requests):
    by_key = {(r['event_id'],r['requested_utc']):r for r in requests}
    result = defaultdict(Counter)
    reasons = Counter()
    seen = set()
    for e in inventory['entries']:
        if e['sport'] != plan.NFL or e['status'] != 'verified_completed':
            continue
        key=(e['event_id'],e['requested_utc'])
        if key not in by_key or key in seen:
            raise ValueError('Coverage input outside exact F3a request set or duplicate')
        seen.add(key)
        row=by_key[key]
        if row['seasons'] != [2025]:raise ValueError('Only unsealed 2025 F3a coverage permitted')
        slot=row['opportunities'][0].rsplit('/',1)[-1]
        if slot not in ('T24','CLOSE_T10'):raise ValueError('Unexpected decision slot')
        path=Path(e['cache_source'])
        if plan.sha(path) != e['cache_sha256']:raise ValueError('Coverage cache changed')
        record=pq.read_table(path).to_pylist()[0]
        body=json.loads(record['body']);snapshot=plan.ts(body['timestamp']);decision=plan.ts(e['requested_utc'])
        books={b['key']:b for b in body['data'].get('bookmakers',[])}
        for book in e['books']:
            market_by_key={m['key']:m for m in books.get(book,{}).get('markets',[])}
            for market in e['requested_markets']:
                dest=result[slot,book,market]
                dest['requested_event_slots']+=1
                if book not in books:dest['book_absent_event_slots']+=1
                elif market not in market_by_key:dest['market_absent_event_slots']+=1
                else:
                    dest['market_present_event_slots']+=1
                    stats=pairs(market_by_key[market],books[book],snapshot,decision)
                    dest['OU_pairs']+=stats['OU_pairs'];dest['fresh_OU_pairs']+=stats['fresh_OU_pairs']
                    dest['incomplete_or_duplicate_pairs']+=stats['incomplete_or_duplicate_pairs']
                    if stats['fresh_OU_pairs']:dest['event_slots_with_fresh_pair']+=1
                    for reason,n in stats['reasons'].items():dest[reason]+=n;reasons[reason]+=n
    if len(seen) != len(requests):raise ValueError('Full F3a denominator not retained')
    return {'scope':'570 F3a 2025 NFL requested event/time snapshots; no player-games coverage denominator inferred',
            'outcomes_joined':False,'variants_tested':0,'sealed_quote_reads':False,'request_count':len(seen),
            'rows':[dict(slot=s,book=b,market=m,**v) for (s,b,m),v in sorted(result.items())],
            'reasons':dict(reasons),
            'limitations':['name/stat/settlement mapping not validated','fresh pairs are quote coverage, not verified fills',
                          'fixed book choice and registered player-game denominator belong to separate analysis repair']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--requests',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.write_bytes(plan.canonical(report(json.loads(a.inventory.read_text()),json.loads(a.requests.read_text())))+b'\n')
