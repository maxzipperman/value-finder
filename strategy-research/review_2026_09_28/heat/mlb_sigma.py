"""Unconditional mean and SD of total runs per game (all played regular-season games, NOT split by weather),
from the cached MLB Stats API schedule (scores are in teams.home.score / teams.away.score). Task C asks for
sigma of the game total to compute the ceiling P = Phi(delta/sigma). Nothing here conditions on the trigger."""
import json, statistics
from pathlib import Path
C = Path(__file__).resolve().parents[3] / "strategy-research" / "data" / "heat"
for season in (2024, 2025):
    body = json.loads((C / f"statsapi_schedule_{season}_R.json").read_text())
    tot = []
    for d in body["dates"]:
        for g in d["games"]:
            if (g.get("status") or {}).get("codedGameState") != "F":
                continue
            h, a = g["teams"]["home"].get("score"), g["teams"]["away"].get("score")
            if h is None or a is None:
                continue
            tot.append(h + a)
    print(f"{season}: n={len(tot)} mean total runs={statistics.mean(tot):.2f} SD={statistics.pstdev(tot):.2f}")
