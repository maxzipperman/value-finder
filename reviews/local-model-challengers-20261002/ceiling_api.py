"""Frozen synthetic ceiling requests; shared API lock, zero/paid guards retained."""
import sys
from ceiling_verify import verify,ROOT
from openrouter_free import main as free
from openrouter_paid import main as paid

if __name__=='__main__':
    manifest=verify();digest=manifest['sha256']['ceiling-api-requests.json']
    if sys.argv[1:] == ['free']:
        free(request_file='ceiling-api-requests.json',list_hash=digest,output='ceiling-space-bunny',count=3,token_cap=65536,ceiling=True)
    elif sys.argv[1:] == ['paid']:
        paid(request_file='ceiling-api-requests.json',list_hash=digest,output='openrouter-ceiling',token_cap=65536,ceiling=True)
    else:raise SystemExit('Specify free or paid; no implicit inference')
