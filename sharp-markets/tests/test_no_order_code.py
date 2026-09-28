"""Paper-only guard: no order-placement code or non-GET HTTP anywhere in the package."""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "markets"
FORBIDDEN = [
    r"\.(post|put|patch|delete)\(",          # requests/session write verbs
    r"method\s*=\s*['\"](POST|PUT|PATCH|DELETE)",
    r"/portfolio/",                           # Kalshi account / order endpoints
    r"['\"]/orders",
    r"create_order|place_order|amend_order|cancel_order|batch_orders",
    r"import\s+pmxt|from\s+pmxt|agenttrader",
]


def test_no_order_placement_code():
    hits = []
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        for pat in FORBIDDEN:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                hits.append(f"{path.relative_to(SRC)}: {m.group(0)}")
    assert not hits, "order-placement / write-HTTP code found:\n" + "\n".join(hits)


def test_kalshi_client_is_get_only():
    from markets.kalshi.client import KalshiClient
    public = [n for n in dir(KalshiClient) if not n.startswith("_")]
    assert not [n for n in public if "order" in n.lower() or "position" in n.lower()]
