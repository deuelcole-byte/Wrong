#!/usr/bin/env python3
"""
Prompt 9 — Stress Test: Constrained Simulation

Simulates the Prompt 8 bracket (3 contrarian upsets) against 99 opponents
per pool across 50,000 tournament outcomes. Includes 4 sensitivity analyses.
"""
import csv
import numpy as np
from collections import defaultdict

np.random.seed(42)

N_SIMS = 50000
POOL_SIZE = 100
POINTS = {'R64': 10, 'R32': 20, 'S16': 40, 'E8': 80, 'F4': 160, 'NCG': 320}

# ============================================================
# LOAD DATA
# ============================================================
print("Loading data...")

# Probability baseline
prob_data = {}
with open('probability_baseline_final_2026.csv') as f:
    for row in csv.DictReader(f):
        prob_data[row['team_name']] = row

# ESPN matchups (bracket structure)
espn = {}
with open('espn_picks_2026.csv') as f:
    for row in csv.DictReader(f):
        espn[row['matchup_id']] = row

# Leverage matrix (public pick distributions for all rounds)
lev_data = {}
with open('leverage_matrix_2026.csv') as f:
    for row in csv.DictReader(f):
        lev_data[(row['team_name'], row['round'])] = row

# NCG pick distribution
ncg_dist = {}
with open('ncg_pick_distribution_2026.csv') as f:
    for row in csv.DictReader(f):
        ncg_dist[row['team_name']] = float(row['ncg_public_pick_pct']) / 100.0

# Prompt 8 bracket
p8_bracket = {}
with open('bracket_2026.csv') as f:
    for row in csv.DictReader(f):
        p8_bracket[row['matchup_id']] = row['team_picked']

print(f"  Loaded {len(prob_data)} teams, {len(espn)} matchups, {len(p8_bracket)} bracket picks")

# ============================================================
# BRACKET STRUCTURE
# ============================================================
# Organize matchups by round
matchups_by_round = defaultdict(list)
for mid, m in espn.items():
    matchups_by_round[m['round']].append(m)

# Build game-level win probabilities for tournament simulation
# For R64-S16: use conditional win prob (higher seed favored prob)
# For E8: use e8_game_prob_corrected
# For F4/NCG: compute from advancement probs

def higher_seed_first(m):
    s1, s2 = int(m['team_1_seed']), int(m['team_2_seed'])
    if s1 <= s2:
        return m['team_1_name'], m['team_2_name'], s1, s2
    return m['team_2_name'], m['team_1_name'], s2, s1

# Build game list with win probs
games = []
for rd in ['R64', 'R32', 'S16', 'E8']:
    for m in matchups_by_round[rd]:
        hi, lo, hs, ls = higher_seed_first(m)
        mid = m['matchup_id']

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

        pub_hi = float(m['team_1_pick_pct']) / 100.0 if m['team_1_name'] == hi \
                 else float(m['team_2_pick_pct']) / 100.0

        games.append({
            'round': rd, 'hi': hi, 'lo': lo, 'mid': mid,
            'vp': vp, 'pub_hi': pub_hi,
        })

def f4_game_prob(t1, t2):
    r5_1 = float(prob_data[t1]['r5'])
    r5_2 = float(prob_data[t2]['r5'])
    total = r5_1 + r5_2
    return r5_1 / total if total > 0 else 0.5

# E8 uncorrected probs (for sensitivity 1)
e8_uncorrected = {}
e8_corrected_teams = []
for g in games:
    if g['round'] == 'E8':
        corr = float(prob_data[g['hi']]['e8_game_prob_corrected'])
        impl = float(prob_data[g['hi']]['e8_game_prob_implied'])
        if abs(corr - impl) > 0.001:
            e8_corrected_teams.append(g['hi'])
            e8_corrected_teams.append(g['lo'])
        hi_impl = float(prob_data[g['hi']]['e8_game_prob_implied'])
        lo_impl = float(prob_data[g['lo']]['e8_game_prob_implied'])
        e8_uncorrected[g['mid']] = hi_impl if hi_impl > lo_impl else 1 - lo_impl

