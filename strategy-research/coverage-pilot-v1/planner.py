"""Pure prospective planning primitives. No I/O, randomness, authority or sends.

Inputs to inventory validation must come from authenticated captured validators;
this module checks set/accounting invariants, not receipt authenticity.
"""
import hashlib
import json


class InvalidPlan(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def unique(rows, key):
    result = {}
    for row in rows:
        identity = row[key]
        if not isinstance(identity, str) or not identity or identity in result:
            raise InvalidPlan('empty or duplicate identity')
        result[identity] = row
    return result


def frame_rows(rows):
    """Retain every intended game, including unbound zero-usability rows."""
    indexed = unique(rows, 'game_id')
    for row in indexed.values():
        if row['season'] not in range(2020, 2026):
            raise InvalidPlan('season outside historical scope')
        if row['classification'] not in {'success', 'failure', 'unknown'}:
            raise InvalidPlan('unknown classification')
        if not row['binding'] and row['classification'] != 'failure':
            raise InvalidPlan('unbound game must remain a zero row')
        if not isinstance(row['stratum'], str) or not row['stratum']:
            raise InvalidPlan('missing stratum')
    return [indexed[k] for k in sorted(indexed)]


def select(rows, record, sizes, *, committed_frame, committed_protocol, committed_seed_record):
    """Replay an externally committed seed; never generate or replace one."""
    if digest(record) != committed_seed_record:
        raise InvalidPlan("seed record changed")
    frame = frame_rows(rows)
    if digest(frame) != committed_frame or record['frame'] != committed_frame:
        raise InvalidPlan('frame changed')
    if record['protocol'] != committed_protocol or not committed_protocol:
        raise InvalidPlan('protocol changed')
    seed = record['seed']
    if not isinstance(seed, str) or len(seed) != 64 or any(c not in '0123456789abcdef' for c in seed):
        raise InvalidPlan('expected committed 256-bit seed')
    strata = {r['stratum'] for r in frame}
    if set(sizes) != strata:
        raise InvalidPlan('incomplete stratum allocation')
    selected = []
    for stratum in sorted(strata):
        n = sizes[stratum]
        if type(n) is not int or n < 0:
            raise InvalidPlan('invalid sample size')
        pool = [r for r in frame if r['stratum'] == stratum and r['classification'] == 'unknown']
        if n > len(pool):
            raise InvalidPlan('sample exceeds unknown frame')
        pool.sort(key=lambda r: (digest([seed, stratum, r['game_id']]), r['game_id']))
        selected.extend(r['game_id'] for r in pool[:n])
    return {'frame': committed_frame, 'protocol': committed_protocol,
            'seed_record': digest(record), 'selected': selected,
            'denominator': len(frame), 'no_request': [r['game_id'] for r in frame if not r['binding']]}


def residual(original, attempted, reused):
    """Remove ALL attempted original IDs; pending/uncertain never become retries."""
    requests = unique(original, 'request_id')
    attempts = unique(attempted, 'request_id')
    reuse = list(reused)
    if len(set(reuse)) != len(reuse) or not (set(attempts) | set(reuse)) <= requests.keys():
        raise InvalidPlan('unknown or duplicate reuse/attempt')
    if set(attempts) & set(reuse):
        raise InvalidPlan('attempt/reuse overlap')
    statuses = {'completed', 'missing', 'pending', 'uncertain'}
    if any(a['status'] not in statuses for a in attempts.values()):
        raise InvalidPlan('unrecognized attempt status')
    remaining = [requests[k] for k in sorted(requests.keys() - attempts.keys() - set(reuse))]
    for r in requests.values():
        if type(r['max_credits']) is not int or r['max_credits'] <= 0:
            raise InvalidPlan('invalid credit reservation')
    return {'requests': remaining, 'max_credits': sum(r['max_credits'] for r in remaining),
            'denominator': len(requests), 'blocked': any(a['status'] in {'pending', 'uncertain'} for a in attempts.values())}


def inventory(base, epochs, observed, *, carried, ceiling):
    """Validate a prospective chain over an already authenticated baseline.

base maps root to ledger digest. Each epoch binds the entire predecessor inventory,
its own ledger digest, and conservative incremental debit (not just billed usage).
Raw receipts and historical certificates MUST be verified by the caller first.
"""
    expected = dict(base)
    if not expected or type(carried) is not int or carried < 0 or type(ceiling) is not int:
        raise InvalidPlan('invalid baseline accounting')
    total = carried
    for epoch in epochs:
        if epoch['root'] in expected or epoch['predecessor'] != digest(expected):
            raise InvalidPlan('duplicate or forked epoch')
        debit = epoch['reserved_debit']
        if type(debit) is not int or debit < 0:
            raise InvalidPlan('invalid retained debit')
        total += debit
        expected[epoch['root']] = epoch['ledger']
    if observed != expected:
        raise InvalidPlan('missing, changed or unrecognized store')
    if total > ceiling:
        raise InvalidPlan('cumulative ceiling exceeded')
    return {'inventory': digest(expected), 'conservative_debit': total}
