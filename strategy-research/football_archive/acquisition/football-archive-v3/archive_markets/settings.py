"""Paths, environment, and UTC helpers."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(os.environ.get("MARKETS_ROOT", Path(__file__).resolve().parents[2]))
CONFIG_DIR = ROOT / "config"
DATA_DIR = Path(os.environ.get("MARKETS_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "markets.duckdb"
REPORTS_DIR = Path(os.environ.get("MARKETS_REPORTS_DIR", ROOT / "reports"))

load_dotenv(ROOT / ".env")


def env(name: str, required: bool = True) -> str | None:
    val = (os.environ.get(name) or "").strip()
    if required and not val:
        raise SystemExit(f"{name} is not set. Add it to {ROOT / '.env'} (see .env.example).")
    return val or None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime."""
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
