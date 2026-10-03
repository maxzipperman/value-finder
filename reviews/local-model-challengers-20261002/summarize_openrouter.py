"""Saved-artifact metadata only: no model execution or credential/account reads."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def summarize():
    planned = json.loads((ROOT / 'openrouter-requests.json').read_text())['requests']
    extra = json.loads((ROOT / 'openrouter-free16k-requests.json').read_text())['requests']
    records = []
    deferred = {(x['model'], x['task']) for x in json.loads((ROOT / 'openrouter-provider-deferral.json').read_text())['deferred']} if (ROOT / 'openrouter-provider-deferral.json').exists() else set()
    for item, diagnostic in [(x, False) for x in planned] + [(x, True) for x in extra]:
        if item['model'] == 'stealth/space-bunny-alpha':
            folder = ROOT / ('openrouter-space-bunny-alpha-16k' if diagnostic else 'openrouter-space-bunny-alpha')
        else:
            folder = ROOT / 'openrouter-paid' / item['model'].replace('/', '--')
        task = item['task']
        record = dict(model=item['model'], task=task, diagnostic='free16k' if diagnostic else 'baseline', folder=str(folder.relative_to(ROOT)), status='not_started', prompt_sha256=item['prompt_sha256'], settings={k: v for k, v in item['body'].items() if k != 'messages'}, deadline_seconds=item['deadline_seconds'])
        if not diagnostic and (item['model'], task) in deferred:
            record.update(status='deferred', reason='Repeated provider Relace520; no retry/fallback. Provider-unavailable, not semantic model score.')
        request = folder / (task + '-request.json')
        if request.exists():
            record.update(status='pending', request_sha256=hashlib.sha256(request.read_bytes()).hexdigest())
        result = folder / (task + '-result.json')
        if result.exists():
            raw = json.loads(result.read_text())
            choice = raw.get('choices', [{}])[0]
            content = choice.get('message', {}).get('content') or ''
            record.update(status='result', returned_model=raw.get('model'), provider=raw.get('provider'), wall_seconds=raw.get('wall_seconds'), finish_reason=choice.get('finish_reason'), final_answer_bytes=len(content.encode()) if isinstance(content, str) else None, usage=raw.get('usage'))
        error = folder / (task + '-error.json')
        if error.exists():
            raw = json.loads(error.read_text())
            record.update(status='error', error_type=raw.get('type'), http_status=raw.get('http_status'), wall_seconds=raw.get('wall_seconds'))
        grade = folder / 'acceptance.json'
        if grade.exists():
            checks = json.loads(grade.read_text()).get(task)
            if checks is not None:
                record['acceptance'] = {'passed': sum(x['passed'] for x in checks), 'cases': len(checks), 'checks': checks}
        manual = folder / 'manual-review.json'
        if manual.exists():
            value = json.loads(manual.read_text()).get(task)
            if value is not None:
                record['manual_review'] = value
        records.append(record)
    snapshot = dict(status='in_progress', grading='author grading, not independent validation', records=records, note='Existing local controls are historical. Actual private helper excluded. Account-level credits/key usage are excluded; usage fields here belong only to synthetic model requests.')
    (ROOT / 'openrouter-summary.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    print(json.dumps({status: sum(r['status'] == status for r in records) for status in ('result', 'error', 'pending', 'not_started', 'deferred')}))


if __name__ == '__main__':
    summarize()
