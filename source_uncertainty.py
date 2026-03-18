#!/usr/bin/env python3
"""
Source Limitation Documentation and Sensitivity Framing.

Step 1: Historical calibration check using FiveThirtyEight data (2011-2014)
        as proxy for Vegas closing line calibration.
Step 2: Inter-source disagreement proxy using seed-based historical base rates
        vs current Vegas-implied probabilities.
Step 3: Output source_uncertainty_2026.csv and brier_scores_historical_vegas.csv
"""
import csv
import math
from collections import defaultdict

# ============================================================
# HISTORICAL SEED-BASED ADVANCEMENT RATES (1985-2025, 40 tournaments)
# Source: bracketodds.cs.illinois.edu/seedadv.html
# 160 teams per seed (4 per tournament × 40 tournaments)
# ============================================================
# Format: seed -> [R64_wins, R32_wins(S16), S16_wins(E8), E8_wins(F4), F4_wins(CG), CG_wins(Champ)]
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

N_TOURNAMENTS = 40  # 1985-2025 (no tournament in 2020 but data says 160 per seed)
N_PER_SEED = 160  # 4 teams per seed × 40 tournaments

# Compute rates and standard deviations
# Rate = count / N_PER_SEED
# StDev of a proportion: sqrt(p * (1-p) / n)
seed_rates = {}  # seed -> [r1_rate, r2_rate, ..., r6_rate]
seed_stdevs = {}  # seed -> [r1_sd, r2_sd, ..., r6_sd]
for seed, counts in seed_advancement_counts.items():
    rates = []
    stdevs = []
    for count in counts:
        p = count / N_PER_SEED
        sd = math.sqrt(p * (1 - p) / N_PER_SEED) if p > 0 and p < 1 else 0
        rates.append(p)
        stdevs.append(sd)
    seed_rates[seed] = rates
    seed_stdevs[seed] = stdevs

print("=" * 80)
print("HISTORICAL SEED ADVANCEMENT RATES (1985-2025, n=160 per seed)")
print("=" * 80)
print(f"{'Seed':>4}  {'R1 Win%':>8}  {'S16':>8}  {'E8':>8}  {'F4':>8}  {'CG':>8}  {'Champ':>8}")
for seed in range(1, 17):
    r = seed_rates[seed]
    print(f"{seed:>4}  {r[0]:>7.1%}  {r[1]:>7.1%}  {r[2]:>7.1%}  {r[3]:>7.1%}  {r[4]:>7.1%}  {r[5]:>7.1%}")

# ============================================================
# STEP 1: HISTORICAL BRIER SCORE COMPUTATION
# Using FiveThirtyEight model data as proxy for Vegas closing lines.
# 538 probabilities correlate highly with closing lines (r>0.95).
# ============================================================
print("\n" + "=" * 80)
print("STEP 1 — HISTORICAL BRIER SCORE (538 Model as Vegas Proxy, 2011-2014)")
print("=" * 80)
print("\nNOTE: Historical Vegas closing moneylines for individual NCAA tournament games")
print("are not available in bulk from any free public source. Using FiveThirtyEight's")
print("model probabilities (2011-2014) as a proxy. 538 probabilities are derived from")
print("a blend of power ratings that correlates highly (r > 0.95) with closing lines.")
print("This is an explicit SUBSTITUTION — not raw Vegas data.\n")

# FiveThirtyEight round encoding:
# 1 = First Four, 2 = Round of 64, 3 = Round of 32, 4 = Sweet 16,
# 5 = Elite Eight, 6 = Final Four, 7 = Championship
# Map to our r1-r6: 2->r1, 3->r2, 4->r3, 5->r4, 6->r5, 7->r6
round_map = {2: 'r1', 3: 'r2', 4: 'r3', 5: 'r4', 6: 'r5', 7: 'r6'}
round_names = {'r1': 'R64', 'r2': 'R32', 'r3': 'S16', 'r4': 'E8', 'r5': 'F4', 'r6': 'NCG'}

# Load 538 data
games_538 = []
with open('538_historical.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        games_538.append({
            'year': int(row['year']),
            'round': int(row['round']),
            'fav_prob': float(row['favorite_probability']),
            'fav_win': int(row['favorite_win_flag'])
        })

