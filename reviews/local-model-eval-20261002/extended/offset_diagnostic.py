"""Supplemental post-inference diagnostic; run in the default sandbox."""
import json
import re
from datetime import datetime, timezone, timedelta
from expanded import ROOT, validated
from real_helper import oracle

def generic_offset_bug(value):
    if isinstance(value,str):
        try:
            parsed=datetime.fromisoformat(value.strip().replace('Z','+00:00'))
            if parsed.utcoffset() not in (None,timedelta(0)):
                return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return oracle(value)

assert generic_offset_bug('2025-01-01T07:00:00-04:00')!=oracle('2025-01-01T07:00:00-04:00')
for model in ['qwen3.6-35b','qwen3-coder-30b','devstral-small-2-latest','glm-4.7-flash-latest']:
    source=(ROOT/model/'real-helper-response.txt').read_text()
    blocks=re.findall(r'```(?:python)?\s*\n(.*?)```',source,re.S)
    try:
        namespace={}
        exec(validated('\n'.join(blocks) if blocks else source,{'datetime','math'}),namespace)
        suite=namespace['run_tests'];suite(oracle)
        try:
            suite(generic_offset_bug);caught=False;error=None
        except Exception as e:
            caught=True;error=f'{type(e).__name__}: {e}'
        result=dict(correct_accepted=True,generic_offset_bug_detected=caught,error=error)
    except Exception as e:
        result=dict(correct_accepted=False,generic_offset_bug_detected=None,error=f'{type(e).__name__}: {e}')
    (ROOT/model/'generic-offset-diagnostic.json').write_text(json.dumps(result,indent=2))
    print(model,result)
