"""H3: closing betting splits at one retail book (BetMGM), NBA. The registered test.

Data: Kaggle caseydurfee/mgm-grand-nba-betting-data (CC BY-SA 4.0), one file, all_odds.csv.
Registration: docs/H3_KAGGLE_PREREGISTRATION.md, committed and pushed before the file was downloaded.
Question: at BetMGM's close, does the split between tickets and money say anything the book's own closing price
hasn't already priced in? 14 variants (families A, B and C); games after 2026-01-31 are left out of everything.

Credentials, in this order: the environment variable KAGGLE_API_TOKEN; the file ~/.kaggle/access_token (refused if
other users can read it); KAGGLE_USERNAME and KAGGLE_KEY from .env (basic auth). The credential is read at run time,
goes into one request header for www.kaggle.com and nowhere else: redirects are followed by hand and any other host
gets no credential. Failures print one plain line with the status code and never the credential or a signed address.
GET only.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import os
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote, urljoin, urlsplit

import numpy as np
import requests
from scipy import stats as sps

from ..settings import RAW_DIR, REPORTS_DIR, env, utcnow

DATASET = "caseydurfee/mgm-grand-nba-betting-data"
KAGGLE_HOST = "www.kaggle.com"
API = f"https://{KAGGLE_HOST}/api/v1"
MAX_REDIRECTS = 5
TIMEOUT_S = 120
_TOKEN_CHARS = re.compile(r"[\x21-\x7e]+")           # visible ASCII only: no spaces or line breaks inside a token

# ---- the registration (docs/H3_KAGGLE_PREREGISTRATION.md); changing any of these is a dated amendment ----
CUTOFF = date(2026, 1, 31)                           # config/backtest.yaml splits.train_end; later games untouched
SEASONS = ("2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
MARKETS = ("money", "spread", "total")
MARKET_LABEL = {"money": "moneyline", "spread": "spread", "total": "total"}
SIDES = {"money": ("home", "away"), "spread": ("home", "away"), "total": ("over", "under")}
THRESHOLDS = (5, 10, 15)                             # family A: money share minus ticket share, points
FADE_MAX_TICKETS = 30                                # family C: back the side with this share of tickets or fewer
FADE_MARKETS = ("spread", "total")
MAX_MARGIN = 0.20                                    # a margin below 0 or above this is a missing figure
N_VARIANTS = len(MARKETS) * len(THRESHOLDS) + len(MARKETS) + len(FADE_MARKETS)     # 9 + 3 + 2 = 14
PRIOR_COUNT = 273
RUNNING_COUNT = PRIOR_COUNT + N_VARIANTS             # 287
BAR = 0.05 / RUNNING_COUNT                           # 0.000174
SEASONS_NEEDED = 4                                   # same sign in at least 4 of the 5 seasons
Z_BAR = float(sps.norm.isf(BAR / 2))                 # about 3.75: the smallest detectable effect is Z_BAR standard errors
REPORT_NAME = "h3_kaggle_mgm.md"
HAND_SECTION = "## Football splits on Kaggle"        # written by hand from metadata; kept when the run rewrites the report


# ================================================================ credentials and HTTP

class _Credential(NamedTuple):
    headers: dict
    basic: tuple | None
    secrets: tuple                                   # every string that must never be shown

    def __repr__(self) -> str:                       # never shows the credential, even in a debugger or a traceback
        return "_Credential(<hidden>)"

    __str__ = __repr__


def token_file() -> Path:
    return Path.home() / ".kaggle" / "access_token"


def _credential() -> _Credential:
    """The Kaggle credential, read at run time. Never printed, logged or written anywhere."""
    tok, where = (os.environ.get("KAGGLE_API_TOKEN") or "").strip(), "KAGGLE_API_TOKEN"
    if not tok:
        path = token_file()
        if path.is_file():
            if path.stat().st_mode & 0o077:
                raise SystemExit(f"Refusing to use {path}: other users on this computer can read or change it. "
                                 f"Run 'chmod 600 {path}' and try again.")
            tok, where = path.read_text().strip(), str(path)
    if tok:
        if not _TOKEN_CHARS.fullmatch(tok):
            raise SystemExit(f"The Kaggle token in {where} has spaces, line breaks or other unexpected characters "
                             "inside it, so it was not sent.")
        return _Credential({"Authorization": f"Bearer {tok}"}, None, (tok,))
    user, key = env("KAGGLE_USERNAME", required=False), env("KAGGLE_KEY", required=False)
    if user and key:
        return _Credential({}, (user, key), (key, base64.b64encode(f"{user}:{key}".encode()).decode()))
    raise SystemExit("No Kaggle credential found: set KAGGLE_API_TOKEN, put the token in ~/.kaggle/access_token "
                     "(mode 600), or set KAGGLE_USERNAME and KAGGLE_KEY in .env.")


def _scrub(text: str, cred: _Credential) -> str:
    for s in cred.secrets:
        if s:
            text = text.replace(s, "[removed]")
    return re.sub(r"(?i)\b(bearer|basic)\s+\S+", r"\1 [removed]", text)


def _kaggle_message(r: requests.Response, cred: _Credential) -> str:
    """Kaggle's own error message from a JSON body, credential removed, one line, at most 200 characters."""
    try:
        body = r.json()
    except ValueError:
        return ""
    msg = (body.get("message") or body.get("error") or "") if isinstance(body, dict) else ""
    msg = " ".join(_scrub(str(msg), cred).split())[:200]
    return f": {msg}" if msg else ""


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False                              # no ~/.netrc credentials or proxy settings from the environment
    return s


