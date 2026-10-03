"""Combined owner $1 reservation guard; private ledgers never returned/published."""
import hashlib
import json
import math
from pathlib import Path

LEDGERS = ('openrouter-paid/billing.json', 'openrouter-paid32k/billing.json', 'openrouter-ceiling/billing.json')
OWNER_CAP = 1.0


def amount(value):
    if isinstance(value, bool):
        raise RuntimeError('invalid reservation')
    n = float(value)
    if not math.isfinite(n) or n < 0:
        raise RuntimeError('invalid reservation')
    return n


def totals(root):
    total = 0.0
    seen = set()
    for name in LEDGERS:
        path = root / name
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for a in data['attempts']:
            identity = (name, a['model'], a['task'])
            if identity in seen:
                raise RuntimeError('duplicate ledger attempt')
            seen.add(identity)
            reserved = amount(a['maximum_estimate_usd'])
            accounted = amount(a['accounted_usd'])
            reported = amount(a.get('reported_usd', 0))
            if accounted < max(reserved, reported):
                raise RuntimeError('under-reserved attempt')
            if a['status'] not in ('reserved', 'completed', 'stopped'):
                raise RuntimeError('unknown attempt status')
            total += accounted
    if total > OWNER_CAP:
        raise RuntimeError('combined owner budget exceeded')
    return total


def reserve_ok(root, next_amount):
    total = totals(root)
    if total + amount(next_amount) > OWNER_CAP:
        raise RuntimeError('combined owner budget exhausted')
    return total


def audited_terminal(root, ledger, folder='openrouter-paid'):
    """Allow distinct missing requests only; never retry an audited failed request."""
    audit_path = root / 'openrouter-error-audit.json'
    audits = json.loads(audit_path.read_text()) if audit_path.exists() else {}
    for attempt in ledger['attempts']:
        if attempt['status'] == 'completed':
            continue
        identity = attempt['model'] + '|' + attempt['task']
        audit = audits.get(identity, {})
        path = root / folder / attempt['model'].replace('/', '--') / (attempt['task'] + '-error.json')
        if attempt['status'] != 'stopped' or not path.exists() or audit.get('continue_distinct_missing_only') is not True or not audit.get('reason'):
            return False
        if audit.get('error_sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
            return False
        if amount(attempt['accounted_usd']) < amount(attempt['maximum_estimate_usd']):
            return False
    return True
