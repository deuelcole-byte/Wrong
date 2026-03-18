#!/usr/bin/env python3
"""
Prompt 4b — E8 Game-Level Probability Correction

Corrects the methodology gap from Prompt 4: applies shrinkage at the
game-level win probability rather than the round advancement probability.

Uses bracket structure to identify probable E8 matchups per region,
back-calculates implicit game-level win probs, applies 30% shrinkage
toward 0.50 for favorites, then propagates back into r4_adjusted.
"""
import csv
import math
from collections import defaultdict

# ============================================================
# BRACKET STRUCTURE
# In each region, the E8 game is between the top-half winner
# and the bottom-half winner.
# ============================================================
# Standard NCAA bracket halves within a region:
TOP_HALF_SEEDS = {1, 16, 8, 9, 5, 12, 4, 13}
BOTTOM_HALF_SEEDS = {2, 15, 7, 10, 6, 11, 3, 14}

# ============================================================
# LOAD DATA
# ============================================================
teams = []
with open('probability_baseline_final_2026.csv') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        # Convert numeric fields
        for col in ['r1', 'r2', 'r3', 'r4_original', 'r4_adjusted', 'r5', 'r6',
                     'r1_low', 'r1_high', 'r2_low', 'r2_high',
                     'r3_low', 'r3_high', 'r4_low', 'r4_high',
                     'r5_low', 'r5_high', 'r6_low', 'r6_high']:
            row[col] = float(row[col])
        row['team_seed'] = int(row['team_seed'])
        teams.append(row)

print(f"Loaded {len(teams)} teams from probability_baseline_final_2026.csv\n")

# Group by region
regions = defaultdict(list)
for t in teams:
    regions[t['region']].append(t)

# ============================================================
# STEP 1 — RECONSTRUCT E8 GAME-LEVEL WIN PROBABILITIES
# ============================================================
print("=" * 90)
print("STEP 1 — RECONSTRUCT E8 GAME-LEVEL WIN PROBABILITIES")
print("=" * 90)

e8_matchups = {}  # region -> {'primary': (teamA, teamB), 'alt': (teamA, teamB)}

for region_name, region_teams in sorted(regions.items()):
    # Split into bracket halves
    top_half = [t for t in region_teams if t['team_seed'] in TOP_HALF_SEEDS]
    bottom_half = [t for t in region_teams if t['team_seed'] in BOTTOM_HALF_SEEDS]

    # Sort by r3 (probability of reaching E8) descending
    top_half.sort(key=lambda x: -x['r3'])
    bottom_half.sort(key=lambda x: -x['r3'])

    print(f"\n  Region: {region_name}")
    print(f"    Top half (reach E8):")
    for i, t in enumerate(top_half[:3]):
        marker = " <-- primary" if i == 0 else (" <-- alt" if i == 1 else "")
        print(f"      {t['team_name']:<18} seed={t['team_seed']:>2}  r3={t['r3']:.4f}{marker}")
    print(f"    Bottom half (reach E8):")
    for i, t in enumerate(bottom_half[:3]):
        marker = " <-- primary" if i == 0 else (" <-- alt" if i == 1 else "")
        print(f"      {t['team_name']:<18} seed={t['team_seed']:>2}  r3={t['r3']:.4f}{marker}")

    # Primary matchup: top r3 from each half
    primary_top = top_half[0]
    primary_bot = bottom_half[0]

    # Alt matchup: swap in 2nd best from each half
    alt_top = top_half[1] if len(top_half) > 1 else top_half[0]
    alt_bot = bottom_half[1] if len(bottom_half) > 1 else bottom_half[0]

    e8_matchups[region_name] = {
        'primary_top': primary_top,
        'primary_bot': primary_bot,
        'alt_top': alt_top,
        'alt_bot': alt_bot,
        'all_top': top_half,
        'all_bot': bottom_half,
    }

