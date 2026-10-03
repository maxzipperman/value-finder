"""Disabled N0 successor execution helpers. No runtime/authority/HTTP initialization.

Pure checks are infrastructure, not authentication or adoption. Production factory
always blocks. The account bridge remains separately owned and unimplemented here.
"""
import copy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Protocol
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"execution-v1"))
import successor151

ACCOUNT_JOURNAL = Path.home() / 'Library/Application Support/ValueFinder/shared-account-state/journal.json'
PURCHASE_LOCK = Path.home() / 'Library/Application Support/ValueFinder/football-acquisition-state/followup-purchase.lock'
CEILING = 400000
CAP = 7540
SOURCE_PROTOCOL_SHA = '3e120d7216412b9dfbf1ae993c07ca5be6a5ca2b7d3219544805323af93b3568'
PROSPECTIVE_PROTOCOL_SHA = '90de30457eff9a1eafb15ba11cb62341861549eeafb9cb76b33a86ab936dc10d'
LINEAGE_SHA = '61f0c1cc6f53b68c52eaa535b43eef4bf9a88e077255b419bf34e98e8ae124e0'
LIST_SHA = 'b9232db3a473992a88c04640ff579d9a834ab7f61c723cd9032b73b7f115c7e5'
SET_SHA = 'b4894a5b1b837372d0a5aa7e649abe49b79840b5b6f1ef4836233c192a51a6a5'

