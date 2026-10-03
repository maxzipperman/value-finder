"""Declared untouched MiMo stress subset after terminal GLM429; no retries."""
from ceiling_verify import verify
from ceiling_local import api
from openrouter_paid import main
if __name__=='__main__':
    manifest=verify()
    if api('ps')['models']:
        raise SystemExit('Local model busy/loaded; defer without unloading')
    main(request_file='ceiling-api-requests.json',list_hash=manifest['sha256']['ceiling-api-requests.json'],output='openrouter-ceiling',token_cap=65536,ceiling=True,ceiling_mimo_only=True)
