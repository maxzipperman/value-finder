"""Exact-response, narrow AST compatibility diagnostic; default sandbox only."""
import ast
import copy
import hashlib
import json
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'ceiling'))
import harness
import grade
from ceiling_verify import verify

ORIGINAL_VALIDATE = harness.validate


def compatible_validate(source, allowed):
    tree = ast.parse(source)
    checked = copy.deepcopy(tree)
    for node in ast.walk(checked):
        if isinstance(node, ast.Name) and node.id == 'type' and isinstance(node.ctx, ast.Store):
            raise ValueError('shadowed type binding')
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == 'type':
            raise ValueError('shadowed type binding')
        if isinstance(node, ast.arg) and node.arg == 'type':
            raise ValueError('shadowed type argument')
        if isinstance(node, ast.Attribute) and node.attr == '__name__':
            value = node.value
            if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == 'type' and len(value.args) == 1 and isinstance(value.args[0], ast.Name) and not value.keywords):
                raise ValueError('only exact type(NAME).__name__ permitted')
            node.attr = 'diagnostic_type_name'
    ORIGINAL_VALIDATE(ast.unparse(checked), allowed)
    return compile(tree, 'inspected_candidate', 'exec')


def helper_checks(modules):
    output = []
    at = '2025-01-01T12:00:00Z'
    q = dict(id='q', book='B', event='E', observed_at='2025-01-01T11:00:00Z', expires_at='2025-01-01T13:00:00Z', last_update='2025-01-01T10:00:00Z', odds=150)
    r = dict(run_id='r', job='J', attempt=1, observed_at='2025-01-01T11:00:00Z', status='ok', downloaded_rows=1)
    def add(case, action):
        try:
            assert action()
            output.append(dict(case=case, passed=True))
        except Exception as exc:
            output.append(dict(case=case, passed=False, error=type(exc).__name__ + ': ' + str(exc)))
    def rejects(fn):
        try:
            fn()
        except ValueError:
            return True
        return False
    add('select invalid asof empty', lambda: rejects(lambda: modules['quotes'].select([], 'E', 'invalid')))
    add('reconcile invalid asof empty', lambda: rejects(lambda: modules['runs'].reconcile([], 'invalid')))
    add('select valid ISO asof', lambda: modules['quotes'].select([q], 'E', at)['B']['row'] is q)
    add('reconcile valid ISO asof', lambda: modules['runs'].reconcile([r], at)['J'] is r)
    return output


def main():
    if sys.argv[1:]:
        raise ValueError('No arbitrary candidate arguments')
    verify()
    manifest = json.loads((ROOT / 'ceiling-type-name-diagnostic-freeze.json').read_text())
    for name, digest in manifest['sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Supplemental diagnostic freeze changed')
    response = ROOT / 'ceiling-local/qwen3.8-27b-q8_0/implementation-response.txt'
    if hashlib.sha256(response.read_bytes()).hexdigest() != '250114de339206914856fd6358df5198857da641d681253384ebb3d86d7fce74':
        raise ValueError('Exact inspected response required')
    safety = []
    for source in ('x = value.__name__', 'x = globals()', 'x = open("x")', 'import os', 'type = str\nx = type(value).__name__'):
        try:
            compatible_validate(source, {'math'})
            raise AssertionError('Negative safety case accepted')
        except ValueError:
            safety.append(dict(source=source, rejected=True))
    harness.validate = compatible_validate
    try:
        ref_source = harness.source_bundle()
        ref_checks = grade.grade('implementation', json.dumps(ref_source))
        ref_helpers = helper_checks(harness.load(ref_source, return_modules=True))
        if len(ref_checks) != 197 or not all(x['passed'] for x in ref_checks + ref_helpers):
            raise ValueError('Reference diagnostic acceptance failed')
        results = grade.grade('implementation', response.read_text())
        helpers = helper_checks(harness.load(json.loads(response.read_text()), return_modules=True))
    finally:
        harness.validate = ORIGINAL_VALIDATE
    report = dict(grading='supplemental author diagnostic, not independent validation or original blinded grading', original_acceptance_preserved=True, source_sha256=manifest['sha256']['ceiling-local/qwen3.8-27b-q8_0/implementation-response.txt'], safety=safety, reference_checks=dict(passed=197, cases=197), reference_helper_checks=ref_helpers, original_197_checks=dict(passed=sum(x['passed'] for x in results), cases=len(results), checks=results), extra_helper_checks=helpers, limitations='Only exact type(NAME).__name__ relaxed; separate four helper probes are post-observation coverage, not added to original197 denominator. No inferred quantization effect.')
    response.with_name('implementation-type-name-diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(original197_passed=sum(x['passed'] for x in results), extra4_passed=sum(x['passed'] for x in helpers))))


if __name__ == '__main__':
    signal.signal(signal.SIGALRM, lambda *args: (_ for _ in ()).throw(TimeoutError('15s diagnostic limit')))
    signal.alarm(15)
    main()
