import importlib.util,json
from pathlib import Path
from unittest.mock import patch
p=Path('/private/tmp/vf-stage-policy-fix/strategy-research/coverage-pass-execution-v1/bootstrap.py')
s=importlib.util.spec_from_file_location('offline_launch_probe',p);b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
packet=Path('/private/tmp/vf-coverage-pilot/strategy-research/coverage-pass-execution-v1/passing-execution-reserve-fix');root='22248e70d445679b488f7900acec69f8e22de957ddf88431ad785f99e61f8935'
seen=[]
class BoundaryReached(Exception):pass
def blocked(name):
 def call(*a,**k):seen.append(name);raise AssertionError('forbidden offline action:'+name)
 return call
def authority_boundary(*a,**k):seen.append('authority_boundary');raise BoundaryReached()
try:
 runner,base,data,source,load=b.verified(packet,root);m=load('orchestration')
 with patch.object(m.authority,'check',authority_boundary),patch.object(base,'register_runtime',blocked('registration')):
  try:m.run(packet,root,None,{},key_factory=blocked('key'),http_factory=blocked('http'))
  except BoundaryReached:result=dict(status='reached_pre_runtime_authority_boundary',calls=seen,diagnosis='No source/bootstrap/checkout/runtime-path failure reproduced before authority boundary. Real authorization/provider/launcher state deliberately not inspected.',runtime_writes=0,paid_calls=0)
except Exception as e:result=dict(status='offline_pre_runtime_failure',exception_type=type(e).__name__,message=str(e),calls=seen,runtime_writes=0,paid_calls=0)
assert not {'registration','key','http'}&set(seen)
Path('/private/tmp/vf-stage-policy-fix/reviews/passing-stage-policy-fix/launch-probe.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