# Path-dependent teams (for sensitivity 2)
path_dep_teams = set()
for t, d in prob_data.items():
    if d.get('path_dependent_flag', 'N') == 'Y':
        path_dep_teams.add(t)

# LOW confidence teams (for sensitivity 3)
low_conf_teams = defaultdict(dict)
for t, d in prob_data.items():
    for r_idx, r_name in enumerate(['r1', 'r2', 'r3', 'r4_adjusted', 'r5', 'r6'], 1):
        tier_col = f'confidence_tier_r{r_idx}'
        if d.get(tier_col) == 'LOW':
            low_conf_teams[t][r_name] = True

print(f"  E8 corrected teams: {e8_corrected_teams}")
print(f"  Path-dependent teams: {path_dep_teams}")
print(f"  LOW confidence teams: {len(low_conf_teams)}")

# Check which corrected teams appear in P8 bracket
p8_teams = set(p8_bracket.values())
corrected_in_bracket = [t for t in e8_corrected_teams if t in p8_teams]
print(f"  Corrected teams in P8 bracket: {corrected_in_bracket}")

# ============================================================
# SIMULATION ENGINE
# ============================================================

def sim_tournament(game_overrides=None):
    """Simulate one tournament. Returns dict of matchup_id -> winner."""
    result = {}
    for g in games:
        mid = g['mid']
        if game_overrides and mid in game_overrides:
            vp = game_overrides[mid]
        else:
            vp = g['vp']
        result[mid] = g['hi'] if np.random.random() < vp else g['lo']

    # F4
    ew = result.get('E_E8', 'Duke'); sw = result.get('S_E8', 'Florida')
    ww = result.get('W_E8', 'Arizona'); mw = result.get('MW_E8', 'Michigan')
    p1 = f4_game_prob(ew, sw)
    result['F4_1'] = ew if np.random.random() < p1 else sw
    p2 = f4_game_prob(ww, mw)
    result['F4_2'] = ww if np.random.random() < p2 else mw
    pn = f4_game_prob(result['F4_1'], result['F4_2'])
    result['NCG'] = result['F4_1'] if np.random.random() < pn else result['F4_2']
    return result

def score_bracket(picks, actual):
    """Score a bracket against actual results."""
    score = 0
    for mid, winner in actual.items():
        if mid in picks and picks[mid] == winner:
            if 'R64' in mid: score += 10
            elif 'R32' in mid: score += 20
            elif 'S16' in mid: score += 40
            elif 'E8' in mid: score += 80
            elif mid.startswith('F4'): score += 160
            elif mid == 'NCG': score += 320
    return score

def gen_opponent_bracket():
    """Generate one opponent bracket from public pick distributions."""
    picks = {}
    # R64 through E8: use ESPN pick percentages
    for g in games:
        picks[g['mid']] = g['hi'] if np.random.random() < g['pub_hi'] else g['lo']

    # F4: use leverage matrix F4 public picks
    ep = picks.get('E_E8', 'Duke'); sp = picks.get('S_E8', 'Florida')
    f4e = float(lev_data.get((ep, 'F4'), {}).get('public_pick_pct', 0.5))
    f4s = float(lev_data.get((sp, 'F4'), {}).get('public_pick_pct', 0.5))
    t = f4e + f4s
    picks['F4_1'] = ep if np.random.random() < (f4e/t if t > 0 else 0.5) else sp

    wp = picks.get('W_E8', 'Arizona'); mp = picks.get('MW_E8', 'Michigan')
    f4w = float(lev_data.get((wp, 'F4'), {}).get('public_pick_pct', 0.5))
    f4m = float(lev_data.get((mp, 'F4'), {}).get('public_pick_pct', 0.5))
    t = f4w + f4m
    picks['F4_2'] = wp if np.random.random() < (f4w/t if t > 0 else 0.5) else mp

    # NCG: use ncg_pick_distribution
    n1 = ncg_dist.get(picks['F4_1'], 0.001)
    n2 = ncg_dist.get(picks['F4_2'], 0.001)
    t = n1 + n2
    picks['NCG'] = picks['F4_1'] if np.random.random() < (n1/t if t > 0 else 0.5) else picks['F4_2']
    return picks

