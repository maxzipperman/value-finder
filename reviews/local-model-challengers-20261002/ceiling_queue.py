"""Declared sequential ceiling queue; only exact frozen synthetic requests."""
from ceiling_local import main as local
from ceiling_verify import verify
from openrouter_free import main as free
from openrouter_paid import main as paid

if __name__=='__main__':
    local()
    manifest=verify();digest=manifest['sha256']['ceiling-api-requests.json']
    free(request_file='ceiling-api-requests.json',list_hash=digest,output='ceiling-space-bunny',count=3,token_cap=65536,ceiling=True)
    paid(request_file='ceiling-api-requests.json',list_hash=digest,output='openrouter-ceiling',token_cap=65536,ceiling=True)
