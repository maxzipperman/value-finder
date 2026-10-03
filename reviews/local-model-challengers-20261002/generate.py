"""LOCAL-BECAUSE: hardware. Collect one matched local-model response; never execute it."""
import json
import fcntl
import argparse
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from expanded import TASKS
from real_helper import PROMPT
from hard_pair import TASKS as HARD_TASKS

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / 'protocol.json').read_text())

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('redirect prohibited')

HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

def api(endpoint, body=None):
    assert endpoint in ('tags', 'ps', 'chat')
    request = urllib.request.Request(
        'http://127.0.0.1:11434/api/' + endpoint,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'},
    )
    with HTTP.open(request, timeout=PROTOCOL['deadline_seconds'] if endpoint == 'chat' else 10) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('response too large')
    return json.loads(data)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+', choices=PROTOCOL['models'])
    parser.add_argument('--no-thinking', action='store_true')
    parser.add_argument('--hard-pair', action='store_true')
    parser.add_argument('--tasks', nargs='+', choices=PROTOCOL['tasks'] + list(HARD_TASKS))
    args = parser.parse_args()
    if args.hard_pair:
        PROTOCOL['deadline_seconds'] = 600
    selected = args.models or PROTOCOL['models']
    inventory = api('tags')['models']
    available = {m['name']: m for m in inventory}
    missing = [m for m in selected if m not in available]
    if missing:
        print(json.dumps({'status': 'waiting_for_downloads', 'missing': missing}))
        return
    if api('ps')['models']:
        print(json.dumps({'status': 'deferred', 'reason': 'another model is loaded'}))
        return
    check = subprocess.run(['/usr/bin/memory_pressure', '-Q'], capture_output=True, text=True, timeout=10)
    import re
    match = re.search(r'System-wide memory free percentage:\s*(\d+)%', check.stdout)
    if check.returncode or not match or int(match[1]) < 40:
        print(json.dumps({'status': 'deferred', 'reason': 'low or unknown memory headroom'}))
        return
    snapshot = ROOT / 'inventory.json'
    current = {m: {'digest': available[m]['digest'], 'artifact_bytes': available[m]['size']} for m in selected}
    if snapshot.exists():
        recorded = json.loads(snapshot.read_text())
        if any(m in recorded and recorded[m] != current[m] for m in selected):
            raise ValueError('installed model inventory changed; review required')
        current = recorded | current
    snapshot.write_text(json.dumps(current, indent=2) + '\n')
    for task in (args.tasks or (list(HARD_TASKS) if args.hard_pair else PROTOCOL['tasks'])):
        for model in selected:
            out = ROOT / (('hard-pair-' if args.hard_pair else '') + model.replace(':', '-') + ('-no-thinking' if args.no_thinking else ''))
            out.mkdir(exist_ok=True)
            result_path = out / (task + '-result.json')
            error_path = out / (task + '-error.json')
            if result_path.exists() or error_path.exists():
                continue
            prompt = PROMPT if task == 'real-helper' else (HARD_TASKS[task] if task in HARD_TASKS else TASKS[task])
            body = dict(model=model, messages=[dict(role='user', content=prompt)],
                        stream=False, keep_alive=0,
                        think=False if args.no_thinking else ('medium' if model.startswith('gpt-oss:') else True),
                        options=PROTOCOL['options'] | ({'draft_num_predict': 0} if args.hard_pair else {}))
            (out / (task + '-request.json')).write_text(json.dumps(body, indent=2) + '\n')
            start = time.monotonic()
            try:
                samples = []
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(api, 'chat', body)
                    while not future.done():
                        try:
                            for loaded in api('ps')['models']:
                                if loaded.get('name') == model:
                                    samples.append({k: loaded.get(k) for k in ('size', 'size_vram', 'context_length')})
                        except Exception:
                            pass
                        time.sleep(1)
                    result = future.result()
                result['memory_samples'] = samples
                result['wall_seconds'] = time.monotonic() - start
                result['request_deadline_seconds'] = PROTOCOL['deadline_seconds']
                result_path.write_text(json.dumps(result, indent=2) + '\n')
                (out / (task + '-response.txt')).write_text(result.get('message', {}).get('content', ''))
                print(json.dumps({'status': 'collected', 'model': model, 'task': task,
                                  'wall_seconds': result['wall_seconds'], 'done_reason': result.get('done_reason')}))
            except Exception as exc:
                # A timeout may leave inference running; don't retry an uncertain request.
                error_path.write_text(json.dumps({'error_type': type(exc).__name__, 'elapsed_seconds': time.monotonic()-start}, indent=2) + '\n')
                print(json.dumps({'status': 'request_error', 'model': model, 'task': task,
                                  'error_type': type(exc).__name__, 'review_required': True}))
            return
    print(json.dumps({'status': 'collection_complete', 'next': 'inspect candidates, grade in restricted sandbox, independently review claims'}))

if __name__ == '__main__':
    with (ROOT / '.collection.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'deferred', 'reason': 'comparison already running'}))
        else:
            main()
