"""Start a verified lab run, or resume the newest interrupted run."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
PYTHON=Path('/Users/maxzipperman/code/value-finder/nfl-weather/.venv/bin/python')

def main():
    lock=json.loads((HERE/'frozen_files.json').read_text())
    for name,expected in lock.items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=expected:
            raise SystemExit(f'Frozen file changed: {name}. Review and version the study before running.')
    mode=sys.argv[1] if len(sys.argv)>1 else 'run'
    if mode not in ['run','resume','preflight']:
        raise SystemExit('Use run, resume, or preflight.')
    args=[str(PYTHON),str(HERE/'runner.py'),mode,'--protocol-hash',lock['protocol.json'],'--workers','2']
    if mode=='resume':
        manifests=sorted((HERE/'runs').glob('*/manifest.json'),reverse=True)
        candidates=[p for p in manifests if json.loads(p.read_text()).get('status') in ['failed','interrupted','running']]
        if not candidates:
            raise SystemExit('No incomplete run to resume.')
        previous=json.loads(candidates[0].read_text())
        args+=['--run-dir',str(candidates[0].parent),'--prior-project-count',str(previous['project_count']-20)]
    elif len(sys.argv)>2:
        args+=['--prior-project-count',str(int(sys.argv[2]))]
    env=os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    print('Running on this Mac. Historical discovery only; outputs stay in the research lab.',flush=True)
    command=['/usr/bin/caffeinate','-i']+args if Path('/usr/bin/caffeinate').exists() else args
    raise SystemExit(subprocess.call(command,cwd=HERE,env=env))

if __name__=='__main__':
    main()
