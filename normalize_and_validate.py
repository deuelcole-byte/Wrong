#!/usr/bin/env python3
"""
Fix structural inconsistency in vegas_raw_2026.csv:
Futures-derived probabilities carry sportsbook overround, causing regional
sums to exceed structural targets. Normalize within each region+round to
enforce single-elimination constraints, then re-validate.

Normalization approach: For each region and round, scale all team probabilities
proportionally so they sum to the structurally required total. This preserves
the relative ordering and ratios from Vegas while enforcing bracket math.
After normalization, re-enforce monotonicity (r1 >= r2 >= ... >= r6).
"""
import csv

# Load data
teams = []
with open('vegas_raw_2026.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if not row['team_name'].strip():
            continue
        for col in ['vegas_prob_game', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6']:
            row[col] = float(row[col])
        row['team_seed'] = int(row['team_seed'])
        teams.append(row)

print(f"Loaded {len(teams)} teams\n")

regions = ['East', 'South', 'West', 'Midwest']
round_cols = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']

# Expected sums per round per region
expected_sums = {
    'r1': 8.0,   # 8 winners from 8 R64 games
    'r2': 4.0,   # 4 winners from 4 R32 games
    'r3': 2.0,   # 2 winners from 2 S16 games
    'r4': 1.0,   # 1 regional champion
    'r5': 0.5,   # 50% chance region produces finalist
    'r6': 0.25,  # 25% chance region produces champion
}

# ============================================================
# STEP 1: Normalize r2-r6 within each region
# r1 already sums to 8.0 (devigged game-level probs are correct)
# ============================================================
print("NORMALIZATION — Scaling futures-derived probabilities to bracket structure")
print("=" * 70)

for region in regions:
    region_teams = [t for t in teams if t['region'] == region]
    for rc in round_cols:
        actual_sum = sum(t[rc] for t in region_teams)
        target = expected_sums[rc]
        if actual_sum == 0:
            continue
        scale = target / actual_sum
        for t in region_teams:
            t[rc] = t[rc] * scale
        new_sum = sum(t[rc] for t in region_teams)
        print(f"  {region} {rc}: {actual_sum:.4f} → {new_sum:.4f} "
              f"(scale={scale:.4f})")

# ============================================================
# STEP 2: Re-enforce monotonicity after normalization
# Normalization can break monotonicity if different rounds had
# different scale factors
# ============================================================
print("\n" + "=" * 70)
print("POST-NORMALIZATION MONOTONICITY FIX")
print("=" * 70)

mono_fixes = 0
for t in teams:
    rounds_keys = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']
    for i in range(1, len(rounds_keys)):
        if t[rounds_keys[i]] > t[rounds_keys[i-1]]:
            old = t[rounds_keys[i]]
            t[rounds_keys[i]] = t[rounds_keys[i-1]]
            mono_fixes += 1

print(f"  Applied {mono_fixes} monotonicity caps")

# After monotonicity fixes, re-normalize to maintain sums
# (monotonicity caps can slightly reduce sums)
print("\n  Re-normalizing after monotonicity fixes...")
for region in regions:
    region_teams = [t for t in teams if t['region'] == region]
    for rc in round_cols:
        actual_sum = sum(t[rc] for t in region_teams)
        target = expected_sums[rc]
        if actual_sum == 0:
            continue
        scale = target / actual_sum
        for t in region_teams:
            t[rc] = round(t[rc] * scale, 6)

# ============================================================
# VALIDATION CHECKS (post-normalization)
# ============================================================
print("\n" + "=" * 70)
print("POST-NORMALIZATION VALIDATION")
print("=" * 70)

# Check 1 — Consistency
print("\nCheck 1 — Internal Consistency (monotonicity)")
consistency_failures = []
for t in teams:
    rounds = [t['r1'], t['r2'], t['r3'], t['r4'], t['r5'], t['r6']]
    fail = False
    for i in range(1, len(rounds)):
        if rounds[i] > rounds[i-1] + 0.0001:
            consistency_failures.append(
                f"  {t['team_name']}: r{i}={rounds[i-1]:.6f} < r{i+1}={rounds[i]:.6f}"
            )
            fail = True
    t['consistency_flag'] = 'fail' if fail else 'pass'

if consistency_failures:
    print(f"  FAIL — {len(consistency_failures)} violations:")
    for cf in consistency_failures:
        print(cf)
else:
    print("  PASS — All teams satisfy r1 >= r2 >= r3 >= r4 >= r5 >= r6")

# Check 2 — Regional sums
print("\nCheck 2 — Regional Sum Constraints")
deviations = []
halt = False
for region in regions:
    region_teams = [t for t in teams if t['region'] == region]
    for rc in round_cols:
        actual = sum(t[rc] for t in region_teams)
        expected = expected_sums[rc]
        dev = abs(actual - expected)
        if dev > 0.01:
            deviations.append((region, rc, actual, expected, dev))
        if dev > 0.05:
            halt = True
        # Set validation flags
        flag = 'fail' if dev > 0.01 else 'pass'
        for t in region_teams:
            t[f'validation_{rc}_flag'] = flag

if deviations:
    print(f"  FAIL — {len(deviations)} deviations > 0.01")
    for region, rc, actual, expected, dev in deviations:
        print(f"    {region} {rc}: sum={actual:.6f} expected={expected:.4f} dev={dev:.6f}")
else:
    print("  PASS — All regional sums within 0.01 tolerance")

# Print actual sums for verification
print("\n  Regional sum verification:")
for region in regions:
    region_teams = [t for t in teams if t['region'] == region]
    sums = [sum(t[rc] for t in region_teams) for rc in round_cols]
    print(f"    {region:>10}: " + " | ".join(f"{rc}={s:.4f}" for rc, s in zip(round_cols, sums)))
print(f"    {'Expected':>10}: " + " | ".join(f"{rc}={expected_sums[rc]:.4f}" for rc in round_cols))

# Check 3 — First Four
print("\nCheck 3 — First Four Handling")
first_four_teams = []
for t in teams:
    t['first_four_flag'] = 'N'
    if t['team_name'] in ('M-OH/SMU', 'PV/LEH'):
        t['first_four_flag'] = 'Y'
        first_four_teams.append(t)
        print(f"  FLAGGED: {t['team_name']} (seed {t['team_seed']}, {t['region']})")
        print(f"    r1={t['r1']:.4f}, r2={t['r2']:.4f}, r3={t['r3']:.4f}, "
              f"r4={t['r4']:.4f}, r5={t['r5']:.4f}, r6={t['r6']:.4f}")

print(f"  {len(first_four_teams)} First Four entries flagged for manual review")
print("  M-OH/SMU: Combined entry using SMU moneyline as proxy")
print("  PV/LEH: Combined entry using estimated composite moneyline")

# Check 4 — Floor check
print("\nCheck 4 — Floor Check (r6 < 0.0005)")
near_zero = []
for t in teams:
    if t['r6'] < 0.0005:
        t['near_zero_flag'] = 'Y'
        near_zero.append(t)
    else:
        t['near_zero_flag'] = 'N'

if near_zero:
    print(f"  {len(near_zero)} teams with r6 < 0.0005:")
    for t in sorted(near_zero, key=lambda x: x['r6']):
        print(f"    {t['team_name']:<20} seed {t['team_seed']:>2}  r6={t['r6']:.6f}")
else:
    print("  No teams below floor threshold")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("VALIDATION SUMMARY (POST-NORMALIZATION)")
print("=" * 70)
print(f"  Check 1 (consistency):   {'FAIL' if consistency_failures else 'PASS'}"
      f" — {len(consistency_failures)} violations")
print(f"  Check 2 (regional sums): {'FAIL' if deviations else 'PASS'}"
      f" — {len(deviations)} deviations > 0.01")
print(f"  Check 3 (First Four):    {len(first_four_teams)} entries flagged")
print(f"  Check 4 (floor):         {len(near_zero)} teams at effective zero")

if halt:
    print("\n  *** HALT: Regional sum deviations still exceed 0.05 ***")
else:
    print("\n  All checks pass or are within acceptable tolerance.")
    print("  Downstream analysis may proceed with documented caveats.")

# ============================================================
# WRITE OUTPUT
# ============================================================
output_fields = [
    'team_name', 'team_seed', 'region', 'vegas_prob_game',
    'r1', 'r2', 'r3', 'r4', 'r5', 'r6',
    'validation_r1_flag', 'validation_r2_flag', 'validation_r3_flag',
    'validation_r4_flag', 'validation_r5_flag', 'validation_r6_flag',
    'consistency_flag', 'first_four_flag', 'near_zero_flag'
]

# Sort by r6 descending
teams.sort(key=lambda x: -x['r6'])

with open('probability_baseline_2026.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction='ignore')
    writer.writeheader()
    for t in teams:
        # Round probabilities for cleaner output
        for col in ['vegas_prob_game', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6']:
            t[col] = round(t[col], 6)
        writer.writerow(t)
    # Metadata row
    meta = {field: '' for field in output_fields}
    meta['team_name'] = '_METADATA'
    meta['r1'] = 'source=ESPN_moneylines_single_book_DraftKings'
    meta['r2'] = 'devig=additive_method'
    meta['r3'] = 'propagation=futures_implied_then_normalized'
    meta['r4'] = 'COOPER=unavailable_paywalled'
    meta['r5'] = 'KenPom=unavailable_login_gated'
    meta['r6'] = 'blend=single_source_no_weighting'
    meta['validation_r1_flag'] = f'check2_deviations={len(deviations)}'
    meta['validation_r2_flag'] = f'consistency_violations={len(consistency_failures)}'
    meta['validation_r3_flag'] = f'first_four_entries={len(first_four_teams)}'
    meta['validation_r4_flag'] = f'near_zero_teams={len(near_zero)}'
    meta['validation_r5_flag'] = f'total_teams={len(teams)}'
    meta['validation_r6_flag'] = 'halt=NO' if not halt else 'halt=YES'
    meta['consistency_flag'] = 'SINGLE_SOURCE_BASELINE'
    meta['first_four_flag'] = 'REVIEW_REQUIRED'
    meta['near_zero_flag'] = 'SEE_SOURCE_AVAILABILITY_LOG'
    writer.writerow(meta)

print(f"\nWrote probability_baseline_2026.csv ({len(teams)} teams + 1 metadata row)")

# Print top 15 for review
print("\nTop 15 teams by championship probability (normalized):")
print(f"{'Team':<20} {'Sd':>2} {'Region':<8} {'R1':>7} {'R32':>7} {'S16':>7} "
      f"{'E8':>7} {'F4':>7} {'Champ':>7}")
for t in teams[:15]:
    print(f"{t['team_name']:<20} {t['team_seed']:>2} {t['region']:<8} "
          f"{t['r1']:>6.1%} {t['r2']:>6.1%} {t['r3']:>6.1%} "
          f"{t['r4']:>6.1%} {t['r5']:>6.1%} {t['r6']:>6.1%}")
