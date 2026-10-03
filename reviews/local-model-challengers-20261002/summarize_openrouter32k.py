"""Index saved synthetic 32K artifacts only; never execute candidates/read billing."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIST_SHA = '441f14b4b605d49e1b9fcc0cc6ee123dd32e7e22ceeff41b213a27c8e34f0156'


def summarize():
    raw = (ROOT / 'openrouter-paid32k-requests.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != LIST_SHA:
        raise ValueError('Declared list changed')
    decisions = json.loads((ROOT / 'openrouter-budget-decisions.json').read_text())
    records = []
    excluded = []
    for item in json.loads(raw)['requests']:
        key = item['model'] + '|' + item['task'] + '|32k'
        decision = decisions.get(key, {})
        if decision.get('proceed') is not True:
            excluded.append(dict(key=key, decision=decision))
            continue
        folder = ROOT / 'openrouter-paid32k' / item['model'].replace('/', '--')
        prefix = folder / item['task']
        record = dict(model=item['model'], task=item['task'], status='not_started',
                      folder=str(folder.relative_to(ROOT)), prompt_sha256=item['prompt_sha256'],
                      settings={k: v for k, v in item['body'].items() if k != 'messages'},
                      deadline_seconds=item['deadline_seconds'], decision=decision)
        request = Path(str(prefix) + '-request.json')
        if request.exists():
            record.update(status='pending', request_sha256=hashlib.sha256(request.read_bytes()).hexdigest())
        result = Path(str(prefix) + '-result.json')
        if result.exists():
            value = json.loads(result.read_text())
            choice = value.get('choices', [{}])[0]
            content = choice.get('message', {}).get('content') or ''
            failed = choice.get('finish_reason') == 'error' or bool(choice.get('error'))
            record.update(status='provider_error' if failed else 'result',
                          finish_reason=choice.get('finish_reason'), error=choice.get('error'),
                          returned_model=value.get('model'), provider=value.get('provider'),
                          wall_seconds=value.get('wall_seconds'), usage=value.get('usage'),
                          final_answer_bytes=len(content.encode()) if isinstance(content, str) else None)
        error = Path(str(prefix) + '-error.json')
        if error.exists():
            value = json.loads(error.read_text())
            record.update(status='transport_error', error_type=value.get('type'),
                          http_status=value.get('http_status'), wall_seconds=value.get('wall_seconds'))
        acceptance = Path(str(prefix) + '-acceptance.json')
        if acceptance.exists():
            checks = json.loads(acceptance.read_text())
            record['acceptance'] = dict(passed=sum(x['passed'] for x in checks), cases=len(checks), checks=checks)
        manual = Path(str(prefix) + '-manual-inspection.json')
        if manual.exists():
            record['manual_inspection'] = json.loads(manual.read_text())
        records.append(record)
    if len(records) != 6 or len(excluded) != 12:
        raise ValueError('Conditional selection changed')
    snapshot = dict(grading='author only; not independent validation', list_sha256=LIST_SHA,
                    records=records, excluded=excluded,
                    note='Original capped attempts remain separate. Embedded provider errors are failures, not valid completions. Gateway per-request costs and upstream cost fields are distinct; private account ledgers excluded.')
    (ROOT / 'openrouter32k-summary.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    print(json.dumps({s: sum(x['status'] == s for x in records) for s in ('result', 'provider_error', 'transport_error', 'pending', 'not_started')}))


if __name__ == '__main__':
    summarize()
