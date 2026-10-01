"""Restore ignored probe fixtures by frozen byte hash, never by an API purchase."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-bundle', required=True, type=Path)
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    source = args.from_bundle.resolve()
    source_hashes = {}
    for path in source.rglob('*.parquet'):
        source_hashes[digest(path)] = path
    copied = 0
    for name in ('football-archive-v3', 'football-archive-v4'):
        bundle = base/'acquisition'/name
        cert = json.loads((bundle/'FREEZE.json').read_text())
        for rel, expected in cert['file_sha256'].items():
            if not rel.endswith('.parquet'):
                continue
            target = bundle/rel
            if target.exists():
                if digest(target) != expected:
                    raise SystemExit('Existing fixture changed; refuse replacement: '+rel)
                continue
            original = source_hashes.get(expected)
            if original is None:
                raise SystemExit('Required frozen probe fixture absent: '+rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            if digest(target) != expected:
                raise SystemExit('Fixture copy hash mismatch: '+rel)
            copied += 1
    print(json.dumps({'local_fixture_copies':copied, 'API_calls':0}))


if __name__ == '__main__':
    main()