# ============================================================
# STEP 2 — APPLY SHRINKAGE CORRECTION AT GAME LEVEL
# ============================================================
print("\n\n" + "=" * 90)
print("STEP 2 — APPLY SHRINKAGE AT GAME LEVEL")
print("=" * 90)
print("\nFormula: For favorite (p_game > 0.50):")
print("  e8_game_prob_corrected = e8_game_prob_implied * 0.70 + 0.50 * 0.30")
print("  Underdog corrected = 1 - favorite_corrected\n")


def compute_game_prob_and_correct(team_a, team_b):
    """
    Back out game-level win probability from r4_original values,
    apply shrinkage, return corrected game probs for both teams.
    """
    r4_a = team_a['r4_original']
    r4_b = team_b['r4_original']
    total = r4_a + r4_b

    if total < 1e-10:
        # Both teams have near-zero E8 advancement — no meaningful correction
        return 0.5, 0.5, 0.5, 0.5

    # Implied game-level win probability
    p_game_a = r4_a / total
    p_game_b = r4_b / total

    # Apply shrinkage to the favorite
    if p_game_a >= p_game_b:
        # A is favorite
        p_corrected_a = p_game_a * 0.70 + 0.50 * 0.30
        p_corrected_b = 1.0 - p_corrected_a
    else:
        # B is favorite
        p_corrected_b = p_game_b * 0.70 + 0.50 * 0.30
        p_corrected_a = 1.0 - p_corrected_b

    return p_game_a, p_game_b, p_corrected_a, p_corrected_b


# ============================================================
# STEP 3 — PROPAGATE CORRECTION BACK INTO R4
# r4_adjusted_A = r3_A * e8_game_prob_corrected_A
# ============================================================
print("=" * 90)
print("STEP 3 — PROPAGATE INTO R4_ADJUSTED")
print("=" * 90)

# Initialize new columns for all teams
for t in teams:
    t['e8_game_prob_implied'] = ''
    t['e8_game_prob_corrected'] = ''
    t['r4_adjusted_new'] = t['r4_original']  # default: unchanged
    t['r4_adjusted_alt'] = t['r4_original']  # default: unchanged
    t['path_dependent_flag'] = 'N'
    t['e8_opponent_primary'] = ''
    t['e8_opponent_alt'] = ''

e8_table = []  # For summary printing