class Held(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',', ':'),ensure_ascii=False,allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hash64(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
        raise ValueError('Full SHA256 required')
    return value


def prospective_protocol(source_bytes):
    """Derive ONLY an unadopted one-field amendment from exact immutable bytes."""
    if sha(source_bytes) != SOURCE_PROTOCOL_SHA:
        raise ValueError('Frozen source protocol changed')
    original = json.loads(source_bytes)
    result = copy.deepcopy(original)
    if (original['budgets']['first_tranche_cumulative_credits'] != 250000
            or original['budgets']['day_one_cumulative_ceiling'] != 400000
            or original['budgets']['broader_cumulative_ceiling'] != 4440000
            or original['budgets']['account_reserve_floor'] != 531630
            or original['budgets']['automatic_retries'] != 0):
        raise ValueError('Unexpected original budget contract')
    result['budgets']['first_tranche_cumulative_credits'] = CEILING
    return {'source_sha256':SOURCE_PROTOCOL_SHA,'protocol':result,'protocol_sha256':sha(canonical(result)),
            'adopted':False,'paid_execution_enabled':False}


@dataclass(frozen=True)
class Plan:
    """Captured-plan identity only: constructors confer no approval/admission."""
    root: str
    source_commit: str
    csv_sha256: str
    request_set_sha256: str
    prospective_protocol_sha256: str
    lineage_pins_sha256: str
    authorization_sha256: str
    def validate(self):
        for value in (self.root,self.csv_sha256,self.request_set_sha256,self.prospective_protocol_sha256,
                      self.lineage_pins_sha256,self.authorization_sha256):hash64(value)
        if not re.fullmatch('[0-9a-f]{40}',self.source_commit):raise ValueError('Exact source commit required')
        if (self.csv_sha256 != LIST_SHA or self.request_set_sha256 != SET_SHA
                or self.prospective_protocol_sha256 != PROSPECTIVE_PROTOCOL_SHA
                or self.lineage_pins_sha256 != LINEAGE_SHA):
            raise ValueError('Exact unchanged N0 candidate required')
        return sha(canonical(self.__dict__))


@dataclass(frozen=True)
class HistoricalRequest:
    plan_identity_sha256: str
    plan_root: str
    request_id: str
    url: str
    public_params_json: str
    maximum_credits: int


def historical_request(plan, row):
    """Explicit frozen historical10 bound; never use live market/book cost formula."""
    identity=plan.validate()
    public=row['params']
    if (set(public) != {'bookmakers','markets','oddsFormat','dateFormat','date'}
            or public['bookmakers'] != 'pinnacle,lowvig,betonlineag' or public['markets'] != 'h2h'
            or public['oddsFormat'] != 'decimal' or public['dateFormat'] != 'iso'
            or row['path'] != '/historical/sports/basketball_nba/odds'
            or row['sport'] != 'nba' or row['source'] != 'oddsapi_hist'
            or row['requested_utc'] != public['date']
            or type(row['max_new_credits']) is not int or row['max_new_credits'] != 10
            or type(row['max_credits']) is not int or row['max_credits'] != 10
            or row['retry_allowance'] != 0 or row['sealed'] is not False):
        raise ValueError('Request differs from exact historical contract')
    url='https://api.the-odds-api.com/v4'+row['path']
    rid=sha(canonical({'source':'oddsapi_hist','url':url,'params':public}))
    if row['request_id'] != rid:raise ValueError('Stable request identity changed')
    # Whole-set membership must be established by factory before admission.
    return HistoricalRequest(identity,plan.root,rid,url,canonical(public).decode(),10)


def exact_requests(plan, rows):
    if len(rows) != 754 or sha(canonical(rows)) != plan.request_set_sha256:
        raise ValueError('Only exact754-request frozen set permitted')
    requests=tuple(historical_request(plan,r) for r in rows)
    if len({r.request_id for r in requests}) != 754 or sum(r.maximum_credits for r in requests) != CAP:
        raise ValueError('Duplicate identity or finite cap differs')
    return requests


class HistoricalAccountBoundary(Protocol):
    """Future auditor-owned interface; owns canonical account lock, no second lock.

    Caller holds purchase then plan locks. Implementation validates exact adopted
    plan/authority/no-reset state, reserves full10 before one GET, persists sanitized
    receipt/terminal state and returns original observed time/replay without charging
    again. This protocol supplies neither implementation nor admission authority.
    """
    def admitted_get(self, request: HistoricalRequest): ...


def historical_session_factory(*args, **kwargs):
    """No fake/session/config/approval constructor can activate production here."""
    raise Held('N0 factory held: historical shared-account integration/adoption/authority absent')


def require_packet_admission(*args, **kwargs):
    raise Held('N0 packet held: ceiling/account/executor adoption and exact authority absent')


def validate_account_receipt(receipt, request):
    """Shape/attribution/original clock check only; not provider authentication."""
    required={'request_id','plan_identity_sha256','status','headers','body','observed_utc','replayed'}
    if (set(receipt) != required or receipt['request_id'] != request.request_id
            or receipt['plan_identity_sha256'] != request.plan_identity_sha256
            or type(receipt['replayed']) is not bool or type(receipt['status']) is not int
            or not isinstance(receipt['headers'],dict) or not isinstance(receipt['body'],str)):
        raise ValueError('Receipt attribution/schema changed')
    at=datetime.fromisoformat(receipt['observed_utc'].replace('Z','+00:00'))
    if at.tzinfo is None or at.utcoffset().total_seconds() != 0:
        raise ValueError('Original observed UTC required')
    if set(receipt['headers']) != {'x-requests-last','x-requests-used','x-requests-remaining'}:
        raise ValueError('Billing fields required')
    numbers={k:int(v) for k,v in receipt['headers'].items() if isinstance(v,str) and re.fullmatch('[0-9]+',v)}
    if len(numbers) != 3 or receipt['status'] != 200 or numbers['x-requests-last'] > request.maximum_credits:
        raise ValueError('Uncertain/status/billing response cannot settle attribution')
    # No new "now" stamp and no rewrite of original billing on replay.
    return copy.deepcopy(receipt)


def active_attribution(plan, ledger, marker, initialized, rows, receipt_bytes, account_receipts):
    """Pure exact-plan attribution before inventory projection; does not authorize.

    Inputs must be captured under outer purchase/plan locks and authenticated by
    future upstream admission. Never blanket-ignore an active root by name.
    """
    requests={r.request_id:r for r in exact_requests(plan,rows)}
    if (ledger['bundle_root_sha256'] != plan.root or ledger['authorization_sha256'] != plan.authorization_sha256
            or ledger['slice_cap'] != CAP or ledger['probe_credits'] != 1687
            or marker != {'bundle_root_sha256':plan.root,'authorization_sha256':plan.authorization_sha256,
                          'runtime_path':str((PURCHASE_LOCK.parent/plan.root).resolve())}
            or initialized != {'bundle_root_sha256':plan.root,'probe_credits':1687}
            or ledger['pending'] or ledger['stopped'] or ledger['status'] not in {'prepared','running','nba_n0_epoch_complete'}):
        raise ValueError('Active N0 root/authority/initialization/state changed')
    values=[ledger['other_usage_reserved']]+[a['reserved_credits'] for a in ledger['attempts'].values()]
    if any(type(v) is not int or v<0 for v in values) or ledger['other_usage_reserved'] < 272899:
        raise ValueError('Active carry reduced or invalid')
    if 1687+sum(values) > CEILING:raise ValueError('Active prospective ceiling exceeded')
    if sum(a['reserved_credits'] for a in ledger['attempts'].values()) > CAP:
        raise ValueError('Active finite cap exceeded')
    if set(receipt_bytes) != set(ledger['attempts']) or set(account_receipts) != set(receipt_bytes):
        raise ValueError('Active receipt inventory changed')
    if ledger['status']=='nba_n0_epoch_complete' and len(ledger['attempts']) != 754:
        raise ValueError('Incomplete active terminal scope')
    for rid,a in ledger['attempts'].items():
        if rid not in requests or a['status'] != 'completed' or a['reserved_credits'] != 10:
            raise ValueError('Active unknown/uncertain request')
        if sha(receipt_bytes[rid]) != a['receipt_sha256']:
            raise ValueError('Active receipt bytes changed')
        # Preserve original v4 per-plan receipt; account receipt is a distinct link,
        # not a second ledger/baseline or a replacement of the frozen format.
        saved=json.loads(receipt_bytes[rid]);record=saved['record']
        request=requests[rid]
        if (saved['request_id']!=rid or saved['cache_key']!=a['cache_key']
                or saved['record_sha256']!=a['response_sha256']
                or saved['body_sha256']!=sha(record['body'].encode())
                or record['cache_key']!=a['cache_key'] or record['http_status']!=200
                or record['url']!=request.url or record['sport']!='nba' or record['source']!='oddsapi_hist'
                or json.loads(record['params_json'])!=json.loads(request.public_params_json)
                or saved['headers']!=json.loads(record['headers_json'])):
            raise ValueError('Original v4 receipt/record identity changed')
        account=validate_account_receipt(account_receipts[rid],request)
        if account['body']!=record['body'] or account['headers']!=saved['headers']:
            raise ValueError('Account/plan receipt divergence')
    return sha(canonical({'plan':plan.validate(),'ledger':ledger,'marker':marker,'initialized':initialized}))


def settled_projection(pinned_ledgers, pins, rows, *, active=None):
    """Pure successor-aware global-settled projection, never an ignore-root switch."""
    captured=dict(pinned_ledgers)
    active_proof=None
    if active is not None:
        plan,ledger,marker,initialized,receipts,account_receipts=active
        if plan.root in pins['ledger_pins'] or plan.root not in captured:
            raise ValueError('Active root missing or overlaps historical root')
        if json.loads(captured[plan.root]) != ledger:raise ValueError('Active capture differs')
        active_proof=active_attribution(plan,ledger,marker,initialized,rows,receipts,account_receipts)
        del captured[plan.root]  # only after exact attribution, not caller declaration
    if set(captured) != set(pins['ledger_pins']):raise ValueError('Unknown/missing global root')
    states={}
    for root,raw in captured.items():
        if sha(raw) != pins['ledger_pins'][root]:raise ValueError('Historical ledger pin changed')
        states[root]=json.loads(raw)
    successor151.validate(states,pins,rows)
    return {'historical_roots':sorted(states),'active_attribution_sha256':active_proof,
            'conservative_carried_debit':274586,'proposed_ceiling':CEILING,
            'adopted':False,'paid_execution_enabled':False}