def _get(url: str, cred: _Credential, what: str, params: dict | None = None) -> requests.Response:
    """GET, following redirects by hand. The credential goes only to https://www.kaggle.com; any other host (Kaggle
    sends downloads to a storage host at a signed address) gets no credential. The signed address is never printed
    or stored. Any failure raises SystemExit with one plain line: the status code and host, never the credential."""
    s = _session()
    for hop in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        host = parts.hostname or "?"
        if parts.scheme != "https":
            raise SystemExit(f"Kaggle {what} failed: refused to follow a redirect to a non-https address on {host}.")
        to_kaggle = host == KAGGLE_HOST
        err = None
        try:
            r = s.get(url, params=params if hop == 0 else None, headers=dict(cred.headers) if to_kaggle else {},
                      auth=cred.basic if to_kaggle else None, allow_redirects=False, timeout=TIMEOUT_S)
        except requests.RequestException as e:       # the message may hold a URL or a header: show only its kind
            err = type(e).__name__
        if err:
            raise SystemExit(f"Kaggle {what} failed: no usable response from {host} ({err}).")
        if r.is_redirect:
            url = urljoin(r.url, r.headers["location"])
            r.close()
            continue
        if r.status_code != 200:
            msg = _kaggle_message(r, cred) if to_kaggle else ""
            raise SystemExit(f"Kaggle {what} failed: HTTP {r.status_code} from {host}{msg}.")
        return r
    raise SystemExit(f"Kaggle {what} failed: more than {MAX_REDIRECTS} redirects.")


def _raw_base() -> Path:
    return RAW_DIR / "nba" / "kaggle_mgm"


def download(force: bool = False) -> bytes:
    """The dataset zip, cache first: data/raw/nba/kaggle_mgm/{date}/dataset.zip, with download.json beside it (the
    time in UTC, the size, the zip's sha256 and the dataset's name; nothing else). A rerun reads the cache."""
    existing = sorted(_raw_base().glob("*/dataset.zip"))
    if existing and not force:
        return existing[-1].read_bytes()
    cred = _credential()
    r = _get(f"{API}/datasets/download/{DATASET}", cred, "download")
    blob = r.content
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise SystemExit(f"Kaggle download failed: the response ({len(blob):,} bytes, "
                         f"{r.headers.get('content-type', 'no content type')}) is not a zip file.")
    when = utcnow().replace(microsecond=0)
    out = _raw_base() / when.date().isoformat() / "dataset.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    (out.parent / "download.json").write_text(json.dumps(
        {"dataset": DATASET, "downloaded_utc": when.isoformat().replace("+00:00", "Z"), "bytes": len(blob),
         "sha256": hashlib.sha256(blob).hexdigest()}, indent=2) + "\n")
    return blob


def download_record() -> dict | None:
    recs = sorted(_raw_base().glob("*/download.json"))
    return json.loads(recs[-1].read_text()) if recs else None


# ---- read-only metadata (issue #66, part 4): search and file lists, cached; nothing is downloaded ----

def _meta_base() -> Path:
    return RAW_DIR / "any" / "kaggle_meta"


def _meta(name: str, url: str, params: dict | None, what: str):
    hits = sorted(_meta_base().glob(f"*/{name}.json"))
    if hits:
        return json.loads(hits[-1].read_text())
    r = _get(url, _credential(), what, params=params)
    try:
        data = r.json()
    except ValueError:
        data = None
    if data is None:
        raise SystemExit(f"Kaggle {what} failed: the answer from {KAGGLE_HOST} was not JSON.")
    out =_meta_base() / utcnow().date().isoformat() / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, sort_keys=True))
    return data


def search(term: str, page: int = 1) -> list[dict]:
    """Kaggle's dataset search for one term (one page of results), cached. Metadata only."""
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
    data = _meta(f"search_{slug}_p{page}", f"{API}/datasets/list", {"search": term, "page": page}, "search")
    return data if isinstance(data, list) else data.get("datasets", [])


def dataset_files(ref: str) -> dict:
    """Kaggle's file list for one dataset (file names, sizes, and the columns where Kaggle has them), cached."""
    owner, slug = ref.split("/", 1)
    return _meta(f"files_{owner}__{slug}", f"{API}/datasets/list/{quote(owner)}/{quote(slug)}", None, "file list")


# ================================================================ the file

def load_rows(blob: bytes) -> tuple[list[dict], list[str]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        text = z.read(name).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), list(reader.fieldnames or [])


# Column names in all_odds.csv (PLAN.md section 2: *_wager_percentage = tickets, *_stake_percentage = money).
COL_DATE, COL_HOME, COL_AWAY, COL_ID = "game_date", "home_team", "away_team", "game_id"
FIELD = {"dec": "decimal_odds", "stake": "stake_percentage", "wager": "wager_percentage", "won": "won",
         "line": "points"}


def _col(market: str, side: str, what: str) -> str:
    return f"{market}_{side}_{FIELD[what]}"


def _num(v):
    try:
        x = float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _b(v):
    return {"true": True, "false": False, "1": True, "0": False, "1.0": True, "0.0": False,
            "yes": True, "no": False}.get(str(v).strip().lower())


def _date(v):
    """The file's game date. all_odds.csv writes it as '2021-10-19-10:00' (the same date as in the game id, on every
    row); the first ten characters are the date."""
    s = str(v or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:$|[-T ])", s)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            return None
    for fmt in ("%m/%d/%Y",):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def season_of(d: date) -> str:
    y = d.year if d.month >= 8 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def _american_to_decimal(x):
    if x is None or x == 0:
        return None
    return 1 + x / 100 if x > 0 else 1 + 100 / abs(x)