for region_name, matchup in sorted(e8_matchups.items()):
    print(f"\n  Region: {region_name}")

    # --- PRIMARY MATCHUP ---
    top_team = matchup['primary_top']
    bot_team = matchup['primary_bot']

    p_impl_top, p_impl_bot, p_corr_top, p_corr_bot = compute_game_prob_and_correct(
        top_team, bot_team
    )

    # Apply to all teams in the region using their most likely opponent
    # For each top-half team: opponent is primary_bot
    # For each bottom-half team: opponent is primary_top
    for t in matchup['all_top']:
        p_impl_t, _, p_corr_t, _ = compute_game_prob_and_correct(t, bot_team)
        t['e8_game_prob_implied'] = p_impl_t
        t['e8_game_prob_corrected'] = p_corr_t
        t['r4_adjusted_new'] = t['r3'] * p_corr_t
        t['e8_opponent_primary'] = bot_team['team_name']

    for t in matchup['all_bot']:
        _, p_impl_t, _, p_corr_t = compute_game_prob_and_correct(top_team, t)
        # Note: compute returns (top_impl, bot_impl, top_corr, bot_corr)
        # We want bot's perspective
        p_impl_t_actual, _, _, _ = compute_game_prob_and_correct(t, top_team)
        t['e8_game_prob_implied'] = p_impl_t_actual
        t['e8_game_prob_corrected'] = 1.0 - (p_impl_t_actual * 0.70 + 0.50 * 0.30) if p_impl_t_actual > 0.5 else (
            1.0 - ((1.0 - p_impl_t_actual) * 0.70 + 0.50 * 0.30)
        )
        # Simpler: just recompute correctly
        r4_t = t['r4_original']
        r4_opp = top_team['r4_original']
        total = r4_t + r4_opp
        if total < 1e-10:
            p_game = 0.5
            p_game_corr = 0.5
        else:
            p_game = r4_t / total
            p_game_opp = r4_opp / total
            if p_game >= 0.5:
                p_game_corr = p_game * 0.70 + 0.50 * 0.30
            else:
                p_game_opp_corr = p_game_opp * 0.70 + 0.50 * 0.30
                p_game_corr = 1.0 - p_game_opp_corr
        t['e8_game_prob_implied'] = p_game
        t['e8_game_prob_corrected'] = p_game_corr
        t['r4_adjusted_new'] = t['r3'] * p_game_corr
        t['e8_opponent_primary'] = top_team['team_name']

    # Print primary matchup
    print(f"    Primary E8: {top_team['team_name']} (seed {top_team['team_seed']}) "
          f"vs {bot_team['team_name']} (seed {bot_team['team_seed']})")
    print(f"      Implied game: {p_impl_top:.3f} vs {p_impl_bot:.3f}")
    print(f"      Corrected:    {p_corr_top:.3f} vs {p_corr_bot:.3f}")

    # Collect for summary table
    if p_impl_top >= p_impl_bot:
        e8_table.append({
            'region': region_name,
            'favorite': top_team['team_name'],
            'fav_seed': top_team['team_seed'],
            'underdog': bot_team['team_name'],
            'und_seed': bot_team['team_seed'],
            'implied': p_impl_top,
            'corrected': p_corr_top,
            'r4_orig_fav': top_team['r4_original'],
            'r4_adj_fav': top_team['r4_adjusted_new'],
            'r4_orig_und': bot_team['r4_original'],
            'r4_adj_und': bot_team['r4_adjusted_new'],
        })
    else:
        e8_table.append({
            'region': region_name,
            'favorite': bot_team['team_name'],
            'fav_seed': bot_team['team_seed'],
            'underdog': top_team['team_name'],
            'und_seed': top_team['team_seed'],
            'implied': p_impl_bot,
            'corrected': p_corr_bot,
            'r4_orig_fav': bot_team['r4_original'],
            'r4_adj_fav': bot_team['r4_adjusted_new'],
            'r4_orig_und': top_team['r4_original'],
            'r4_adj_und': top_team['r4_adjusted_new'],
        })

    # --- STEP 4: ALT MATCHUP ---
    # Alt scenario: swap in 2nd-most-likely from each half
    # Scenario A: alt_top vs primary_bot
    # Scenario B: primary_top vs alt_bot
    # Use the one that changes r4 the most for the primary teams
    alt_top = matchup['alt_top']
    alt_bot = matchup['alt_bot']

    # For top-half teams: alt opponent is alt_bot
    for t in matchup['all_top']:
        r4_t = t['r4_original']
        r4_opp = alt_bot['r4_original']
        total = r4_t + r4_opp
        if total < 1e-10:
            p_game_corr = 0.5
        else:
            p_game = r4_t / total
            p_game_opp = r4_opp / total
            if p_game >= 0.5:
                p_game_corr = p_game * 0.70 + 0.50 * 0.30
            else:
                p_game_opp_corr = p_game_opp * 0.70 + 0.50 * 0.30
                p_game_corr = 1.0 - p_game_opp_corr
        t['r4_adjusted_alt'] = t['r3'] * p_game_corr
        t['e8_opponent_alt'] = alt_bot['team_name']

    # For bottom-half teams: alt opponent is alt_top
    for t in matchup['all_bot']:
        r4_t = t['r4_original']
        r4_opp = alt_top['r4_original']
        total = r4_t + r4_opp
        if total < 1e-10:
            p_game_corr = 0.5
        else:
            p_game = r4_t / total
            p_game_opp = r4_opp / total
            if p_game >= 0.5:
                p_game_corr = p_game * 0.70 + 0.50 * 0.30
            else:
                p_game_opp_corr = p_game_opp * 0.70 + 0.50 * 0.30
                p_game_corr = 1.0 - p_game_opp_corr
        t['r4_adjusted_alt'] = t['r3'] * p_game_corr
        t['e8_opponent_alt'] = alt_top['team_name']

    print(f"    Alt E8:     {alt_top['team_name']} (seed {alt_top['team_seed']}) "
          f"vs {alt_bot['team_name']} (seed {alt_bot['team_seed']})")

