"""Part 4 credit arithmetic from strategy-research/odds_5m.py's constants: PER_SNAP = 10 x 3 markets x 1 group = 30
per featured snapshot; season snapshots = (days + 7) + slots, slots = reg x ratio + post x 0.95."""
PER_SNAP = 30
def snaps(reg, post, days, ratio): return (days + 7) + round(reg * ratio + post * 0.95)
seasons = {  # from odds_5m.py SPORTS, 2024 and 2025 rows
    "MLB 2024": (2430, 43, 215, 0.66), "MLB 2025": (2430, 43, 215, 0.66),
    "MLS 2024": (493, 29, 285, 0.45), "MLS 2025": (510, 29, 285, 0.45),
    "Liga MX 2024": (306, 36, 330, 0.70), "Liga MX 2025": (306, 36, 330, 0.70),
    "Brasileirao 2024": (380, 0, 240, 0.55), "Brasileirao 2025": (380, 0, 240, 0.55),
    "J1 2024": (380, 0, 280, 0.45), "J1 2025": (380, 0, 280, 0.45),
    "K League 2024": (228, 0, 260, 0.50), "K League 2025": (228, 0, 260, 0.50),
    "Euro 2024": (51, 0, 31, 0.90), "Copa America 2024": (32, 0, 25, 0.90), "Club World Cup 2025": (63, 0, 30, 0.90),
    "Gold Cup 2025": (31, 0, 23, 0.90), "Leagues Cup 2025": (45, 0, 34, 0.90),
}
tot = {}
for k, v in seasons.items():
    s = snaps(*v); tot[k] = s * PER_SNAP
    print(f"{k:22s} snapshots {s:5d}  credits {s*PER_SNAP:8,d}")
mlb = tot["MLB 2024"] + tot["MLB 2025"]
big3 = sum(tot[k] for k in tot if k.split(" 20")[0] in ("MLS", "Liga MX", "Brasileirao"))
five = big3 + sum(tot[k] for k in tot if k.split(" 20")[0] in ("J1", "K League"))
tourn = sum(tot[k] for k in ("Euro 2024", "Copa America 2024", "Club World Cup 2025", "Gold Cup 2025", "Leagues Cup 2025"))
print(f"\nB1 as designed, 2024-25 only (daily + every close): {mlb:,}")
print(f"S1 as designed, 2024-25, MLS+LigaMX+Brasileirao: {big3:,}; five leagues: {five:,}; plus tournaments {tourn:,} -> {five+tourn:,}")
# close-only for qualifying games only (the trigger is free from Open-Meteo before any odds are pulled)
for name, games, ratio in (("MLB qualifying (146 obs., ERA5)", 146, 0.66), ("Soccer leagues qualifying (~225)", 225, 0.55),
                           ("Soccer tournaments qualifying (~47)", 47, 0.90)):
    s = round(games * ratio)
    print(f"{name:40s}: ~{s:4d} close snapshots x 30 = {s*30:6,} credits (totals-only at 10 credits/snapshot: {s*10:,})")
