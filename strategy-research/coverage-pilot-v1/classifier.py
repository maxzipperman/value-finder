"""Prospective outcome-blind quote feasibility; no outcomes or settlement claims.

Inputs are authenticated metadata and response bodies from the receipt adapter.
No alternate snapshot search, closing-provider substitution or first-play claim.
"""
from collections import defaultdict
from datetime import timedelta
from math import isfinite
from timing import utc, scheduled_guard

CORE={'player_pass_yds','player_rush_yds','player_reception_yds','player_receptions'}


def bind_asof(observations, game_id, decision):
    """Latest snapshot across ALL aliases for this game, never latest per alias."""
    at=utc(decision)
    seen=[o for o in observations if o.get('canonical_game_id')==game_id and utc(o['returned_utc'])<=at]
    if not seen:return {'status':'unbound','reason':'no_asof_observation'}
    newest=max(utc(o['returned_utc']) for o in seen)
    latest=[o for o in seen if utc(o['returned_utc'])==newest]
    identities={(o['provider_id'],utc(o['provider_kickoff_utc']),o['home_team'],o['away_team']) for o in latest}
    if len(identities)!=1:return {'status':'unbound','reason':'conflicting_latest_snapshot'}
    eid,kick,home,away=next(iter(identities))
    if not eid or not home or not away or home==away:return {'status':'unbound','reason':'invalid_identity'}
    aliases={o.get('canonical_game_id') for o in observations if o['provider_id']==eid and o.get('canonical_game_id')}
    if aliases!={game_id}:return {'status':'unbound','reason':'provider_id_conflict'}
    if at>=kick:return {'status':'unbound','reason':'decision_not_before_asof_kickoff'}
    return {'status':'bound','event_id':eid,'provider_kickoff_utc':kick.isoformat(),
            'binding_observed_utc':newest.isoformat(),'home_team':home,'away_team':away,
            'stale_alias_count':len({o['provider_id'] for o in seen if utc(o['returned_utc'])<newest}-{eid})}


def finite(value):
    return type(value) in (int,float) and isfinite(value)


def slot_pairs(body, *, requested, execution, binding, independent_kickoff,
               slot, candidate_books, markets):
    """Two-sided same-point quote keys at this fixed slot, plus reason counts.

    A key is (market, book, exact provider-player label, point). No cross-book
    sides or different-point Over/Under pairs are synthesized. Featured totals
    use the fixed label '__total__'; props retain exact nonempty description.
    """
    reasons=[]
    if binding.get('status')!='bound':return {'pairs':set(),'reasons':['unbound_slot']}
    payload=body.get('data');events=payload if isinstance(payload,list) else [payload]
    found=[e for e in events if isinstance(e,dict) and e.get('id')==binding['event_id']]
    if len(found)!=1:return {'pairs':set(),'reasons':['missing_or_duplicate_event']}
    event=found[0]
    try:
        snapshot=utc(body['timestamp']);decision=utc(requested)
        provider=utc(binding['provider_kickoff_utc']);response=utc(event['commence_time']);independent=utc(independent_kickoff)
        if utc(binding['binding_observed_utc'])>decision:reasons.append('binding_after_decision')
        if not utc(body['previous_timestamp'])<snapshot<utc(body['next_timestamp']):reasons.append('snapshot_neighbors')
        if not 0<=(decision-snapshot).total_seconds()<=600:reasons.append('snapshot_lag')
        if max(provider,response,independent)-min(provider,response,independent)>timedelta(minutes=5):
            reasons.append('kickoff_conflict')
        horizon=(min(provider,response,independent)-decision).total_seconds()
        if slot=='T24' and not 24*3600-300<=horizon<=24*3600+600:
            reasons.append('outside_T24_horizon')
        if slot=='EARLY_18_54' and not 18*3600<=(independent-decision).total_seconds()<=54*3600:
            reasons.append('outside_early_horizon')
        if slot=='CLOSE_T10' and not 300<=(provider-snapshot).total_seconds()<=1200:reasons.append('outside_close_proxy')
        if slot not in ('T24','EARLY_18_54','CLOSE_T10'):reasons.append('unsupported_slot')
        if (event.get('home_team'),event.get('away_team'))!=(binding['home_team'],binding['away_team']):reasons.append('team_orientation_conflict')
        guard=scheduled_guard(base_eligible=not reasons,requested=requested,returned=body['timestamp'],execution=execution,
                              provider_kickoffs=[binding['provider_kickoff_utc'],event['commence_time']],independent_kickoffs=[independent_kickoff])
        reasons.extend(guard['reasons'])
    except (KeyError,ValueError,TypeError,OverflowError):reasons.append('missing_or_invalid_schedule_clock')
    if reasons:return {'pairs':set(),'reasons':sorted(set(reasons))}
    sides=defaultdict(set)
    for book in event.get('bookmakers',[]):
        if book['key'] not in candidate_books:continue
        for market in book.get('markets',[]):
            if market['key'] not in markets:continue
            try:
                updated=utc(market.get('last_update') or book.get('last_update'))
                if not 0<=(snapshot-updated).total_seconds()<=900 or not 0<=(decision-updated).total_seconds()<=1500:
                    reasons.append('quote_age');continue
            except (ValueError,TypeError):reasons.append('missing_quote_clock');continue
            for out in market.get('outcomes',[]):
                player='__total__' if market['key']=='totals' else out.get('description')
                if not isinstance(player,str) or not player or not finite(out.get('point')) or not finite(out.get('price')) or out['price']<=1 or out.get('name') not in ('Over','Under'):
                    reasons.append('invalid_quote');continue
                sides[(market['key'],book['key'],player,out['point'])].add(out['name'])
    return {'pairs':{k for k,s in sides.items() if s=={'Over','Under'}},'reasons':sorted(set(reasons))}


def props_feasibility(early, close):
    """Book/player may differ BETWEEN families, never within a paired family."""
    left={k[:3] for k in early['pairs']};right={k[:3] for k in close['pairs']}
    families={k[0] for k in left & right if k[0] in CORE}
    same_point={k[0] for k in early['pairs'] & close['pairs'] if k[0] in CORE}
    return {'success':len(families)>=2,'paired_families':sorted(families),
            'same_point_success':len(same_point)>=2,'grading_enabled':False,
            'timing_basis':'scheduled_proxy','actual_play_certified':False}


def older_totals_feasibility(early,close,domestic_books,reference='pinnacle'):
    """Fixed primary totals: same domestic book at both slots AND reference both.
    Different points remain paired quote feasibility, not simple same-line CLV.
    """
    left={k[1] for k in early['pairs'] if k[0]=='totals'}
    right={k[1] for k in close['pairs'] if k[0]=='totals'}
    paired=left & right & set(domestic_books)
    ref=reference in left and reference in right
    exact={k[1] for k in early['pairs'] & close['pairs'] if k[0]=='totals'}
    return {'success':bool(paired) and ref,'paired_books':sorted(paired),'reference_both':ref,
            'same_point_success':bool(exact & set(domestic_books)) and reference in exact,
            'timing_basis':'scheduled_proxy','actual_play_certified':False,'grading_enabled':False}
