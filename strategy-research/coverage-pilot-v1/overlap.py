"""Read-only semantic overlap check, metadata columns only; no quote/outcome use."""
import json
from pathlib import Path
import capture
from timing import utc


def query(row):
    params=row['params']
    if row['source']=='oddsapi/hist_event_markets':
        return (row['sport'],row['source'],row['url'],utc(params['date'])),set(),set()
    if set(params)-{'date','dateFormat','oddsFormat','bookmakers','markets'}:
        raise ValueError('unreviewed overlapping query filters')
    if params.get('dateFormat','iso')!='iso' or params.get('oddsFormat','decimal')!='decimal':
        raise ValueError('unreviewed overlapping query format')
    books=params.get('bookmakers','').split(',');markets=params.get('markets','').split(',')
    if not all(books) or not all(markets):raise ValueError('explicit book/market panel required')
    return (row['sport'],row['source'],row['url'],utc(params['date'])),set(books),set(markets)


def check(rows, raw_roots, *, expected_inventory_sha256):
    import pyarrow as pa
    import pyarrow.parquet as pq
    targets=[query(r) for r in rows]
    seen={};roots=[Path(p).absolute() for p in raw_roots]
    if len(roots)!=len(set(roots)):raise ValueError('duplicate raw roots')
    for root in roots:
        if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('symlink raw root')
        for sport in ('americanfootball_nfl','americanfootball_ncaaf'):
            for source in ('oddsapi/hist_odds','oddsapi/hist_event_odds','oddsapi/hist_event_markets'):
                for path in (root/sport/source).glob('*/*.parquet'):
                    # Historical metadata projection only; never open sealed2026season files.
                    if not '2020-01-01'<=path.parent.name<'2026-02-10':continue
                    raw=capture.regular(path);seen[str(path)]=capture.digest(raw)
                    records=pq.read_table(pa.BufferReader(raw),columns=['sport','source','url','params_json']).to_pylist()
                    if len(records)!=1:raise ValueError('ambiguous cache metadata')
                    rec=records[0];rec['params']=json.loads(rec.pop('params_json'))
                    # Only compare exact event/sport/source/time before interpreting filters.
                    key=(rec['sport'],rec['source'],rec['url'],utc(rec['params']['date']))
                    for target,books,markets in targets:
                        if key!=target:continue
                        _,prior_books,prior_markets=query(rec)
                        if rec['source']=='oddsapi/hist_event_markets' or (books & prior_books and markets & prior_markets):
                            raise ValueError('previously requested market cells overlap; never repurchase')
    fingerprint=capture.identity(seen)
    if fingerprint!=expected_inventory_sha256:raise ValueError('frozen raw inventory changed')
    return fingerprint
