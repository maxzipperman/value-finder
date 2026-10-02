#!/usr/bin/env python3
"""Future-only content/evidence/plan guards. No keys, network or runtime writes."""
import argparse
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import os
import shutil
import re
from datetime import datetime, timezone

BOUND = {'executable', 'dependency', 'requests', 'eligibility', 'policy'}
SUPPORT = {'test', 'documentation'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def relative(name):
    p = PurePosixPath(name)
    require(isinstance(name, str) and name and not p.is_absolute() and
            '..' not in p.parts and str(p) == name, 'unsafe or noncanonical path')
    return p


def safe_file(root, name):
    p = relative(name)
    candidate = root.joinpath(*p.parts)
    require(not any(x.is_symlink() for x in [candidate, *candidate.parents] if x != root.parent),
            'symlink forbidden')
    require(candidate.is_file() and candidate.is_relative_to(root), 'missing file: ' + name)
    return candidate


def inventory(root, scopes):
    require(isinstance(scopes, list) and scopes and len(set(scopes)) == len(scopes), 'invalid scopes')
    found = set()
    for scope in scopes:
        p = root.joinpath(*relative(scope).parts)
        require(p.exists() and not p.is_symlink(), 'missing/symlink scope')
        paths = p.rglob('*') if p.is_dir() else [p]
        for item in paths:
            require(not item.is_symlink(), 'symlink forbidden')
            if item.is_file():
                name = item.relative_to(root).as_posix()
                safe_file(root, name)
                found.add(name)
    return found


def check_python_imports(root, files):
    """Conservative static check; adoption still needs a captured-source loader."""
    for name, role in files.items():
        if role not in BOUND or not name.endswith('.py'):
            continue
        for node in ast.walk(ast.parse(safe_file(root, name).read_text())):
            if isinstance(node, ast.Call):
                fn = node.func
                call = fn.id if isinstance(fn, ast.Name) else getattr(fn, 'attr', '')
                require(call not in {'exec', 'eval', '__import__', 'import_module',
                                     'spec_from_file_location', 'run_path', 'run_module'},
                        'dynamic executable loading requires separate design: ' + name)
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            modules = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module or '']
            for module in modules:
                bases = [root, safe_file(root, name).parent]
                if isinstance(node, ast.ImportFrom) and node.level:
                    bases = [safe_file(root, name).parent]
                    for _ in range(node.level - 1):
                        bases = [bases[0].parent]
                for base in bases:
                    target = base.joinpath(*module.split('.')) if module else base
                    candidates = [target.with_suffix('.py'), target / '__init__.py']
                    ancestor = target.parent
                    while ancestor.is_relative_to(root):
                        candidates.append(ancestor / '__init__.py')
                        if ancestor == root: break
                        ancestor = ancestor.parent
                    if isinstance(node, ast.ImportFrom):
                        candidates += [target / (x.name + '.py') for x in node.names]
                        candidates += [target / x.name / '__init__.py' for x in node.names]
                    for candidate in candidates:
                        if candidate.is_file() and candidate.is_relative_to(root):
                            local = candidate.relative_to(root).as_posix()
                            require(files.get(local) in BOUND, 'undeclared local import: ' + local)


def content_manifest(root, spec):
    require(set(spec) == {'version', 'scopes', 'files'} and type(spec['version']) is int and spec['version'] == 1, 'invalid freeze spec')
    files = spec['files']
    require(isinstance(files, dict) and files, 'empty input map')
    require(inventory(root, spec['scopes']) == set(files), 'undeclared or missing input')
    bound, supporting = {}, {}
    for name, role in sorted(files.items()):
        path = safe_file(root, name)
        require(role in BOUND | SUPPORT, 'unknown input role')
        if role == 'documentation':
            require(path.suffix == '.md' and not any(x in path.name.upper() for x in
                    ('PREREGISTRATION', 'STRATEGY', 'ELIGIBILITY', 'PROTOCOL', 'GOVERNANCE')),
                    'rule/eligibility document cannot be supporting')
        if role == 'test':
            require(('tests' in path.parts or path.name.startswith('test_')),
                    'test role requires dedicated test path')
        require(not path.name.startswith('.env'), 'secret input forbidden')
        (bound if role in BOUND else supporting)[name] = {'role': role, 'sha256': file_hash(path)}
    require({'executable', 'dependency', 'requests', 'eligibility', 'policy'} <= {x['role'] for x in bound.values()},
            'incomplete purchase input classes')
    check_python_imports(root, files)
    payload = {'version': 1, 'scopes': spec['scopes'], 'inputs': bound}
    return {'version': 1, 'purchase_identity': digest(payload), 'content': payload,
            'supporting': supporting, 'supporting_identity': digest(supporting)}


def verify_content(root, spec, saved):
    current = content_manifest(root, spec)
    require(saved['content'] == current['content'] and
            saved['purchase_identity'] == current['purchase_identity'], 'purchase content changed')
    return {'purchase_identity': current['purchase_identity'],
            'supporting_changed': current['supporting'] != saved['supporting'],
            'supporting_identity': current['supporting_identity']}


