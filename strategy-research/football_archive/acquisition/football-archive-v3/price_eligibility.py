"""Bound quote eligibility; no outcomes, CLV values, stakes or returns are ranked."""
from datetime import datetime, timezone
import hashlib
import json
import math


def timestamp(value):
    if value is None:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timing must include timezone')
    return dt.astimezone(timezone.utc)


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def observation_id(obs):
    return identity({k: obs.get(k) for k in ('source_cache_key','source_body_sha256','provider_id','canonical_game_id','returned_utc','provider_kickoff_utc','team_keys')})


def asof_listing(observations, decision, provider_id, canonical_game_id):
    valid = [o for o in observations if o.get('provider_id') == provider_id
             and o.get('canonical_game_id') == canonical_game_id and timestamp(o['returned_utc']) <= timestamp(decision)]
    if not valid:
        return None, 'missing_asof_exact_listing'
    latest = max(timestamp(o['returned_utc']) for o in valid)
    tied = [o for o in valid if timestamp(o['returned_utc']) == latest]
    signatures = {(o['provider_kickoff_utc'], tuple(o['team_keys'])) for o in tied}
    if len(signatures) != 1:
        return None, 'conflicting_asof_exact_listing'
    return min(tied, key=observation_id), None


def evaluate(protocol, row, catalog, horizon='entry'):
    reasons, metrics = [], {}
    result = {'eligible': False, 'status': 'conflicted_or_ineligible', 'scheduled_pregame_eligible': False,
              'actual_play_certified': False, 'snapshot_pre_actual_play': False,
              'decision_pre_actual_play': False, 'execution_pre_actual_play': False,
              'reasons': reasons, 'metrics': metrics, 'paper_listing_status': 'unresolved'}
    try:
        quote = catalog['quotes'].get(row.get('quote_id'))
        if quote is None:
            reasons.append('unbound_quote_identity'); return result
        # Caller fields cannot replace any source-owned identity, quote or timing field.
        for k, v in quote.items():
            if k in row and row[k] != v:
                reasons.append('quote_source_field_mismatch'); return result
        gid, pid = quote['canonical_game_id'], quote['provider_game_id']
        game = catalog['games'].get(gid)
        if game is None or pid not in game['provider_ids']:
            reasons.append('invalid_provider_canonical_binding'); return result
        requested, returned = timestamp(quote['requested_utc']), timestamp(quote['returned_utc'])
        execution = timestamp(row.get('execution_utc')) or requested
        if execution < requested:
            reasons.append('execution_precedes_decision')
        if execution != requested:
            reasons.append('execution_requires_separately_observed_quote')
        obs, why = asof_listing(catalog['listing_index'].get((pid,gid),[]) if 'listing_index' in catalog else catalog['observations'].values(), requested, pid, gid)
        bound = catalog['observations'].get(quote['observation_id'])
        if why:
            reasons.append(why)
        if bound is None or observation_id(bound) != quote['observation_id']:
            reasons.append('unbound_schedule_observation'); return result
        if obs is not None and (obs['returned_utc'] != bound['returned_utc'] or obs['provider_kickoff_utc'] != bound['provider_kickoff_utc'] or obs['team_keys'] != bound['team_keys']):
            reasons.append('quote_not_bound_to_latest_exact_listing')
        if (bound['provider_id'] != pid or bound['canonical_game_id'] != gid or
            bound['source_body_sha256'] != quote['source_body_sha256'] or
            bound['provider_kickoff_utc'] != quote['provider_kickoff_utc'] or
            bound['returned_utc'] != quote['returned_utc']):
            reasons.append('schedule_quote_source_mismatch')
        provider, independent = timestamp(bound['provider_kickoff_utc']), timestamp(game['scheduled_utc'])
        if timestamp(bound['returned_utc']) > requested:
            reasons.append('future_schedule_observation')
        rules = protocol['price_row_eligibility']
        lag = (requested-returned).total_seconds(); metrics['snapshot_lag_seconds'] = lag
        metrics['provider_gap_over_five_minutes'] = lag > 300
        if not 0 <= lag <= rules['maximum_snapshot_lag_seconds']:
            reasons.append('snapshot_lag_invalid')
        updated = timestamp(quote.get('market_last_update') or quote.get('bookmaker_last_update'))
        if updated is None:
            reasons.append('missing_quote_timestamp')
        else:
            age_snapshot, age_decision = (returned-updated).total_seconds(), (requested-updated).total_seconds()
            metrics.update(quote_age_at_snapshot_seconds=age_snapshot, quote_age_at_decision_seconds=age_decision,
                           quote_timestamp_source='market.last_update' if quote.get('market_last_update') else 'bookmaker.last_update')
            if min(age_snapshot, age_decision) < 0: reasons.append('future_quote_timestamp')
            if age_snapshot > rules['maximum_quote_age_at_snapshot_seconds']: reasons.append('quote_stale_at_snapshot')
            if age_decision > rules['maximum_quote_age_at_requested_decision_seconds']: reasons.append('quote_stale_at_decision')
        if quote['book'] not in protocol['book_panel'] or quote['market'] not in protocol['markets']:
            reasons.append('unexpected_book_or_market')
        teams = set(game['team_keys'])
        side = quote['side']
        if set(bound['team_keys']) != teams or side not in ({'Over','Under'} if quote['market']=='totals' else teams):
            reasons.append('invalid_market_side_or_event_teams')
        price = quote.get('decimal_price')
        if isinstance(price, bool) or not isinstance(price, (int,float)) or not math.isfinite(price) or price <= 1:
            reasons.append('invalid_offered_price')
        if quote['market'] in ('totals','spreads'):
            line = quote.get('line')
            if isinstance(line, bool) or not isinstance(line, (int,float)) or not math.isfinite(line):
                reasons.append('missing_or_invalid_line')
        actual_record = catalog.get('actual_play', {}).get(gid)
        actual = None
        if actual_record is not None:
            if (actual_record.get('canonical_game_id') != gid or actual_record.get('independent') is not True
                or not actual_record.get('source_id')):
                reasons.append('unbound_actual_play_evidence')
            else:
                actual = timestamp(actual_record.get('utc'))
                if actual is None: reasons.append('missing_actual_play_timestamp')
        if horizon=='close' and quote.get('request_id') not in catalog.get('close_request_ids',{}).get(gid,set()):
            reasons.append('not_a_frozen_close_candidate')
        if horizon not in ('entry','close'):
            raise ValueError('Unknown horizon')
        conflict = abs((provider-independent).total_seconds()) > 300
        scheduled_ok = returned < min(provider, independent)
        if horizon == 'entry': scheduled_ok = scheduled_ok and max(requested,execution) < min(provider,independent)
        scheduled_lead = (provider-returned).total_seconds()
        if horizon == 'close': scheduled_ok = scheduled_ok and 300 <= scheduled_lead <= 1200
        result['scheduled_pregame_eligible'] = scheduled_ok and not conflict and not reasons
        metrics['independent_schedule_basis'] = 'retrospective_safety_check'
        metrics['timing_guard_basis'] = 'verified_actual_play' if actual else 'scheduled_proxy'
        lead = ((actual or provider)-returned).total_seconds(); metrics['actual_snapshot_lead_seconds'] = lead
        if actual is not None:
            result.update(snapshot_pre_actual_play=returned<actual, decision_pre_actual_play=requested<actual,
                          execution_pre_actual_play=execution<actual)
            if returned >= actual: reasons.append('snapshot_not_before_actual_play')
            if horizon == 'entry' and requested >= actual: reasons.append('decision_not_before_actual_play')
            if horizon == 'entry' and execution >= actual: reasons.append('execution_not_before_actual_play')
            eventual_delta = abs((actual-provider).total_seconds())
            result['paper_listing_status'] = 'postponed_over_24h_void' if eventual_delta > 86400 else 'within_24h_no_void_inferred'
        else:
            if not scheduled_ok: reasons.append('not_in_scheduled_pregame_window')
            if conflict: reasons.append('unresolved_material_kickoff_conflict')
        if horizon == 'close' and not 300 <= lead <= 1200:
            reasons.append('close_proxy_not_in_valid_pregame_window')
        result['eligible'] = not reasons
        result['actual_play_certified'] = actual is not None and result['eligible']
        result['status'] = ('actual_play_certified' if result['actual_play_certified'] else
                            'scheduled_pregame_eligible' if result['eligible'] else 'conflicted_or_ineligible')
    except (KeyError, ValueError, TypeError, OverflowError):
        reasons.append('invalid_or_missing_source_field')
        result['eligible'] = False
        result['status'] = 'conflicted_or_ineligible'
    return result


