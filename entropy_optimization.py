#!/usr/bin/env python3
"""
Prompt 7 — Entropy-Based Upset Budget (corrected simulation)

BUG FIX: Original simulation capped opponents at N_OPP_PER_SIM=40 regardless
of pool size, producing ~5% win rate for all N. Fix uses CDF-based approach:
generate large opponent score sample, then P(win) = CDF(our_score)^(N-1).

Implements Brill-Wyner-Barnett entropy framework for bracket optimization.
"""
import csv
import math
import numpy as np
from collections import defaultdict

np.random.seed(42)

# ============================================================
# LOAD DATA
# ============================================================
prob_data = {}
with open('probability_baseline_final_2026.csv') as f:
    for row in csv.DictReader(f):
        prob_data[row['team_name']] = row

matchups_by_round = defaultdict(list)
with open('espn_picks_2026.csv') as f:
    for row in csv.DictReader(f):
        if row['round'] in ('R64', 'R32', 'S16', 'E8'):
            matchups_by_round[row['round']].append(row)

lev_data = defaultdict(dict)
with open('leverage_matrix_2026.csv') as f:
    for row in csv.DictReader(f):
        lev_data[row['team_name']][row['round']] = float(row['public_pick_pct'])

ncg_dist = {}
with open('ncg_pick_distribution_2026.csv') as f:
    for row in csv.DictReader(f):
        ncg_dist[row['team_name']] = float(row['ncg_public_pick_pct']) / 100.0

# Validation
f4_sum = sum(lev_data[t].get('F4', 0) for t in lev_data)
ncg_sum = sum(lev_data[t].get('NCG', 0) for t in lev_data)
print(f"F4 sum: {f4_sum:.4f}, NCG sum: {ncg_sum:.4f}")
assert 3.95 <= f4_sum <= 4.05 and 0.99 <= ncg_sum <= 1.01, "HALT: Distribution check failed"
print("Validation PASSED.\n")

# ============================================================
# BUILD GAME LIST (60 pre-determined games R64-E8)
# ============================================================
def higher_seed_first(t1, s1, t2, s2):
    s1i, s2i = int(s1), int(s2)
    return (t1, s1i, t2, s2i) if s1i <= s2i else (t2, s2i, t1, s1i)

games = []
ROUND_PTS = {'R64': 10, 'R32': 20, 'S16': 40, 'E8': 80}

for rd in ['R64', 'R32', 'S16', 'E8']:
    for m in matchups_by_round[rd]:
        hi, hs, lo, ls = higher_seed_first(
            m['team_1_name'], m['team_1_seed'],
            m['team_2_name'], m['team_2_seed'])

        if rd == 'R64':
            vp = float(prob_data[hi]['r1'])
        elif rd == 'E8':
            hi_e8 = float(prob_data[hi]['e8_game_prob_corrected'])
            lo_e8 = float(prob_data[lo]['e8_game_prob_corrected'])
            vp = hi_e8 if hi_e8 > lo_e8 else 1 - lo_e8
        else:
            pc = {'R32': 'r2', 'S16': 'r3'}[rd]
            p_hi = float(prob_data[hi][pc])
            p_lo = float(prob_data[lo][pc])
            vp = p_hi / (p_hi + p_lo) if (p_hi + p_lo) > 0 else 0.5

        pub_hi = float(m['team_1_pick_pct']) / 100.0 if m['team_1_name'] == hi else float(m['team_2_pick_pct']) / 100.0

        games.append({
            'round': rd, 'hi': hi, 'lo': lo, 'hs': hs, 'ls': ls,
            'vp': vp, 'pub_hi': pub_hi, 'mid': m['matchup_id'],
            'pts': ROUND_PTS[rd],
        })

# E8 uncorrected probs
e8_uncorrected = {}
for g in games:
    if g['round'] == 'E8':
        hi_impl = float(prob_data[g['hi']]['e8_game_prob_implied'])
        lo_impl = float(prob_data[g['lo']]['e8_game_prob_implied'])
        e8_uncorrected[g['mid']] = hi_impl if hi_impl > lo_impl else 1 - lo_impl
        print(f"  E8: {g['hi']} vs {g['lo']}  corr={g['vp']:.3f}  uncorr={e8_uncorrected[g['mid']]:.3f}  "
              f"delta={g['vp'] - e8_uncorrected[g['mid']]:+.3f}")