# ============================================================
# STEP 4 — PATH DEPENDENCY FLAGS
# ============================================================
print("\n\n" + "=" * 90)
print("STEP 4 — PATH DEPENDENCY FLAGS")
print("=" * 90)

path_dependent_count = 0
for t in teams:
    diff = abs(t['r4_adjusted_new'] - t['r4_adjusted_alt'])
    if diff > 0.05:  # 5 percentage points
        t['path_dependent_flag'] = 'Y'
        path_dependent_count += 1
        print(f"  PATH-DEPENDENT: {t['team_name']:<18} seed={t['team_seed']:>2}  "
              f"r4_adj={t['r4_adjusted_new']:.4f}  r4_alt={t['r4_adjusted_alt']:.4f}  "
              f"delta={diff:.4f}  opp_primary={t['e8_opponent_primary']}  "
              f"opp_alt={t['e8_opponent_alt']}")

if path_dependent_count == 0:
    print("  No teams flagged — all r4_adjusted vs r4_adjusted_alt differences < 5pp")
    print("  (This is expected when top-2 teams in each half are close in strength)")

print(f"\n  Total path-dependent flags: {path_dependent_count}")

# ============================================================
# SUMMARY TABLE — E8 CORRECTION DETAILS
# ============================================================
print("\n\n" + "=" * 90)
print("SUMMARY TABLE: E8 GAME-LEVEL CORRECTION BY REGION")
print("=" * 90)
print(f"\n{'Region':<10} {'Favorite':<18} {'Sd':>2} {'Underdog':<18} {'Sd':>2} "
      f"{'Impl':>7} {'Corr':>7} {'Fav r4_o':>8} {'Fav r4_a':>8} {'Delta':>7} "
      f"{'Und r4_o':>8} {'Und r4_a':>8} {'Delta':>7}")
print("-" * 130)

for entry in e8_table:
    fav_delta = entry['r4_adj_fav'] - entry['r4_orig_fav']
    und_delta = entry['r4_adj_und'] - entry['r4_orig_und']
    fav_material = " ***" if abs(fav_delta) > 0.03 else ""
    und_material = " ***" if abs(und_delta) > 0.03 else ""
    print(f"{entry['region']:<10} {entry['favorite']:<18} {entry['fav_seed']:>2} "
          f"{entry['underdog']:<18} {entry['und_seed']:>2} "
          f"{entry['implied']:>6.1%} {entry['corrected']:>6.1%} "
          f"{entry['r4_orig_fav']:>7.1%} {entry['r4_adj_fav']:>7.1%} {fav_delta:>+6.1%}{fav_material} "
          f"{entry['r4_orig_und']:>7.1%} {entry['r4_adj_und']:>7.1%} {und_delta:>+6.1%}{und_material}")

print("\n  *** = Material correction (|delta| > 3 percentage points)")

# Full team detail table for favorites
print("\n\n" + "=" * 90)
print("DETAILED TABLE: ALL TEAMS WITH E8 GAME PROBABILITIES")
print("=" * 90)
print(f"\n{'Team':<18} {'Sd':>2} {'Region':<8} {'r3':>7} {'e8_impl':>8} {'e8_corr':>8} "
      f"{'r4_orig':>8} {'r4_adj':>8} {'delta':>7} {'r4_alt':>8} {'path':>5}")
print("-" * 110)