def select_close(protocol, candidates, catalog):
    """One partition only; ranking deliberately excludes price, line, CLV and outcomes."""
    diagnostics = [{'row': row, 'eligibility': evaluate(protocol,row,catalog,'close')} for row in candidates]
    keys = {tuple(catalog['quotes'].get(d['row'].get('quote_id'),{}).get(k) for k in ('canonical_game_id','book','market','side')) for d in diagnostics}
    if len(keys) > 1:
        return {'primary': None, 'reason':'mixed_close_partition', 'diagnostics':diagnostics}
    valid = [d for d in diagnostics if d['eligibility']['eligible']]
    if not valid:
        return {'primary':None, 'reason':'missing_eligible_close', 'diagnostics':diagnostics}
    def rank(d):
        q = catalog['quotes'][d['row']['quote_id']]
        updated = timestamp(q.get('market_last_update') or q.get('bookmaker_last_update'))
        return (-timestamp(q['returned_utc']).timestamp(), -updated.timestamp(), q['quote_id'])
    return {'primary':min(valid,key=rank), 'reason':'deterministic_timing_and_freshness', 'diagnostics':diagnostics}


def primary_reference_pair(entry, close):
    return (entry.get('book') == close.get('book') == 'pinnacle'
            and all(entry.get(k) and entry[k] == close.get(k) for k in ('canonical_game_id','market','side'))
            and entry.get('eligibility',{}).get('eligible') is True and close.get('eligibility',{}).get('eligible') is True)