N_GAMES = len(games)
print(f"\n{N_GAMES} games (R64-E8). F4+NCG computed dynamically.\n")

# ============================================================
# BRACKET ENTROPY
# ============================================================
def bracket_entropy(probs):
    H = 0
    for p in probs:
        p = max(min(p, 0.9999), 0.0001)
        H -= p * math.log2(p) + (1-p) * math.log2(1-p)
    return H

all_vps = [g['vp'] for g in games] + [0.55, 0.55, 0.55]
max_H = bracket_entropy(all_vps)
print(f"Approximate max bracket entropy: {max_H:.1f} bits\n")

# ============================================================
# SIMULATION FUNCTIONS
# ============================================================
N_SIMS = 3000         # tournament outcomes
N_OPP_SAMPLE = 500    # opponent brackets per tournament (for CDF)
POOL_SIZES = [50, 200, 1000, 10000]
UPSET_COUNTS = list(range(0, 22))

def f4_game_prob(t1, t2):
    r5_1 = float(prob_data[t1]['r5'])
    r5_2 = float(prob_data[t2]['r5'])
    total = r5_1 + r5_2
    return r5_1 / total if total > 0 else 0.5

def round_pts_from_mid(mid):
    if 'R64' in mid: return 10
    if 'R32' in mid: return 20
    if 'S16' in mid: return 40
    if 'E8' in mid: return 80
    if mid.startswith('F4'): return 160
    if mid == 'NCG': return 320
    return 0

def sim_tournament(use_uncorrected=False):
    """Simulate one tournament outcome."""
    r = {}
    for g in games:
        if g['round'] == 'E8' and use_uncorrected:
            p = e8_uncorrected[g['mid']]
        else:
            p = g['vp']
        r[g['mid']] = g['hi'] if np.random.random() < p else g['lo']

    ew = r.get('E_E8', 'Duke'); sw = r.get('S_E8', 'Florida')
    ww = r.get('W_E8', 'Arizona'); mw = r.get('MW_E8', 'Michigan')
    p1 = f4_game_prob(ew, sw)
    r['F4_1'] = ew if np.random.random() < p1 else sw
    p2 = f4_game_prob(ww, mw)
    r['F4_2'] = ww if np.random.random() < p2 else mw
    pn = f4_game_prob(r['F4_1'], r['F4_2'])
    r['NCG'] = r['F4_1'] if np.random.random() < pn else r['F4_2']
    return r

def gen_opponent_bracket():
    """Generate one opponent bracket from public pick distribution."""
    picks = {}
    for g in games:
        picks[g['mid']] = g['hi'] if np.random.random() < g['pub_hi'] else g['lo']

    ep = picks.get('E_E8', 'Duke'); sp = picks.get('S_E8', 'Florida')
    f4e = lev_data.get(ep, {}).get('F4', 0.5)
    f4s = lev_data.get(sp, {}).get('F4', 0.5)
    t = f4e + f4s
    picks['F4_1'] = ep if np.random.random() < (f4e/t if t > 0 else 0.5) else sp

    wp = picks.get('W_E8', 'Arizona'); mp = picks.get('MW_E8', 'Michigan')
    f4w = lev_data.get(wp, {}).get('F4', 0.5)
    f4m = lev_data.get(mp, {}).get('F4', 0.5)
    t = f4w + f4m
    picks['F4_2'] = wp if np.random.random() < (f4w/t if t > 0 else 0.5) else mp

    n1 = ncg_dist.get(picks['F4_1'], 0.001)
    n2 = ncg_dist.get(picks['F4_2'], 0.001)
    t = n1 + n2
    picks['NCG'] = picks['F4_1'] if np.random.random() < (n1/t if t > 0 else 0.5) else picks['F4_2']
    return picks

