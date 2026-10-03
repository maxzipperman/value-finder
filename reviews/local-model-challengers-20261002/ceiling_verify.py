"""Verify whole-artifact stress freeze before inference; no credentials/inference."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FREEZE_HASH="265b3cf10c20b32e22f988da3ccb4a2cc53fbfe586f97d218bc5f348b7540c21"
def verify():
    raw=(ROOT/'ceiling/freeze.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FREEZE_HASH:raise RuntimeError('ceiling manifest changed')
    manifest=json.loads(raw)
    for name,digest in manifest['sha256'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('ceiling artifact changed: '+name)
    return manifest
