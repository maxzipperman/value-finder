"""Ceiling win rates P = Phi(delta/sigma) for B-H1 (MLB heat -> over) and S-H1 (soccer heat -> under), the
half-adjusted-market case, and the sample sizes the pre-registered bar needs. Pure arithmetic, no data."""
import math

def Phi(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def z_for_p(p):  # one-sided, bisection
    lo, hi = 0.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if 1 - Phi(mid) > p: lo = mid
        else: hi = mid
    return (lo + hi) / 2

Z_BAR = z_for_p(0.00026)          # repo-wide bar, one-sided
Z_05 = z_for_p(0.05)
Z_80 = z_for_p(0.20)               # 80% power
BE_110 = 110 / 210                 # -110 break-even
BE_105 = 105 / 205                 # Pinnacle-style -105 break-even (typical totals vig; UNVERIFIED for these leagues)
print(f"z for p<0.00026 (one-sided) = {Z_BAR:.3f}; z for p<0.05 = {Z_05:.3f}; -110 break-even = {BE_110:.4f}; -105 = {BE_105:.4f}")

def n_needed(e, z, zpow=0.0):
    """n so that a true excess win rate e (over 0.5) is significant at z with power given by zpow (0 = 50% power)."""
    return ((z + zpow) * 0.5 / e) ** 2

def mde(n, z=Z_05, zpow=Z_80):
    return (z + zpow) * 0.5 / math.sqrt(n)

print("\n=== MLB, B-H1 (over). sigma = SD of total runs (2024: 4.31, 2025: 4.59 from statsapi cache; use 4.45) ===")
SIG_MLB = 4.45
HR_PER_F = 0.044 / 1.8           # Callahan et al. 2023: 0.044 HR/game per 1 C  ->  per 1 F
for label, runs_per_hr in (("1.4 runs/HR", 1.4), ("1.6 runs/HR", 1.6)):
    print(f"  HR channel, {label}: {HR_PER_F*runs_per_hr:.4f} runs per F")
rows = [
    ("Callahan HR-only, +10F vs park-month norm, 1.5 R/HR", HR_PER_F * 1.5 * 10),
    ("Callahan HR-only, +15F, 1.5 R/HR", HR_PER_F * 1.5 * 15),
    ("Blog 1952-2015 slope 1 run/50F, +10F", 10 / 50),
    ("Blog 2016 slope 1 run/20F, +10F", 10 / 20),
    ("Blog 2016 slope 1 run/20F, +15F", 15 / 20),
    ("Koch&Panorska cold->warm gap 1.13 runs (upper, confounded)", 1.13),
]
print(f"  {'delta scenario':62s} {'delta':>6s} {'P_full':>7s} {'P_half':>7s} {'n(bar,50%pow)':>14s} {'n(bar,80%pow)':>14s} {'n(p<.05,80%)':>13s}")
for name, d in rows:
    pf, ph = Phi(d / SIG_MLB), Phi(d / 2 / SIG_MLB)
    print(f"  {name:62s} {d:6.2f} {pf:7.4f} {ph:7.4f} {n_needed(pf-0.5, Z_BAR):14.0f} {n_needed(pf-0.5, Z_BAR, Z_80):14.0f} {n_needed(pf-0.5, Z_05, Z_80):13.0f}")

print("\n=== Soccer, S-H1 (under). sigma = sqrt(goals/match): MLS 3.15->1.77, LigaMX 2.75->1.66, BRA 2.44->1.56, J1 2.67->1.63, K1 2.61->1.62; use 1.65 ===")
SIG_SOC = 1.65
rows = [
    ("Schwarz 2025 beta 0.01 goals/C x 10C (n.s., p=0.79)", 0.10),
    ("Nassis 2015: no goal difference; assume 0.05 goals", 0.05),
    ("generous 0.2 goals", 0.20),
    ("very generous 0.3 goals", 0.30),
]
print(f"  {'delta scenario':62s} {'delta':>6s} {'P_full':>7s} {'P_half':>7s} {'n(bar,50%pow)':>14s} {'n(bar,80%pow)':>14s} {'n(p<.05,80%)':>13s}")
for name, d in rows:
    pf, ph = Phi(d / SIG_SOC), Phi(d / 2 / SIG_SOC)
    print(f"  {name:62s} {d:6.2f} {pf:7.4f} {ph:7.4f} {n_needed(pf-0.5, Z_BAR):14.0f} {n_needed(pf-0.5, Z_BAR, Z_80):14.0f} {n_needed(pf-0.5, Z_05, Z_80):13.0f}")

print("\n=== minimum detectable excess win rate (one-sided p<0.05, 80% power) at fixed n ===")
for n in (150, 200, 300, 500, 1000, 2000):
    print(f"  n={n:5d}: MDE = {mde(n):.3f}  (win rate {0.5+mde(n):.3f});  at the p<0.00026 bar with 80% power: {mde(n, Z_BAR):.3f}")
print("\n=== what P a given n can clear at the bar, 50% power (observed rate needed) ===")
for n in (146, 150, 300, 500, 1000):
    print(f"  n={n:5d}: observed win rate needed for p<0.00026 = {0.5 + Z_BAR*0.5/math.sqrt(n):.3f}; for p<0.05 = {0.5 + Z_05*0.5/math.sqrt(n):.3f}")