def gen_entropy_bracket(target_upsets):
    """Generate bracket with target_upsets upsets in R64-E8."""
    upset_probs = [(i, 1 - g['vp']) for i, g in enumerate(games)]
    upset_probs.sort(key=lambda x: -x[1])

    upset_set = set()
    for idx, up in upset_probs:
        if len(upset_set) >= target_upsets:
            break
        if np.random.random() < up * 1.8:
            upset_set.add(idx)
    for idx, up in upset_probs:
        if len(upset_set) >= target_upsets:
            break
        upset_set.add(idx)

    picks = {}
    for i, g in enumerate(games):
        picks[g['mid']] = g['lo'] if i in upset_set else g['hi']

    ep = picks.get('E_E8', 'Duke'); sp = picks.get('S_E8', 'Florida')
    picks['F4_1'] = ep if float(prob_data[ep]['r5']) >= float(prob_data[sp]['r5']) else sp
    wp = picks.get('W_E8', 'Arizona'); mp = picks.get('MW_E8', 'Michigan')
    picks['F4_2'] = wp if float(prob_data[wp]['r5']) >= float(prob_data[mp]['r5']) else mp
    picks['NCG'] = picks['F4_1'] if float(prob_data[picks['F4_1']]['r6']) >= float(prob_data[picks['F4_2']]['r6']) else picks['F4_2']
    return picks

def score_bracket(picks, actual):
    """Score a bracket against actual results."""
    score = 0
    for gid, winner in actual.items():
        if gid in picks and picks[gid] == winner:
            score += round_pts_from_mid(gid)
    return score

# ============================================================
# CORRECTED SIMULATION: CDF-BASED APPROACH
# ============================================================
# For each tournament outcome:
#   1. Score N_OPP_SAMPLE opponent brackets -> empirical CDF
#   2. Score our bracket -> our_score
#   3. P(win | N) = P(our_score > all N-1 opponents)
#      = (fraction of opponents scoring < our_score)^(N-1)
#      With ties: P(opponent < our_score) computed strictly
#
# Average P(win) across all tournament sims = expected win rate.

def run_simulation(label, use_uncorrected=False):
    """Run corrected CDF-based simulation."""
    print(f"  Running [{label}]...", end='', flush=True)

    # results[pool_size][upset_count] = list of per-sim win probs
    results = {ps: {u: [] for u in UPSET_COUNTS} for ps in POOL_SIZES}

    for s in range(N_SIMS):
        # 1. Simulate tournament outcome
        actual = sim_tournament(use_uncorrected)

        # 2. Score N_OPP_SAMPLE opponent brackets
        opp_scores = np.zeros(N_OPP_SAMPLE)
        for o in range(N_OPP_SAMPLE):
            opp = gen_opponent_bracket()
            opp_scores[o] = score_bracket(opp, actual)

        # Sort for CDF computation
        opp_scores_sorted = np.sort(opp_scores)

        # 3. For each upset count, score our bracket and compute P(win|N)
        for u in UPSET_COUNTS:
            our = gen_entropy_bracket(u)
            our_score = score_bracket(our, actual)

            # Fraction of opponents scoring strictly less than our_score
            # This is the empirical CDF at our_score (strictly less)
            n_beaten = np.searchsorted(opp_scores_sorted, our_score, side='left')
            frac_beaten = n_beaten / N_OPP_SAMPLE

            for ps in POOL_SIZES:
                # P(win) = P(beat all N-1 opponents) = frac_beaten^(N-1)
                if frac_beaten > 0:
                    p_win = frac_beaten ** (ps - 1)
                else:
                    p_win = 0.0
                results[ps][u].append(p_win)

        if (s + 1) % 500 == 0:
            print(f" {s+1}", end='', flush=True)

    print(" done.")

    # Average across sims
    avg_results = {}
    for ps in POOL_SIZES:
        for u in UPSET_COUNTS:
            avg_results[(ps, u)] = np.mean(results[ps][u])

    return avg_results

# ============================================================
# RUN ALL SIMULATIONS
# ============================================================
print("=" * 90)
print("RUNNING CORRECTED MONTE CARLO SIMULATIONS (CDF-based)")
print("=" * 90)
print(f"  N_SIMS={N_SIMS}, N_OPP_SAMPLE={N_OPP_SAMPLE}")
print(f"  Pool sizes: {POOL_SIZES}")
print(f"  Upset counts: 0-{max(UPSET_COUNTS)}\n")

res_corrected = run_simulation('corrected', use_uncorrected=False)
res_uncorrected = run_simulation('uncorrected', use_uncorrected=True)

