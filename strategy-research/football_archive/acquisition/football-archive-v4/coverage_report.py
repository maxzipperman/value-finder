"""Outcome-blind coverage with explicit intended-slot and provider-opportunity denominators."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from price_eligibility import observation_id,identity,evaluate,select_close,timestamp


def make_catalog(bundle):
    bundle=Path(bundle)
    games=json.loads((bundle/'canonical-games.json').read_text())
    obs=json.loads((bundle/'provider-observations.json').read_text())
    catalog={'games':{g['canonical_game_id']:g for g in games},'observations':{observation_id(o):o for o in obs},'quotes':{},'actual_play':{}}
    catalog['close_request_ids']=defaultdict(set)
    for link in json.loads((bundle/'close-candidates.json').read_text()):catalog['close_request_ids'][link['canonical_game_id']].add(link['request_id'])
    catalog['listing_index']=defaultdict(list)
    for o in obs:catalog['listing_index'][(o['provider_id'],o.get('canonical_game_id'))].append(o)
    return catalog


def normalize_response(catalog,row,record,aliases):
    body=json.loads(record['body']);body_hash=hashlib.sha256(record['body'].encode()).hexdigest()
    pid_games=defaultdict(set)
    for gid,g in catalog['games'].items():
        for pid in g['provider_ids']:pid_games[(g['sport'],pid)].add(gid)
    event_status=[];quote_ids=[]
    for event in body['data']:
        kick=timestamp(event.get('commence_time'));season=kick.year if kick.month>=7 else kick.year-1
        if season not in range(2020,2026):
            event_status.append({'provider_id':event['id'],'status':'outside_registered_seasons','season':season});continue
        ids=pid_games.get((row['sport'],event['id']),set());gid=next(iter(ids)) if len(ids)==1 else None
        team_keys=[aliases.get((row['sport'],event.get(k))) for k in ('home_team','away_team')]
        status='bound_canonical_listing' if gid and None not in team_keys else 'unmatched_or_unknown_returned_listing'
        event_status.append({'provider_id':event['id'],'status':status,'canonical_game_id':gid,'season':season,
                             'provider_kickoff_utc':event.get('commence_time'),'requested_utc':row['requested_utc']})
        if status!='bound_canonical_listing':continue
        obs={'provider_id':event['id'],'canonical_game_id':gid,'sport':row['sport'],'season':season,
             'returned_utc':body['timestamp'],'provider_kickoff_utc':event['commence_time'],
             'team_keys':team_keys,'source_cache_key':row['cache_key'],'source_body_sha256':body_hash}
        oid=observation_id(obs);catalog['observations'][oid]=obs
        catalog.setdefault('listing_index',defaultdict(list))[(event['id'],gid)].append(obs)
        for bi,book in enumerate(event.get('bookmakers',[])):
            for mi,market in enumerate(book.get('markets',[])):
                for oi,outcome in enumerate(market.get('outcomes',[])):
                    side=outcome.get('name') if market['key']=='totals' else aliases.get((row['sport'],outcome.get('name')))
                    q={'canonical_game_id':gid,'provider_game_id':event['id'],'book':book['key'],'market':market['key'],'side':side,
                       'line':outcome.get('point'),'decimal_price':outcome.get('price'),'requested_utc':row['requested_utc'],
                       'returned_utc':body['timestamp'],'provider_kickoff_utc':event['commence_time'],
                       'market_last_update':market.get('last_update'),'bookmaker_last_update':book.get('last_update'),
                       'observation_id':oid,'source_body_sha256':body_hash,'source_cache_key':row['cache_key'],'request_id':row['request_id'],
                       'outcome_index':[bi,mi,oi]}
                    q['quote_id']=identity(q);catalog['quotes'][q['quote_id']]=q;quote_ids.append(q['quote_id'])
    return event_status,quote_ids


def build_report(bundle,runtime,read_record):
    bundle,runtime=Path(bundle),Path(runtime);manifest=json.loads((bundle/'request-manifest.json').read_text())
    ledger=json.loads((runtime/'spending-ledger.json').read_text());catalog=make_catalog(bundle)
    cfg=json.loads((bundle/'protocol.json').read_text())
    aliases={(a['sport'],a['provider_name']):a['canonical_team_key'] for a in json.loads((bundle/'aliases.json').read_text())}
    intended,events,quote_quality,strata=[],[],Counter(),defaultdict(Counter)
    all_grades={}; raw_quote_ages=[]
    source_rows={};close_requests=defaultdict(set)
    for c in json.loads((bundle/'close-candidates.json').read_text()):close_requests[c['canonical_game_id']].add(c['request_id'])
    for r in manifest['requests']:
        if r['priority']!=1:continue
        path=bundle/r['cache_source'] if r['max_new_credits']==0 else Path(ledger['attempts'][r['request_id']]['response_path'])
        rec=read_record(path);event_status,ids=normalize_response(catalog,r,rec,aliases);events.extend(event_status);source_rows[r['request_id']]=(r,ids)
    # Evaluate after collecting responses so equal-timestamp conflicts remain visible.
    eligible_entries=defaultdict(list);close_candidates=defaultdict(list)
    for rid,(r,ids) in source_rows.items():
        present=Counter((catalog['quotes'][qid]['canonical_game_id'],catalog['quotes'][qid]['book'],catalog['quotes'][qid]['market']) for qid in ids)
        # Empty MOS canonical targets remain instrument/slot denominators, not invented forecast-game counts.
        targets=r['canonical_game_ids'] or [None]
        for gid in targets:
            for book in cfg['book_panel']:
                for market in ('h2h','spreads','totals'):
                    count=present[(gid,book,market)] if gid else sum(v for (g,b,m),v in present.items() if b==book and m==market)
                    intended.append({'request_id':rid,'canonical_game_id':gid,'book':book,'market':market,
                       'request_purposes':r['purposes'],'population':'intended_canonical_game' if gid else 'MOS_slot_instrument_not_inferred_game_cohort',
                       'status':'quote_present' if count else 'missing_quote','outcomes_present':count})
        for qid in ids:
            q=catalog['quotes'][qid];grade=evaluate(cfg,{'quote_id':qid},catalog,'entry')
            key=(q['canonical_game_id'],q['book'],q['market'],q['side'])
            all_grades[qid]=grade
            raw_quote_ages.append({'quote_id':qid,'requested_utc':q['requested_utc'],'metrics':grade['metrics'],'reasons':grade['reasons']})
            if grade['eligible'] and any(p in r['purposes'] for p in ('daily_16UTC','MOS_original_evening_slot_diagnostic')):eligible_entries[key].append({'quote_id':qid,'eligibility':grade})
            if rid in close_requests[q['canonical_game_id']]:close_candidates[key].append({'quote_id':qid})
            quote_quality[grade['status']]+=1
            for why in grade['reasons']:quote_quality[why]+=1
            game=catalog['games'][q['canonical_game_id']];lead=(timestamp(q['provider_kickoff_utc'])-timestamp(q['requested_utc'])).total_seconds()/3600
            lead_bucket='under_24h' if lead<24 else '24_to_72h' if lead<=72 else 'over_72h'
            first_bucket='first_observed_under_48h' if game['first_observed_lead_hours']<48 else 'first_observed_at_least_48h'
            sk='|'.join(map(str,(r['sport'],game['season'],r['requested_utc'][:7],q['book'],q['market'],lead_bucket,first_bucket)))
            strata[sk][grade['status']]+=1
            if grade['metrics'].get('provider_gap_over_five_minutes'):strata[sk]['provider_gap_over_five_minutes']+=1
    close_results=[];pair_records=[]
    for key in sorted(set(close_candidates)|set(eligible_entries),key=str):
        candidates=close_candidates.get(key,[])
        selected=select_close(cfg,candidates,catalog);primary=selected['primary'];close_results.append({'partition':key,'selection':selected})
        for entry in eligible_entries.get(key,[]):
            q=catalog['quotes'][entry['quote_id']]
            if primary and timestamp(catalog['quotes'][primary['row']['quote_id']]['returned_utc'])<timestamp(q['requested_utc']):
                status='close_precedes_entry'
            else:status='valid_entry_close_pair' if primary else 'missing_eligible_close'
            pair_records.append({'entry_quote_id':entry['quote_id'],'partition':key,'status':status,'primary_reference':key[1]=='pinnacle',
                                 'close_quote_id':primary['row']['quote_id'] if primary and status=='valid_entry_close_pair' else None})
    intended_pairs=[]
    pair_by_entry={p['entry_quote_id']:p for p in pair_records}
    quotes_by_request=defaultdict(list)
    for q in catalog['quotes'].values():quotes_by_request[q['request_id']].append(q)
    for item in intended:
        r=source_rows[item['request_id']][0]
        if not any(p in r['purposes'] for p in ('daily_16UTC','MOS_original_evening_slot_diagnostic')):continue
        matches=[q for q in quotes_by_request[item['request_id']] if q['book']==item['book'] and q['market']==item['market'] and
                 (item['canonical_game_id'] is None or q['canonical_game_id']==item['canonical_game_id'])]
        accepted=[q for q in matches if all_grades[q['quote_id']]['eligible']]
        valid_pairs=[pair_by_entry[q['quote_id']] for q in accepted if q['quote_id'] in pair_by_entry and pair_by_entry[q['quote_id']]['status']=='valid_entry_close_pair']
        if item['canonical_game_id'] in catalog['games']:
            g=catalog['games'][item['canonical_game_id']]
            lead=(timestamp(g['scheduled_utc'])-timestamp(r['requested_utc'])).total_seconds()/3600
            lead_bucket='under_24h' if lead<24 else '24_to_72h' if lead<=72 else 'over_72h'
            first_bucket='first_observed_under_48h' if g['first_observed_lead_hours']<48 else 'first_observed_at_least_48h'
            season=g['season']
        else:
            lead_bucket='MOS_slot_only';first_bucket='not_inferred';season=r['seasons'][0]
        sk='|'.join(map(str,(r['sport'],season,r['requested_utc'][:7],item['book'],item['market'],lead_bucket,first_bucket)))
        strata[sk][item['status']]+=1
        strata[sk]['intended_entry_instruments']+=1
        strata[sk]['intended_instruments_with_valid_pair']+=bool(valid_pairs)
        intended_pairs.append({**item,'eligible_entry_outcomes':len(accepted),'valid_pair_outcomes':len(valid_pairs),
          'pair_status':'valid_pair_present' if valid_pairs else 'missing_or_ineligible_entry' if not accepted else 'missing_or_invalid_close',
          'entry_exclusion_reasons':dict(Counter(why for q in matches for why in all_grades[q['quote_id']]['reasons']))})
    registry=json.loads((bundle/'opportunity-registry.json').read_text())
    return {'status':'outcome_blind_recent_coverage_requires_owner_review','bundle_root_sha256':ledger['bundle_root_sha256'],
       'outcomes_joined':False,'all_recent_requests_completed':len(source_rows)==sum(r['priority']==1 for r in manifest['requests']),
       'before_older_slice':{'sport_season_month_book_market_lead_first_observed_strata':{k:dict(v) for k,v in strata.items()},
       'identity_and_opportunity_accounting':Counter(r['status'] for r in registry),'quote_quality_and_exclusions':dict(quote_quality),
       'valid_reference_pairs':sum(p['status']=='valid_entry_close_pair' and p['primary_reference'] for p in pair_records)},
       'alternate_close_plan':json.loads((bundle/'alternate-close-summary.json').read_text()),
       'request_purpose_coverage':[{'request_id':r['request_id'],'purposes':r['purposes'],'canonical_game_ids':r['canonical_game_ids']} for r,_ in source_rows.values()],
       'intended_slot_book_market_accounting':intended,'quote_age_and_exclusion_records':raw_quote_ages,'returned_events_including_unmatched':events,
       'provider_observed_opportunity_registry':registry,'all_quotes_and_eligibility_source_bindings':[{'quote':q,'entry_eligibility':all_grades[qid]} for qid,q in catalog['quotes'].items()],
       'close_diagnostics':close_results,'entry_pair_records':pair_records,'intended_decision_pair_accounting':intended_pairs,
       'limits':['Observed provider universe is incomplete','MOS slot counts are not full live-rule game/decision counts',
                 'Missing actual-play evidence does not certify pre-play','No verified fills or settlement; no profit results',
                 'Quote-level pairs are archive coverage, not a registered strategy cohort']}