def environment():
    return {'python': sys.version, 'executable_sha256': file_hash(Path(sys.executable).resolve()),
            'platform': platform.platform(),
            'packages': sorted([x.metadata['Name'], x.version] for x in importlib.metadata.distributions())}


def evidence_inputs(root, config):
    require(set(config) == {'version', 'scopes', 'commands', 'environment'} and type(config['version']) is int and config['version'] == 1,
            'invalid evidence config')
    commands = config['commands']
    require(isinstance(commands, list) and commands and all(isinstance(c, list) and c and
            all(isinstance(x, str) and x for x in c) for c in commands), 'commands must be argv arrays')
    files = {name: file_hash(safe_file(root, name)) for name in sorted(inventory(root, config['scopes']))}
    require(all(not Path(n).name.startswith('.env') for n in files), 'secret evidence input forbidden')
    require(isinstance(config['environment'], dict) and all(isinstance(k, str) and
            isinstance(v, str) for k, v in config['environment'].items()), 'invalid test environment')
    effective_env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', **config['environment']}
    require(all(Path(part).is_absolute() for part in effective_env['PATH'].split(os.pathsep)),
            'test PATH must use absolute directories')
    binaries = {}
    for command in commands:
        binary = (sys.executable if command[0] == '{python}' else
                  shutil.which(command[0], path=effective_env['PATH']))
        require(binary is not None, 'missing command binary')
        path = Path(binary)
        if not path.is_absolute(): path = root / path
        path = path.absolute()  # Preserve venv interpreter symlink invocation.
        require(path.read_bytes()[:2] != b'#!',
                'invoke script with an explicitly bound interpreter')
        binaries[command[0]] = {'path': str(path), 'sha256': file_hash(path.resolve())}
        for token in command[1:]:
            argument = root / token
            if argument.is_file():
                require(argument.is_relative_to(root) and argument.relative_to(root).as_posix() in files,
                        'script/file command argument outside declared test inputs')
    return {'files': files, 'commands': commands, 'environment': environment(),
            'configured_environment': config['environment'], 'effective_environment': effective_env,
            'command_binaries': binaries}


def run_evidence(root, config):
    inputs = evidence_inputs(root, config)
    results = []
    for command in config['commands']:
        actual = [inputs['command_binaries'][command[0]]['path'], *command[1:]]
        run = subprocess.run(actual, cwd=root, capture_output=True, shell=False,
                             env=inputs['effective_environment'])
        results.append({'argv': command, 'exit_code': run.returncode,
                        'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
                        'stderr_sha256': hashlib.sha256(run.stderr).hexdigest(),
                        'unittest_count': [int(n) for n in re.findall(rb'Ran (\d+) tests?', run.stderr)]})
    require(evidence_inputs(root, config) == inputs, 'tested inputs changed during execution')
    report = {'version': 1, 'tested_identity': digest(inputs), 'inputs': inputs, 'results': results,
            'passed': all(x['exit_code'] == 0 for x in results),
            'recorded_at': datetime.now(timezone.utc).isoformat(),
            'worktree_clean': not bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)),
            'tested_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()}
    report['evidence_digest'] = digest(report)
    return report


def verify_evidence(root, config, saved):
    inputs = evidence_inputs(root, config)
    require(saved.get('evidence_digest') == digest({k: v for k, v in saved.items() if k != 'evidence_digest'}),
            'evidence integrity mismatch')
    require(saved['version'] == 1 and saved['tested_identity'] == digest(inputs) and
            saved['inputs'] == inputs, 'test evidence input/environment mismatch')
    require(saved['passed'] is True and len(saved['results']) == len(config['commands']) and
            all(r['argv'] == c and type(r['exit_code']) is int and r['exit_code'] == 0
                for r, c in zip(saved['results'], config['commands'])), 'failed/incomplete evidence')
    return {'tested_identity': saved['tested_identity'], 'passed': True,
            'provenance_check_required': True}


def integer(n):
    return type(n) is int and n >= 0


def sha(n):
    return isinstance(n, str) and len(n) == 64 and all(c in '0123456789abcdef' for c in n)


