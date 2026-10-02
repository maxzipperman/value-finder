"""Packaging-only diagnostic; execute separately in the default sandbox."""
import json
import re
from expanded import ROOT, grade

for model in ['qwen3.6-35b','qwen3-coder-30b','devstral-small-2-latest','glm-4.7-flash-latest']:
    response=(ROOT/model/'multifile-response.txt').read_text()
    blocks=re.findall(r'```json\s*\n(.*?)```',response,re.S)
    text=blocks[0] if blocks else response.strip()
    decoder=json.JSONDecoder();files={};position=0
    while position<len(text):
        while position<len(text) and text[position] in ' \t\r\n,':position+=1
        if position==len(text):break
        obj,end=decoder.raw_decode(text,position)
        assert isinstance(obj,dict) and not set(obj)&set(files)
        files.update(obj);position=end
    (ROOT/model/'multifile-packaging-diagnostic.json').write_text(json.dumps({
        'method':'extract first JSON fence if present; merge disjoint consecutive top-level objects; no source edits',
        'files':files},indent=2))
    checks=grade('multifile',json.dumps(files))
    (ROOT/model/'multifile-diagnostic-acceptance.json').write_text(json.dumps(checks,indent=2))
    print(model,sum(c['passed'] for c in checks),len(checks))
