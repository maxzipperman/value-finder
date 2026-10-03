"""Cache-first raw response store: data/raw/{sport}/{source}/{date}/{cache_key}.parquet.

Every HTTP response is persisted (one row per file, body kept verbatim) *before* it is used.
Lookups ignore the date directory, so a rerun on any day finds the cached file and never re-fetches.
Secrets (e.g. apiKey) are stripped from the stored params and the cache key.

Dated sources (`dated_sources`) are the exception: their requests are keyed to one date (the forward
collector's tick), so get_or_fetch looks only in that date's directory. That keeps a once-a-minute
process from listing a source's whole, ever-growing history on every run.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pyarrow as pa
import pyarrow.parquet as pq

from .settings import RAW_DIR, utcnow

SECRET_PARAMS = {"apiKey", "api_key", "key"}
KEPT_HEADERS = ("x-requests-remaining", "x-requests-used", "x-requests-last", "content-type")

SCHEMA = pa.schema([
    ("cache_key", pa.string()),
    ("sport", pa.string()),
    ("source", pa.string()),
    ("data_date", pa.string()),
    ("url", pa.string()),
    ("params_json", pa.string()),
    ("fetched_at", pa.timestamp("us", tz="UTC")),
    ("http_status", pa.int32()),
    ("headers_json", pa.string()),
    ("body", pa.large_string()),
])


class CacheMiss(RuntimeError):
    pass


@dataclass
class Fetched:
    status: int
    headers: dict
    body: str
    observed_at: datetime | None = None


def public_params(params: dict) -> dict:
    return {k: v for k, v in sorted(params.items()) if k not in SECRET_PARAMS and v is not None}


def cache_key(source: str, url: str, params: dict) -> str:
    blob = json.dumps({"source": source, "url": url, "params": public_params(params)}, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:20]


class RawCache:
    def __init__(self, raw_dir: Path = RAW_DIR, offline: bool = False, dated_sources: frozenset[str] = frozenset()):
        self.raw_dir = Path(raw_dir)
        self.offline = offline
        self.dated_sources = frozenset(dated_sources)
        self.stats: Counter = Counter()
        self._index: dict[tuple, dict[str, Path]] = {}

    def _source_index(self, sport: str, source: str, data_date: str | None = None) -> dict[str, Path]:
        """key -> path for a source: every date directory, or just `data_date`'s when given."""
        key = (sport, source) if data_date is None else (sport, source, data_date)
        if key not in self._index:
            idx: dict[str, Path] = {}
            base = self.raw_dir / sport / source
            if base.exists():
                for p in base.glob("*/*.parquet" if data_date is None else f"{data_date}/*.parquet"):
                    idx[p.stem] = p
            self._index[key] = idx
        return self._index[key]

    def lookup(self, sport: str, source: str, key: str) -> Path | None:
        return self._source_index(sport, source).get(key)

    def get_or_fetch(self, *, sport: str, source: str, data_date: str, url: str, params: dict,
                     fetch: Callable[[], Fetched], key_extra: dict | None = None,
                     cache_statuses: tuple[int, ...] = (200, 404), refresh: bool = False) -> dict:
        """Return the stored record (dict) for this request, fetching and persisting it on a miss.

        `key_extra` is folded into the cache key and stored params but never sent to the server
        (e.g. an `as_of` label for listings, or the market ticker for path-parameter endpoints).
        `refresh` fetches even on a hit; the new answer replaces the stored one only if its status is in
        `cache_statuses` (the bulk puller's --retry-404 passes (200,), so a 404 is replaced only by a 200).
        """
        params = {**params, **(key_extra or {})}
        key = cache_key(source, url, params)
        dated = data_date if source in self.dated_sources else None
        hit = None if refresh else self._source_index(sport, source, dated).get(key)
        if hit is not None:
            self.stats[f"hit:{source}"] += 1
            return read_record(hit)
        if self.offline:
            raise CacheMiss(f"{source} {url} {public_params(params)} not cached (offline mode)")
        res = fetch()
        self.stats[f"http:{source}"] += 1
        record = {
            "cache_key": key,
            "sport": sport,
            "source": source,
            "data_date": data_date,
            "url": url,
            "params_json": json.dumps(public_params(params), sort_keys=True, default=str),
            "fetched_at": res.observed_at if res.observed_at is not None else utcnow(),
            "http_status": res.status,
            "headers_json": json.dumps({h: res.headers.get(h) for h in KEPT_HEADERS if res.headers.get(h) is not None}),
            "body": res.body,
        }
        if res.status in cache_statuses:
            path = self.raw_dir / sport / source / data_date / f"{key}.parquet"
            write_record(path, record)
            self._source_index(sport, source, dated)[key] = path
        return record

    @property
    def http_requests(self) -> int:
        return sum(v for k, v in self.stats.items() if k.startswith("http:"))


def write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist([record], schema=SCHEMA), tmp, compression="zstd")
    os.replace(tmp, path)


def read_record(path: Path) -> dict:
    return pq.read_table(path).to_pylist()[0]


def read_status(path: Path) -> int:
    """A stored record's HTTP status alone (faster than read_record: the body isn't read)."""
    return pq.read_table(path, columns=["http_status"]).column(0)[0].as_py()


def body_json(record: dict):
    return json.loads(record["body"]) if record.get("body") else None
