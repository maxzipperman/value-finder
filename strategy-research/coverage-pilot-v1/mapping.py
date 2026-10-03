"""Pure exact request and market-cell mapping; no discovery, fetch or seed draw."""
from collections import defaultdict
from datetime import timedelta
from planner import InvalidPlan, unique, frame_rows
from timing import utc

MARKETS = ('player_pass_yds', 'player_rush_yds', 'player_reception_yds',
           'player_receptions', 'player_field_goals', 'player_kicking_points')
STATES = {'completed', 'absent', 'missing', 'pending', 'uncertain'}


def early_rank(row, kickoff):
    # Source/window admissibility is enforced by older_slots before this rank.
    at = utc(row['requested_utc'])
    return (abs(kickoff-at-timedelta(hours=24)), at, row['request_id'])


def older_slots(game, originals, close_ids, *, primary_close_id, include_diagnostics=False, primary_close_anchor=None):
    """Pick nearest original daily time to T24, with immutable-ID tie break.

    close_ids is the frozen game-to-original-close map. primary_close_id must be
    its provider-anchor close. Other closes remain diagnostic, purchased only with
    the separately frozen include_diagnostics flag and included in the exact cap.
    Unbound or missing early/close emits a zero row, never drops the game.
    """
    rows = unique(originals, 'request_id')
    if game['season'] not in (2020, 2021, 2022):
        raise InvalidPlan('older season required')
    if not game['binding']:
        return {'game_id': game['game_id'], 'request_ids': [], 'reason': 'unbound'}
    kickoff = utc(game['scheduled_utc'])
    if len(close_ids) != len(set(close_ids)) or any(r not in rows for r in close_ids):
        raise InvalidPlan('unknown/duplicate original close')
    close_anchor=utc(primary_close_anchor) if primary_close_anchor is not None else kickoff
    for rid in close_ids:
        r = rows[rid]
        anchor=close_anchor if rid==primary_close_id else kickoff
        if r['sport'] != game['sport'] or not timedelta(minutes=5) <= anchor-utc(r['requested_utc']) <= timedelta(minutes=20):
            raise InvalidPlan('close mapping outside scheduled proxy')
    if (primary_close_id not in close_ids or 'pregame_close_proxy' not in rows[primary_close_id].get('purposes',[])):
        raise InvalidPlan('frozen provider-anchor primary close required')
    candidates = [r for r in rows.values() if r['sport'] == game['sport']
                  and 'daily_16UTC' in r.get('purposes',[])
                  and (utc(r['requested_utc']).hour,utc(r['requested_utc']).minute,utc(r['requested_utc']).second)==(16,0,0)
                  and timedelta(hours=18) <= kickoff-utc(r['requested_utc']) <= timedelta(hours=54)]
    if not candidates or not close_ids:
        return {'game_id': game['game_id'], 'request_ids': [], 'reason': 'missing_original_slot'}
    early = min(candidates, key=lambda r: early_rank(r,kickoff))
    primary=[early['request_id'],primary_close_id]
    diagnostic=sorted(set(close_ids)-{primary_close_id})
    return {'game_id':game['game_id'],'request_ids':primary+(diagnostic if include_diagnostics else []),
            'primary_request_ids':primary,'diagnostic_request_ids':diagnostic,
            'diagnostics_in_purchase':include_diagnostics,'reason':None}


def original_union(frame, selected, mappings, originals, attempted, reused):
    from planner import residual
    games = unique(frame_rows(frame), 'game_id'); mapping = unique(mappings, 'game_id')
    if len(selected) != len(set(selected)) or not set(selected) <= games.keys() or set(mapping) != set(selected):
        raise InvalidPlan('selected denominator mapping differs')
    all_rows = unique(originals, 'request_id')
    mapped = set()
    for gid in selected:
        row = mapping[gid]; ids = row['request_ids']
        if games[gid]['classification'] != 'unknown':
            raise InvalidPlan('known game cannot enter unknown sample')
        if len(ids) != len(set(ids)) or not set(ids) <= all_rows.keys():
            raise InvalidPlan('duplicate/unknown original mapping')
        if (not ids) != bool(row['reason']):
            raise InvalidPlan('explicit no-request reason required')
        if ids and not games[gid]['binding']:
            raise InvalidPlan('unbound purchase')
        mapped.update(ids)
    # Validate history against complete original universe, not just selected subset.
    status = residual([dict(r, max_credits=r['max_new_credits']) for r in originals], attempted, reused)
    untouched = {r['request_id'] for r in status['requests']}
    paid = [all_rows[rid] for rid in sorted(mapped & untouched)]
    return {'requests': paid, 'max_new_credits': sum(r['max_new_credits'] for r in paid),
            'selected_denominator': len(selected), 'full_denominator': len(games),
            'mappings': mappings, 'reused_or_attempted': sorted(mapped - untouched),
            'blocked': status['blocked']}


def cell(sport, event_id, at, book, market):
    return (sport, event_id, utc(at).isoformat(), book, market)