# Sort by r4_original descending
for t in sorted(teams, key=lambda x: -x['r4_original']):
    if t['r4_original'] < 0.005:
        continue  # Skip very low probability teams for readability
    delta = t['r4_adjusted_new'] - t['r4_original']
    highlight = " ***" if abs(delta) > 0.03 else ""
    impl = t['e8_game_prob_implied']
    corr = t['e8_game_prob_corrected']
    impl_str = f"{impl:>7.1%}" if isinstance(impl, float) else f"{'N/A':>7}"
    corr_str = f"{corr:>7.1%}" if isinstance(corr, float) else f"{'N/A':>7}"
    print(f"{t['team_name']:<18} {t['team_seed']:>2} {t['region']:<8} "
          f"{t['r3']:>6.1%} {impl_str} {corr_str} "
          f"{t['r4_original']:>7.1%} {t['r4_adjusted_new']:>7.1%} {delta:>+6.1%}{highlight} "
          f"{t['r4_adjusted_alt']:>7.1%} {t['path_dependent_flag']:>5}")

# ============================================================
# STEP 5 — UPDATE probability_baseline_final_2026.csv
# ============================================================
print("\n\n" + "=" * 90)
print("STEP 5 — WRITING UPDATED probability_baseline_final_2026.csv")
print("=" * 90)

METADATA_APPEND = (
    "; E8 correction reapplied at game level via r4 back-calculation "
    "after methodology gap identified — original formula incorrectly "
    "targeted advancement probability rather than game-level win probability"
)

output_fields = [
    'team_name', 'team_seed', 'region',
    'r1', 'r2', 'r3', 'r4_original', 'r4_adjusted', 'r5', 'r6',
    'r1_low', 'r1_high', 'r2_low', 'r2_high',
    'r3_low', 'r3_high', 'r4_low', 'r4_high',
    'r5_low', 'r5_high', 'r6_low', 'r6_high',
    'confidence_tier_r1', 'confidence_tier_r2', 'confidence_tier_r3',
    'confidence_tier_r4', 'confidence_tier_r5', 'confidence_tier_r6',
    'e8_correction_applied', 'first_four_flag', 'near_zero_flag',
    'seed_line_deviation_flag',
    'e8_game_prob_implied', 'e8_game_prob_corrected',
    'r4_adjusted_alt', 'path_dependent_flag',
    'source_metadata',
]

# Recompute r4 uncertainty ranges around the new r4_adjusted
import math
seed_advancement_counts = {
    1:  [158, 136, 107, 66, 41, 26], 2:  [149, 103,  72, 32, 13,  5],
    3:  [137,  84,  41, 17, 11,  4], 4:  [127,  77,  25, 15,  4,  2],
    5:  [103,  55,  12,  9,  4,  0], 6:  [ 98,  47,  17,  3,  2,  1],
    7:  [ 98,  29,  10,  3,  1,  1], 8:  [ 77,  16,   9,  6,  4,  1],
    9:  [ 83,   8,   5,  2,  0,  0], 10: [ 62,  24,   9,  1,  0,  0],
    11: [ 62,  27,  10,  6,  0,  0], 12: [ 57,  22,   2,  0,  0,  0],
    13: [ 33,   6,   0,  0,  0,  0], 14: [ 23,   2,   0,  0,  0,  0],
    15: [ 11,   4,   1,  0,  0,  0], 16: [  2,   0,   0,  0,  0,  0],
}
N_PER_SEED = 160