def parse_games(rows: list[dict], teams) -> tuple[list[dict], dict]:
    """Rows -> games dated on or before the cut-off, plus counts about the whole file. Rows after the cut-off are
    counted and nothing else: their results and splits are never read."""
    info = {"n_rows": len(rows), "bad_date": 0, "after_cutoff": 0, "after_cutoff_by_season": Counter(),
            "unknown_teams": Counter(), "exact_duplicate_rows": 0}
    kept, seen_rows = [], Counter()
    for r in rows:
        d = _date(r.get(COL_DATE))
        if d is None:
            info["bad_date"] += 1
            continue
        if d > CUTOFF:
            info["after_cutoff"] += 1
            info["after_cutoff_by_season"][season_of(d)] += 1
            continue
        sig = tuple(sorted((str(key), str(val)) for key, val in r.items()))
        info["exact_duplicate_rows"] += seen_rows[sig] > 0
        seen_rows[sig] += 1
        kept.append((d, r))
    columns = list(rows[0].keys()) if rows else []
    info["constant_columns"] = {c: vals.pop() for c in columns
                                if len(vals := {str(r.get(c)) for _, r in kept}) == 1} if kept else {}
    share_cols = [_col(m, s, w) for m in MARKETS for s in SIDES[m] for w in ("stake", "wager")]
    shares = [x for _, r in kept for c in share_cols if (x := _num(r.get(c))) is not None]
    info["share_scale"] = 100.0 if shares and max(shares) <= 1.0 else 1.0
    prices = [x for _, r in kept for m in MARKETS for s in SIDES[m] if (x := _num(r.get(_col(m, s, "dec")))) is not None]
    info["american_prices"] = bool(prices) and min(prices) < 0
    games = []
    for d, r in kept:
        home, away = teams.from_name(r.get(COL_HOME)), teams.from_name(r.get(COL_AWAY))
        for name, code in ((r.get(COL_HOME), home), (r.get(COL_AWAY), away)):
            if code is None:
                info["unknown_teams"][str(name)] += 1
        g = {"key": r.get(COL_ID), "date": d, "season": season_of(d), "home": home, "away": away,
             "names": (r.get(COL_HOME), r.get(COL_AWAY)), "pregame": r.get("pregame_odds"), "m": {}}
        digits = re.sub(r"\D", "", str(r.get(COL_ID) or ""))
        info["id_date_checked"] = info.get("id_date_checked", 0) + bool(digits)
        info["id_date_differs"] = info.get("id_date_differs", 0) + (bool(digits) and
                                                                     not digits.startswith(d.strftime("%Y%m%d")))
        for m in MARKETS:
            g["m"][m] = {}
            for s in SIDES[m]:
                dec = _num(r.get(_col(m, s, "dec")))
                if info["american_prices"]:
                    dec = _american_to_decimal(dec)
                st, wg = _num(r.get(_col(m, s, "stake"))), _num(r.get(_col(m, s, "wager")))
                g["m"][m][s] = {"dec": dec, "stake": None if st is None else st * info["share_scale"],
                                "wager": None if wg is None else wg * info["share_scale"],
                                "won": _b(r.get(_col(m, s, "won"))), "line": _num(r.get(_col(m, s, "line"))),
                                "american": _num(r.get(f"{m}_{s}_odds"))}
        games.append(g)
    return games, info


def market_records(games: list[dict], market: str) -> tuple[list[dict], Counter]:
    """One record per game with every figure of this market present and decided; the rest counted by reason."""
    s1, s2 = SIDES[market]
    recs, excl = [], Counter()
    for g in games:                     # team names play no part in the test: an unresolved name only loses its code
        a, b = g["m"][market][s1], g["m"][market][s2]
        if any(v is None for o in (a, b) for v in (o["dec"], o["stake"], o["wager"], o["won"])) \
                or a["dec"] <= 1 or b["dec"] <= 1:
            excl["missing figure"] += 1
            continue
        margin = 1 / a["dec"] + 1 / b["dec"] - 1
        if margin < 0 or margin > MAX_MARGIN:
            excl["margin below 0% or above 20%"] += 1
            continue
        if a["won"] and b["won"]:
            excl["both sides marked won"] += 1
            continue
        if not a["won"] and not b["won"]:
            excl["push"] += 1
            continue
        fair_a = (1 / a["dec"]) / (1 / a["dec"] + 1 / b["dec"])
        sides = {}
        for s, o, fair in ((s1, a, fair_a), (s2, b, 1 - fair_a)):
            sides[s] = {"fair": fair, "won": int(bool(o["won"])), "dec": o["dec"], "div": o["stake"] - o["wager"],
                        "wager": o["wager"]}
        recs.append({"date": g["date"], "season": g["season"], "sides": sides})
    return recs, excl


def _bet(rec: dict, side: str) -> dict:
    o = rec["sides"][side]
    return {"date": rec["date"], "season": rec["season"], "fair": o["fair"], "won": o["won"], "dec": o["dec"]}


def pick_bets(recs: list[dict], market: str, rule) -> tuple[list[dict], int]:
    """One bet per game on the side the rule picks. A game where both sides qualify is left out and counted."""
    bets, both = [], 0
    for r in recs:
        q = [s for s in SIDES[market] if rule(r["sides"][s])]
        if len(q) == 2:
            both += 1
        elif q:
            bets.append(_bet(r, q[0]))
    return bets, both


def _p_two_sided(est: float, se: float, df: int) -> float:
    if not (se > 0) or df < 1:
        return float("nan")
    return float(2 * sps.t.sf(abs(est) / se, df))


def _blank(n: int, G: int) -> dict:
    nan = float("nan")
    return {"n": n, "win_rate": nan, "mean_fair": nan, "est": nan, "se_plain": nan, "se_grouped": nan, "G": G,
            "wider": "none", "se": nan, "df": 0, "p": nan, "roi": nan, "detectable": nan, "sd_div10": nan}


def mean_test(bets: list[dict]) -> dict:
    """Families A and C: mean of (won - fair) with the wider of the plain and the grouped-by-date standard error."""
    n, G = len(bets), len({b["date"] for b in bets})
    out = _blank(n, G)
    if n == 0:
        return out
    r = np.array([b["won"] - b["fair"] for b in bets], dtype=float)
    m = float(r.mean())
    out.update(win_rate=float(np.mean([b["won"] for b in bets])), mean_fair=float(np.mean([b["fair"] for b in bets])),
               est=m, roi=float(np.mean([(b["dec"] - 1) if b["won"] else -1.0 for b in bets])),
               detectable=Z_BAR * 0.5 / math.sqrt(n))
    if n < 2:
        return out
    out["se_plain"] = float(r.std(ddof=1) / math.sqrt(n))
    if G >= 2:
        sums = defaultdict(float)
        for b, x in zip(bets, r):
            sums[b["date"]] += x - m
        out["se_grouped"] = math.sqrt(G / (G - 1) * sum(v * v for v in sums.values()) / n ** 2)
    return _pick_wider(out, df_plain=n - 1, df_grouped=G - 1)


def _pick_wider(out: dict, df_plain: int, df_grouped: int) -> dict:
    sp, sg = out["se_plain"], out["se_grouped"]
    if math.isnan(sg) or sp > sg * (1 + 1e-9):
        out.update(wider="plain", se=sp, df=df_plain)
    elif sg > sp * (1 + 1e-9):
        out.update(wider="grouped", se=sg, df=df_grouped)
    else:
        out.update(wider="equal", se=sp, df=min(df_plain, df_grouped))
    out["p"] = _p_two_sided(out["est"], out["se"], out["df"])
    return out