def gen_chalk_bracket():
    """Generate pure chalk bracket (every favorite)."""
    picks = {}
    for g in games:
        picks[g['mid']] = g['hi']
    # F4/NCG: pick by highest r5/r6
    ep = picks.get('E_E8', 'Duke'); sp = picks.get('S_E8', 'Florida')
    picks['F4_1'] = ep if float(prob_data[ep]['r5']) >= float(prob_data[sp]['r5']) else sp
    wp = picks.get('W_E8', 'Arizona'); mp = picks.get('MW_E8', 'Michigan')
    picks['F4_2'] = wp if float(prob_data[wp]['r5']) >= float(prob_data[mp]['r5']) else mp
    picks['NCG'] = picks['F4_1'] if float(prob_data[picks['F4_1']]['r6']) >= \
                   float(prob_data[picks['F4_2']]['r6']) else picks['F4_2']
    return picks

def gen_random_bracket():
    """Generate uniform random bracket."""
    picks = {}
    for g in games:
        picks[g['mid']] = g['hi'] if np.random.random() < 0.5 else g['lo']
    # F4/NCG: random
    ew = picks.get('E_E8', 'Duke'); sw = picks.get('S_E8', 'Florida')
    picks['F4_1'] = ew if np.random.random() < 0.5 else sw
    ww = picks.get('W_E8', 'Arizona'); mw = picks.get('MW_E8', 'Michigan')
    picks['F4_2'] = ww if np.random.random() < 0.5 else mw
    picks['NCG'] = picks['F4_1'] if np.random.random() < 0.5 else picks['F4_2']
    return picks

# ============================================================
# RUN BASE SIMULATION
# ============================================================
def run_full_sim(label, our_bracket, game_overrides=None, n_sims=N_SIMS):
    """Run full simulation. Returns metrics dict and per-sim details."""
    print(f"  Running [{label}]...", end='', flush=True)

    wins = 0
    top10 = 0
    our_scores = []
    our_ranks = []
    all_sim_details = []

    for s in range(n_sims):
        actual = sim_tournament(game_overrides)
        our_score = score_bracket(our_bracket, actual)

        # Score 99 opponents
        opp_scores = []
        for _ in range(POOL_SIZE - 1):
            opp = gen_opponent_bracket()
            opp_scores.append(score_bracket(opp, actual))

        # Rank
        rank = 1 + sum(1 for os in opp_scores if os > our_score)
        pct = rank / POOL_SIZE

        our_scores.append(our_score)
        our_ranks.append(rank)

        if rank == 1:
            wins += 1
        if rank <= 10:
            top10 += 1

        all_sim_details.append({
            'our_score': our_score,
            'rank': rank,
            'max_opp': max(opp_scores),
            'actual': actual,
        })

        if (s + 1) % 10000 == 0:
            print(f" {s+1}", end='', flush=True)

    print(" done.")

    win_rate = wins / n_sims
    top10_rate = top10 / n_sims
    avg_score = np.mean(our_scores)
    avg_rank_pct = np.mean(our_ranks) / POOL_SIZE

    metrics = {
        'label': label,
        'win_rate': win_rate,
        'top10_rate': top10_rate,
        'avg_score': avg_score,
        'avg_rank_pct': avg_rank_pct,
        'score_std': np.std(our_scores),
        'score_median': np.median(our_scores),
    }

    return metrics, all_sim_details

# ============================================================
# BASE + COMPARISON BRACKETS
# ============================================================
print("\n" + "=" * 90)
print("BASE SIMULATION — Prompt 8 bracket vs 99 opponents (N=100)")
print("=" * 90)

chalk_bracket = gen_chalk_bracket()

# Run base simulation for P8 bracket
p8_metrics, p8_details = run_full_sim('P8 Optimal', p8_bracket)

# Run chalk bracket
chalk_metrics, _ = run_full_sim('Pure Chalk', chalk_bracket)