def props_union(opportunities, history, make_request):
    """Build only unattempted six-market cells using captured reviewed constructor.

    history must be authenticated compatible requests (decimal/ISO, same provider
    identity and exact historical time). Requested-but-absent cells count as tried.
    Caller supplies selected opportunities AND zero/no-request rows; not outcomes.
    """
    ops = unique(opportunities, 'opportunity_id')
    prior = {}
    for item in history:
        key = tuple(item['cell'])
        if len(key) != 5 or item['status'] not in STATES or key in prior:
            raise InvalidPlan('ambiguous cell history')
        prior[key] = item['status']
    requests = {}; mappings = []; blocked = False; planned = {}
    for oid, op in sorted(ops.items()):
        if op['season'] not in (2023,2024,2025) or op['sport'] not in ('americanfootball_nfl','americanfootball_ncaaf'):
            raise InvalidPlan('props historical scope required')
        if op['slot'] not in ('T24','CLOSE_T10'):
            raise InvalidPlan('primary slots only')
        if op.get('no_request_reason'):
            mappings.append({'opportunity_id': oid, 'request_ids': [], 'reason': op['no_request_reason']})
            continue
        if not op['event_id'] or not op['books'] or len(set(op['books'])) != len(op['books']):
            raise InvalidPlan('explicit unique books and event required')
        if any(not isinstance(b,str) or not b for b in op['books']):
            raise InvalidPlan('invalid book')
        groups = defaultdict(list); ids = set()
        for market in MARKETS:
            remaining = []
            for book in sorted(op['books']):
                key = cell(op['sport'],op['event_id'],op['requested_utc'],book,market)
                state = prior.get(key)
                if state in {'pending','uncertain'}: blocked = True
                if key in planned: ids.add(planned[key])
                elif state is None: remaining.append(book)
            if remaining: groups[tuple(remaining)].append(market)
        for books, markets in sorted(groups.items()):
            r = make_request('odds',utc(op['requested_utc']),books=books,markets=markets,event_id=op['event_id'],sport=op['sport'])
            if utc(r['requested_utc']) != utc(op['requested_utc']):
                raise InvalidPlan('constructor rounded selected time')
            rid = r['request_id']
            if rid in requests and requests[rid] != r: raise InvalidPlan('conflicting request identity')
            requests[rid] = r; ids.add(rid)
            for market in markets:
                for book in books:
                    planned[cell(op['sport'],op['event_id'],op['requested_utc'],book,market)] = rid
        mappings.append({'opportunity_id':oid,'request_ids':sorted(ids),'reason':'all_cells_previously_attempted' if not ids else None})
    return {'requests':[requests[k] for k in sorted(requests)],'mappings':mappings,
            'opportunity_denominator':len(ops),'blocked':blocked,
            'max_new_credits':sum(r['max_new_credits'] for r in requests.values())}


def selected_availability(opportunities, attempted_ids, make_request):
    """Finite selected slots only; never substitutes full-season discovery."""
    ops=unique(opportunities,'opportunity_id');rows={};mappings=[]
    for oid,op in sorted(ops.items()):
        if op['season'] not in (2023,2024,2025) or op['slot'] not in ('T24','CLOSE_T10'):
            raise InvalidPlan('selected primary availability only')
        if op.get('no_request_reason'):
            mappings.append({'opportunity_id':oid,'request_ids':[],'reason':op['no_request_reason']});continue
        row=make_request('markets',utc(op['requested_utc']),event_id=op['event_id'],sport=op['sport'])
        if utc(row['requested_utc'])!=utc(op['requested_utc']):raise InvalidPlan('availability rounded time')
        rid=row['request_id']
        if rid in attempted_ids:
            mappings.append({'opportunity_id':oid,'request_ids':[],'reason':'prior_metadata_attempt','prior_request_id':rid})
        else:
            rows[rid]=row;mappings.append({'opportunity_id':oid,'request_ids':[rid],'reason':None})
    return {'requests':[rows[k] for k in sorted(rows)],'mappings':mappings,
            'max_new_credits':len(rows),'opportunity_denominator':len(ops)}


def older_metadata_disposition(game,slots):
    """Frozen known-clock veto; source bindings must be authenticated upstream.

    Whole paired game is a failure if either original slot is known ineligible.
    Selection/frame stays unchanged; no replacement and no quote inspection.
    """
    independent=utc(game['scheduled_utc']);reasons=[]
    for name in ('EARLY','CLOSE'):
        slot=slots[name];decision=utc(slot['requested_utc']);binding=slot['binding']
        provider=utc(binding['provider_kickoff_utc'])
        if utc(binding['returned_utc'])>decision:reasons.append(name+':binding_after_decision')
        if abs(provider-independent)>timedelta(minutes=5):reasons.append(name+':provider_independent_conflict')
        if decision>=min(provider,independent):reasons.append(name+':not_strictly_pregame')
        if name=='EARLY' and not timedelta(hours=18)<=independent-decision<=timedelta(hours=54):
            reasons.append(name+':outside_early_horizon')
        if name=='CLOSE' and not timedelta(minutes=5)<=provider-decision<=timedelta(minutes=20):
            reasons.append(name+':outside_provider_close_proxy')
    return {'classification':'failure' if reasons else 'unknown','reasons':sorted(set(reasons))}