# Sensitivity Check 3: uncertainty bounds
def make_modified_games(bound):
    modified = []
    for g in games:
        ng = dict(g)
        hi, lo, rd = g['hi'], g['lo'], g['round']
        tier_col = {'R64': 'confidence_tier_r1', 'R32': 'confidence_tier_r2',
                    'S16': 'confidence_tier_r3', 'E8': 'confidence_tier_r4'}.get(rd)
        if tier_col:
            hi_tier = prob_data[hi].get(tier_col, 'HIGH')
            lo_tier = prob_data[lo].get(tier_col, 'HIGH')
            if hi_tier == 'LOW' or lo_tier == 'LOW':
                if bound == 'low':
                    ng['vp'] = max(0.35, g['vp'] - 0.05)
                else:
                    ng['vp'] = min(0.95, g['vp'] + 0.05)
        modified.append(ng)
    return modified

orig_games = games
games = make_modified_games('low')
res_prob_low = run_simulation('prob_low')
games = make_modified_games('high')
res_prob_high = run_simulation('prob_high')
games = orig_games

# ============================================================
# FIND OPTIMAL
# ============================================================
def find_optimal(results):
    opt = {}
    for ps in POOL_SIZES:
        best_u, best_wr = 0, 0
        for u in UPSET_COUNTS:
            wr = results.get((ps, u), 0)
            if wr > best_wr:
                best_wr = wr
                best_u = u
        opt[ps] = (best_u, best_wr)
    return opt

opt_c = find_optimal(res_corrected)
opt_u = find_optimal(res_uncorrected)
opt_lo = find_optimal(res_prob_low)
opt_hi = find_optimal(res_prob_high)

# ============================================================
# PRE-FIX vs POST-FIX COMPARISON
# ============================================================
print("\n" + "=" * 90)
print("BUG FIX VALIDATION: Pre-fix vs Post-fix Win Rates")
print("=" * 90)

pre_fix_rates = {50: 0.052, 200: 0.053, 1000: 0.051, 10000: 0.052}
print(f"\n{'Pool':>8} {'Pre-fix':>10} {'Post-fix':>10} {'Expected Range':>20} {'Status':>10}")
print("-" * 65)
for ps in POOL_SIZES:
    pre = pre_fix_rates[ps]
    post_u, post_wr = opt_c[ps]
    expected_ranges = {50: (0.03, 0.08), 200: (0.01, 0.03),
                       1000: (0.003, 0.01), 10000: (0.0005, 0.002)}
    lo, hi = expected_ranges[ps]
    in_range = lo <= post_wr <= hi
    status = "OK" if in_range else "INVESTIGATE"
    print(f"{ps:>8} {pre:>9.1%} {post_wr:>9.4%} {lo:.3%}-{hi:.3%}       {status:>10}")

# ============================================================
# OPTIMAL UPSET BUDGET TABLE
# ============================================================
print("\n" + "=" * 90)
print("OPTIMAL UPSET BUDGET BY POOL SIZE (corrected simulation)")
print("=" * 90)

print(f"\n{'Pool':>8} {'Corrected':>22} {'Uncorrected':>22} {'Delta':>8}")
print(f"{'':>8} {'Upsets   WinRate':>22} {'Upsets   WinRate':>22} {'Upsets':>8}")
print("-" * 65)
for ps in POOL_SIZES:
    cu, cw = opt_c[ps]
    uu, uw = opt_u[ps]
    print(f"{ps:>8} {cu:>8} {cw:>10.4%}    {uu:>8} {uw:>10.4%}    {cu-uu:>+6d}")

# Monotonicity check
print("\nSANITY CHECK — Monotonicity:")
prev = 0
ok = True
for ps in POOL_SIZES:
    u, _ = opt_c[ps]
    if u < prev:
        print(f"  VIOLATION at N={ps}: {u} < {prev}")
        ok = False
    prev = u
print(f"  {'PASSED' if ok else 'FAILED — investigating'}: optimal upsets non-decreasing with pool size")

# ============================================================
# SENSITIVITY CHECK 1 — E8 Correction Impact
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY CHECK 1 — E8 Correction Impact")
print("=" * 90)
for ps in POOL_SIZES:
    cu, cw = opt_c[ps]
    uu, uw = opt_u[ps]
    d = cu - uu
    print(f"  N={ps:>5}: corrected={cu} upsets ({cw:.4%}), uncorrected={uu} upsets ({uw:.4%}), delta={d:+d}")

