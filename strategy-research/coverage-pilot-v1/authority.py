"""Exact prospective pilot approval check; live lookup occurs only when invoked."""
import json
import re
import subprocess
from planner import digest


def check(base, auth, manifest, root, commit, context, *, fetch=None):
    base.validate_authorization(auth,manifest,root,commit)
    rec=base.validate_reconciliation(auth['account_reconciliation'],root)
    if (rec.get('baseline_mode') != 'capture_first_free_check' or rec.get('account_only_recovery')
            or 'pre_run_other_usage_budget_debit' in rec or auth.get('pilot_context') != context):
        raise ValueError('exact prospective context/account binding required')
    required_keys={'policy_sha256','plan_sha256','global_snapshot_sha256','historical_bindings_sha256',
                   'cache_union_sha256','captured_closure_sha256'}
    if set(context) != required_keys or any(not re.fullmatch('[a-f0-9]{64}',v or '') for v in context.values()):
        raise ValueError('complete frozen pilot context required')
    hub=auth['hub_go_ahead'];body=hub['comment_body']
    states=[line.strip() for line in body.splitlines() if re.match(r'^CURRENT PAID AUTHORITY\b',line.strip(),re.I)]
    if states != ['CURRENT PAID AUTHORITY: ACTIVE']:
        raise ValueError('exactly one unambiguous ACTIVE authority state required')
    required=[f'APPROVED pilot context: sha256 {digest(context)}, root {root}',
              f'APPROVED account reconciliation: sha256 {digest(rec)}, root {root}',
              'CURRENT PAID AUTHORITY: ACTIVE']
    if not all(line in body.splitlines() for line in required) or re.search(r'\b(HALTED|EXHAUSTED|REVOKED|NOT APPROVED|NOT READY)\b',body,re.I):
        raise ValueError('pilot authority inactive or incomplete')
    cid=hub['comment_url'].rsplit('-',1)[-1]
    if fetch is None:
        live=json.loads(subprocess.check_output(['gh','api',f'repos/maxzipperman/value-finder/issues/comments/{cid}'],text=True))
    else: live=fetch(cid)  # synthetic tests only; production bootstrap supplies no override
    if live.get('html_url') != hub['comment_url'] or live.get('body') != body or live.get('user',{}).get('login') != 'maxzipperman':
        raise ValueError('live hub authority changed')
