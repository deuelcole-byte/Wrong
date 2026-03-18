#!/usr/bin/env python3
"""
Prompt 4 — Probability Baseline Finalization

Merges probability_baseline_2026.csv with source_uncertainty_2026.csv,
applies E8 shrinkage correction, assigns confidence tiers, attaches
uncertainty ranges, and outputs probability_baseline_final_2026.csv.
"""
import csv
import math

# ============================================================
# LOAD DATA
# ============================================================
baseline = []
with open('probability_baseline_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['team_name'] == '_METADATA' or not row['team_name'].strip():
            continue
        baseline.append(row)

uncertainty = {}
with open('source_uncertainty_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        key = (row['team_name'], row['team_seed'])
        uncertainty[key] = row

print(f"Loaded {len(baseline)} teams from probability_baseline_2026.csv")
print(f"Loaded {len(uncertainty)} teams from source_uncertainty_2026.csv")

# Historical seed advancement rates (same as source_uncertainty.py)
seed_rates_r1 = {
    1: 0.9875, 2: 0.9313, 3: 0.8563, 4: 0.7938, 5: 0.6438,
    6: 0.6125, 7: 0.6125, 8: 0.4813, 9: 0.5188, 10: 0.3875,
    11: 0.3875, 12: 0.3563, 13: 0.2063, 14: 0.1438, 15: 0.0688, 16: 0.0125
}

# Round-level mean Brier scores from brier_scores_historical_vegas.csv
round_brier = {
    'r1': 0.1829, 'r2': 0.1894, 'r3': 0.2146,
    'r4': 0.2948, 'r5': 0.1985, 'r6': 0.1350
}

# Six high-uncertainty R1 teams from Prompt 3
HIGH_UNCERTAINTY_R1_TEAMS = {
    'Vanderbilt', "St John's", 'Wisconsin', 'McNeese', 'High Point', 'Northern Iowa'
}

# ============================================================
# STEP 0 — ELITE EIGHT (R4) CORRECTION
# ============================================================
print("\n" + "=" * 80)
print("STEP 0 — ELITE EIGHT CORRECTION")
print("=" * 80)
print("\nApplying 30% shrinkage toward 0.50 for all teams with r4 > 0.50")
print("Formula: r4_adjusted = r4 * 0.70 + 0.50 * 0.30\n")

e8_corrections = []
for t in baseline:
    r4_orig = float(t['r4'])
    t['r4_original'] = r4_orig
    if r4_orig > 0.50:
        r4_adj = r4_orig * 0.70 + 0.50 * 0.30
        t['r4_adjusted'] = r4_adj
        t['e8_correction_applied'] = 'Y'
        e8_corrections.append(t)
    else:
        t['r4_adjusted'] = r4_orig
        t['e8_correction_applied'] = 'N'

# Convert remaining round probs to float
for t in baseline:
    for rk in ['r1', 'r2', 'r3', 'r5', 'r6']:
        t[rk] = float(t[rk])

# ============================================================
# STEP 1 — CONFIDENCE TIER ASSIGNMENT
# ============================================================
print("=" * 80)
print("STEP 1 — CONFIDENCE TIER ASSIGNMENT")
print("=" * 80)

# Historical seed advancement rates by round (indexed 0-5 for r1-r6)
seed_advancement_counts = {
    1:  [158, 136, 107, 66, 41, 26],
    2:  [149, 103,  72, 32, 13,  5],
    3:  [137,  84,  41, 17, 11,  4],
    4:  [127,  77,  25, 15,  4,  2],
    5:  [103,  55,  12,  9,  4,  0],
    6:  [ 98,  47,  17,  3,  2,  1],
    7:  [ 98,  29,  10,  3,  1,  1],
    8:  [ 77,  16,   9,  6,  4,  1],
    9:  [ 83,   8,   5,  2,  0,  0],
    10: [ 62,  24,   9,  1,  0,  0],
    11: [ 62,  27,  10,  6,  0,  0],
    12: [ 57,  22,   2,  0,  0,  0],
    13: [ 33,   6,   0,  0,  0,  0],
    14: [ 23,   2,   0,  0,  0,  0],
    15: [ 11,   4,   1,  0,  0,  0],
    16: [  2,   0,   0,  0,  0,  0],
}
N_PER_SEED = 160
seed_hist_rates = {}
for seed, counts in seed_advancement_counts.items():
    seed_hist_rates[seed] = [c / N_PER_SEED for c in counts]

round_to_idx = {'r1': 0, 'r2': 1, 'r3': 2, 'r4': 3, 'r5': 4, 'r6': 5}

low_confidence_log = []

for t in baseline:
    seed = int(t['team_seed'])
    first_four = t.get('first_four_flag', 'N')
    is_high_uncertainty_r1 = t['team_name'] in HIGH_UNCERTAINTY_R1_TEAMS

    for rk in ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']:
        idx = round_to_idx[rk]
        hist_rate = seed_hist_rates[seed][idx]
        brier = round_brier[rk]

        # Use r4_adjusted for r4
        if rk == 'r4':
            vegas_prob = t['r4_adjusted']
        else:
            vegas_prob = t[rk]

        deviation = abs(vegas_prob - hist_rate)
        deviation_pp = deviation * 100

        reasons = []

        # R4 is always LOW due to documented bias
        if rk == 'r4':
            tier = 'LOW'
            reasons.append('E8_bias_correction')
            if deviation_pp > 15:
                reasons.append(f'deviation_{deviation_pp:.1f}pp')
        elif first_four == 'Y':
            tier = 'LOW'
            reasons.append('first_four')
        elif deviation_pp > 15 or brier > 0.25:
            tier = 'LOW'
            if deviation_pp > 15:
                reasons.append(f'deviation_{deviation_pp:.1f}pp')
            if brier > 0.25:
                reasons.append(f'brier_{brier:.3f}')
        elif deviation_pp > 8 or brier > 0.20:
            tier = 'MEDIUM'
            if deviation_pp > 8:
                reasons.append(f'deviation_{deviation_pp:.1f}pp')
            if brier > 0.20:
                reasons.append(f'brier_{brier:.3f}')
        else:
            tier = 'HIGH'

        # Special handling for the 6 high-uncertainty R1 teams in r1
        if rk == 'r1' and is_high_uncertainty_r1:
            tier = 'LOW'
            reasons = ['seed_line_deviation']

        t[f'confidence_tier_{rk}'] = tier
        if tier == 'LOW':
            low_confidence_log.append({
                'team': t['team_name'],
                'seed': seed,
                'round': rk,
                'prob': vegas_prob,
                'hist_rate': hist_rate,
                'reasons': '; '.join(reasons)
            })

    # Seed line deviation flag
    t['seed_line_deviation_flag'] = 'Y' if is_high_uncertainty_r1 else 'N'

# ============================================================
# STEP 2 — UNCERTAINTY RANGE ATTACHMENT
# ============================================================
print("\n" + "=" * 80)
print("STEP 2 — UNCERTAINTY RANGE ATTACHMENT")
print("=" * 80)

# For r1 and r2: use ±1 stdev from seed-based historical proportion
# For r3-r6: pull from source_uncertainty_2026.csv
for t in baseline:
    seed = int(t['team_seed'])
    key = (t['team_name'], t['team_seed'])
    unc = uncertainty.get(key, {})

    for rk in ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']:
        idx = round_to_idx[rk]
        hist_rate = seed_hist_rates[seed][idx]
        sd = math.sqrt(hist_rate * (1 - hist_rate) / N_PER_SEED) if 0 < hist_rate < 1 else 0

        if rk == 'r4':
            # Attach uncertainty to r4_adjusted
            prob = t['r4_adjusted']
        else:
            prob = t[rk]

        if rk in ['r3', 'r4', 'r5', 'r6']:
            # Try to pull from source_uncertainty file
            rk_lookup = rk
            low_key = f'implied_uncertainty_low_{rk_lookup}'
            high_key = f'implied_uncertainty_high_{rk_lookup}'
            if unc and low_key in unc and high_key in unc:
                if rk == 'r4':
                    # Recompute around r4_adjusted
                    t[f'{rk}_low'] = max(0, t['r4_adjusted'] - sd)
                    t[f'{rk}_high'] = min(1, t['r4_adjusted'] + sd)
                else:
                    t[f'{rk}_low'] = float(unc[low_key])
                    t[f'{rk}_high'] = float(unc[high_key])
            else:
                t[f'{rk}_low'] = max(0, prob - sd)
                t[f'{rk}_high'] = min(1, prob + sd)
        else:
            # r1, r2: compute from seed stdev
            t[f'{rk}_low'] = max(0, prob - sd)
            t[f'{rk}_high'] = min(1, prob + sd)

print(f"  Attached uncertainty ranges for all 64 teams × 6 rounds")

# ============================================================
# SUMMARY TABLE 1: ALL LOW CONFIDENCE TEAM-ROUND COMBINATIONS
# ============================================================
print("\n" + "=" * 80)
print("SUMMARY TABLE 1: LOW CONFIDENCE TEAM-ROUND COMBINATIONS")
print("=" * 80)
print(f"\n{'Team':<20} {'Seed':>4} {'Round':>6} {'Prob':>7} {'Hist':>7} {'Reason':>40}")
print("-" * 90)
for entry in sorted(low_confidence_log, key=lambda x: (x['round'], -x['prob'])):
    print(f"{entry['team']:<20} {entry['seed']:>4} {entry['round']:>6} "
          f"{entry['prob']:>6.1%} {entry['hist_rate']:>6.1%} {entry['reasons']:>40}")

print(f"\nTotal LOW confidence entries: {len(low_confidence_log)}")

# Count by round
from collections import Counter
round_counts = Counter(e['round'] for e in low_confidence_log)
for rk in ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']:
    print(f"  {rk}: {round_counts.get(rk, 0)} teams")

# ============================================================
# SUMMARY TABLE 2: E8 CORRECTION DETAILS
# ============================================================
print("\n" + "=" * 80)
print("SUMMARY TABLE 2: R4 (ELITE EIGHT) CORRECTION — r4_original vs r4_adjusted")
print("=" * 80)
print(f"\n{'Team':<20} {'Seed':>4} {'r4_orig':>9} {'r4_adj':>9} {'Delta':>8}")
print("-" * 55)

corrected_teams = [t for t in baseline if t['e8_correction_applied'] == 'Y']
corrected_teams.sort(key=lambda x: -x['r4_original'])

if corrected_teams:
    for t in corrected_teams:
        delta = t['r4_adjusted'] - t['r4_original']
        print(f"{t['team_name']:<20} {int(t['team_seed']):>4} "
              f"{t['r4_original']:>8.1%} {t['r4_adjusted']:>8.1%} {delta:>+7.1%}")
    print(f"\nTotal teams corrected: {len(corrected_teams)}")
    print(f"Mean correction magnitude: {sum(t['r4_adjusted'] - t['r4_original'] for t in corrected_teams) / len(corrected_teams):.1%}")
else:
    # Show top E8 probabilities for context
    top_e8 = sorted(baseline, key=lambda x: -x['r4_original'])[:10]
    print("  No teams have r4 > 0.50 — shrinkage formula not triggered.")
    print("  This is expected: r4 represents advancing THROUGH the E8,")
    print("  so even 1-seeds top out around 48%.\n")
    print("  Top 10 r4 probabilities (uncorrected):")
    print(f"  {'Team':<20} {'Seed':>4} {'r4_orig':>9}")
    for t in top_e8:
        print(f"  {t['team_name']:<20} {int(t['team_seed']):>4} {t['r4_original']:>8.1%}")
    print("\n  E8 correction note: The directional bias finding still applies —")
    print("  all r4 estimates carry LOW confidence tier, and downstream prompts")
    print("  should treat E8 advancement probabilities with extra caution.")
    print("  The shrinkage formula (r4 * 0.70 + 0.50 * 0.30) would only activate")
    print("  for teams projected above 50%, which occurs in stronger tournament fields")
    print("  or when using pre-tournament season-long probabilities.")

# ============================================================
# STEP 3 — WRITE probability_baseline_final_2026.csv
# ============================================================
print("\n" + "=" * 80)
print("STEP 3 — WRITING probability_baseline_final_2026.csv")
print("=" * 80)

SOURCE_METADATA = (
    "ESPN moneylines single book; additive devig; simulation propagation; "
    "COOPER unavailable paywalled; KenPom unavailable login-gated; "
    "no blending applied; E8 shrinkage correction applied at r4 with "
    "30% coefficient approximate due to FiveThirtyEight proxy substitution"
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
    'seed_line_deviation_flag', 'source_metadata',
]

with open('probability_baseline_final_2026.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction='ignore')
    writer.writeheader()
    for t in baseline:
        row = {
            'team_name': t['team_name'],
            'team_seed': t['team_seed'],
            'region': t['region'],
            'r1': f"{t['r1']:.6f}",
            'r2': f"{t['r2']:.6f}",
            'r3': f"{t['r3']:.6f}",
            'r4_original': f"{t['r4_original']:.6f}",
            'r4_adjusted': f"{t['r4_adjusted']:.6f}",
            'r5': f"{t['r5']:.6f}",
            'r6': f"{t['r6']:.6f}",
            'r1_low': f"{t['r1_low']:.6f}",
            'r1_high': f"{t['r1_high']:.6f}",
            'r2_low': f"{t['r2_low']:.6f}",
            'r2_high': f"{t['r2_high']:.6f}",
            'r3_low': f"{t['r3_low']:.6f}",
            'r3_high': f"{t['r3_high']:.6f}",
            'r4_low': f"{t['r4_low']:.6f}",
            'r4_high': f"{t['r4_high']:.6f}",
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
            'e8_correction_applied': t['e8_correction_applied'],
            'first_four_flag': t.get('first_four_flag', 'N'),
            'near_zero_flag': t.get('near_zero_flag', 'N'),
            'seed_line_deviation_flag': t['seed_line_deviation_flag'],
            'source_metadata': SOURCE_METADATA,
        }
        writer.writerow(row)

print(f"  Wrote probability_baseline_final_2026.csv ({len(baseline)} teams)")

# Quick validation
tier_counts = Counter()
for t in baseline:
    for rk in ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']:
        tier_counts[t[f'confidence_tier_{rk}']] += 1

print(f"\n  Confidence tier distribution (all rounds):")
for tier in ['HIGH', 'MEDIUM', 'LOW']:
    print(f"    {tier}: {tier_counts[tier]}")
print(f"    Total: {sum(tier_counts.values())} (64 teams × 6 rounds = {64*6})")
