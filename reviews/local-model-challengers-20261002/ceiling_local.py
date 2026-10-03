"""Frozen synthetic local ceiling collection, never executes candidate output."""
import fcntl
import hashlib
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from ceiling_verify import verify,ROOT
from openrouter_free import NoRedirect

HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

def api(path,body=None):
    assert path in ('tags','ps','chat','show')
    req=urllib.request.Request('http://127.0.0.1:11434/api/'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with HTTP.open(req,timeout=3600 if path=="chat" else 10) as f:
        data=f.read(2_000_001)
    if len(data)>2_000_000:raise RuntimeError('response size limit')
    return json.loads(data)

def main():
    verify()
    plan=json.loads((ROOT/'ceiling-local-requests.json').read_text())
    with (ROOT/'.collection.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status':'local_collector_busy'}),flush=True);return
        # Also serialize against all OpenRouter collectors: one inference at a time.
        with (ROOT/'openrouter-space-bunny-alpha/.collection.lock').open('a') as global_lock:
            fcntl.flock(global_lock,fcntl.LOCK_EX)
            for item in plan['requests']:
                out=ROOT/'ceiling-local'/item['model'].replace(':','-');out.mkdir(parents=True,exist_ok=True);prefix=out/item['task']
                if any(Path(str(prefix)+s).exists() for s in ('-request.json','-result.json','-error.json')):continue
                verify()
                tags={m['name']:m for m in api('tags')['models']};tag=tags.get(item['model'])
                if tag is None or tag['digest']!=item['digest'] or tag['size']!=item['artifact_bytes']:
                    print(json.dumps({'status':'missing_or_changed_artifact','model':item['model']}),flush=True);return
                metadata=api('show',{'model':item['model']})
                contexts=[v for k,v in metadata.get('model_info',{}).items() if k.endswith('.context_length') and isinstance(v,int)]
                if not contexts or max(contexts)<item['body']['options']['num_ctx']:
                    print(json.dumps({'status':'unsupported_or_unknown_native_context','model':item['model']}),flush=True);return
                Path(str(prefix)+'-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
                if api('ps')['models']:
                    print(json.dumps({'status':'another_model_loaded'}),flush=True);return
                memory=subprocess.run(['/usr/bin/memory_pressure','-Q'],capture_output=True,text=True,timeout=10)
                match=re.search(r'System-wide memory free percentage:\s*(\d+)%',memory.stdout)
                if memory.returncode or not match or int(match[1])<plan['memory_free_percentage_floor']:
                    print(json.dumps({'status':'low_or_unknown_memory_headroom'}),flush=True);return
                Path(str(prefix)+'-request.json').write_text(json.dumps(item,indent=2)+'\n');start=time.monotonic();samples=[]
                try:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future=pool.submit(api,'chat',item['body'])
                        while not future.done():
                            try:samples.extend({k:m.get(k) for k in ('name','size','size_vram','context_length')} for m in api('ps')['models'] if m.get('name')==item['model'])
                            except Exception:pass
                            time.sleep(1)
                        result=future.result()
                    result.update(wall_seconds=time.monotonic()-start,memory_samples=samples,preflight_memory_free_percentage=int(match[1]),sampling_note='Ollama allocation samples, not complete machine peak/RSS or swap measurements')
                    Path(str(prefix)+'-result.json').write_text(json.dumps(result,indent=2)+'\n')
                    Path(str(prefix)+'-response.txt').write_text(result.get('message',{}).get('content') or '')
                    print(json.dumps({'model':item['model'],'task':item['task'],'status':'collected','seconds':result['wall_seconds'],'finish':result.get('done_reason')}),flush=True)
                    # Keepalive0 can take a short moment to unload our completed request.
                    for _ in range(10):
                        if not api('ps')['models']:break
                        time.sleep(1)
                except Exception as exc:
                    error={'type':type(exc).__name__,'wall_seconds':time.monotonic()-start,'http_status':getattr(exc,'code',None)}
                    if hasattr(exc,'read'):error['bounded_server_error']=exc.read(4096).decode(errors='replace')
                    Path(str(prefix)+'-error.json').write_text(json.dumps(error,indent=2)+'\n');print(json.dumps({'status':'error_preserved_no_retry',**error}),flush=True);return
            print(json.dumps({'status':'collection_complete'}),flush=True)

if __name__=='__main__':main()
