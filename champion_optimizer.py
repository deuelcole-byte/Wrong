#!/usr/bin/env python3
"""
Prompt 6 — Champion Selection Optimizer

Computes expected_value = r6_prob * (N - public_pick_pct * N) for each
champion candidate across pool sizes, with ownership tier classification,
sign-flip guards, path dependency checks, and uncertainty bounds.
"""
import csv
import math

# ============================================================
# LOAD DATA
# ============================================================
# Probability baseline
prob_data = {}
with open('probability_baseline_final_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        prob_data[row['team_name']] = row

# NCG pick distribution (authoritative source from Prompt 5b)
ncg_picks = {}
with open('ncg_pick_distribution_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        ncg_picks[row['team_name']] = {
            'pct': float(row['ncg_public_pick_pct']),
            'floor_applied': row['floor_applied'],
            'data_source': row['data_source'],
        }

# Leverage matrix for confidence types
leverage_types = {}
with open('leverage_matrix_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        key = (row['team_name'], row['round'])
        leverage_types[key] = row

POOL_SIZES = [10, 25, 50, 100, 250, 500, 1000, 5000]

# ============================================================
# BUILD CANDIDATE LIST
# ============================================================
candidates = []
for team_name, pdata in prob_data.items():
    r6 = float(pdata['r6'])
    r6_low = float(pdata['r6_low'])
    r6_high = float(pdata['r6_high'])
    near_zero = pdata['near_zero_flag']
    first_four = pdata['first_four_flag']
    path_dep = pdata['path_dependent_flag']
    r4_adj = float(pdata['r4_adjusted'])
    r4_alt = float(pdata['r4_adjusted_alt'])
    r5 = float(pdata['r5'])
    conf_tier_r6 = pdata['confidence_tier_r6']

    pick_info = ncg_picks.get(team_name, {'pct': 0, 'floor_applied': 'N', 'data_source': 'zero'})
    public_pct = pick_info['pct'] / 100.0  # Convert to fraction
    floor_applied = pick_info['floor_applied']
    data_source = pick_info['data_source']

    # Exclude near_zero_flag teams
    if near_zero == 'Y':
        continue

    # Ownership tier
    pct_display = pick_info['pct']  # percentage form
    if pct_display > 10:
        ownership_tier = 'HIGH'
    elif pct_display >= 1:
        ownership_tier = 'LOW_OWN'  # 1-10%
    else:
        ownership_tier = 'NEAR_ZERO'

    # Confidence type from leverage matrix
    lev_entry = leverage_types.get((team_name, 'E8'), {})
    conf_type = lev_entry.get('confidence_type', 'NA')

    # Path dependency: compute r6 range if Type C
    if path_dep == 'Y' and r4_adj > 0:
        # Scale r6 by ratio of r4_alt / r4_adj
        r4_ratio = r4_alt / r4_adj if r4_adj > 0 else 1.0
        r6_path_alt = r6 * r4_ratio
        r6_path_low = min(r6, r6_path_alt)
        r6_path_high = max(r6, r6_path_alt)
    else:
        r6_path_alt = r6
        r6_path_low = r6
        r6_path_high = r6

    candidates.append({
        'team_name': team_name,
        'team_seed': int(pdata['team_seed']),
        'region': pdata['region'],
        'r6': r6,
        'r6_low': r6_low,
        'r6_high': r6_high,
        'r6_path_alt': r6_path_alt,
        'r6_path_low': r6_path_low,
        'r6_path_high': r6_path_high,
        'public_pct': public_pct,
        'public_pct_display': pct_display,
        'ownership_tier': ownership_tier,
        'conf_tier_r6': conf_tier_r6,
        'conf_type': conf_type,
        'floor_applied': floor_applied,
        'path_dependent': path_dep,
        'data_source': data_source,
    })

# Sort by r6 descending
candidates.sort(key=lambda x: -x['r6'])
print(f"Champion candidates: {len(candidates)} (after excluding near_zero_flag)")

# ============================================================
# EXPECTED VALUE COMPUTATION
# ============================================================
def compute_ev(r6_prob, public_pct, N):
    """EV = r6_prob * (N - public_pct * N) = r6_prob * N * (1 - public_pct)"""
    return r6_prob * (N - public_pct * N)


# ============================================================
# OWNERSHIP TIER CLASSIFICATION
# ============================================================
print("\n" + "=" * 100)
print("OWNERSHIP TIER CLASSIFICATION")
print("=" * 100)

for tier, label in [('HIGH', 'HIGH OWNERSHIP (>10%)'),
                     ('LOW_OWN', 'LOW OWNERSHIP (1-10%)'),
                     ('NEAR_ZERO', 'NEAR-ZERO OWNERSHIP (<1%)')]:
    tier_teams = [c for c in candidates if c['ownership_tier'] == tier]
    print(f"\n  {label}:")
    for c in sorted(tier_teams, key=lambda x: -x['r6']):
        flag = " [FLOOR]" if c['floor_applied'] == 'Y' else ""
        path = " [PATH-DEP]" if c['path_dependent'] == 'Y' else ""
        print(f"    {c['team_name']:<18} seed={c['team_seed']:>2}  "
              f"r6={c['r6']:>5.1%}  public={c['public_pct_display']:>6.2f}%  "
              f"leverage={c['r6'] - c['public_pct']:>+6.1%}{flag}{path}")

# ============================================================
# FULL EV MATRIX ACROSS POOL SIZES
# ============================================================
print("\n\n" + "=" * 100)
print("EXPECTED VALUE MATRIX — TOP 15 CANDIDATES ACROSS POOL SIZES")
print("=" * 100)

# Compute EV for all candidates at all pool sizes
for c in candidates:
    c['ev_by_pool'] = {}
    c['ev_low_by_pool'] = {}
    c['ev_high_by_pool'] = {}
    c['ev_path_alt_by_pool'] = {}
    for N in POOL_SIZES:
        c['ev_by_pool'][N] = compute_ev(c['r6'], c['public_pct'], N)
        c['ev_low_by_pool'][N] = compute_ev(c['r6_low'], c['public_pct'], N)
        c['ev_high_by_pool'][N] = compute_ev(c['r6_high'], c['public_pct'], N)
        c['ev_path_alt_by_pool'][N] = compute_ev(c['r6_path_alt'], c['public_pct'], N)

# Find optimal pick at each pool size
print(f"\n{'N':>6}", end="")
for N in POOL_SIZES:
    print(f"  {'N='+str(N):>12}", end="")
print()
print("-" * (6 + 14 * len(POOL_SIZES)))

# Show top 15 candidates sorted by EV at N=100
top_by_ev100 = sorted(candidates, key=lambda x: -x['ev_by_pool'][100])[:15]

for c in top_by_ev100:
    print(f"{c['team_name']:<18} [{c['ownership_tier']:<9}]", end="")
    for N in POOL_SIZES:
        print(f"  {c['ev_by_pool'][N]:>11.3f}", end="")
    print()

# Optimal picks row
print(f"\n{'OPTIMAL':>18} {'':>11}", end="")
optimal_picks = {}
for N in POOL_SIZES:
    best = max(candidates, key=lambda x: x['ev_by_pool'][N])
    optimal_picks[N] = best
    print(f"  {best['team_name']:>11}", end="")
print()

# ============================================================
# OPTIMAL PICK TABLE WITH FULL METADATA
# ============================================================
print("\n\n" + "=" * 100)
print("OPTIMAL CHAMPION PICK BY POOL SIZE (with metadata)")
print("=" * 100)

print(f"\n{'Pool':>6} {'Champion':<18} {'Tier':<10} {'r6':>6} {'Public':>7} "
      f"{'EV':>8} {'Conf':>5} {'Type':>4} {'Floor':>5} {'Path':>5}")
print("-" * 90)

for N in POOL_SIZES:
    c = optimal_picks[N]
    print(f"{N:>6} {c['team_name']:<18} {c['ownership_tier']:<10} "
          f"{c['r6']:>5.1%} {c['public_pct_display']:>6.2f}% "
          f"{c['ev_by_pool'][N]:>7.3f} {c['conf_tier_r6']:>5} "
          f"{c['conf_type']:>4} {c['floor_applied']:>5} "
          f"{c['path_dependent']:>5}")

# ============================================================
# SIGN-FLIP GUARD
# ============================================================
print("\n\n" + "=" * 100)
print("SIGN-FLIP GUARD — Type C Path-Dependent Teams")
print("=" * 100)

sign_flip_teams = ['Iowa State', 'Purdue']
for team_name in sign_flip_teams:
    c = next((x for x in candidates if x['team_name'] == team_name), None)
    if c is None:
        continue
    print(f"\n  {team_name} (seed {c['team_seed']}, {c['region']})")
    print(f"    r6 (primary path):  {c['r6']:.4f}")
    print(f"    r6 (alt path):      {c['r6_path_alt']:.4f}")
    print(f"    r6 ratio (alt/pri): {c['r6_path_alt']/c['r6']:.2f}x")
    print(f"    Public pick pct:    {c['public_pct_display']:.2f}%")
    print(f"\n    {'Pool':>6} {'EV(primary)':>12} {'EV(alt)':>12} {'Delta%':>8} {'Optimal?':>10}")
    print(f"    {'-'*50}")
    for N in POOL_SIZES:
        ev_pri = c['ev_by_pool'][N]
        ev_alt = c['ev_path_alt_by_pool'][N]
        delta_pct = ((ev_alt - ev_pri) / ev_pri * 100) if ev_pri > 0 else 0
        is_optimal = "YES ***" if optimal_picks[N]['team_name'] == team_name else "no"
        print(f"    {N:>6} {ev_pri:>11.3f} {ev_alt:>11.3f} {delta_pct:>+7.1f}% {is_optimal:>10}")

# ============================================================
# PATH DEPENDENCY CHECK — ALL TYPE C TEAMS
# ============================================================
print("\n\n" + "=" * 100)
print("PATH DEPENDENCY CHECK — All Type C Teams")
print("=" * 100)

type_c_teams = [c for c in candidates if c['path_dependent'] == 'Y']
for c in type_c_teams:
    print(f"\n  {c['team_name']:<18} r6={c['r6']:.4f}  r6_alt={c['r6_path_alt']:.4f}  "
          f"ratio={c['r6_path_alt']/c['r6']:.2f}x  public={c['public_pct_display']:.2f}%")
    # Check if EV changes by >15% at any pool size
    for N in POOL_SIZES:
        ev_pri = c['ev_by_pool'][N]
        ev_alt = c['ev_path_alt_by_pool'][N]
        if ev_pri > 0:
            delta_pct = abs(ev_alt - ev_pri) / ev_pri * 100
            if delta_pct > 15:
                print(f"    FLAG: N={N} EV changes by {delta_pct:.1f}% across path scenarios")
                break
    else:
        print(f"    OK: EV change < 15% across all pool sizes")

# ============================================================
# UNCERTAINTY BOUNDS CHECK
# ============================================================
print("\n\n" + "=" * 100)
print("UNCERTAINTY BOUNDS CHECK — r6_low vs r6_high")
print("=" * 100)

unstable_pools = []
for N in POOL_SIZES:
    best_low = max(candidates, key=lambda x: x['ev_low_by_pool'][N])
    best_mid = max(candidates, key=lambda x: x['ev_by_pool'][N])
    best_high = max(candidates, key=lambda x: x['ev_high_by_pool'][N])

    if best_low['team_name'] != best_mid['team_name'] or best_high['team_name'] != best_mid['team_name']:
        unstable_pools.append(N)
        print(f"\n  UNSTABLE at N={N}:")
        print(f"    r6_low  optimal: {best_low['team_name']:<18} EV={best_low['ev_low_by_pool'][N]:.3f}")
        print(f"    r6_mid  optimal: {best_mid['team_name']:<18} EV={best_mid['ev_by_pool'][N]:.3f}")
        print(f"    r6_high optimal: {best_high['team_name']:<18} EV={best_high['ev_high_by_pool'][N]:.3f}")

if not unstable_pools:
    print("\n  All pool sizes have STABLE optimal picks across uncertainty bounds")
else:
    print(f"\n  Unstable pool sizes: {unstable_pools}")

# Show detailed uncertainty for top 5 candidates
print(f"\n  Uncertainty ranges for top 5 candidates (N=100):")
print(f"  {'Team':<18} {'r6_low':>7} {'r6_mid':>7} {'r6_high':>7} "
      f"{'EV_low':>8} {'EV_mid':>8} {'EV_high':>8} {'Range%':>8}")
for c in sorted(candidates, key=lambda x: -x['ev_by_pool'][100])[:5]:
    ev_lo = c['ev_low_by_pool'][100]
    ev_mid = c['ev_by_pool'][100]
    ev_hi = c['ev_high_by_pool'][100]
    range_pct = (ev_hi - ev_lo) / ev_mid * 100 if ev_mid > 0 else 0
    print(f"  {c['team_name']:<18} {c['r6_low']:>6.1%} {c['r6']:>6.1%} {c['r6_high']:>6.1%} "
          f"{ev_lo:>7.3f} {ev_mid:>7.3f} {ev_hi:>7.3f} {range_pct:>+7.1f}%")

# ============================================================
# CROSSOVER ANALYSIS: When to deviate from Duke/Arizona
# ============================================================
print("\n\n" + "=" * 100)
print("CROSSOVER ANALYSIS: At what pool size deviate from Duke/Arizona?")
print("=" * 100)

duke = next(c for c in candidates if c['team_name'] == 'Duke')
arizona = next(c for c in candidates if c['team_name'] == 'Arizona')

print(f"\n  {'Pool':>6} {'Duke EV':>10} {'Arizona EV':>12} {'Best Non-D/A':<18} {'Its EV':>10} {'Winner':<18}")
print(f"  {'-'*80}")

for N in POOL_SIZES:
    duke_ev = duke['ev_by_pool'][N]
    az_ev = arizona['ev_by_pool'][N]
    non_da = max((c for c in candidates if c['team_name'] not in ('Duke', 'Arizona')),
                 key=lambda x: x['ev_by_pool'][N])
    non_da_ev = non_da['ev_by_pool'][N]
    best_overall = max(duke_ev, az_ev, non_da_ev)

    if best_overall == duke_ev:
        winner = "Duke"
    elif best_overall == az_ev:
        winner = "Arizona"
    else:
        winner = non_da['team_name']

    print(f"  {N:>6} {duke_ev:>9.3f} {az_ev:>11.3f} {non_da['team_name']:<18} "
          f"{non_da_ev:>9.3f} {winner:<18}")

# ============================================================
# GENUINE LEVERAGE VS FORMULA ARTIFACTS
# ============================================================
print("\n\n" + "=" * 100)
print("GENUINE LEVERAGE PLAYS vs FORMULA ARTIFACTS (among non-Duke/Arizona)")
print("=" * 100)

non_da = [c for c in candidates if c['team_name'] not in ('Duke', 'Arizona')]
non_da.sort(key=lambda x: -x['ev_by_pool'][100])

print(f"\n  {'Team':<18} {'Tier':<10} {'r6':>6} {'Public':>7} {'Lev':>7} "
      f"{'EV@100':>8} {'EV@500':>8} {'Assessment':<35}")
print(f"  {'-'*110}")

for c in non_da[:20]:
    leverage = c['r6'] - c['public_pct']
    ev100 = c['ev_by_pool'][100]
    ev500 = c['ev_by_pool'][500]

    if c['ownership_tier'] == 'NEAR_ZERO' and c['floor_applied'] == 'Y':
        assessment = "ARTIFACT — floor-applied"
    elif c['ownership_tier'] == 'NEAR_ZERO':
        assessment = "ARTIFACT — near-zero ownership"
    elif c['ownership_tier'] == 'LOW_OWN' and leverage > 0.03:
        assessment = "GENUINE — under-picked vs Vegas"
    elif c['ownership_tier'] == 'LOW_OWN' and leverage > 0:
        assessment = "MODERATE — slight under-pricing"
    elif c['ownership_tier'] == 'LOW_OWN':
        assessment = "WEAK — not under-picked"
    else:
        assessment = "GENUINE — high ownership leverage"

    if c['path_dependent'] == 'Y':
        assessment += " [PATH-DEP]"

    print(f"  {c['team_name']:<18} {c['ownership_tier']:<10} "
          f"{c['r6']:>5.1%} {c['public_pct_display']:>6.2f}% "
          f"{leverage:>+6.1%} {ev100:>7.3f} {ev500:>7.3f} {assessment:<35}")

# ============================================================
# PLAIN-LANGUAGE RECOMMENDATIONS
# ============================================================
print("\n\n" + "=" * 100)
print("PLAIN-LANGUAGE CHAMPION RECOMMENDATIONS")
print("=" * 100)

for N, label in [(25, "Small office pool (~25 entries)"),
                  (100, "Medium pool (~100 entries)"),
                  (500, "Large pool (~500 entries)")]:
    best = optimal_picks[N]
    # Also get runner-up
    ev_list = sorted(candidates, key=lambda x: -x['ev_by_pool'][N])
    runner_up = ev_list[1] if ev_list[0] == best else ev_list[0]

    print(f"\n  {label}:")
    print(f"    RECOMMENDED: {best['team_name']} "
          f"(r6={best['r6']:.1%}, public={best['public_pct_display']:.1f}%, "
          f"EV={best['ev_by_pool'][N]:.3f})")

    # Path dependency warning
    if best['path_dependent'] == 'Y':
        print(f"    ⚠ PATH-CONDITIONAL: This pick depends on E8 matchup assumption.")
        print(f"      Alt-path EV: {best['ev_path_alt_by_pool'][N]:.3f}")

    # Ownership tier context
    if best['ownership_tier'] == 'HIGH':
        print(f"    Ownership context: High-ownership pick. Genuine contrarian signal —")
        print(f"      public significantly over-picks this team relative to Vegas probability.")
    elif best['ownership_tier'] == 'LOW_OWN':
        print(f"    Ownership context: Low-ownership pick. Leverage comes from both")
        print(f"      probability edge and low public adoption, but ownership gap is moderate.")
    elif best['ownership_tier'] == 'NEAR_ZERO':
        print(f"    CAUTION: Near-zero ownership. High EV is partly a formula artifact")
        print(f"      from extremely low public picks, not solely from probability edge.")

    print(f"    Runner-up: {runner_up['team_name']} (EV={runner_up['ev_by_pool'][N]:.3f})")

    # Stability note
    if N in unstable_pools:
        print(f"    NOTE: This pool size has UNSTABLE recommendation across uncertainty bounds.")

# ============================================================
# FOUR KEY QUESTIONS
# ============================================================
print("\n\n" + "=" * 100)
print("ANSWERS TO FOUR KEY QUESTIONS")
print("=" * 100)

# Q1: At what pool size does it become optimal to deviate from Duke/Arizona?
print(f"""
Q1: At what pool size does it become optimal to deviate from Duke or Arizona?
""")
for N in POOL_SIZES:
    best = optimal_picks[N]
    if best['team_name'] not in ('Duke', 'Arizona'):
        print(f"  At N={N}, the optimal pick shifts to {best['team_name']}.")
        print(f"  Below N={N}, Duke or Arizona provides the best EV.")
        break
else:
    print(f"  Duke or Arizona is optimal at ALL tested pool sizes ({POOL_SIZES}).")
    # Find the closest competitor
    for N in POOL_SIZES:
        best = optimal_picks[N]
        ev_list = sorted(candidates, key=lambda x: -x['ev_by_pool'][N])
        gap = ev_list[0]['ev_by_pool'][N] - ev_list[1]['ev_by_pool'][N]
        print(f"    N={N}: {best['team_name']} leads by {gap:.3f} EV over {ev_list[1]['team_name']}")

# Q2: Genuine leverage vs artifacts
print(f"""
Q2: Among non-Duke/Arizona teams, which are genuine leverage plays vs artifacts?
""")
genuine = [c for c in non_da if c['ownership_tier'] == 'LOW_OWN' and c['r6'] - c['public_pct'] > 0.02]
artifacts = [c for c in non_da if c['ownership_tier'] == 'NEAR_ZERO']
print(f"  Genuine leverage plays (LOW_OWN tier, >2pp edge over public):")
for c in sorted(genuine, key=lambda x: -(x['r6'] - x['public_pct'])):
    lev = c['r6'] - c['public_pct']
    print(f"    {c['team_name']:<18} r6={c['r6']:.1%}  public={c['public_pct_display']:.1f}%  edge={lev:>+5.1%}")
print(f"\n  Formula artifacts (NEAR_ZERO ownership, EV inflated by ownership gap):")
print(f"    {len(artifacts)} teams — their high EV scores reflect missing public data,")
print(f"    not genuine mispricing. Do not use for champion selection.")

# Q3: Path-conditional recommendations
print(f"""
Q3: Which champion recommendations are path-conditional?
""")
path_cands = [c for c in candidates if c['path_dependent'] == 'Y' and c['r6'] > 0.01]
if path_cands:
    for c in path_cands:
        ratio = c['r6_path_alt'] / c['r6'] if c['r6'] > 0 else 0
        print(f"  {c['team_name']:<18} r6={c['r6']:.1%} (primary) vs {c['r6_path_alt']:.1%} (alt)  "
              f"ratio={ratio:.2f}x")
        for N in [100, 500]:
            ev_change = abs(c['ev_path_alt_by_pool'][N] - c['ev_by_pool'][N]) / c['ev_by_pool'][N] * 100
            print(f"    N={N}: EV changes by {ev_change:.1f}% across paths")
else:
    print("  No path-conditional champion candidates with r6 > 1%.")

# Q4: Sensitivity to single-source risk
print(f"""
Q4: How sensitive is each recommendation to single-source estimation risk?
""")
for N in [25, 100, 500]:
    best = optimal_picks[N]
    ev_lo = best['ev_low_by_pool'][N]
    ev_mid = best['ev_by_pool'][N]
    ev_hi = best['ev_high_by_pool'][N]
    range_pct = (ev_hi - ev_lo) / ev_mid * 100
    # Check if runner-up overtakes at r6_low
    runner_candidates = sorted(candidates, key=lambda x: -x['ev_low_by_pool'][N])
    runner_low = runner_candidates[0]
    overtake = runner_low['team_name'] != best['team_name']
    print(f"  N={N}: {best['team_name']}  EV range: {ev_lo:.3f} — {ev_hi:.3f} "
          f"(±{range_pct/2:.1f}%)")
    if overtake:
        print(f"    UNSTABLE: At r6_low, {runner_low['team_name']} overtakes "
              f"(EV={runner_low['ev_low_by_pool'][N]:.3f})")
    else:
        print(f"    STABLE: Recommendation holds across uncertainty bounds")

# ============================================================
# OUTPUT CSV
# ============================================================
csv_fields = ['team_name', 'team_seed', 'region', 'r6', 'r6_low', 'r6_high',
              'r6_path_alt', 'r6_path_low', 'r6_path_high',
              'public_pct', 'public_pct_display', 'ownership_tier',
              'conf_tier_r6', 'conf_type', 'floor_applied', 'path_dependent',
              'data_source']
# Add EV columns for each pool size
for N in POOL_SIZES:
    csv_fields.append(f'ev_{N}')
    csv_fields.append(f'ev_low_{N}')
    csv_fields.append(f'ev_high_{N}')
    csv_fields.append(f'ev_path_alt_{N}')

with open('champion_optimizer_results.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=csv_fields)
    w.writeheader()
    for c in sorted(candidates, key=lambda x: -x['ev_by_pool'][100]):
        row = {k: c[k] for k in csv_fields if k in c}
        for N in POOL_SIZES:
            row[f'ev_{N}'] = f"{c['ev_by_pool'][N]:.6f}"
            row[f'ev_low_{N}'] = f"{c['ev_low_by_pool'][N]:.6f}"
            row[f'ev_high_{N}'] = f"{c['ev_high_by_pool'][N]:.6f}"
            row[f'ev_path_alt_{N}'] = f"{c['ev_path_alt_by_pool'][N]:.6f}"
        w.writerow(row)
print(f"\nWrote champion_optimizer_results.csv ({len(candidates)} candidates)")

print("\n" + "=" * 100)
print("CHAMPION OPTIMIZER COMPLETE")
print("=" * 100)