# ============================================================
# SENSITIVITY CHECK 3 — Single-source Uncertainty
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY CHECK 3 — Single-source Uncertainty")
print("=" * 90)
for ps in POOL_SIZES:
    lu, _ = opt_lo[ps]
    hu, _ = opt_hi[ps]
    spread = abs(hu - lu)
    flag = " *** SENSITIVE" if spread > 2 else ""
    print(f"  N={ps:>5}: low_bound={lu} upsets, high_bound={hu} upsets, spread={spread}{flag}")

# ============================================================
# FLAT CURVE CHECK
# ============================================================
print("\n" + "=" * 90)
print("FLAT CURVE CHECK — Does the win-rate curve steepen after fix?")
print("=" * 90)

for ps in POOL_SIZES:
    chalk_wr = res_corrected.get((ps, 0), 0)
    opt_upsets, opt_wr = opt_c[ps]
    delta_pp = (opt_wr - chalk_wr) * 100
    pct_improvement = (opt_wr / chalk_wr - 1) * 100 if chalk_wr > 0 else 0
    print(f"  N={ps:>5}: chalk={chalk_wr:.4%}  optimal({opt_upsets} upsets)={opt_wr:.4%}  "
          f"delta={delta_pp:+.2f}pp  improvement={pct_improvement:+.1f}%")

# ============================================================
# WIN RATE TABLE
# ============================================================
print("\n" + "=" * 90)
print("WIN RATE vs UPSET COUNT (corrected)")
print("=" * 90)

print(f"\n{'Upsets':>7}", end="")
for ps in POOL_SIZES:
    print(f"  {'N='+str(ps):>12}", end="")
print()
print("-" * (7 + 14*len(POOL_SIZES)))

for u in UPSET_COUNTS:
    print(f"{u:>7}", end="")
    for ps in POOL_SIZES:
        wr = res_corrected.get((ps, u), 0)
        m = " *" if opt_c[ps][0] == u else "  "
        print(f"  {wr:>10.4%}{m}", end="")
    print()
print("  * = optimal")

# ============================================================
# OUTPUT CSV
# ============================================================
fields = ['pool_size', 'upset_count', 'win_rate_corrected', 'win_rate_uncorrected',
          'win_rate_prob_low', 'win_rate_prob_high',
          'optimal_corrected_flag', 'optimal_uncorrected_flag']

with open('entropy_optimization_2026.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for ps in POOL_SIZES:
        for u in UPSET_COUNTS:
            w.writerow({
                'pool_size': ps,
                'upset_count': u,
                'win_rate_corrected': f"{res_corrected.get((ps,u),0):.8f}",
                'win_rate_uncorrected': f"{res_uncorrected.get((ps,u),0):.8f}",
                'win_rate_prob_low': f"{res_prob_low.get((ps,u),0):.8f}",
                'win_rate_prob_high': f"{res_prob_high.get((ps,u),0):.8f}",
                'optimal_corrected_flag': 'Y' if u == opt_c[ps][0] else 'N',
                'optimal_uncorrected_flag': 'Y' if u == opt_u[ps][0] else 'N',
            })
print(f"\nWrote entropy_optimization_2026.csv")

# ============================================================
# PLOT
# ============================================================
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 7))
    colors = {50: '#1f77b4', 200: '#ff7f0e', 1000: '#2ca02c', 10000: '#d62728'}
    for ps in POOL_SIZES:
        wrs = [res_corrected.get((ps, u), 0) for u in UPSET_COUNTS]
        ax.plot(UPSET_COUNTS, wrs, '-o', color=colors[ps], label=f'N={ps}', markersize=3)
        ou, owr = opt_c[ps]
        ax.annotate(f'{ou} upsets\n{owr:.3%}', xy=(ou, owr),
                    xytext=(ou+1.5, owr + owr*0.05), fontsize=8, color=colors[ps],
                    arrowprops=dict(arrowstyle='->', color=colors[ps], lw=0.8))

    ax.set_xlabel('Number of Upset Picks (R64-E8)', fontsize=12)
    ax.set_ylabel('Win Rate P(Rank 1)', fontsize=12)
    ax.set_title('Optimal Upset Budget by Pool Size — 2026 NCAA Tournament (corrected)', fontsize=14)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')
    plt.tight_layout()
    plt.savefig('entropy_optimization_2026.png', dpi=150)
    print("Saved entropy_optimization_2026.png")
