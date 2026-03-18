#!/usr/bin/env python3
"""
Prompt 5 — Leverage Calculation Engine (updated per Prompt 5b audit)

Computes leverage = vegas_prob - public_pick_pct for every team in every round.
Classifies confidence types (A/B/C/NA), handles Type C leverage ranges,
and detects sign-flip risk for path-dependent teams.

CRITICAL FIX: Uses ncg_pick_distribution_2026.csv as authoritative NCG source.
Reconstructs F4 ownership from E8 matchup picks and regional advancement data
rather than using matchup-level head-to-head artifacts.
"""
import csv
from collections import defaultdict

# ============================================================
# CONFIGURATION
# ============================================================
ROUND_WEIGHTS = {'R64': 10, 'R32': 20, 'S16': 40, 'E8': 80, 'F4': 160, 'NCG': 320}
ROUND_TO_PROB_COL = {'R64': 'r1', 'R32': 'r2', 'S16': 'r3', 'E8': 'r4_adjusted', 'F4': 'r5', 'NCG': 'r6'}
ROUND_TO_TIER_COL = {'R64': 'confidence_tier_r1', 'R32': 'confidence_tier_r2',
                      'S16': 'confidence_tier_r3', 'E8': 'confidence_tier_r4',
                      'F4': 'confidence_tier_r5', 'NCG': 'confidence_tier_r6'}

# Type A teams (seed-line deviation)
TYPE_A_TEAMS = {'Vanderbilt', "St John's", 'Wisconsin', 'McNeese', 'Northern Iowa', 'High Point'}