# Run public consensus (generate fresh each sim — this is the opponent bracket itself)
# For public consensus we need to run it differently: generate one public bracket per sim
print("  Running [Public Consensus]...", end='', flush=True)
pub_wins = 0; pub_top10 = 0; pub_scores = []; pub_ranks = []
for s in range(N_SIMS):
    actual = sim_tournament()
    pub_bracket = gen_opponent_bracket()
    pub_score = score_bracket(pub_bracket, actual)

    opp_scores = []
    for _ in range(POOL_SIZE - 1):
        opp = gen_opponent_bracket()
        opp_scores.append(score_bracket(opp, actual))

    rank = 1 + sum(1 for os in opp_scores if os > pub_score)
    pub_scores.append(pub_score)
    pub_ranks.append(rank)
    if rank == 1: pub_wins += 1
    if rank <= 10: pub_top10 += 1
    if (s + 1) % 10000 == 0: print(f" {s+1}", end='', flush=True)
print(" done.")

pub_metrics = {
    'label': 'Public Consensus',
    'win_rate': pub_wins / N_SIMS,
    'top10_rate': pub_top10 / N_SIMS,
    'avg_score': np.mean(pub_scores),
    'avg_rank_pct': np.mean(pub_ranks) / POOL_SIZE,
    'score_std': np.std(pub_scores),
    'score_median': np.median(pub_scores),
}

# Run random bracket
print("  Running [Random]...", end='', flush=True)
rand_wins = 0; rand_top10 = 0; rand_scores = []; rand_ranks = []
for s in range(N_SIMS):
    actual = sim_tournament()
    rand_bracket = gen_random_bracket()
    rand_score = score_bracket(rand_bracket, actual)

    opp_scores = []
    for _ in range(POOL_SIZE - 1):
        opp = gen_opponent_bracket()
        opp_scores.append(score_bracket(opp, actual))

    rank = 1 + sum(1 for os in opp_scores if os > rand_score)
    rand_scores.append(rand_score)
    rand_ranks.append(rank)
    if rank == 1: rand_wins += 1
    if rank <= 10: rand_top10 += 1
    if (s + 1) % 10000 == 0: print(f" {s+1}", end='', flush=True)
print(" done.")

rand_metrics = {
    'label': 'Random',
    'win_rate': rand_wins / N_SIMS,
    'top10_rate': rand_top10 / N_SIMS,
    'avg_score': np.mean(rand_scores),
    'avg_rank_pct': np.mean(rand_ranks) / POOL_SIZE,
    'score_std': np.std(rand_scores),
    'score_median': np.median(rand_scores),
}

# ============================================================
# FOUR-WAY COMPARISON TABLE
# ============================================================
print("\n" + "=" * 90)
print("FOUR-WAY COMPARISON TABLE")
print("=" * 90)

all_metrics = [p8_metrics, chalk_metrics, pub_metrics, rand_metrics]

print(f"\n{'Bracket':<22} {'Win Rate':>10} {'Top 10%':>10} {'Avg Score':>10} "
      f"{'Avg Rank%':>10} {'Score SD':>10} {'Median':>10}")
print("-" * 85)
for m in all_metrics:
    print(f"  {m['label']:<20} {m['win_rate']:>9.2%} {m['top10_rate']:>9.2%} "
          f"{m['avg_score']:>9.1f} {m['avg_rank_pct']:>9.1%} "
          f"{m['score_std']:>9.1f} {m['score_median']:>9.1f}")

# Flag if P8 win rate outside expected range
expected_lo, expected_hi = 0.01, 0.06
if p8_metrics['win_rate'] < expected_lo or p8_metrics['win_rate'] > expected_hi:
    print(f"\n  FLAG: P8 win rate {p8_metrics['win_rate']:.2%} outside expected range "
          f"({expected_lo:.0%}-{expected_hi:.0%}). Investigating...")

# Score histogram
p8_scores = [d['our_score'] for d in p8_details]
hist_bins = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1920]
hist, _ = np.histogram(p8_scores, bins=hist_bins)
print(f"\nP8 Score Distribution:")
for i in range(len(hist)):
    bar = '#' * int(hist[i] / N_SIMS * 200)
    print(f"  {hist_bins[i]:>5}-{hist_bins[i+1]:>5}: {hist[i]:>6} ({hist[i]/N_SIMS:>6.1%}) {bar}")

