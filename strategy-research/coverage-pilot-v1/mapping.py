"""Pure exact request and market-cell mapping; no discovery, fetch or seed draw."""
from collections import defaultdict
from datetime import timedelta
from planner import InvalidPlan, unique, frame_rows
from timing import utc

MARKETS = ('player_pass_yds', 'player_rush_yds', 'player_reception_yds',
           'player_receptions', 'player_field_goals', 'player_kicking_points')
STATES = {'completed', 'absent', 'missing', 'pending', 'uncertain'}


def older_slots(game, originals, close_ids):
    """Pick nearest original daily time to T24, with immutable-ID tie break.

    close_ids is the previously frozen game-to-original-close mapping, not a
    re-created endpoint. Multiple original close candidates remain in exact cost.
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
    for rid in close_ids:
        r = rows[rid]
        if r['sport'] != game['sport'] or not timedelta(minutes=5) <= kickoff-utc(r['requested_utc']) <= timedelta(minutes=20):
            raise InvalidPlan('close mapping outside scheduled proxy')
    candidates = [r for r in rows.values() if r['sport'] == game['sport']
                  and timedelta(hours=18) <= kickoff-utc(r['requested_utc']) <= timedelta(hours=54)]
    if not candidates or not close_ids:
        return {'game_id': game['game_id'], 'request_ids': [], 'reason': 'missing_original_slot'}
    early = min(candidates, key=lambda r: (abs(kickoff-utc(r['requested_utc'])-timedelta(hours=24)),r['request_id']))
    return {'game_id': game['game_id'], 'request_ids': [early['request_id'], *sorted(close_ids)], 'reason': None}


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