except Exception as e:
    print(f"Plot skipped: {e}")

# ============================================================
# BUG REPORT
# ============================================================
bug_report = f"""SIMULATION AUDIT REPORT — entropy_optimization.py
{'='*60}

BUG IDENTIFICATION
------------------
Check A — Pool size parameter usage: **BUG FOUND (PRIMARY)**
  Line 126: N_OPP_PER_SIM = 40 (hardcoded cap)
  Line 246: n_opp = min(pool_size - 1, N_OPP_PER_SIM)

  For N=50:    n_opp = min(49, 40) = 40
  For N=200:   n_opp = min(199, 40) = 40
  For N=1000:  n_opp = min(999, 40) = 40
  For N=10000: n_opp = min(9999, 40) = 40

  ALL pool sizes above 41 used exactly 40 opponents.
  This is why win rates were ~5% for all pool sizes.

Check B — Win condition: Correct in structure (beat ALL opponents)
  but operated on capped 40-opponent pool. Secondary consequence
  of Check A bug.

Check C — Opponent bracket generation: OK. Opponents independently
  generated per sim iteration.

Check D — Scoring: OK. ESPN point-doubling correctly applied
  (R64=10, R32=20, S16=40, E8=80, F4=160, NCG=320).

FIX APPLIED
-----------
Replaced direct opponent-counting approach with CDF-based method:
  1. Generate {N_OPP_SAMPLE} opponent brackets per tournament sim
  2. Score all opponents, build empirical score CDF
  3. P(win | pool_size=N) = CDF(our_score)^(N-1)

This correctly scales win probability with pool size without
needing to generate N-1 brackets for each N.

PRE-FIX WIN RATES (at optimal upset count)
-------------------------------------------
  N=50:    5.2%
  N=200:   5.3%
  N=1000:  5.1%
  N=10000: 5.2%
  (All approximately equal — the bug signature)

POST-FIX WIN RATES
------------------
"""

for ps in POOL_SIZES:
    cu, cw = opt_c[ps]
    chalk_wr = res_corrected.get((ps, 0), 0)
    bug_report += f"  N={ps:>5}: {cw:.4%} at {cu} upsets (chalk: {chalk_wr:.4%})\n"

# Flat curve finding
bug_report += f"""
FLAT CURVE FINDING
------------------
"""
for ps in POOL_SIZES:
    chalk_wr = res_corrected.get((ps, 0), 0)
    opt_upsets, opt_wr = opt_c[ps]
    delta_pp = (opt_wr - chalk_wr) * 100
    bug_report += f"  N={ps:>5}: chalk={chalk_wr:.4%} vs optimal({opt_upsets})={opt_wr:.4%} delta={delta_pp:+.2f}pp\n"

bug_report += f"""
MONOTONICITY CHECK: {'PASSED' if ok else 'FAILED'}

SENSITIVITY CHECKS (post-fix)
------------------------------
"""
for ps in POOL_SIZES:
    cu, _ = opt_c[ps]
    uu, _ = opt_u[ps]
    lu, _ = opt_lo[ps]
    hu, _ = opt_hi[ps]
    bug_report += f"  N={ps:>5}: E8_delta={cu-uu:+d}  uncertainty_spread={abs(hu-lu)}\n"

with open('simulation_audit_2026.txt', 'w') as f:
    f.write(bug_report)
print("Wrote simulation_audit_2026.txt")

# ============================================================
# FINAL SUMMARY
# ============================================================
print("\n" + "=" * 90)
print("FINAL SUMMARY — CORRECTED OPTIMAL UPSET COUNT")
print("=" * 90)
print(f"\n{'Pool':>8} {'Opt Upsets':>10} {'Win Rate':>10} {'vs Chalk':>10} {'E8 Δ':>6} {'Lo':>5} {'Hi':>5}")
print("-" * 58)
for ps in POOL_SIZES:
    cu, cw = opt_c[ps]
    chalk_wr = res_corrected.get((ps, 0), 0)
    uu, _ = opt_u[ps]
    lu, _ = opt_lo[ps]
    hu, _ = opt_hi[ps]
    print(f"{ps:>8} {cu:>10} {cw:>9.4%} {cw-chalk_wr:>+9.4%} {cu-uu:>+5d} {lu:>5} {hu:>5}")