# ============================================================
# LOAD PROBABILITY BASELINE
# ============================================================
prob_data = {}
with open('probability_baseline_final_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        prob_data[row['team_name']] = row

print(f"Loaded {len(prob_data)} teams from probability_baseline_final_2026.csv")

# ============================================================
# LOAD ESPN PICKS (R64 through E8 — matchup-level data is correct here)
# ============================================================
picks_data = []
with open('espn_picks_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if not row['round'].strip():
            continue
        picks_data.append(row)

print(f"Loaded {len(picks_data)} matchup rows from espn_picks_2026.csv")

# Build pick percentages: team -> round -> pick_pct
# Only use R64-E8 from matchup data (these are structurally correct)
team_picks = defaultdict(dict)
for row in picks_data:
    rd = row['round']
    if rd in ('F4', 'NCG', 'NCG_CHAMP'):
        continue  # Skip — these will be overridden below
    t1 = row['team_1_name']
    t2 = row['team_2_name']
    team_picks[t1][rd] = float(row['team_1_pick_pct']) / 100.0
    if t2:  # NCG_CHAMP rows have empty team_2
        team_picks[t2][rd] = float(row['team_2_pick_pct']) / 100.0

# ============================================================
# LOAD NCG DISTRIBUTION (authoritative, from Prompt 5b)
# ============================================================
ncg_dist = {}
with open('ncg_pick_distribution_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        ncg_dist[row['team_name']] = float(row['ncg_public_pick_pct']) / 100.0

print(f"Loaded {len(ncg_dist)} teams from ncg_pick_distribution_2026.csv (NCG authority)")

# Override NCG picks for ALL teams
for team_name in prob_data:
    team_picks[team_name]['NCG'] = ncg_dist.get(team_name, 0.0)

# ============================================================
# RECONSTRUCT F4 OWNERSHIP
# ============================================================
# F4 ownership = "what fraction of brackets have this team in the Final Four"
# = P(team wins their region) in public brackets.
#
# The E8 matchup picks give us the top-2 per region: e.g., Duke 81% and
# UConn 19% means 81% of brackets have Duke winning the East. But these
# two teams don't account for 100% of the region — some brackets have
# teams like Michigan St or Louisville winning through. We need to
# redistribute a small fraction from the E8 favorites to cover non-E8 teams.
#
# APPROACH: Per-region normalization.
# 1. E8 matchup picks for the top 2 teams in each region sum to 100%.
#    These ARE the dominant F4 picks but are slightly inflated because
#    ESPN's matchup UI forces a binary choice between predicted E8 teams.
# 2. Estimate non-E8 teams' F4 ownership from their S16/R32 picks.
# 3. Normalize WITHIN each region so each region sums to exactly 1.0.
#    This preserves the E8 teams' relative values while making room
#    for the long tail without compressing the leaders.

print("\nReconstructing F4 public ownership from E8 matchup picks...")
print("  Method: Per-region normalization (preserves E8 team absolute values)")

# Map teams to regions
team_regions = {}
for team_name, pdata in prob_data.items():
    team_regions[team_name] = pdata['region']

# Parse E8 matchup data by region
e8_matchups = [r for r in picks_data if r['round'] == 'E8']
e8_by_region = {}
for matchup in e8_matchups:
    # Extract region from matchup_id (e.g. "E_E8" -> East, "S_E8" -> South)
    mid = matchup['matchup_id']
    t1 = matchup['team_1_name']
    t2 = matchup['team_2_name']
    region = team_regions[t1]
    e8_by_region[region] = {
        t1: float(matchup['team_1_pick_pct']) / 100.0,
        t2: float(matchup['team_2_pick_pct']) / 100.0,
    }

# Build per-region F4 ownership
f4_ownership = {}
for region in ['East', 'South', 'West', 'Midwest']:
    region_teams = [t for t, r in team_regions.items() if r == region]
    e8_teams = e8_by_region.get(region, {})

    # Estimate non-E8 teams' F4 ownership
    non_e8_estimates = {}
    for team_name in region_teams:
        if team_name in e8_teams:
            continue
        # Use S16 pick% as proxy, with decay
        s16_pct = team_picks.get(team_name, {}).get('S16', 0)
        if s16_pct > 0:
            # Brackets with this team in S16: ~5-15% also have them
            # beating E8 opponent. Use 8% as middle estimate.
            non_e8_estimates[team_name] = s16_pct * 0.08
        else:
            r32_pct = team_picks.get(team_name, {}).get('R32', 0)
            if r32_pct > 0:
                non_e8_estimates[team_name] = r32_pct * 0.015
            else:
                non_e8_estimates[team_name] = 0.0005  # tiny floor

    non_e8_total = sum(non_e8_estimates.values())

    # The E8 pair sums to 1.0 (100% of ESPN's binary choice).
    # In reality, non-E8 teams take some fraction of that.
    # Estimate: non-E8 teams collectively hold ~5-15% of regional
    # F4 ownership. Use their estimated total, capped at 15%.
    non_e8_share = min(non_e8_total, 0.15)

    # Scale E8 teams down to make room for non-E8 share
    e8_scale = 1.0 - non_e8_share
    for team_name, raw_pct in e8_teams.items():
        f4_ownership[team_name] = raw_pct * e8_scale

    # Scale non-E8 teams to fill their share
    if non_e8_total > 0:
        for team_name, est in non_e8_estimates.items():
            f4_ownership[team_name] = (est / non_e8_total) * non_e8_share
    else:
        for team_name in non_e8_estimates:
            f4_ownership[team_name] = 0.0005

    # Verify region sums to ~1.0
    region_sum = sum(f4_ownership[t] for t in region_teams if t in f4_ownership)
    print(f"  {region:<8}: E8 teams scaled to {e8_scale:.3f}, "
          f"non-E8 share={non_e8_share:.3f}, region_sum={region_sum:.4f}")

f4_total_after = sum(f4_ownership.values())
print(f"  F4 ownership sum after normalization:  {f4_total_after:.3f}")

# Set F4 picks for all teams
for team_name in prob_data:
    team_picks[team_name]['F4'] = f4_ownership.get(team_name, 0.001)

# Report F4 reconstruction
print(f"\n  F4 ownership (top 15):")
f4_sorted = sorted(f4_ownership.items(), key=lambda x: -x[1])
for team, pct in f4_sorted[:15]:
    r5 = float(prob_data[team]['r5'])
    print(f"    {team:<18} F4_own={pct:>6.1%}  vegas_r5={r5:>6.1%}  leverage={r5-pct:>+6.1%}")

print(f"\n  DATA SOURCE NOTE:")
print(f"    R64-E8: ESPN matchup-level picks (structurally correct)")
print(f"    F4: Reconstructed from E8 winner pick% (= P(team wins region))")
print(f"    NCG: ncg_pick_distribution_2026.csv (Prompt 5b authoritative)")
print(f"    F4 non-E8 teams: S16_pick% * 0.10 decay proxy")

# ============================================================
# COMPUTE LEVERAGE FOR EVERY TEAM × ROUND
# ============================================================
leverage_rows = []

for team_name, pdata in prob_data.items():
    seed = int(pdata['team_seed'])
    region = pdata['region']
    first_four = pdata['first_four_flag']
    path_dep = pdata['path_dependent_flag']
    r4_alt = float(pdata['r4_adjusted_alt'])

    for rd_name, prob_col in ROUND_TO_PROB_COL.items():
        vegas_prob = float(pdata[prob_col])
        tier_col = ROUND_TO_TIER_COL[rd_name]
        conf_tier = pdata[tier_col]

        # Get public pick percentage
        pick_pct = team_picks.get(team_name, {}).get(rd_name)
        if pick_pct is None:
            continue  # Team not in ESPN picks for this round

        # Core leverage
        leverage = vegas_prob - pick_pct
        leverage_ratio = vegas_prob / pick_pct if pick_pct > 0 else 999.0

        # Confidence type classification
        if rd_name == 'R64' and team_name in TYPE_A_TEAMS:
            conf_type = 'A'
        elif rd_name == 'E8':
            if path_dep == 'Y':
                conf_type = 'C'
            else:
                conf_type = 'B'
        elif first_four == 'Y':
            conf_type = 'B'  # First four carry structural uncertainty
        else:
            conf_type = 'NA'

        # For Type C (path-dependent E8): compute leverage range
        if conf_type == 'C':
            leverage_at_alt = r4_alt - pick_pct
            leverage_low = min(leverage, leverage_at_alt)
            leverage_high = max(leverage, leverage_at_alt)
            sign_flip = (leverage > 0 and leverage_at_alt < 0) or (leverage < 0 and leverage_at_alt > 0)
        else:
            leverage_low = leverage
            leverage_high = leverage
            sign_flip = False

        # Round-weighted leverage
        weight = ROUND_WEIGHTS[rd_name]
        round_weighted_leverage = leverage * weight

        # High-signal flag
        high_signal = abs(leverage) > 0.10

        leverage_rows.append({
            'team_name': team_name,
            'team_seed': seed,
            'region': region,
            'round': rd_name,
            'vegas_prob': vegas_prob,
            'public_pick_pct': pick_pct,
            'leverage': leverage,
            'leverage_ratio': leverage_ratio,
            'leverage_low': leverage_low,
            'leverage_high': leverage_high,
            'round_weighted_leverage': round_weighted_leverage,
            'confidence_tier': conf_tier,
            'confidence_type': conf_type,
            'high_signal_flag': 'Y' if high_signal else 'N',
            'sign_flip_flag': 'Y' if sign_flip else 'N',
        })

print(f"\nComputed {len(leverage_rows)} leverage entries")

# ============================================================
# SUMMARY TABLE 1: TOP 15 BY ROUND-WEIGHTED LEVERAGE
# ============================================================
print("\n" + "=" * 130)
print("TABLE 1: TOP 15 HIGHEST-LEVERAGE TEAMS (by |round_weighted_leverage|)")
print("=" * 130)

# Sort by absolute round-weighted leverage
sorted_by_rwl = sorted(leverage_rows, key=lambda x: -abs(x['round_weighted_leverage']))

print(f"\n{'Team':<18} {'Sd':>2} {'Region':<8} {'Round':<5} {'Vegas':>7} {'Public':>7} "
      f"{'Lev':>7} {'Ratio':>6} {'Lev_Lo':>7} {'Lev_Hi':>7} {'RWL':>8} "
      f"{'Tier':<6} {'Type':<4} {'HiSig':>5} {'Flip':>4}")
print("-" * 130)

for entry in sorted_by_rwl[:15]:
    lev_lo_str = f"{entry['leverage_low']:>+6.1%}" if entry['confidence_type'] == 'C' else f"{'—':>7}"
    lev_hi_str = f"{entry['leverage_high']:>+6.1%}" if entry['confidence_type'] == 'C' else f"{'—':>7}"
    print(f"{entry['team_name']:<18} {entry['team_seed']:>2} {entry['region']:<8} "
          f"{entry['round']:<5} {entry['vegas_prob']:>6.1%} {entry['public_pick_pct']:>6.1%} "
          f"{entry['leverage']:>+6.1%} {entry['leverage_ratio']:>5.2f}x "
          f"{lev_lo_str} {lev_hi_str} "
          f"{entry['round_weighted_leverage']:>+7.1f} "
          f"{entry['confidence_tier']:<6} {entry['confidence_type']:<4} "
          f"{entry['high_signal_flag']:>5} {entry['sign_flip_flag']:>4}")

# ============================================================
# SUMMARY TABLE 2: ALL SIGN-FLIP TEAMS
# ============================================================
print("\n\n" + "=" * 130)
print("TABLE 2: SIGN-FLIP TEAMS (Type C — leverage changes sign across E8 scenarios)")
print("=" * 130)

sign_flips = [r for r in leverage_rows if r['sign_flip_flag'] == 'Y']

if sign_flips:
    print(f"\n{'Team':<18} {'Sd':>2} {'Region':<8} {'Round':<5} {'Vegas':>7} {'Public':>7} "
          f"{'Lev_Primary':>12} {'Lev_Alt':>10} {'Lev_Lo':>7} {'Lev_Hi':>7} {'Tier':<6} {'Type':<4}")
    print("-" * 120)
    for entry in sign_flips:
        # Compute alt leverage for display
        r4_alt = float(prob_data[entry['team_name']]['r4_adjusted_alt'])
        lev_alt = r4_alt - entry['public_pick_pct']
        print(f"{entry['team_name']:<18} {entry['team_seed']:>2} {entry['region']:<8} "
              f"{entry['round']:<5} {entry['vegas_prob']:>6.1%} {entry['public_pick_pct']:>6.1%} "
              f"{entry['leverage']:>+11.1%} {lev_alt:>+9.1%} "
              f"{entry['leverage_low']:>+6.1%} {entry['leverage_high']:>+6.1%} "
              f"{entry['confidence_tier']:<6} {entry['confidence_type']:<4}")
    print(f"\n  WARNING: These {len(sign_flips)} teams have contrarian signals that depend entirely")
    print(f"  on bracket path. Do NOT act on these without a view on which opponent they face.")
else:
    print("\n  No sign-flip teams detected.")

# ============================================================
# ADDITIONAL ANALYSIS: HIGH-SIGNAL DIVERGENCES
# ============================================================
print("\n\n" + "=" * 130)
print("HIGH-SIGNAL DIVERGENCES (|leverage| > 10 percentage points)")
print("=" * 130)

high_signal = [r for r in leverage_rows if r['high_signal_flag'] == 'Y']
high_signal.sort(key=lambda x: -abs(x['leverage']))

print(f"\n{'Team':<18} {'Sd':>2} {'Region':<8} {'Round':<5} {'Vegas':>7} {'Public':>7} "
      f"{'Leverage':>9} {'Ratio':>6} {'Type':<4} {'Direction':<15}")
print("-" * 100)

for entry in high_signal:
    direction = "UNDER-PICKED" if entry['leverage'] > 0 else "OVER-PICKED"
    print(f"{entry['team_name']:<18} {entry['team_seed']:>2} {entry['region']:<8} "
          f"{entry['round']:<5} {entry['vegas_prob']:>6.1%} {entry['public_pick_pct']:>6.1%} "
          f"{entry['leverage']:>+8.1%} {entry['leverage_ratio']:>5.2f}x "
          f"{entry['confidence_type']:<4} {direction:<15}")

print(f"\n  Total high-signal entries: {len(high_signal)}")

# ============================================================
# SAVE leverage_matrix_2026.csv
# ============================================================
output_fields = [
    'team_name', 'team_seed', 'region', 'round',
    'vegas_prob', 'public_pick_pct', 'leverage', 'leverage_ratio',
    'leverage_low', 'leverage_high', 'round_weighted_leverage',
    'confidence_tier', 'confidence_type', 'high_signal_flag', 'sign_flip_flag',
]

with open('leverage_matrix_2026.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=output_fields)
    writer.writeheader()
    for entry in leverage_rows:
        row = {
            'team_name': entry['team_name'],
            'team_seed': entry['team_seed'],
            'region': entry['region'],
            'round': entry['round'],
            'vegas_prob': f"{entry['vegas_prob']:.6f}",
            'public_pick_pct': f"{entry['public_pick_pct']:.4f}",
            'leverage': f"{entry['leverage']:+.6f}",
            'leverage_ratio': f"{entry['leverage_ratio']:.4f}",
            'leverage_low': f"{entry['leverage_low']:+.6f}",
            'leverage_high': f"{entry['leverage_high']:+.6f}",
            'round_weighted_leverage': f"{entry['round_weighted_leverage']:+.4f}",
            'confidence_tier': entry['confidence_tier'],
            'confidence_type': entry['confidence_type'],
            'high_signal_flag': entry['high_signal_flag'],
            'sign_flip_flag': entry['sign_flip_flag'],
        }
        writer.writerow(row)

print(f"\nWrote leverage_matrix_2026.csv ({len(leverage_rows)} rows)")

# ============================================================
# SUMMARY STATISTICS
# ============================================================
print("\n" + "=" * 90)
print("SUMMARY STATISTICS")
print("=" * 90)

from collections import Counter
type_counts = Counter(r['confidence_type'] for r in leverage_rows)
tier_counts = Counter(r['confidence_tier'] for r in leverage_rows)
hs_counts = Counter(r['high_signal_flag'] for r in leverage_rows)
round_counts = Counter(r['round'] for r in leverage_rows)

print(f"\n  By confidence type: {dict(type_counts)}")
print(f"  By confidence tier: {dict(tier_counts)}")
print(f"  High-signal entries: {hs_counts.get('Y', 0)} / {len(leverage_rows)}")
print(f"  Sign-flip entries:   {len(sign_flips)}")
print(f"  By round: {dict(sorted(round_counts.items()))}")

# Mean leverage by round
print(f"\n  Mean absolute leverage by round:")
for rd in ['R64', 'R32', 'S16', 'E8', 'F4', 'NCG']:
    rd_rows = [r for r in leverage_rows if r['round'] == rd]
    if rd_rows:
        mean_abs_lev = sum(abs(r['leverage']) for r in rd_rows) / len(rd_rows)
        mean_lev = sum(r['leverage'] for r in rd_rows) / len(rd_rows)
        print(f"    {rd:<5}: mean_abs={mean_abs_lev:.3f}  mean_signed={mean_lev:+.3f}  n={len(rd_rows)}")