def validate_plan(plan):
    require(set(plan) == {'version', 'request_list_sha256', 'requests',
                         'budget', 'missing', 'restart', 'coverage'}, 'invalid plan fields')
    require(type(plan['version']) is int and plan['version'] == 1 and sha(plan['request_list_sha256']),
            'invalid plan identity')
    requests = plan['requests']
    require(isinstance(requests, list) and requests, 'empty allowlist')
    require(all(set(r) == {'id', 'max_credits'} and sha(r['id']) and integer(r['max_credits']) and
                r['max_credits'] > 0 for r in requests), 'invalid request')
    ids = {r['id'] for r in requests}
    require(len(ids) == len(requests), 'duplicate request IDs')
    budget = plan['budget']
    require(set(budget) == {'new_cap', 'prior_reserved', 'probe', 'other_usage', 'cumulative_cap',
                           'reserve_floor'} and all(integer(x) for x in budget.values()), 'invalid budget')
    require(sum(r['max_credits'] for r in requests) == budget['new_cap'], 'allowlist cap mismatch')
    require(budget['prior_reserved'] + budget['probe'] + budget['other_usage'] + budget['new_cap']
            <= budget['cumulative_cap'], 'cumulative ceiling exceeded')
    missing = plan['missing']
    require(set(missing) == {'ids', 'http_status', 'error_code', 'last_cost', 'retain_full_reservation',
                            'retain_denominator'}, 'invalid missing policy')
    require(isinstance(missing['ids'], list) and len(set(missing['ids'])) == len(missing['ids']) and
            set(missing['ids']) <= ids and missing['http_status'] == 404 and
            missing['error_code'] == 'EVENT_NOT_FOUND' and type(missing['last_cost']) is int and
            missing['last_cost'] == 0 and missing['retain_full_reservation'] is True and
            missing['retain_denominator'] is True, 'unsafe missing policy')
    require(plan['restart'] == {'states': ['clean_stopped', 'complete'], 'automatic_retries': 0,
            'send_only_untouched': True, 'live_authority_required': True,
            'global_lock_ledger_required': True}, 'unsafe restart policy')
    coverage = plan['coverage']
    require(set(coverage) == {'metric', 'minimum', 'denominator', 'halt_before_next_tranche',
                             'outcome_blind'} and isinstance(coverage['metric'], str) and
            coverage['metric'] and type(coverage['minimum']) in (float, int) and
            0 <= coverage['minimum'] <= 1 and coverage['denominator'] == 'all_planned_opportunities' and
            coverage['halt_before_next_tranche'] is True and coverage['outcome_blind'] is True,
            'unsafe coverage gate')
    return plan


def restart_candidates(plan, checkpoint, *, purchase_identity, live_authority, shared_lock):
    """Pure check only. The adopting executor must authenticate every supplied fact."""
    validate_plan(plan)
    require(live_authority is True and shared_lock is True, 'live authority/shared lock required')
    require(set(checkpoint) == {'purchase_identity', 'request_list_sha256', 'state', 'attempts',
                               'remaining_credits', 'coverage_passed'}, 'invalid checkpoint')
    require(sha(purchase_identity) and checkpoint['purchase_identity'] == purchase_identity and
            checkpoint['request_list_sha256'] == plan['request_list_sha256'], 'checkpoint identity mismatch')
    require(checkpoint['state'] in plan['restart']['states'], 'uncertain/unapproved restart state')
    costs = {r['id']: r['max_credits'] for r in plan['requests']}
    attempts = checkpoint['attempts']
    require(isinstance(attempts, dict) and set(attempts) <= set(costs), 'unknown attempts')
    for rid, attempt in attempts.items():
        require(set(attempt) == {'status', 'reserved', 'billed', 'receipt_verified'} and
                attempt['status'] in {'valid', 'allowed_missing'} and integer(attempt['reserved']) and
                integer(attempt['billed']) and attempt['reserved'] == costs[rid] and
                attempt['billed'] <= attempt['reserved'] and attempt['receipt_verified'] is True,
                'uncertain or inconsistent receipt/reservation')
        if attempt['status'] == 'allowed_missing':
            require(rid in plan['missing']['ids'] and attempt['billed'] == 0, 'missing outside policy')
    require(integer(checkpoint['remaining_credits']), 'invalid provider balance')
    remaining = [r['id'] for r in plan['requests'] if r['id'] not in attempts]
    require(checkpoint['remaining_credits'] - sum(costs[r] for r in remaining) >=
            plan['budget']['reserve_floor'], 'reserve floor violated')
    if checkpoint['state'] == 'complete':
        require(not remaining and type(checkpoint['coverage_passed']) is bool, 'incomplete completed state')
    else:
        require(checkpoint['coverage_passed'] is None, 'coverage cannot be finalized during tranche')
    return {'untouched_ids': remaining, 'next_tranche_allowed': checkpoint['state'] == 'complete' and
            checkpoint['coverage_passed'] is True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'verify-freeze', 'test', 'verify-test', 'test-key', 'plan'])
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--saved', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--request-list', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    config = json.loads(args.config.read_text())
    try:
        if args.action == 'freeze': result = content_manifest(root, config)
        elif args.action == 'test': result = run_evidence(root, config)
        elif args.action == 'test-key': result = {'tested_identity': digest(evidence_inputs(root, config))}
        elif args.action == 'plan':
            validate_plan(config)
            require(args.request_list is not None, '--request-list is required')
            require(file_hash(args.request_list) == config['request_list_sha256'] and
                    json.loads(args.request_list.read_text()) == config['requests'], 'request list mismatch')
            result = {'plan_identity': digest(config), 'valid': True}
        else:
            require(args.saved is not None, '--saved is required')
            saved = json.loads(args.saved.read_text())
            result = (verify_content if args.action == 'verify-freeze' else verify_evidence)(root, config, saved)
        encoded = json.dumps(result, indent=2, sort_keys=True) + '\n'
        if args.output: args.output.write_text(encoded)
        else: print(encoded, end='')
        return 0 if result.get('passed', True) else 1
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('Guard rejected: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