# ============================================================
# SENSITIVITY 1 — E8 Correction Impact
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY 1 — E8 Correction Impact")
print("=" * 90)

print(f"  Using uncorrected e8_game_prob_implied for E8 games")
print(f"  Corrected teams in P8 bracket: {corrected_in_bracket}")

e8_overrides = {}
for g in games:
    if g['round'] == 'E8':
        e8_overrides[g['mid']] = e8_uncorrected[g['mid']]

s1_metrics, _ = run_full_sim('S1: E8 Uncorrected', p8_bracket, game_overrides=e8_overrides)
s1_delta = p8_metrics['win_rate'] - s1_metrics['win_rate']
print(f"  Baseline win rate: {p8_metrics['win_rate']:.3%}")
print(f"  Uncorrected win rate: {s1_metrics['win_rate']:.3%}")
print(f"  Delta: {s1_delta:+.3%}")

# ============================================================
# SENSITIVITY 2 — Path Dependency
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY 2 — Path Dependency (alternate E8 scenario)")
print("=" * 90)

print(f"  Path-dependent teams: {path_dep_teams}")

# Build alternate game overrides: use r4_adjusted_alt for path-dep teams
# This changes the E8 game probs for games involving path-dep teams
alt_overrides = {}
for g in games:
    if g['round'] == 'E8':
        hi, lo = g['hi'], g['lo']
        if hi in path_dep_teams or lo in path_dep_teams:
            # Recompute E8 game prob using r4_adjusted_alt
            hi_r4_alt = float(prob_data[hi].get('r4_adjusted_alt', prob_data[hi]['r4_adjusted']))
            lo_r4_alt = float(prob_data[lo].get('r4_adjusted_alt', prob_data[lo]['r4_adjusted']))
            # Game prob from advancement probs
            total = hi_r4_alt + lo_r4_alt
            alt_vp = hi_r4_alt / total if total > 0 else 0.5
            alt_overrides[g['mid']] = alt_vp
            print(f"  {g['mid']}: {hi} vs {lo}: primary={g['vp']:.4f}, alt={alt_vp:.4f}")

s2_metrics, _ = run_full_sim('S2: Alt Path', p8_bracket, game_overrides=alt_overrides)
s2_delta = p8_metrics['win_rate'] - s2_metrics['win_rate']
print(f"  Baseline win rate: {p8_metrics['win_rate']:.3%}")
print(f"  Alt-path win rate: {s2_metrics['win_rate']:.3%}")
print(f"  Delta: {s2_delta:+.3%}")
if abs(s2_delta) > 0.03:
    print(f"  *** MATERIAL: delta exceeds 3pp")

# ============================================================
# SENSITIVITY 3 — Single-Source Bounds (LOW confidence)
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY 3 — Single-Source Bounds (LOW confidence teams)")
print("=" * 90)

# Modify game probs for LOW confidence teams
def make_conf_overrides(bound):
    """Create game overrides with LOW confidence shifted."""
    overrides = {}
    for g in games:
        hi, lo, rd = g['hi'], g['lo'], g['round']
        tier_col = {'R64': 'confidence_tier_r1', 'R32': 'confidence_tier_r2',
                    'S16': 'confidence_tier_r3', 'E8': 'confidence_tier_r4'}.get(rd)
        if tier_col:
            hi_tier = prob_data[hi].get(tier_col, 'HIGH')
            lo_tier = prob_data[lo].get(tier_col, 'HIGH')
            if hi_tier == 'LOW' or lo_tier == 'LOW':
                if bound == 'low':
                    overrides[g['mid']] = max(0.35, g['vp'] - 0.05)
                else:
                    overrides[g['mid']] = min(0.95, g['vp'] + 0.05)
    return overrides

low_overrides = make_conf_overrides('low')
high_overrides = make_conf_overrides('high')

print(f"  LOW confidence game overrides: {len(low_overrides)} games affected")