def _ols(y, x, bins, groups):
    """OLS of y on [1, x, tenth-of-fair-chance dummies]: the x coefficient, its HC1 and grouped standard errors."""
    y, x, bins = np.asarray(y, float), np.asarray(x, float), np.asarray(bins)
    present = sorted(set(bins.tolist()))
    X = np.column_stack([np.ones(len(y)), x, *[(bins == q).astype(float) for q in present[1:]]])
    n, kk = X.shape
    if n <= kk or np.ptp(x) == 0:
        return None
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta
    hc1 = XtX_inv @ ((X * e[:, None] ** 2).T @ X) @ XtX_inv * n / (n - kk)
    keys = {g: i for i, g in enumerate(dict.fromkeys(groups))}
    G = len(keys)
    S = np.zeros((G, kk))
    np.add.at(S, np.array([keys[g] for g in groups]), X * e[:, None])
    se_g = float("nan")
    if G > 1:
        cr1 = XtX_inv @ (S.T @ S) @ XtX_inv * (G / (G - 1)) * ((n - 1) / (n - kk))
        se_g = float(math.sqrt(max(cr1[1, 1], 0)))
    return {"coef": float(beta[1]), "se_hc1": float(math.sqrt(max(hc1[1, 1], 0))), "se_grouped": se_g,
            "n": n, "k": kk, "G": G}


def regression_test(recs: list[dict], market: str) -> dict:
    """Family B: (won - fair) for the home side (the over) on its divergence per 10 points, with fair-chance tenths."""
    s1 = SIDES[market][0]
    rows = [(r["sides"][s1], r["date"], r["season"]) for r in recs]
    y = [o["won"] - o["fair"] for o, _, _ in rows]
    x = [o["div"] / 10 for o, _, _ in rows]
    bins = [min(int(o["fair"] * 10), 9) for o, _, _ in rows]
    dates = [d for _, d, _ in rows]
    out = _blank(len(rows), len(set(dates)))
    out["season"] = {s: (None, sum(1 for _, _, se_ in rows if se_ == s)) for s in SEASONS}
    if rows:
        out.update(win_rate=float(np.mean([o["won"] for o, _, _ in rows])),
                   mean_fair=float(np.mean([o["fair"] for o, _, _ in rows])))
    fit = _ols(y, x, bins, dates)
    if fit is None:
        return out
    sd = float(np.std(x, ddof=1))
    out.update(est=fit["coef"], se_plain=fit["se_hc1"], se_grouped=fit["se_grouped"], G=fit["G"], sd_div10=sd,
               detectable=Z_BAR * 0.5 / (math.sqrt(fit["n"]) * sd) if sd > 0 else float("nan"))
    out = _pick_wider(out, df_plain=fit["n"] - fit["k"], df_grouped=fit["G"] - 1)
    for s in SEASONS:                                   # the sign check only: no standard error, no p-value
        idx = [i for i, (_, _, se_) in enumerate(rows) if se_ == s]
        f = _ols([y[i] for i in idx], [x[i] for i in idx], [bins[i] for i in idx], [dates[i] for i in idx]) \
            if idx else None
        out["season"][s] = (f["coef"] if f else None, len(idx))
    return out


def _season_means(bets: list[dict]) -> dict:
    by = defaultdict(list)
    for b in bets:
        by[b["season"]].append(b["won"] - b["fair"])
    return {s: ((float(np.mean(by[s])) if by[s] else None), len(by[s])) for s in SEASONS}


def _sign_check(res: dict) -> dict:
    overall = 0 if math.isnan(res["est"]) else int(np.sign(res["est"]))
    signs = {s: (None if v is None or v == 0 else int(np.sign(v))) for s, (v, _) in res["season"].items()}
    same = sum(1 for v in signs.values() if v is not None and overall != 0 and v == overall)
    passes = (not math.isnan(res["p"])) and res["p"] < BAR and same >= SEASONS_NEEDED
    return res | {"signs": signs, "same_sign": same, "passes": bool(passes)}


def analyse(games: list[dict]) -> dict:
    """The 14 registered variants, on games already cut at CUTOFF."""
    recs, excluded, variants = {}, {}, []
    for m in MARKETS:
        recs[m], excluded[m] = market_records(games, m)
    for m in MARKETS:                                                   # family A
        for kpts in THRESHOLDS:
            bets, both = pick_bets(recs[m], m, lambda o, kpts=kpts: o["div"] >= kpts)
            res = mean_test(bets) | {"season": _season_means(bets), "both_sides": both}
            variants.append(_sign_check(res) | {"family": "A", "market": m, "k": kpts})
    for m in MARKETS:                                                   # family B
        res = regression_test(recs[m], m) | {"both_sides": 0}
        variants.append(_sign_check(res) | {"family": "B", "market": m, "k": None})
    for m in FADE_MARKETS:                                              # family C
        bets, both = pick_bets(recs[m], m, lambda o: o["wager"] <= FADE_MAX_TICKETS)
        res = mean_test(bets) | {"season": _season_means(bets), "both_sides": both}
        variants.append(_sign_check(res) | {"family": "C", "market": m, "k": FADE_MAX_TICKETS})
    if len(variants) != N_VARIANTS:
        raise RuntimeError(f"{len(variants)} variants computed, {N_VARIANTS} registered")
    return {"variants": variants, "excluded": excluded, "n_records": {m: len(recs[m]) for m in MARKETS},
            "n_variants": len(variants)}


# ================================================================ the file itself (no results after the cut-off)

