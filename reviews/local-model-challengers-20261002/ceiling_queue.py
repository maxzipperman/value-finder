"""Declared sequential ceiling queue; only exact frozen synthetic requests."""
from ceiling_local import main as local, api
from ceiling_verify import verify,ROOT
from openrouter_free import main as free
from openrouter_paid import main as paid

if __name__=='__main__':
    local()
    if api('ps')['models']:
        raise SystemExit('Local model still loaded/possibly running; cloud phases deferred, no unload')
    manifest=verify();digest=manifest['sha256']['ceiling-api-requests.json']
    free(request_file='ceiling-api-requests.json',list_hash=digest,output='ceiling-space-bunny',count=3,token_cap=65536,ceiling=True)
    folder=ROOT/'ceiling-space-bunny'
    if any(not (folder/(task+'-result.json')).exists() or (folder/(task+'-error.json')).exists() for task in ('implementation','review','regression')):
        raise SystemExit('Free ceiling phase incomplete/error; paid phase deferred, no competing uncertain call')
    paid(request_file='ceiling-api-requests.json',list_hash=digest,output='openrouter-ceiling',token_cap=65536,ceiling=True)
