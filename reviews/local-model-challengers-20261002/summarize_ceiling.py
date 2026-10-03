"""Index saved synthetic trial metadata; never execute candidates/read private billing."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def summarize():
    records = []
    for family in ('local', 'api'):
        for item in json.loads((ROOT / ('ceiling-' + family + '-requests.json')).read_text())['requests']:
            model, task = item['model'], item['task']
            if family == 'local':
                folder = ROOT / 'ceiling-local' / model.replace(':', '-')
            elif model == 'stealth/space-bunny-alpha':
                folder = ROOT / 'ceiling-space-bunny'
            else:
                folder = ROOT / 'openrouter-ceiling' / model.replace('/', '--')
            body = item['body']
            rec = dict(family=family, model=model, task=task, status='not_started', folder=str(folder.relative_to(ROOT)), prompt_sha256=item['prompt_sha256'], digest=item.get('digest'), deadline_seconds=item['deadline_seconds'], settings={k: v for k, v in body.items() if k != 'messages'})
            request = folder / (task + '-request.json')
            if request.exists():
                rec.update(status='pending', request_sha256=hashlib.sha256(request.read_bytes()).hexdigest())
            result = folder / (task + '-result.json')
            if result.exists():
                raw = json.loads(result.read_text())
                rec.update(status='result', returned_model=raw.get('model'), wall_seconds=raw.get('wall_seconds'))
                if family == 'local':
                    rec.update(finish_reason=raw.get('done_reason'), final_answer_bytes=len((raw.get('message', {}).get('content') or '').encode()), load_seconds=raw.get('load_duration', 0) / 1e9, generation_seconds=raw.get('eval_duration', 0) / 1e9, generated_tokens=raw.get('eval_count'), prompt_tokens=raw.get('prompt_eval_count'), preflight_memory_free_percentage=raw.get('preflight_memory_free_percentage'), sampled_memory=raw.get('memory_samples'), memory_note=raw.get('sampling_note'))
                else:
                    choice = raw.get('choices', [{}])[0]
                    content = choice.get('message', {}).get('content') or ''
                    rec.update(provider=raw.get('provider'), finish_reason=choice.get('finish_reason'), final_answer_bytes=len(content.encode()) if isinstance(content, str) else None, usage=raw.get('usage'))
            error = folder / (task + '-error.json')
            if error.exists():
                raw = json.loads(error.read_text())
                rec.update(status='error', error_type=raw.get('type'), http_status=raw.get('http_status'), wall_seconds=raw.get('wall_seconds'))
            grade = folder / (task + '-acceptance.json')
            if grade.exists():
                checks = json.loads(grade.read_text())
                rec['acceptance'] = dict(passed=sum(x['passed'] for x in checks), cases=len(checks), checks=checks)
            manual = folder / 'manual-review.json'
            if task == 'review' and manual.exists():
                rec['manual_review'] = json.loads(manual.read_text())
            records.append(rec)
    counts = {s: sum(r['status'] == s for r in records) for s in ('result', 'error', 'pending', 'not_started')}
    snapshot = dict(status='collection_in_progress', grading='author only; independent validation pending', counts=counts, records=records, limitations='Modes/artifacts/providers/tokenization differ; single draws and adaptive profiles are not causal or equal-compute rankings. Sampled allocation is not complete machine peak memory or swap evidence.')
    (ROOT / 'ceiling-summary.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    print(json.dumps(counts))


if __name__ == '__main__':
    summarize()