def file_checks(games: list[dict], info: dict) -> dict:
    """What the tested part of the file looks like: rows and games per season, duplicates, missing splits, whether
    the two shares add to 100, odd prices, results and lines. Counts only."""
    per_season = {}
    for s in SEASONS + tuple(sorted({g["season"] for g in games} - set(SEASONS))):
        gs = [g for g in games if g["season"] == s]
        if gs or info["after_cutoff_by_season"].get(s):
            per_season[s] = {"rows": len(gs), "games": len({(g["date"], *g["names"]) for g in gs}),
                             "first": min((g["date"] for g in gs), default=None),
                             "last": max((g["date"] for g in gs), default=None),
                             "after_cutoff": info["after_cutoff_by_season"].get(s, 0),
                             "missing_splits": sum(1 for g in gs if any(
                                 g["m"][m][sd][w] is None for m in MARKETS for sd in SIDES[m]
                                 for w in ("stake", "wager")))}
    pregame = Counter()
    for g in games:                     # does the file's pregame_odds text repeat the row's spread and total?
        mt = re.match(r"\s*(-?\d+(?:\.\d+)?)?\s*,?\s*O/U\s*(\d+(?:\.\d+)?)", str(g.get("pregame") or ""))
        if not mt:
            pregame["unreadable"] += 1
            continue
        tot, sp = g["m"]["total"]["over"]["line"], [g["m"]["spread"][s]["line"] for s in ("home", "away")]
        if tot is not None:
            pregame["total agrees" if abs(float(mt.group(2)) - tot) < 1e-9 else "total differs"] += 1
        if mt.group(1) is not None and None not in sp:
            pregame["spread agrees" if abs(float(mt.group(1)) - min(sp)) < 1e-9 else "spread differs"] += 1
    keys = Counter((g["date"], *g["names"]) for g in games)
    ids = Counter(g["key"] for g in games if g["key"] not in (None, ""))
    markets = {}
    for m in MARKETS:
        s1, s2 = SIDES[m]
        c = Counter()
        sums = {"stake": [], "wager": []}
        margins, decs, off_pairs = [], [], Counter()
        for g in games:
            a, b = g["m"][m][s1], g["m"][m][s2]
            if m != "money" and a["line"] is not None:
                c["whole-number line"] += float(a["line"]).is_integer()
            if any(o[w] is None for o in (a, b) for w in ("stake", "wager")):
                c["missing splits"] += 1
            for w in ("stake", "wager"):
                if a[w] is not None and b[w] is not None:
                    sums[w].append(a[w] + b[w])
            if a["dec"] is None or b["dec"] is None or a["dec"] <= 1 or b["dec"] <= 1:
                c["missing or impossible price"] += 1
            else:
                mg = 1 / a["dec"] + 1 / b["dec"] - 1
                margins.append(mg)
                decs += [a["dec"], b["dec"]]
                c["margin below 0%"] += mg < 0
                c["margin above 20%"] += mg > MAX_MARGIN
            if a["won"] is None or b["won"] is None:
                c["missing result"] += 1
            elif a["won"] and b["won"]:
                c["both sides marked won"] += 1
            elif not a["won"] and not b["won"]:
                c["push"] += 1
            if a["line"] is not None and b["line"] is not None:
                off = (a["line"] + b["line"]) if m == "spread" else (a["line"] - b["line"]) if m == "total" else 0
                c["lines that don't mirror"] += abs(off) > 1e-9
            for o in (a, b):
                conv = _american_to_decimal(o.get("american"))
                if conv is not None and o["dec"] is not None:
                    c["prices checked against American odds"] += 1
                    if abs(conv - o["dec"]) > 0.01:
                        c["decimal and American differ by more than 0.01"] += 1
                        off_pairs[(o["american"], o["dec"])] += 1
        markets[m] = {"counts": c, "n": len(games),
                      **{f"{w}_sum_within_1": (sum(abs(x - 100) <= 1 for x in v) / len(v)) if v else float("nan")
                         for w, v in sums.items()},
                      **{f"{w}_sum_range": ((min(v), max(v)) if v else (None, None)) for w, v in sums.items()},
                      "margin_median": float(np.median(margins)) if margins else float("nan"),
                      "margin_range": (min(margins), max(margins)) if margins else (None, None),
                      "dec_range": (min(decs), max(decs)) if decs else (None, None),
                      "off_pairs": off_pairs.most_common(3)}
    return {"per_season": per_season, "dup_games": sum(v - 1 for v in keys.values() if v > 1),
            "dup_ids": sum(v - 1 for v in ids.values() if v > 1), "markets": markets, "pregame": pregame}


# ================================================================ storing the splits