# Compute Brier scores by year and round
# Brier Score = (1/N) * Σ (forecast_prob - outcome)²
# For each game: the forecast gives P(favorite wins).
# Brier for the game = (p_fav - result)² where result = 1 if fav wins, 0 if not.
# This is for the favorite's perspective. Since p_underdog = 1 - p_fav,
# Brier is the same from either perspective.

brier_by_year_round = defaultdict(lambda: defaultdict(list))
for g in games_538:
    rkey = round_map.get(g['round'])
    if rkey is None:
        continue  # skip First Four
    brier_score = (g['fav_prob'] - g['fav_win']) ** 2
    brier_by_year_round[g['year']][rkey].append(brier_score)

years = sorted(brier_by_year_round.keys())
round_keys = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']

print(f"{'Year':>6}", end="")
for rk in round_keys:
    print(f"  {round_names[rk]:>8}", end="")
print(f"  {'Overall':>8}")

year_brier = {}
for year in years:
    year_brier[year] = {}
    all_scores = []
    print(f"{year:>6}", end="")
    for rk in round_keys:
        scores = brier_by_year_round[year].get(rk, [])
        if scores:
            bs = sum(scores) / len(scores)
            year_brier[year][rk] = bs
            all_scores.extend(scores)
            print(f"  {bs:>8.4f}", end="")
        else:
            year_brier[year][rk] = None
            print(f"  {'N/A':>8}", end="")
    if all_scores:
        overall = sum(all_scores) / len(all_scores)
        year_brier[year]['overall'] = overall
        print(f"  {overall:>8.4f}")
    else:
        print()

# Compute mean and stdev across years
print(f"\n{'Mean':>6}", end="")
round_means = {}
round_stdevs_brier = {}
for rk in round_keys:
    vals = [year_brier[y][rk] for y in years if year_brier[y].get(rk) is not None]
    if vals:
        mean = sum(vals) / len(vals)
        if len(vals) > 1:
            var = sum((v - mean)**2 for v in vals) / (len(vals) - 1)
            sd = math.sqrt(var)
        else:
            sd = 0
        round_means[rk] = mean
        round_stdevs_brier[rk] = sd
        print(f"  {mean:>8.4f}", end="")
    else:
        round_means[rk] = None
        print(f"  {'N/A':>8}", end="")

all_overalls = [year_brier[y]['overall'] for y in years if 'overall' in year_brier[y]]
if all_overalls:
    print(f"  {sum(all_overalls)/len(all_overalls):>8.4f}")

print(f"{'StDev':>6}", end="")
for rk in round_keys:
    sd = round_stdevs_brier.get(rk)
    if sd is not None:
        print(f"  {sd:>8.4f}", end="")
    else:
        print(f"  {'N/A':>8}", end="")
print()

# Directional bias check
print("\n--- Directional Bias Analysis ---")
print("Checking if favorites systematically over- or under-perform forecasts by round:\n")

for rk in round_keys:
    fav_probs = []
    fav_wins = []
    for g in games_538:
        mapped = round_map.get(g['round'])
        if mapped == rk:
            fav_probs.append(g['fav_prob'])
            fav_wins.append(g['fav_win'])
    if fav_probs:
        avg_prob = sum(fav_probs) / len(fav_probs)
        avg_win = sum(fav_wins) / len(fav_wins)
        bias = avg_win - avg_prob  # positive = favorites win MORE than forecasted
        n = len(fav_probs)
        se = math.sqrt(avg_win * (1 - avg_win) / n)
        z = bias / se if se > 0 else 0
        sig = "*" if abs(z) > 1.96 else ""
        direction = "favorites underrated" if bias > 0 else "favorites overrated"
        print(f"  {round_names[rk]:>4}: avg_forecast={avg_prob:.3f}  actual_win_rate={avg_win:.3f}  "
              f"bias={bias:+.3f} ({direction})  n={n}  z={z:+.2f} {sig}")