s3_lo_metrics, _ = run_full_sim('S3: Conf LOW bound', p8_bracket, game_overrides=low_overrides)
s3_hi_metrics, _ = run_full_sim('S3: Conf HIGH bound', p8_bracket, game_overrides=high_overrides)

s3_range = abs(s3_hi_metrics['win_rate'] - s3_lo_metrics['win_rate'])
print(f"  Low-bound win rate: {s3_lo_metrics['win_rate']:.3%}")
print(f"  High-bound win rate: {s3_hi_metrics['win_rate']:.3%}")
print(f"  Range: {s3_range:.3%}")
if s3_range > 0.03:
    print(f"  *** MATERIAL: range exceeds 3pp — sensitive to single-source estimation")

# ============================================================
# SENSITIVITY 4 — Scenario Dependency
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY 4 — Scenario Dependency (best/worst tournament outcomes)")
print("=" * 90)

# Find best and worst 10 scenarios from base simulation
sorted_by_rank = sorted(p8_details, key=lambda d: (d['rank'], -d['our_score']))
best_10 = sorted_by_rank[:10]
worst_10 = sorted_by_rank[-10:]

def describe_scenario(detail):
    """Describe key features of a tournament outcome."""
    actual = detail['actual']
    # Key results: who won each E8, F4, NCG
    e8_winners = {mid: actual[mid] for mid in ['E_E8', 'S_E8', 'W_E8', 'MW_E8']}
    f4_winners = {mid: actual[mid] for mid in ['F4_1', 'F4_2']}
    champion = actual['NCG']

    # Check which of our picks hit
    hits = []
    for mid in ['E_E8', 'S_E8', 'W_E8', 'MW_E8', 'F4_1', 'F4_2', 'NCG']:
        if p8_bracket.get(mid) == actual.get(mid):
            hits.append(f"{mid}={actual[mid]}")

    # Check path-dependent teams
    path_dep_surprise = []
    for mid in ['E_E8', 'S_E8', 'W_E8', 'MW_E8', 'F4_1', 'F4_2', 'NCG']:
        winner = actual.get(mid, '')
        if winner in path_dep_teams:
            # Check if this conflicts with primary path
            # Primary path: team is picked to advance in P8 bracket
            if p8_bracket.get(mid) != winner:
                path_dep_surprise.append(f"{winner} wins {mid} (path-dep, not in our bracket)")

    return e8_winners, f4_winners, champion, hits, path_dep_surprise

print(f"\n  TOP 10 SCENARIOS (best bracket performance):")
print(f"  {'Rank':>4} {'Score':>6} {'Champion':<18} {'E8/F4/NCG Hits':<40} {'Path-Dep Flags'}")
print("  " + "-" * 100)
for d in best_10:
    e8w, f4w, champ, hits, pdflags = describe_scenario(d)
    hits_str = ', '.join(hits[-4:]) if hits else 'none'
    pd_str = '; '.join(pdflags) if pdflags else 'none'
    print(f"  {d['rank']:>4} {d['our_score']:>6} {champ:<18} {hits_str:<40} {pd_str}")

print(f"\n  BOTTOM 10 SCENARIOS (worst bracket performance):")
print(f"  {'Rank':>4} {'Score':>6} {'Champion':<18} {'E8/F4/NCG Hits':<40} {'Path-Dep Flags'}")
print("  " + "-" * 100)
for d in worst_10:
    e8w, f4w, champ, hits, pdflags = describe_scenario(d)
    hits_str = ', '.join(hits[-4:]) if hits else 'none'
    pd_str = '; '.join(pdflags) if pdflags else 'none'
    print(f"  {d['rank']:>4} {d['our_score']:>6} {champ:<18} {hits_str:<40} {pd_str}")

# Flag acute structural vulnerabilities
print(f"\n  PATH-DEPENDENT STRUCTURAL VULNERABILITIES:")
path_dep_worst = [d for d in worst_10 if any(describe_scenario(d)[4])]
if path_dep_worst:
    for d in path_dep_worst:
        _, _, champ, _, pdflags = describe_scenario(d)
        print(f"    Rank {d['rank']}, Score {d['our_score']}: {'; '.join(pdflags)}")