def store_splits(games: list[dict], db_path) -> int:
    """Closing splits of the tested games into the shared `splits` table; returns how many join to Kalshi games."""
    from ..build.run import connect
    con = connect(db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS splits (sport VARCHAR, dataset VARCHAR, collected_ts TIMESTAMPTZ,
                       is_closing BOOLEAN, source_game_key VARCHAR, game_id VARCHAR, game_date DATE, market VARCHAR,
                       side VARCHAR, team_code VARCHAR, bets_pct DOUBLE, handle_pct DOUBLE, line DOUBLE,
                       price_decimal DOUBLE)""")
        con.execute("DELETE FROM splits WHERE dataset = 'kaggle_mgm'")
        kalshi = {}
        if con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'games'").fetchone()[0]:
            kalshi = {(d, a, h): gid for gid, d, a, h in con.execute(
                "SELECT game_id, game_date_et, away_code, home_code FROM games WHERE sport = 'nba'").fetchall()}
        out, joined = [], set()
        for g in games:
            gid = kalshi.get((g["date"], g["away"], g["home"]))
            if gid:
                joined.add((g["date"], g["away"], g["home"]))
            for m in MARKETS:
                for s in SIDES[m]:
                    o = g["m"][m][s]
                    out.append(("nba", "kaggle_mgm", None, True, g["key"], gid, g["date"], {"money": "ml"}.get(m, m),
                                s, g["home"] if s == "home" else g["away"] if s == "away" else None,
                                o["wager"], o["stake"], o["line"], o["dec"]))
        if out:
            con.executemany("INSERT INTO splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", out)
        return len(joined)
    finally:
        con.close()


# ================================================================ the run and the report

REGISTRATION = {"commit": "ea635ecf1628955ebc806a5d487ba1e968c90b76", "committed_utc": "2026-09-29T23:05:39Z",
                "pushed_utc": "2026-09-29T23:05:41Z"}


def run_h3(blob: bytes | None = None, db_path=None, reports_dir=None) -> dict:
    from ..settings import DB_PATH
    from ..sport import load_teams
    blob = download() if blob is None else blob
    rows, fields = load_rows(blob)
    missing = [c for c in (COL_DATE, COL_HOME, COL_AWAY) + tuple(_col(m, s, w) for m in MARKETS for s in SIDES[m]
                                                             for w in ("dec", "stake", "wager", "won"))
               if c not in fields]
    if missing:
        raise SystemExit(f"all_odds.csv is not what PLAN.md describes: {len(missing)} expected columns are missing "
                         f"({', '.join(missing[:6])}{'...' if len(missing) > 6 else ''}). Nothing was computed.")
    games, info = parse_games(rows, load_teams("nba"))
    res = analyse(games)
    res.update(fields=fields, info=info, checks=file_checks(games, info), n_rows=info["n_rows"],
               n_games=len(games), unknown_teams=dict(info["unknown_teams"]),
               sha256=hashlib.sha256(blob).hexdigest(), download=download_record())
    res["kalshi_joined_games"] = store_splits(games, db_path or DB_PATH)
    res["report"] = write_report(res, reports_dir or REPORTS_DIR)
    return res


def _pct(x, nd=1):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{nd}f}%"


def _pts(x, nd=2):
    """A difference in win chance, in percentage points."""
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:+.{nd}f}"


def _se(x, nd=2):
    """A standard error or a detectable effect, in percentage points (no sign)."""
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{nd}f}"


def _range(t, nd=1):
    return "—" if t[0] is None else f"{t[0]:.{nd}f} to {t[1]:.{nd}f}"


def _p(x):
    if x is None or math.isnan(x):
        return "—"
    return f"{x:.2e}" if x < 0.001 else f"{x:.3f}"


def _colname(c: str) -> str:
    return f"`{c}`" if c.strip() else "an unnamed first column"


def _signs(v: dict) -> str:
    return " ".join({1: "+", -1: "−", None: "·"}[v["signs"][s]] for s in SEASONS)


def _name(v: dict) -> str:
    mk = MARKET_LABEL[v["market"]]
    if v["family"] == "A":
        return f"A: {mk}, money − tickets ≥ {v['k']}"
    if v["family"] == "B":
        return f"B: {mk}, per 10 points ({'over' if v['market'] == 'total' else 'home side'})"
    return f"C: {mk}, tickets ≤ {v['k']}%"


def _plain(v: dict) -> str:
    """One variant's result in words."""
    mk, x = MARKET_LABEL[v["market"]], abs(v["est"]) * 100
    more = "more" if v["est"] > 0 else "less"
    if v["family"] == "A":
        return (f"backing the {mk} side with at least {v['k']} points more of the money than of the tickets (it won "
                f"{x:.1f} points {more} often than its fair chance)")
    if v["family"] == "B":
        side = "over" if v["market"] == "total" else "home side"
        return (f"the {mk} regression (the {side} won {x:.1f} points {more} often than its fair chance for every 10 "
                "points by which its share of money beat its share of tickets)")
    return (f"fading the public on {mk}s, backing the side with {v['k']}% of the tickets or fewer (it won {x:.1f} "
            f"points {more} often than its fair chance)")


def finding_text(res: dict) -> list[str]:
    vs = res["variants"]
    passed = [v for v in vs if v["passes"]]
    ps = [v for v in vs if not math.isnan(v["p"])]
    best = min(ps, key=lambda v: v["p"]) if ps else None
    below05 = sum(v["p"] < 0.05 for v in ps)
    det = [v["detectable"] for v in vs if v["family"] in "AC" and not math.isnan(v["detectable"])]
    if not passed:
        s1 = (f"**None of the 14 variants passes the bar** (p below {BAR:.6f} and the same sign in at least 4 of the "
              "5 seasons): at BetMGM's close in the NBA, from 2021-22 to January 2026, the split between tickets and "
              "money says nothing detectable that BetMGM's own closing price hadn't already priced in.")
        s2 = (f"The closest was {_plain(best)}, with p = {_p(best['p'])}, about {best['p'] / BAR:,.0f} times too large "
              f"for the bar; {below05} of the 14 {'was' if below05 == 1 else 'were'} below an ordinary 0.05, where "
              "chance alone would give about 0.7." if best else "No variant had enough games to test.")
        s3 = (f"The test could only have detected effects of about {min(det) * 100:.1f} points of win chance or more "
              "in its biggest variants, and far more in the thin ones, so a small edge of the size that matters in "
              "betting is not ruled out." if det else "")
        return [s for s in (s1, s2, s3) if s]
    names = "; ".join(f"{_plain(v)}, p = {_p(v['p'])}" for v in passed)
    return [f"**{len(passed)} of the 14 variants pass the bar:** {names}.",
            "That is a lead, not a rule: the next steps would be the same test against Pinnacle's close (Odds API "
            "credits, the owner's decision) and a forward test. No rule is registered from it and no money follows."]


def _table(vs: list[dict], family: str) -> list[str]:
    reg = family == "B"
    head = ("| Variant | n | Win rate | Mean fair chance | " + ("Coefficient per 10 points" if reg else "Won − fair")
            + " | SE plain" + (" (HC1)" if reg else "") + " | SE by date | Wider | p | Bar | Passes | Signs by season"
            " | Same sign | Smallest detectable | Return at the close |")
    L = [head, "|" + "---|" * 15]
    for v in vs:
        if v["family"] != family:
            continue
        L.append(f"| {_name(v)} | {v['n']:,} | {_pct(v['win_rate'])} | {_pct(v['mean_fair'])} | "
                 f"{_pts(v['est'])} | {_se(v['se_plain'])} | {_se(v['se_grouped'])} ({v['G']:,} dates) | "
                 f"{v['wider']} | {_p(v['p'])} | {BAR:.6f} | {'**yes**' if v['passes'] else 'no'} | "
                 f"{_signs(v)} | {v['same_sign']} of 5 | {_se(v['detectable'])} | "
                 f"{'no bet' if reg else _pct(v['roi'], 2)} |")
    return L


def write_report(res: dict, reports_dir) -> Path:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / REPORT_NAME
    kept = ""
    if path.exists():
        old = path.read_text()
        if HAND_SECTION in old:
            kept = old[old.index(HAND_SECTION):]
    vs, info, ch = res["variants"], res["info"], res["checks"]
    dl = res.get("download") or {}
    passed = [v for v in vs if v["passes"]]
    L = ["# Betting splits, first test (H3): NBA money versus tickets at BetMGM's close", "",
         f"Registered in [`docs/H3_KAGGLE_PREREGISTRATION.md`](../docs/H3_KAGGLE_PREREGISTRATION.md) before the file "
         f"was downloaded. Data: Kaggle `{DATASET}` (CC BY-SA 4.0). Part of issue "
         "[#66](https://github.com/maxzipperman/value-finder/issues/66). "
         f"**n_variants_tested = {res['n_variants']}**; the project's running count goes from {PRIOR_COUNT} to "
         f"{RUNNING_COUNT}, so the bar is p < 0.05 / {RUNNING_COUNT} = {BAR:.6f}.", "",
         "## The finding", "", *(" ".join(finding_text(res)),), "",
         "## Limits", "",
         "- **One retail book.** BetMGM's own tickets and money, not the market's. One large bet can move a retail "
         "book's money share.",
         "- **Closing figures only, no timestamps.** Whether a line moved against the public (reverse line movement) "
         "and anything about timing can't be tested: the file has no opening figures.",
         "- **The benchmark is BetMGM's own close,** with the margin removed proportionally, not Pinnacle's.",
         "- **Scraped by a third party from Yahoo.** Provenance is a caveat; the checks under \"The file itself\" "
         "are what we could verify.",
         f"- **Games after {CUTOFF:%B %d, %Y} are left out of everything** ({info['after_cutoff']:,} rows): they are "
         "the validation period of the Kalshi study. Their results were never read.",
         "- **Only large effects are detectable.** See the \"Smallest detectable\" column: a null here means any "
         "effect is smaller than that, not that there is none.",
         "- **NBA only.** Nothing here tests football.", "",
         "## Results", "",
         "Differences, standard errors and detectable effects are in percentage points of win chance (for family B, "
         "per 10 points of divergence). \"Won − fair\" is how much more often the backed side won than BetMGM's "
         "closing price, margin removed, said it would. Signs by season run 2021-22, 2022-23, 2023-24, 2024-25, "
         "2025-26 (to January 31); \"·\" is a season with no bets. The return at the close decides nothing.", "",
         "### Family A: back the side whose share of money exceeds its share of tickets by at least k points", "",
         *_table(vs, "A"), "",
         "### Family B: the same idea without a threshold (regression with fair-chance tenths)", "",
         *_table(vs, "B"), "",
         "### Family C: fade the public (back the side with 30% of the tickets or fewer)", "",
         *_table(vs, "C"), "",
         "### Season figures (used only for the sign check; no standard error or p-value is computed for a season)",
         "", "| Variant | " + " | ".join(SEASONS) + " |", "|" + "---|" * (len(SEASONS) + 1)]
    for v in vs:
        L.append(f"| {_name(v)} | " + " | ".join(
            f"{_pts(v['season'][s][0])} (n {v['season'][s][1]:,})" for s in SEASONS) + " |")
    reasons = ("missing figure", "margin below 0% or above 20%", "both sides marked won", "push")
    L += ["", "### Games left out, by market and reason", "",
          f"Out of {res['n_games']:,} games dated on or before {CUTOFF.isoformat()}.", "",
          "| Market | Games tested | " + " | ".join(reasons) + " |", "|" + "---|" * (len(reasons) + 2)]
    for m in MARKETS:
        e = res["excluded"][m]
        L.append(f"| {MARKET_LABEL[m]} | {res['n_records'][m]:,} | " + " | ".join(f"{e.get(r, 0):,}" for r in reasons)
                 + " |")
    both = [(v, v["both_sides"]) for v in vs if v["both_sides"]]
    L += ["", "Games where both sides met a family A or C rule (left out of that variant): "
          + ("; ".join(f"{_name(v)}: {n}" for v, n in both) if both else "none") + "."]
    near = sorted((v for v in vs if not math.isnan(v["p"]) and v["p"] < 0.05), key=lambda v: v["p"])
    L += ["", "### Closest to the bar", "",
          "Variants with p below an ordinary 0.05, none of which comes near the bar:" if near and not passed else
          "Variants with p below an ordinary 0.05:" if near else "No variant has p below an ordinary 0.05."]
    L += [f"- {_name(v)}: {_plain(v)}; p = {_p(v['p'])}, {v['p'] / BAR:,.0f} times the bar; the same sign in "
          f"{v['same_sign']} of 5 seasons." for v in near]
    L += ["", "## What it means", ""]
    if passed:
        L += ["**Something passes.** A lead, not a rule. The next steps would be the same test against Pinnacle's "
              "close (that costs credits: the owner's decision) and a forward test. No rule is registered from this "
              "test and no money follows from it.", ""]
    else:
        L += ["**Nothing passes: recorded as a null.** Closing splits at one retail book add nothing detectable to "
              "that book's own closing price in the NBA. This does not test football, and it does not test splits "
              "before the close.", ""]
    L += ["Either way, no football splits data is bought on the strength of this test alone.", "",
          "## The file itself", "",
          f"- **Columns ({len(res['fields'])}):** " + ", ".join(_colname(c) for c in res["fields"]) + ".",
          f"- **Rows:** {info['n_rows']:,} in all; {info['after_cutoff']:,} dated after {CUTOFF.isoformat()} (counted, "
          f"nothing else read); {info['bad_date']:,} with an unreadable date; {res['n_games']:,} tested.",
          f"- **Shares** were read as {'fractions and multiplied by 100' if info['share_scale'] == 100 else 'percentages'}"
          f"; prices as {'American odds, converted to decimal' if info['american_prices'] else 'decimal odds'}.",
          "- **Columns with one value on every tested row:** "
          + (", ".join(f"{_colname(c)} (always \"{v}\")" for c, v in info.get("constant_columns", {}).items())
             or "none") + ".",
          f"- **Duplicated games** (same date, home and away team): {ch['dup_games']:,}; duplicated game ids: "
          f"{ch['dup_ids']:,}; rows that repeat an earlier row in every column: {info['exact_duplicate_rows']:,}. "
          "They are counted as the file gives them (so twice)"
          + ("; that few can't move any result." if info["exact_duplicate_rows"] <= 0.005 * max(res["n_games"], 1)
             else "."),
          "- **Opening figures:** none. The `pregame_odds` column repeats the closing spread and total as text: the "
          f"spread agrees with the line columns in {ch['pregame'].get('spread agrees', 0):,} of "
          f"{ch['pregame'].get('spread agrees', 0) + ch['pregame'].get('spread differs', 0):,} games and the total in "
          f"{ch['pregame'].get('total agrees', 0):,} of "
          f"{ch['pregame'].get('total agrees', 0) + ch['pregame'].get('total differs', 0):,} "
          f"({ch['pregame'].get('unreadable', 0):,} unreadable). The test never uses the lines themselves.",
          "- **Pushes:** " + (
              f"none in spreads or totals. A push can only happen on a whole-number line, and only "
              f"{ch['markets']['spread']['counts']['whole-number line']:,} spreads and "
              f"{ch['markets']['total']['counts']['whole-number line']:,} totals closed on one. At the usual NBA rates "
              "(roughly 3% of whole-number spreads and 2% of whole-number totals land exactly on the number) about "
              f"{0.03 * ch['markets']['spread']['counts']['whole-number line']:.0f} and "
              f"{0.02 * ch['markets']['total']['counts']['whole-number line']:.0f} would be expected, so the file most "
              "likely records those few as a win for one side. Too few to move any result."
              if not ch["markets"]["spread"]["counts"]["push"] and not ch["markets"]["total"]["counts"]["push"] else
              f"{ch['markets']['spread']['counts']['push']:,} in spreads and "
              f"{ch['markets']['total']['counts']['push']:,} in totals, left out as registered."),
          "- **Prices:** the test uses the file's decimal prices as given. They mostly agree with the file's American "
          "odds; " + "; ".join(
              f"{MARKET_LABEL[m]}s: {ch['markets'][m]['counts']['decimal and American differ by more than 0.01']:,} of "
              f"{ch['markets'][m]['counts']['prices checked against American odds']:,} differ by more than 0.01"
              for m in MARKETS) + ". "
          + ("The most common mismatches are " + ", ".join(
              f"American {a:+.0f} given as decimal {d:.2f} (where {a:+.0f} is {_american_to_decimal(a):.2f}; {n:,} times)"
              for (a, d), n in ch["markets"]["money"]["off_pairs"])
             + ". An error of 0.02 in a favourite's price moves its fair chance by a fraction of a point."
             if ch["markets"]["money"]["off_pairs"] else ""),
          f"- **Dates:** every game id carries a date; it matches the `game_date` column on "
          f"{info.get('id_date_checked', 0) - info.get('id_date_differs', 0):,} of {info.get('id_date_checked', 0):,} "
          "tested rows.",
          "- **Team names that don't resolve** against `config/teams/nba.csv`: "
          + (", ".join(f"\"{n}\" ({c:,} appearances)" for n, c in sorted(res["unknown_teams"].items()))
             if res["unknown_teams"] else "none")
          + ". Team names play no part in the test, so these games stay in it; they only get no team code in the "
            "`splits` table and can't join to a Kalshi game.",
          f"- **Games that join to a Kalshi game** (same Eastern date, away and home team): "
          f"{res['kalshi_joined_games']:,}. Their closing splits are in the `splits` table of `data/markets.duckdb`.",
          "", "| Season | Rows tested | Games | First date | Last date | Games missing any split | "
              "Rows after the cut-off |", "|---|---|---|---|---|---|---|"]
    for s, d in ch["per_season"].items():
        L.append(f"| {s} | {d['rows']:,} | {d['games']:,} | {d['first'] or '—'} | {d['last'] or '—'} | "
                 f"{d['missing_splits']:,} | {d['after_cutoff']:,} |")
    L += ["", "| Market | Games | Missing splits | Tickets add to 100 (±1) | Money adds to 100 (±1) | Ticket sums, min to max"
          " | Money sums, min to max | Missing or impossible price | Margin below 0% | Margin above 20% | Median margin"
          " | Decimal prices, min to max | Missing result | Push | Both won | Lines that don't mirror |",
          "|" + "---|" * 16]
    for m in MARKETS:
        c = ch["markets"][m]
        k_ = c["counts"]
        mirror = k_["lines that don't mirror"]
        L.append(f"| {MARKET_LABEL[m]} | {c['n']:,} | {k_['missing splits']:,} | {_pct(c['wager_sum_within_1'])} | "
                 f"{_pct(c['stake_sum_within_1'])} | {_range(c['wager_sum_range'])} | {_range(c['stake_sum_range'])} | "
                 f"{k_['missing or impossible price']:,} | {k_['margin below 0%']:,} | {k_['margin above 20%']:,} | "
                 f"{_pct(c['margin_median'], 2)} | {_range(c['dec_range'], 2)} | {k_['missing result']:,} | "
                 f"{k_['push']:,} | {k_['both sides marked won']:,} | {mirror:,} |")
    L += ["", "## Record", "",
          f"- **Registration:** commit `{REGISTRATION['commit']}`, committed {REGISTRATION['committed_utc']} and pushed "
          f"by {REGISTRATION['pushed_utc']} (UTC), before the download.",
          f"- **Download:** {dl.get('downloaded_utc', 'not recorded')} (UTC), {dl.get('bytes', 0):,} bytes.",
          f"- **The file's sha256** (the zip as downloaded): `{res['sha256']}`.",
          f"- **Variants:** {res['n_variants']} ({len(MARKETS) * len(THRESHOLDS)} in family A, {len(MARKETS)} in B, "
          f"{len(FADE_MARKETS)} in C); running count {PRIOR_COUNT} → {RUNNING_COUNT}; bar p < {BAR:.6f}; the "
          f"smallest detectable effect is {Z_BAR:.2f} × 0.5 / √n.",
          "- Command: `uv run markets h3-kaggle` in `sharp-markets/`.", ""]
    text = "\n".join(L) + "\n"
    if kept:
        text += "\n" + kept
    path.write_text(text)
    return path
