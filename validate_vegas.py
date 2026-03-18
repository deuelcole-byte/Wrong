#!/usr/bin/env python3
"""
Validate vegas_raw_2026.csv and produce probability_baseline_2026.csv
with validation flags and metadata.
"""
import csv
import sys

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

# ============================================================
# CHECK 1 — Internal consistency: r1 >= r2 >= r3 >= r4 >= r5 >= r6
# ============================================================
print("=" * 70)
print("CHECK 1 — Internal Consistency (monotonicity)")
print("=" * 70)
consistency_failures = []
for t in teams:
    rounds = [t['r1'], t['r2'], t['r3'], t['r4'], t['r5'], t['r6']]
    for i in range(1, len(rounds)):
        if rounds[i] > rounds[i - 1] + 0.0001:  # small tolerance for float
            consistency_failures.append(
                f"  {t['team_name']}: r{i} ({rounds[i-1]:.4f}) < r{i+1} ({rounds[i]:.4f})"
            )
    t['consistency_flag'] = 'pass'

if consistency_failures:
    print(f"FAILED — {len(consistency_failures)} violations:")
    for cf in consistency_failures:
        print(cf)
    for t in teams:
        rounds = [t['r1'], t['r2'], t['r3'], t['r4'], t['r5'], t['r6']]
        for i in range(1, len(rounds)):
            if rounds[i] > rounds[i - 1] + 0.0001:
                t['consistency_flag'] = 'fail'
else:
    print("PASSED — All teams satisfy r1 >= r2 >= r3 >= r4 >= r5 >= r6")

# ============================================================
# CHECK 2 — Regional sum constraints
# ============================================================
print("\n" + "=" * 70)
print("CHECK 2 — Regional Sum Constraints")
print("=" * 70)

# Expected sums per round per region:
# r1: 8 games per region, 8 winners → but wait:
# Actually: 16 teams per region in R64. 8 games. 8 winners advance.
# So sum of r1 probs = 8.0 (each game sums to 1.0, 8 games)
# r2: 4 games in R32 → 4 winners → sum = 4.0
# r3: 2 games in S16 → 2 winners → sum = 2.0
# r4: 1 game in E8 → 1 winner → sum = 1.0
# r5: regional winner goes to F4, but F4 involves cross-region → sum = 0.5? No.
# Actually r4 = reach Final Four = win the region = 1 team per region → sum = 1.0
#
# Wait, let me re-read the column definitions from build_vegas_probs.py:
# r1 = P(win first round) = P(advance past R64)
# r2 = P(reach Sweet 16) = P(advance past R32)
# r3 = P(reach Elite 8) = P(advance past S16)
# r4 = P(reach Final Four) = P(advance past E8 = win region)
# r5 = P(reach Finals) = P(advance past F4)
# r6 = P(win championship)
#
# Per region (16 teams):
# r1 sum: 8 winners from 8 games → expected sum = 8.0
# r2 sum: 4 winners from 4 R32 games → expected sum = 4.0
# r3 sum: 2 winners from 2 S16 games → expected sum = 2.0
# r4 sum: 1 winner from 1 E8 game → expected sum = 1.0
# r5 sum: This is cross-region (F4). Each region sends 1 team.
#         2 F4 games → 2 finalists from 4 regions → each region expected = 0.5
# r6 sum: 1 champion from 4 regions → each region expected = 0.25

# The prompt says:
# r1 sum = 4.0, r2 = 2.0, r3 = 1.0, r4 = 0.5, r5 = 0.25, r6 = 0.125
# This seems to use a different convention. Let me check...
# The prompt says "r1 sum per region should equal 4.0 (4 teams advance from 16)"
# This implies r1 = P(reach R32), and the prompt counts 4 teams advancing?
# No — from 16 teams, 8 advance in R64. Unless the prompt is wrong?
# Actually re-reading: "r1 sum per region should equal 4.0 (4 teams advance from 16)"
# This doesn't match. 8 teams advance from R64 per region, not 4.
#
# BUT: The actual data has r1 values summing to... let me compute:

regions = ['East', 'South', 'West', 'Midwest']
round_cols = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']

# Expected sums based on tournament structure:
# 16 teams per region, single elimination
# r1 (win R64): 8 games → 8 winners → sum = 8.0
# r2 (win R32 / reach S16): 4 games → 4 winners → sum = 4.0
# r3 (win S16 / reach E8): 2 games → 2 winners → sum = 2.0
# r4 (win E8 / reach F4): 1 game → 1 winner → sum = 1.0
# r5 (reach Finals): cross-region, 1 of 2 semifinal → sum = 0.5
# r6 (win title): 1 of 4 regions → sum = 0.25
expected_sums = {
    'r1': 8.0,
    'r2': 4.0,
    'r3': 2.0,
    'r4': 1.0,
    'r5': 0.5,
    'r6': 0.25
}

# Initialize validation flags
for t in teams:
    for rc in round_cols:
        t[f'validation_{rc}_flag'] = 'pass'

halt = False
deviations = []
for region in regions:
    region_teams = [t for t in teams if t['region'] == region]
    print(f"\n  {region} Region ({len(region_teams)} teams):")
    for rc in round_cols:
        actual = sum(t[rc] for t in region_teams)
        expected = expected_sums[rc]
        dev = abs(actual - expected)
        status = "PASS" if dev <= 0.01 else "FAIL"
        if dev > 0.01:
            deviations.append((region, rc, actual, expected, dev))
            for t in region_teams:
                t[f'validation_{rc}_flag'] = 'fail'
        if dev > 0.05:
            halt = True
        print(f"    {rc}: sum = {actual:.4f}, expected = {expected:.4f}, "
              f"dev = {dev:.4f} [{status}]")