else:
    print(f"    None in bottom 10 scenarios")

# Check how often path-dep teams cause problems across all sims
path_dep_issue_count = 0
for d in p8_details:
    _, _, _, _, pdflags = describe_scenario(d)
    if pdflags:
        path_dep_issue_count += 1
print(f"    Path-dep contrary to primary path in {path_dep_issue_count}/{N_SIMS} sims "
      f"({path_dep_issue_count/N_SIMS:.1%})")

# ============================================================
# SENSITIVITY DELTA TABLE
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY DELTA TABLE")
print("=" * 90)

print(f"\n{'Sensitivity':<35} {'Win Rate':>10} {'Delta':>10} {'Flag'}")
print("-" * 70)
baseline_wr = p8_metrics['win_rate']
sensitivities = [
    ('Baseline (P8 Optimal)', baseline_wr, 0),
    ('S1: E8 Uncorrected', s1_metrics['win_rate'], s1_delta),
    ('S2: Alt Path', s2_metrics['win_rate'], s2_delta),
    ('S3: Conf LOW bound', s3_lo_metrics['win_rate'], s3_lo_metrics['win_rate'] - baseline_wr),
    ('S3: Conf HIGH bound', s3_hi_metrics['win_rate'], s3_hi_metrics['win_rate'] - baseline_wr),
]

for label, wr, delta in sensitivities:
    flag = '*** >3pp' if abs(delta) > 0.03 else ''
    print(f"  {label:<33} {wr:>9.3%} {delta:>+9.3%} {flag}")

# ============================================================
# OUTPUT CSV
# ============================================================
print("\n" + "=" * 90)
print("SAVING OUTPUT")
print("=" * 90)

csv_rows = []
for m in all_metrics:
    csv_rows.append({
        'bracket_type': m['label'],
        'win_rate': f"{m['win_rate']:.6f}",
        'top10_rate': f"{m['top10_rate']:.6f}",
        'avg_score': f"{m['avg_score']:.2f}",
        'avg_rank_percentile': f"{m['avg_rank_pct']:.4f}",
        'score_std': f"{m['score_std']:.2f}",
        'score_median': f"{m['score_median']:.1f}",
        'sensitivity': 'baseline',
    })

# Add sensitivity results
for label, wr, delta in sensitivities[1:]:
    csv_rows.append({
        'bracket_type': 'P8 Optimal',
        'win_rate': f"{wr:.6f}",
        'top10_rate': '',
        'avg_score': '',
        'avg_rank_percentile': '',
        'score_std': '',
        'score_median': '',
        'sensitivity': label,
    })

fields = ['bracket_type', 'sensitivity', 'win_rate', 'top10_rate', 'avg_score',
          'avg_rank_percentile', 'score_std', 'score_median']
with open('stress_test_constrained_2026.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for row in csv_rows:
        w.writerow(row)

print(f"Wrote stress_test_constrained_2026.csv")

# ============================================================
# FINAL SUMMARY
# ============================================================
print("\n" + "=" * 90)
print("STRESS TEST COMPLETE")
print("=" * 90)

print(f"\n  P8 Optimal bracket at N=100:")
print(f"    Win rate: {p8_metrics['win_rate']:.2%}")
print(f"    Top 10%: {p8_metrics['top10_rate']:.2%}")
print(f"    Avg score: {p8_metrics['avg_score']:.1f}")
print(f"    vs Chalk: {p8_metrics['win_rate'] - chalk_metrics['win_rate']:+.2%} win rate")
print(f"    vs Public: {p8_metrics['win_rate'] - pub_metrics['win_rate']:+.2%} win rate")
print(f"    vs Random: {p8_metrics['win_rate'] - rand_metrics['win_rate']:+.2%} win rate")
print(f"\n  Key sensitivities:")
print(f"    E8 correction: {s1_delta:+.3%}")
print(f"    Path dependency: {s2_delta:+.3%}")
print(f"    Single-source range: {s3_range:.3%}")
