"""Power table for a one-sided z test of a proportion vs break-even at -110. Pure math, no data.

n     = ((z_{1-a} * sqrt(p0 q0) + z_{1-b} * sqrt(p1 q1)) / (p1 - p0))^2       (80% power -> z_{1-b} = 0.8416)
power = Phi( ((p1 - p0) * sqrt(n) - z_{1-a} * sqrt(p0 q0)) / sqrt(p1 q1) )
Exact binomial cross-check: critical k* = smallest k with P(X >= k | n, p0) <= alpha; power = P(X >= k* | n, p1).
"""
import numpy as np
import pandas as pd
from scipy import stats

p0 = 110 / 210
q0 = 1 - p0
P1 = [0.54, 0.55, 0.56, 0.577]
ALPHAS = [0.05, 0.01, 0.0035, 0.00037, 0.00026]
NS = [110, 150, 300, 650, 1000]
zb = stats.norm.ppf(0.80)
pd.set_option("display.width", 200)

print(f"p0 (break-even at -110) = {p0:.5f}; z_0.80 = {zb:.4f}")
print("z_{1-alpha}:", {a: round(float(stats.norm.ppf(1 - a)), 4) for a in ALPHAS})

rows = []
for p1 in P1:
    q1 = 1 - p1
    r = {"true_win_rate": p1}
    for a in ALPHAS:
        za = stats.norm.ppf(1 - a)
        n = ((za * np.sqrt(p0 * q0) + zb * np.sqrt(p1 * q1)) / (p1 - p0)) ** 2
        r[f"n_alpha_{a}"] = int(np.ceil(n))
    rows.append(r)
print("\n=== n needed for 80% power, one-sided z test vs 52.38% ===")
print(pd.DataFrame(rows).to_string(index=False))

for a in (0.05, 0.00026):
    za = stats.norm.ppf(1 - a)
    rows = []
    for p1 in P1:
        q1 = 1 - p1
        r = {"true_win_rate": p1}
        for n in NS:
            pw = stats.norm.cdf(((p1 - p0) * np.sqrt(n) - za * np.sqrt(p0 * q0)) / np.sqrt(p1 * q1))
            r[f"power_n{n}"] = round(float(pw), 3)
        rows.append(r)
    print(f"\n=== power at alpha = {a} (one-sided z) ===")
    print(pd.DataFrame(rows).to_string(index=False))

    rows = []
    for p1 in P1:
        r = {"true_win_rate": p1}
        for n in NS:
            k = int(stats.binom.isf(a, n, p0)) + 1        # smallest k with P(X>=k|p0) <= alpha
            while stats.binom.sf(k - 1, n, p0) > a:
                k += 1
            r[f"exact_n{n}"] = round(float(stats.binom.sf(k - 1, n, p1)), 3)
            r[f"crit_n{n}"] = k
        rows.append(r)
    print(f"--- exact binomial cross-check at alpha = {a}: power and critical wins k* ---")
    print(pd.DataFrame(rows).to_string(index=False))

# Rule HT STRATEGY.md check: ~105 bets, p<0.05 one-sided vs 52.38%, true rate 57.7%
n = 105
k = int(stats.binom.isf(0.05, n, p0)) + 1
while stats.binom.sf(k - 1, n, p0) > 0.05:
    k += 1
print(f"\nRule HT check: n=105 -> critical wins k*={k} ({k / n:.1%}); power at 57.7% = {stats.binom.sf(k - 1, n, 0.577):.3f} (STRATEGY.md says ~62% to pass, 22-27% chance)")

# CLV: n = ((z_a + z_b) * sd / delta)^2 ; sd inserted from the data scripts
za = stats.norm.ppf(0.95)
print(f"\nCLV formula constant (z_0.95 + z_0.80)^2 = {(za + zb) ** 2:.4f}; n = {(za + zb) ** 2:.4f} * (sd / delta)^2")
