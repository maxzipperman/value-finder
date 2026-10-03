"""Read-only prospective review evidence and conservative frozen-path audit.

Never authenticates a reviewer or purchase. Git object IDs bind tracked bytes;
untracked/private runtime inputs require separate native evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

POLICY = 'ops/process/review-policy.json'


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def commit(root, ref):
    return git(root, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()


def tree(root, ref):
    result = {}
    for row in git(root, 'ls-tree', '-rz', '--full-tree', ref).split(b'\0'):
        if row:
            metadata, name = row.split(b'\t', 1)
            mode, kind, oid = metadata.decode().split()
            result[name.decode()] = {'mode': mode, 'kind': kind, 'oid': oid}
    return result


def blob(root, ref, name):
    return git(root, 'show', ref + ':' + name)


def review_inputs(root, base, head, environment):
    """Exclusions come only from already adopted base policy, never PR policy.

    Unknown inputs, deletions and base changes remain bound. Candidate reuse is
    evidence only: merger must authenticate original review and current opinion.
    """
    base, head = commit(root, base), commit(root, head)
    before, after = tree(root, base), tree(root, head)
    try:
        policy = json.loads(blob(root, base, POLICY))
    except subprocess.CalledProcessError:
        policy = {'version': 1, 'explanatory_paths': []}
    if set(policy) != {'version', 'explanatory_paths'} or policy['version'] != 1:
        raise ValueError('invalid adopted review policy')
    exclusions = policy['explanatory_paths']
    if (not isinstance(exclusions, list) or len(set(exclusions)) != len(exclusions)
            or any(not isinstance(p, str) or not p.endswith('.md') or
                   str(PurePosixPath(p)) != p or PurePosixPath(p).is_absolute() or
                   '..' in PurePosixPath(p).parts for p in exclusions)):
        raise ValueError('only explicit canonical explanatory paths may be excluded')
    forbidden = ('GOVERNANCE', 'CLAUDE', 'AGENTS', 'STRATEGY', 'PREREGISTRATION',
                 'ELIGIBILITY', 'PROTOCOL', 'POLICY', 'STATUS')
    if any(any(token in Path(p).name.upper() for token in forbidden) for p in exclusions):
        raise ValueError('control or rule path cannot be excluded')
    # Deletion/type changes/new paths are substantive even for an approved path.
    allowed = {p for p in exclusions if p in before and p in after and
               before[p]['mode'] == after[p]['mode'] == '100644' and
               before[p]['kind'] == after[p]['kind'] == 'blob'}
    bound = {'base_tree': {p: v for p, v in before.items() if p not in allowed},
             'merge_tree': {p: v for p, v in after.items() if p not in allowed},
             'adopted_policy': policy, 'environment': environment}
    changed = sorted(p for p in before.keys() | after.keys()
                     if before.get(p) != after.get(p))
    return {'version': 1, 'base_commit': base, 'merge_result_commit': head,
            'relevant_identity': identity(bound), 'inputs': bound,
            'changed_paths': changed, 'excluded_paths': sorted(allowed),
            'effect_review_required': bool(set(changed) - allowed),
            'authorization': False, 'provenance_check_required': True}


def verify_review(current, saved):
    for record in (current, saved):
        if (record.get('version') != 1 or record.get('authorization') is not False or
                record.get('relevant_identity') != identity(record.get('inputs'))):
            raise ValueError('invalid review evidence integrity')
    if current['inputs'] != saved['inputs']:
        raise ValueError('base/merge inputs or environment changed')
    return {'reusable_evidence': True, 'authorization': False,
            'original_review_provenance_required': True,
            'current_reviewer_disposition_required': True}


def immutable_audit(root, base, head):
    """Definite path violations block; incomplete capture mapping stays explicit.

    All pre-existing freeze directories are protected conservatively, including
    unexecuted ones. External/logical closures need their native verifier. This is
    not a runtime integrity proof, or a blanket approval of new freeze packets.
    """
    before, after = tree(root, base), tree(root, head)
    changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    frozen = [p for p in before if Path(p).name == 'FREEZE.json']
    violations, gaps = [], []
    for freeze in frozen:
        directory = str(PurePosixPath(freeze).parent)
        prefix = '' if directory == '.' else directory + '/'
        violations.extend({'freeze': freeze, 'path': p, 'reason': 'pre-existing frozen scope changed'}
                          for p in sorted(changed) if p.startswith(prefix))
        cert = json.loads(blob(root, base, freeze))
        pins = cert.get('files', cert.get('file_sha256'))
        # Do not guess physical mappings for code/, source/, absolute or local://.
        if not isinstance(pins, dict):
            gaps.append({'freeze': freeze, 'reason': 'unsupported inventory schema'})
        else:
            logical = [p for p in pins if prefix + p not in before]
            if logical:
                gaps.append({'freeze': freeze, 'reason': 'logical/external captured paths need native verification',
                             'unresolved_count': len(logical)})
    violations.extend({'path': p, 'reason': 'historical archive is append-only'} for p in changed
                      if p in before and p.startswith('docs/status-archive/')
                      and Path(p).name != 'README.md')
    return {'mode': 'shadow-for-incomplete-captures', 'violations': violations,
            'coverage_gaps': gaps, 'frozen_scopes_checked': len(frozen),
            'runtime_safety_proven': False, 'authorization': False}


def main():
    from process_guard import environment
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['review-key', 'verify-review', 'audit'])
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--saved', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'audit':
        result = immutable_audit(args.root, args.base, args.head)
    else:
        result = review_inputs(args.root, args.base, args.head, environment())
        if args.action == 'verify-review':
            if args.saved is None: raise ValueError('--saved required')
            result = verify_review(result, json.loads(args.saved.read_text()))
    encoded = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output: args.output.write_text(encoded)
    else: print(encoded, end='')
    return 1 if result.get('violations') else 0


if __name__ == '__main__':
    raise SystemExit(main())