with open('probability_baseline_final_2026.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction='ignore')
    writer.writeheader()
    for t in teams:
        seed = t['team_seed']
        hist_r4 = seed_advancement_counts[seed][3] / N_PER_SEED
        sd_r4 = math.sqrt(hist_r4 * (1 - hist_r4) / N_PER_SEED) if 0 < hist_r4 < 1 else 0

        # Determine if correction was actually applied (game prob != 0.5 exactly)
        impl = t['e8_game_prob_implied']
        was_corrected = isinstance(impl, float) and abs(impl - 0.5) > 0.001

        # Update source_metadata
        old_meta = t['source_metadata']
        new_meta = old_meta + METADATA_APPEND if METADATA_APPEND not in old_meta else old_meta

        row = {
            'team_name': t['team_name'],
            'team_seed': t['team_seed'],
            'region': t['region'],
            'r1': f"{t['r1']:.6f}",
            'r2': f"{t['r2']:.6f}",
            'r3': f"{t['r3']:.6f}",
            'r4_original': f"{t['r4_original']:.6f}",
            'r4_adjusted': f"{t['r4_adjusted_new']:.6f}",
            'r5': f"{t['r5']:.6f}",
            'r6': f"{t['r6']:.6f}",
            'r1_low': f"{t['r1_low']:.6f}",
            'r1_high': f"{t['r1_high']:.6f}",
            'r2_low': f"{t['r2_low']:.6f}",
            'r2_high': f"{t['r2_high']:.6f}",
            'r3_low': f"{t['r3_low']:.6f}",
            'r3_high': f"{t['r3_high']:.6f}",
            'r4_low': f"{max(0, t['r4_adjusted_new'] - sd_r4):.6f}",
            'r4_high': f"{min(1, t['r4_adjusted_new'] + sd_r4):.6f}",
            'r5_low': f"{t['r5_low']:.6f}",
            'r5_high': f"{t['r5_high']:.6f}",
            'r6_low': f"{t['r6_low']:.6f}",
            'r6_high': f"{t['r6_high']:.6f}",
            'confidence_tier_r1': t['confidence_tier_r1'],
            'confidence_tier_r2': t['confidence_tier_r2'],
            'confidence_tier_r3': t['confidence_tier_r3'],
            'confidence_tier_r4': t['confidence_tier_r4'],
            'confidence_tier_r5': t['confidence_tier_r5'],
            'confidence_tier_r6': t['confidence_tier_r6'],
            'e8_correction_applied': 'Y' if was_corrected else 'N',
            'first_four_flag': t['first_four_flag'],
            'near_zero_flag': t['near_zero_flag'],
            'seed_line_deviation_flag': t['seed_line_deviation_flag'],
            'e8_game_prob_implied': f"{impl:.6f}" if isinstance(impl, float) else '',
            'e8_game_prob_corrected': f"{t['e8_game_prob_corrected']:.6f}" if isinstance(t['e8_game_prob_corrected'], float) else '',
            'r4_adjusted_alt': f"{t['r4_adjusted_alt']:.6f}",
            'path_dependent_flag': t['path_dependent_flag'],
            'source_metadata': new_meta,
        }
        writer.writerow(row)

print(f"  Wrote probability_baseline_final_2026.csv ({len(teams)} teams)")
print(f"  New columns: e8_game_prob_implied, e8_game_prob_corrected, r4_adjusted_alt, path_dependent_flag")
print(f"  source_metadata updated with game-level correction note")

# ============================================================
# VALIDATION: Check r4_adjusted sums are reasonable
# ============================================================
print("\n\n" + "=" * 90)
print("VALIDATION")
print("=" * 90)

for region_name, region_teams in sorted(regions.items()):
    r4_orig_sum = sum(t['r4_original'] for t in region_teams)
    r4_adj_sum = sum(t['r4_adjusted_new'] for t in region_teams)
    # In each region, exactly 1 team advances through E8, so sum of r4
    # across all teams in a region should be ~1.0 (if r4 = P(reach F4))
    # Wait — r4 = P(reach F4 from start), so it's not constrained to sum to 1
    # across a region because it includes the probability of getting TO the E8.
    # But we can check: sum should be <= 1
    print(f"  {region_name}: Σ(r4_orig)={r4_orig_sum:.4f}  Σ(r4_adj)={r4_adj_sum:.4f}  "
          f"delta={r4_adj_sum - r4_orig_sum:+.4f}")

# Total across all regions: should be ~4.0 (4 F4 spots)
total_orig = sum(t['r4_original'] for t in teams)
total_adj = sum(t['r4_adjusted_new'] for t in teams)
print(f"\n  Total: Σ(r4_orig)={total_orig:.4f}  Σ(r4_adj)={total_adj:.4f}  "
      f"(expected ~4.0 for 4 F4 spots)")
print(f"  Net correction magnitude: {total_adj - total_orig:+.4f}")