# ============================================================
# STEP 2: INTER-SOURCE DISAGREEMENT PROXY
# Compare Vegas r1 probabilities to historical seed win rates
# ============================================================
print("\n" + "=" * 80)
print("STEP 2 — INTER-SOURCE DISAGREEMENT PROXY")
print("=" * 80)

# Load probability baseline
baseline = []
with open('probability_baseline_2026.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['team_name'] == '_METADATA' or not row['team_name'].strip():
            continue
        for col in ['vegas_prob_game', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6']:
            row[col] = float(row[col])
        row['team_seed'] = int(row['team_seed'])
        baseline.append(row)

print(f"\nLoaded {len(baseline)} teams from probability_baseline_2026.csv\n")

# Compare R1 probabilities to historical seed win rates
print("R1: Vegas-implied probability vs historical seed win rate")
print(f"{'Team':<20} {'Seed':>4} {'Vegas R1':>9} {'Hist Rate':>10} {'Deviation':>10} {'Flag':>6}")
print("-" * 65)

high_uncertainty_r1 = []
for t in baseline:
    seed = t['team_seed']
    hist_rate = seed_rates[seed][0]
    vegas_r1 = t['r1']
    deviation = vegas_r1 - hist_rate
    flag = 'HIGH' if abs(deviation) > 0.12 else ''
    if flag:
        high_uncertainty_r1.append(t['team_name'])
    t['historical_seed_winrate_r1'] = hist_rate
    t['r1_deviation_from_historical'] = deviation
    t['high_uncertainty_flag_r1'] = 'Y' if flag else 'N'
    print(f"{t['team_name']:<20} {seed:>4} {vegas_r1:>8.1%} {hist_rate:>9.1%} "
          f"{deviation:>+9.1%} {flag:>6}")

print(f"\n  High-uncertainty R1 games (deviation > 12pp): {len(high_uncertainty_r1)}")
for name in high_uncertainty_r1:
    print(f"    - {name}")

# Compute later-round historical rates and stdevs per seed
# r2(S16) = index 1, r3(E8) = index 2, r4(F4) = index 3, r5(CG) = index 4, r6(Champ) = index 5
round_indices = {'r2': 1, 'r3': 2, 'r4': 3, 'r5': 4, 'r6': 5}

for t in baseline:
    seed = t['team_seed']
    for rk, idx in round_indices.items():
        t[f'historical_advancement_rate_{rk}'] = seed_rates[seed][idx]
        t[f'historical_stdev_{rk}'] = seed_stdevs[seed][idx]
        vegas_prob = t[rk]
        sd = seed_stdevs[seed][idx]
        t[f'implied_uncertainty_low_{rk}'] = max(0, vegas_prob - sd)
        t[f'implied_uncertainty_high_{rk}'] = min(1, vegas_prob + sd)

# ============================================================
# STEP 3: OUTPUT FILES
# ============================================================
print("\n" + "=" * 80)
print("STEP 3 — WRITING OUTPUT FILES")
print("=" * 80)

# --- brier_scores_historical_vegas.csv ---
brier_fields = ['year'] + [f'{rk}_brier' for rk in round_keys] + ['overall_brier']
with open('brier_scores_historical_vegas.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    # Header comment
    writer.writerow(['# Brier Scores by round using FiveThirtyEight model probabilities (2011-2014) as Vegas proxy'])
    writer.writerow(['# SUBSTITUTION: Not raw Vegas closing moneylines. 538 model probabilities used.'])
    writer.writerow(['# Round encoding: r1=R64, r2=R32, r3=S16, r4=E8, r5=F4, r6=NCG'])
    writer.writerow(brier_fields)
    for year in years:
        row = [year]
        for rk in round_keys:
            val = year_brier[year].get(rk)
            row.append(f"{val:.4f}" if val is not None else 'N/A')
        row.append(f"{year_brier[year].get('overall', 0):.4f}")
        writer.writerow(row)
    # Mean row
    mean_row = ['MEAN']
    for rk in round_keys:
        m = round_means.get(rk)
        mean_row.append(f"{m:.4f}" if m is not None else 'N/A')
    mean_row.append(f"{sum(all_overalls)/len(all_overalls):.4f}" if all_overalls else 'N/A')
    writer.writerow(mean_row)
    # StDev row
    sd_row = ['STDEV']
    for rk in round_keys:
        s = round_stdevs_brier.get(rk)
        sd_row.append(f"{s:.4f}" if s is not None else 'N/A')
    sd_row.append('N/A')
    writer.writerow(sd_row)

print(f"  Wrote brier_scores_historical_vegas.csv ({len(years)} years + summary)")

# --- source_uncertainty_2026.csv ---
uncertainty_fields = [
    'team_name', 'team_seed', 'region',
    'historical_seed_winrate_r1', 'vegas_r1_prob', 'r1_deviation_from_historical',
    'high_uncertainty_flag_r1',
]
# Add r3-r6 fields (later rounds where uncertainty matters most)
for rk in ['r3', 'r4', 'r5', 'r6']:
    uncertainty_fields.extend([
        f'historical_advancement_rate_{rk}',
        f'historical_stdev_{rk}',
        f'vegas_prob_{rk}',
        f'implied_uncertainty_low_{rk}',
        f'implied_uncertainty_high_{rk}',
    ])

with open('source_uncertainty_2026.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=uncertainty_fields, extrasaction='ignore')
    # Header comments as a preamble row
    writer.writeheader()
    for t in baseline:
        row = {
            'team_name': t['team_name'],
            'team_seed': t['team_seed'],
            'region': t['region'],
            'historical_seed_winrate_r1': f"{t['historical_seed_winrate_r1']:.4f}",
            'vegas_r1_prob': f"{t['r1']:.4f}",
            'r1_deviation_from_historical': f"{t['r1_deviation_from_historical']:+.4f}",
            'high_uncertainty_flag_r1': t['high_uncertainty_flag_r1'],
        }
        for rk in ['r3', 'r4', 'r5', 'r6']:
            row[f'historical_advancement_rate_{rk}'] = f"{t[f'historical_advancement_rate_{rk}']:.4f}"
            row[f'historical_stdev_{rk}'] = f"{t[f'historical_stdev_{rk}']:.4f}"
            row[f'vegas_prob_{rk}'] = f"{t[rk]:.4f}"
            row[f'implied_uncertainty_low_{rk}'] = f"{t[f'implied_uncertainty_low_{rk}']:.4f}"
            row[f'implied_uncertainty_high_{rk}'] = f"{t[f'implied_uncertainty_high_{rk}']:.4f}"
        writer.writerow(row)

print(f"  Wrote source_uncertainty_2026.csv ({len(baseline)} teams)")

# ============================================================
# FINAL SUMMARY
# ============================================================
print("\n" + "=" * 80)
print("FINAL SUMMARY")
print("=" * 80)

print(f"""
STEP 1 — Historical Brier Score Analysis:
  Data source: FiveThirtyEight model (2011-2014) — SUBSTITUTION for Vegas closing lines
  Years covered: {len(years)} (2011-2014)
  Total games: {len(games_538)} ({sum(1 for g in games_538 if g['round'] >= 2)} excl. First Four)
  Mean Brier Score by round:""")
for rk in round_keys:
    m = round_means.get(rk)
    if m is not None:
        print(f"    {round_names[rk]:>4}: {m:.4f}")

print(f"""
  Directional bias flags:
  - Watch for rounds where favorites systematically outperform or
    underperform forecasted probabilities (see bias analysis above)
  - Small sample size (4 years) limits confidence in bias detection

STEP 2 — Inter-Source Disagreement Proxy:
  Historical base rates: 1985-2025 (40 tournaments, n=160 per seed)
  High-uncertainty R1 games: {len(high_uncertainty_r1)} teams with >12pp deviation
  Later-round uncertainty ranges: Computed using historical stdev by seed

  Key interpretation: Large R1 deviations from historical seed rates indicate
  the current Vegas line sees a team as significantly stronger/weaker than a
  typical team at that seed. This is EXPECTED for top teams and bottom teams
  but flags where the single-source baseline might be least reliable.

STEP 3 — Output files:
  brier_scores_historical_vegas.csv — Historical calibration by round
  source_uncertainty_2026.csv — Per-team uncertainty metrics for downstream use
""")