if deviations:
    print(f"\n  SUMMARY: {len(deviations)} round-region combinations exceed 0.01 threshold")
    if halt:
        print("\n  *** HALT CONDITION: Deviations > 0.05 detected! ***")
        print("  This indicates a structural error in the simulation.")
        print("  Details of critical deviations:")
        for region, rc, actual, expected, dev in deviations:
            if dev > 0.05:
                print(f"    {region} {rc}: sum={actual:.4f} expected={expected:.4f} dev={dev:.4f}")
else:
    print("\n  PASSED — All regional sums within tolerance")

# ============================================================
# CHECK 3 — First Four handling
# ============================================================
print("\n" + "=" * 70)
print("CHECK 3 — First Four Handling")
print("=" * 70)

first_four_teams = []
for t in teams:
    t['first_four_flag'] = 'N'
    name = t['team_name']
    if name in ('M-OH/SMU', 'PV/LEH'):
        t['first_four_flag'] = 'Y'
        first_four_teams.append(t)
        print(f"\n  FLAGGED: {name} (seed {t['team_seed']}, {t['region']})")
        print(f"    r1={t['r1']:.4f}, r2={t['r2']:.4f}, r3={t['r3']:.4f}, "
              f"r4={t['r4']:.4f}, r5={t['r5']:.4f}, r6={t['r6']:.4f}")

if first_four_teams:
    print(f"\n  {len(first_four_teams)} First Four entries found.")
    print("  HANDLING: These entries represent combined play-in matchups.")
    print("  M-OH/SMU: Miami (OH) vs SMU — moneyline used SMU line (-310/+250)")
    print("    as proxy. The r1 probability (0.2742) reflects SMU's probability")
    print("    of winning the play-in AND the R64 game, which may understate")
    print("    the actual probability since it conflates two games.")
    print("  PV/LEH: Prairie View A&M vs Lehigh — moneyline estimated as")
    print("    composite (-5000/+2000). Same conflation issue applies.")
    print("  RECOMMENDATION: Flag for manual review. Consider splitting into")
    print("    separate team entries once First Four results are known.")
else:
    print("  No First Four entries found.")

# ============================================================
# CHECK 4 — Floor check (r6 < 0.0005)
# ============================================================
print("\n" + "=" * 70)
print("CHECK 4 — Floor Check (r6 < 0.0005)")
print("=" * 70)

near_zero = []
for t in teams:
    if t['r6'] < 0.0005:
        t['near_zero_flag'] = 'Y'
        near_zero.append(t)
    else:
        t['near_zero_flag'] = 'N'

if near_zero:
    print(f"  {len(near_zero)} teams with r6 < 0.0005 (effectively zero title probability):")
    for t in near_zero:
        print(f"    {t['team_name']:<20} seed {t['team_seed']:>2}  r6={t['r6']:.4f}")
    print("  These teams should NOT appear as contrarian champion picks.")
else:
    print("  No teams below floor threshold.")

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("VALIDATION SUMMARY")
print("=" * 70)
print(f"  Check 1 (consistency):   {'FAIL' if consistency_failures else 'PASS'}"
      f" — {len(consistency_failures)} violations")
print(f"  Check 2 (regional sums): {'FAIL' if deviations else 'PASS'}"
      f" — {len(deviations)} deviations > 0.01")
print(f"  Check 3 (First Four):    {len(first_four_teams)} entries flagged")
print(f"  Check 4 (floor):         {len(near_zero)} teams at effective zero")

if halt:
    print("\n  *** HALTING: Regional sum deviations exceed 0.05. ***")
    print("  *** Structural correction required before proceeding. ***")
    print("  *** probability_baseline_2026.csv will still be written ***")
    print("  *** but downstream analysis should NOT proceed until ***")
    print("  *** deviations are investigated and resolved. ***")

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

with open('probability_baseline_2026.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction='ignore')
    writer.writeheader()
    for t in teams:
        writer.writerow(t)
    # Metadata row
    meta = {field: '' for field in output_fields}
    meta['team_name'] = '_METADATA'
    meta['team_seed'] = ''
    meta['region'] = ''
    meta['vegas_prob_game'] = ''
    meta['r1'] = 'source=ESPN_moneylines_single_book'
    meta['r2'] = 'devig=additive'
    meta['r3'] = 'propagation=futures_implied'
    meta['r4'] = 'COOPER=unavailable_paywalled'
    meta['r5'] = 'KenPom=unavailable_login_gated'
    meta['r6'] = 'blend=single_source_no_weighting'
    meta['validation_r1_flag'] = f'check2_deviations={len(deviations)}'
    meta['validation_r2_flag'] = f'consistency_violations={len(consistency_failures)}'
    meta['validation_r3_flag'] = f'first_four_entries={len(first_four_teams)}'
    meta['validation_r4_flag'] = f'near_zero_teams={len(near_zero)}'
    meta['validation_r5_flag'] = f'total_teams={len(teams)}'
    meta['validation_r6_flag'] = 'halt=YES' if halt else 'halt=NO'
    meta['consistency_flag'] = 'SINGLE_SOURCE_BASELINE'
    meta['first_four_flag'] = 'REVIEW_REQUIRED'
    meta['near_zero_flag'] = 'SEE_DOCUMENTATION'
    writer.writerow(meta)

print(f"\nWrote probability_baseline_2026.csv ({len(teams)} teams + 1 metadata row)")
