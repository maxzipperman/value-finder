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


def audited_terminal(root, ledger, folder='openrouter-paid', audit_file='openrouter-error-audit.json'):
    """Allow distinct missing requests only; never retry an audited failed request."""
    audit_path = root / audit_file
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


DEFERRAL_HASH = "17c6b7e3baa74fe28c5ed91c59efe9b1288d7818f908edf76810bdba318b03ff"

def deferral(root):
    raw=(root/'openrouter-provider-deferral.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DEFERRAL_HASH:
        raise RuntimeError('provider deferral changed; review required')
    d=json.loads(raw)
    original=(root/'openrouter-requests.json').read_bytes()
    if hashlib.sha256(original).hexdigest()!=d['original_list_sha256'] or d['selected_models']!=['xiaomi/mimo-v2.6-flash']:
        raise RuntimeError('subset is not matched baseline')
    return d

def baseline_terminal(root,ledger):
    if not audited_terminal(root,ledger):
        return False
    planned=[x for x in json.loads((root/'openrouter-requests.json').read_text())['requests'] if x['model']!='stealth/space-bunny-alpha']
    attempted={(a['model'],a['task']) for a in ledger['attempts']}
    deferred={(x['model'],x['task']) for x in deferral(root)['deferred']}
    for item in planned:
        if (item['model'],item['task']) not in attempted|deferred:
            return False
    return attempted.isdisjoint(deferred) and len(attempted)+len(deferred)==21


CEILING_DEFERRAL_HASH = '20ec745611149b9b68d21e064005a29bd579aa86ed71c56691ebbbf9b35795c7'

def ceiling_deferral(root):
    raw=(root/'ceiling-provider-deferral.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CEILING_DEFERRAL_HASH:
        raise RuntimeError('ceiling deferral changed; review required')
    d=json.loads(raw)
    original=(root/'ceiling-api-requests.json').read_bytes()
    audit=(root/'ceiling-error-audit.json').read_bytes()
    if hashlib.sha256(original).hexdigest()!=d['original_list_sha256'] or hashlib.sha256(audit).hexdigest()!=d['error_audit_sha256'] or d['selected_models']!=['xiaomi/mimo-v2.6-flash']:
        raise RuntimeError('ceiling subset/audit changed')
    selected=[x for x in json.loads(original)['requests'] if x['model'] in d['selected_models']]
    hashes=[hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest() for x in selected]
    if len(selected)!=3 or hashes!=d['selected_request_sha256']:
        raise RuntimeError('ceiling subset does not match frozen requests')
    return d
