#!/usr/bin/env python3
"""
Prompt 9B — Unconstrained Stress Test + Upset Count Sweep

Builds unconstrained bracket (all threshold-passing upsets), runs full
simulation, and sweeps upset count 0-10 to map the win-rate curve at N=100.
"""
import csv
import math
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

prob_data = {}
with open('probability_baseline_final_2026.csv') as f:
    for row in csv.DictReader(f):
        prob_data[row['team_name']] = row

espn = {}
with open('espn_picks_2026.csv') as f:
    for row in csv.DictReader(f):
        espn[row['matchup_id']] = row

lev_data = {}
with open('leverage_matrix_2026.csv') as f:
    for row in csv.DictReader(f):
        lev_data[(row['team_name'], row['round'])] = row

ncg_dist = {}
with open('ncg_pick_distribution_2026.csv') as f:
    for row in csv.DictReader(f):
        ncg_dist[row['team_name']] = float(row['ncg_public_pick_pct']) / 100.0

champ_data = []
with open('champion_optimizer_results.csv') as f:
    for row in csv.DictReader(f):
        champ_data.append(row)

# Constrained bracket (from Prompt 8)
p8_bracket = {}
with open('bracket_2026.csv') as f:
    for row in csv.DictReader(f):
        p8_bracket[row['matchup_id']] = row['team_picked']

# Champion: highest EV at N=100
champ_data.sort(key=lambda x: -float(x['ev_100']))
champion = champ_data[0]
champ_name = champion['team_name']
champ_region = champion['region']
print(f"  Champion: {champ_name} ({champ_region})")

# ============================================================
# BRACKET STRUCTURE HELPERS
# ============================================================
def higher_seed_first(m):
    s1, s2 = int(m['team_1_seed']), int(m['team_2_seed'])
    if s1 <= s2: return m['team_1_name'], m['team_2_name'], s1, s2
    return m['team_2_name'], m['team_1_name'], s2, s1

def get_chalk(m):
    s1, s2 = int(m['team_1_seed']), int(m['team_2_seed'])
    if s1 < s2: return m['team_1_name']
    elif s2 < s1: return m['team_2_name']
    return m['team_1_name']

def get_underdog(m):
    s1, s2 = int(m['team_1_seed']), int(m['team_2_seed'])
    if s1 < s2: return m['team_2_name']
    elif s2 < s1: return m['team_1_name']
    return m['team_2_name']

sign_flip_teams = set()
for (team, rd), entry in lev_data.items():
    if entry.get('sign_flip_flag', 'N') == 'Y':
        sign_flip_teams.add((team, rd))

DEV_THRESHOLDS = {'NA': 1.15, 'A': 1.15, 'B': 1.20, 'C': 1.25}

# Build game list for simulation
games = []
for rd in ['R64', 'R32', 'S16', 'E8']:
    for m in [v for v in espn.values() if v['round'] == rd]:
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
        games.append({'round': rd, 'hi': hi, 'lo': lo, 'mid': mid, 'vp': vp, 'pub_hi': pub_hi})

# E8 uncorrected probs
e8_uncorrected = {}
e8_corrected_teams = []
for g in games:
    if g['round'] == 'E8':
        corr = float(prob_data[g['hi']]['e8_game_prob_corrected'])
        impl = float(prob_data[g['hi']]['e8_game_prob_implied'])
        if abs(corr - impl) > 0.001:
            e8_corrected_teams.extend([g['hi'], g['lo']])
        hi_impl = float(prob_data[g['hi']]['e8_game_prob_implied'])
        lo_impl = float(prob_data[g['lo']]['e8_game_prob_implied'])
        e8_uncorrected[g['mid']] = hi_impl if hi_impl > lo_impl else 1 - lo_impl

path_dep_teams = set(t for t, d in prob_data.items() if d.get('path_dependent_flag', 'N') == 'Y')

# ============================================================
# STEP 1 — BUILD UNCONSTRAINED BRACKET
# ============================================================
print("\n" + "=" * 90)
print("STEP 1 — BUILD UNCONSTRAINED BRACKET")
print("=" * 90)

e8_matchups = {m['matchup_id']: m for m in espn.values() if m['round'] == 'E8'}
s16_matchups = {m['matchup_id']: m for m in espn.values() if m['round'] == 'S16'}
r32_matchups = {m['matchup_id']: m for m in espn.values() if m['round'] == 'R32'}
r64_matchups = {m['matchup_id']: m for m in espn.values() if m['round'] == 'R64'}
f4_matchups_map = {m['matchup_id']: m for m in espn.values() if m['round'] == 'F4'}

# E8 picks (same as P8 — all chalk due to sign-flip / Type C bounds)
e8_picks = {}
f4_picks = {}
for mid, m in sorted(e8_matchups.items()):
    chalk = get_chalk(m)
    underdog = get_underdog(m)
    region = m['region']
    if region == champ_region:
        e8_picks[mid] = champ_name
        f4_picks[region] = champ_name
        continue
    ud_lev = lev_data.get((underdog, 'E8'), {})
    ud_lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
    ud_conf = ud_lev.get('confidence_type', 'NA') if ud_lev else 'NA'
    ud_sf = (underdog, 'E8') in sign_flip_teams
    ud_lo = float(ud_lev.get('leverage_low', '0')) if ud_lev else 0
    ud_hi = float(ud_lev.get('leverage_high', '0')) if ud_lev else 0
    ud_vegas = float(ud_lev.get('vegas_prob', 0)) if ud_lev else 0
    threshold = DEV_THRESHOLDS.get(ud_conf, 1.15)
    if ud_sf:
        pick = chalk
    elif ud_conf == 'C' and (ud_lo <= 0 or ud_hi <= 0):
        pick = chalk
    elif ud_lr > threshold and ud_vegas > 0.35:
        pick = underdog
    else:
        pick = chalk
    e8_picks[mid] = pick
    f4_picks[region] = pick

# S16 picks — unconstrained: include ALL upsets passing thresholds
s16_picks = {}
for mid, m in sorted(s16_matchups.items()):
    chalk = get_chalk(m)
    underdog = get_underdog(m)
    region = m['region']
    e8_mid = {'East': 'E_E8', 'South': 'S_E8', 'West': 'W_E8', 'Midwest': 'MW_E8'}[region]
    e8_pick = e8_picks.get(e8_mid, '')
    if e8_pick == m['team_1_name'] or e8_pick == m['team_2_name']:
        s16_picks[mid] = e8_pick
        continue
    ud_lev = lev_data.get((underdog, 'S16'), {})
    ud_lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
    ud_vegas = float(ud_lev.get('vegas_prob', 0)) if ud_lev else 0
    ud_conf = ud_lev.get('confidence_type', 'NA') if ud_lev else 'NA'
    ud_sf = (underdog, 'S16') in sign_flip_teams
    ud_lo = float(ud_lev.get('leverage_low', '0')) if ud_lev else 0
    ud_hi = float(ud_lev.get('leverage_high', '0')) if ud_lev else 0
    threshold = DEV_THRESHOLDS.get(ud_conf, 1.15)
    if ud_sf:
        pick = chalk
    elif ud_conf == 'C' and (ud_lo <= 0 or ud_hi <= 0):
        pick = chalk
    elif ud_lr > threshold and ud_vegas > 0.35:
        pick = underdog
    else:
        pick = chalk
    s16_picks[mid] = pick

# R32 picks — unconstrained
r32_picks = {}
for mid, m in sorted(r32_matchups.items()):
    chalk = get_chalk(m)
    underdog = get_underdog(m)
    region_prefix = mid.split('_R32_')[0]
    r32_num = int(mid.split('_R32_')[1])
    s16_num = (r32_num + 1) // 2
    s16_mid = f"{region_prefix}_S16_{s16_num}"
    s16_pick = s16_picks.get(s16_mid, '')
    if s16_pick == m['team_1_name'] or s16_pick == m['team_2_name']:
        r32_picks[mid] = s16_pick
        continue
    ud_lev = lev_data.get((underdog, 'R32'), {})
    ud_lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
    ud_vegas = float(prob_data.get(underdog, {}).get('r2', 0))
    ud_abs_lev = abs(float(ud_lev.get('leverage', 0))) if ud_lev else 0
    if ud_abs_lev > 0.10 and ud_lr > 1.25 and ud_vegas > 0.35:
        pick = underdog
    else:
        pick = chalk
    r32_picks[mid] = pick

# R64 picks — unconstrained
r64_picks = {}
for mid, m in sorted(r64_matchups.items()):
    chalk = get_chalk(m)
    underdog = get_underdog(m)
    region_prefix = mid.split('_R64_')[0]
    r64_num = int(mid.split('_R64_')[1])
    r32_num = (r64_num + 1) // 2
    r32_mid = f"{region_prefix}_R32_{r32_num}"
    r32_pick = r32_picks.get(r32_mid, '')
    if r32_pick == m['team_1_name'] or r32_pick == m['team_2_name']:
        if r32_pick != chalk:
            r64_picks[mid] = r32_pick
            continue
    ud_lev = lev_data.get((underdog, 'R64'), {})
    ud_lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
    ud_vegas = float(prob_data.get(underdog, {}).get('r1', 0))
    ud_abs_lev = abs(float(ud_lev.get('leverage', 0))) if ud_lev else 0
    if ud_abs_lev > 0.10 and ud_lr > 1.25 and ud_vegas > 0.35:
        pick = underdog
    else:
        pick = chalk
    r64_picks[mid] = pick

# Assemble F4/NCG
f4_bracket_picks = {}
for fmid in ['F4_1', 'F4_2']:
    fm = f4_matchups_map[fmid]
    if fmid == 'F4_1':
        east_f4, south_f4 = f4_picks['East'], f4_picks['South']
        if champ_region in ('East', 'South'):
            pick = champ_name
        else:
            pick = east_f4 if float(prob_data[east_f4]['r5']) >= float(prob_data[south_f4]['r5']) else south_f4
    elif fmid == 'F4_2':
        west_f4, mw_f4 = f4_picks['West'], f4_picks['Midwest']
        if champ_region in ('West', 'Midwest'):
            pick = champ_name
        else:
            pick = west_f4 if float(prob_data[west_f4]['r5']) >= float(prob_data[mw_f4]['r5']) else mw_f4
    f4_bracket_picks[fmid] = pick

unc_bracket = {}
unc_bracket.update(r64_picks)
unc_bracket.update(r32_picks)
unc_bracket.update(s16_picks)
unc_bracket.update(e8_picks)
unc_bracket.update(f4_bracket_picks)
unc_bracket['NCG'] = champ_name

# Count upsets
unc_upsets = {}
for mid, m in espn.items():
    if mid in unc_bracket and m['round'] not in ('F4', 'NCG', 'NCG_CHAMP'):
        chalk = get_chalk(m)
        if unc_bracket[mid] != chalk:
            unc_upsets[mid] = unc_bracket[mid]

# Document differences from P8
print(f"\nUnconstrained bracket: {len(unc_upsets)} contrarian upsets (P8 had 3)")
print(f"\nDIFFERENCES FROM P8 CONSTRAINED BRACKET:")
print(f"  {'Round':<6} {'Matchup':<12} {'P8 Pick':<18} {'Unc Pick':<18} {'LevR':>8} {'Vegas':>8} {'Reason Suppressed in P8'}")
print("  " + "-" * 100)

diffs = []
for mid in sorted(unc_bracket.keys()):
    if mid not in p8_bracket:
        continue
    if unc_bracket[mid] != p8_bracket[mid]:
        m = espn.get(mid, {})
        rd = m.get('round', '?')
        underdog = unc_bracket[mid]
        ud_lev = lev_data.get((underdog, rd), {})
        lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
        vegas = float(ud_lev.get('vegas_prob', 0)) if ud_lev else 0
        # Why was it suppressed in P8? At N=100 with 3-upset budget, it didn't make the cut
        reason = "entropy budget (3 upsets already used)"
        diffs.append((rd, mid, p8_bracket[mid], underdog, lr, vegas, reason))
        print(f"  {rd:<6} {mid:<12} {p8_bracket[mid]:<18} {underdog:<18} {lr:>8.4f} {vegas:>8.4f} {reason}")

if not diffs:
    print("  No differences — unconstrained bracket is identical to constrained.")

# Save unconstrained bracket CSV
bracket_rows = []
for mid in sorted(unc_bracket.keys()):
    m = espn.get(mid, {})
    if not m:
        if mid.startswith('F4'):
            m = f4_matchups_map.get(mid, {'round': 'F4', 'region': 'National', 'matchup_id': mid,
                                           'team_1_name': '', 'team_1_seed': '1', 'team_1_pick_pct': '50',
                                           'team_2_name': '', 'team_2_seed': '1', 'team_2_pick_pct': '50'})
        elif mid == 'NCG':
            m = espn.get('NCG', {'round': 'NCG', 'region': 'National', 'matchup_id': 'NCG',
                                  'team_1_name': '', 'team_1_seed': '1', 'team_1_pick_pct': '50',
                                  'team_2_name': '', 'team_2_seed': '1', 'team_2_pick_pct': '50'})
    pick = unc_bracket[mid]
    rd = m.get('round', '?')
    region = m.get('region', 'National')
    chalk = get_chalk(m) if 'team_1_seed' in m else pick
    deviation = 'Y' if pick != chalk else 'N'
    pick_seed = int(prob_data.get(pick, {}).get('team_seed', 0))
    rd_prob_col = {'R64': 'r1', 'R32': 'r2', 'S16': 'r3', 'E8': 'r4_adjusted', 'F4': 'r5', 'NCG': 'r6'}.get(rd, 'r1')
    pick_vegas = float(prob_data.get(pick, {}).get(rd_prob_col, 0))
    pick_pub = float(m.get('team_1_pick_pct', 50)) / 100 if m.get('team_1_name') == pick \
               else float(m.get('team_2_pick_pct', 50)) / 100
    le = lev_data.get((pick, rd), {})
    lr = float(le.get('leverage_ratio', 0)) if le else 0
    ct = le.get('confidence_tier', 'N/A') if le else 'N/A'
    ctype = le.get('confidence_type', 'NA') if le else 'NA'
    threshold = DEV_THRESHOLDS.get(ctype, 1.15) if deviation == 'Y' else 0
    pd = prob_data.get(pick, {}).get('path_dependent_flag', 'N')
    bracket_rows.append({
        'round': rd, 'region': region, 'matchup_id': mid, 'team_picked': pick,
        'seed': pick_seed, 'vegas_win_prob': f"{pick_vegas:.4f}",
        'public_pick_pct': f"{pick_pub:.4f}", 'leverage_ratio': f"{lr:.4f}",
        'confidence_tier': ct, 'confidence_type': ctype,
        'deviation_from_chalk': deviation,
        'deviation_threshold_applied': f"{threshold:.2f}" if threshold > 0 else 'N/A',
        'path_assumption': 'primary' if pd == 'Y' else 'NA',
    })

csv_fields = ['round', 'region', 'matchup_id', 'team_picked', 'seed',
              'vegas_win_prob', 'public_pick_pct', 'leverage_ratio',
              'confidence_tier', 'confidence_type', 'deviation_from_chalk',
              'deviation_threshold_applied', 'path_assumption']
with open('bracket_unconstrained_2026.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=csv_fields)
    w.writeheader()
    for r in bracket_rows:
        w.writerow(r)
print(f"\nWrote bracket_unconstrained_2026.csv ({len(bracket_rows)} games)")

# ============================================================
# SIMULATION ENGINE (shared with 9A)
# ============================================================
def f4_game_prob(t1, t2):
    r5_1, r5_2 = float(prob_data[t1]['r5']), float(prob_data[t2]['r5'])
    total = r5_1 + r5_2
    return r5_1 / total if total > 0 else 0.5

def sim_tournament(game_overrides=None):
    result = {}
    for g in games:
        mid = g['mid']
        vp = game_overrides[mid] if game_overrides and mid in game_overrides else g['vp']
        result[mid] = g['hi'] if np.random.random() < vp else g['lo']
    ew, sw = result.get('E_E8', 'Duke'), result.get('S_E8', 'Florida')
    ww, mw = result.get('W_E8', 'Arizona'), result.get('MW_E8', 'Michigan')
    p1 = f4_game_prob(ew, sw)
    result['F4_1'] = ew if np.random.random() < p1 else sw
    p2 = f4_game_prob(ww, mw)
    result['F4_2'] = ww if np.random.random() < p2 else mw
    pn = f4_game_prob(result['F4_1'], result['F4_2'])
    result['NCG'] = result['F4_1'] if np.random.random() < pn else result['F4_2']
    return result

def score_bracket(picks, actual):
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
    picks = {}
    for g in games:
        picks[g['mid']] = g['hi'] if np.random.random() < g['pub_hi'] else g['lo']
    ep, sp = picks.get('E_E8', 'Duke'), picks.get('S_E8', 'Florida')
    f4e = float(lev_data.get((ep, 'F4'), {}).get('public_pick_pct', 0.5))
    f4s = float(lev_data.get((sp, 'F4'), {}).get('public_pick_pct', 0.5))
    t = f4e + f4s
    picks['F4_1'] = ep if np.random.random() < (f4e/t if t > 0 else 0.5) else sp
    wp, mp = picks.get('W_E8', 'Arizona'), picks.get('MW_E8', 'Michigan')
    f4w = float(lev_data.get((wp, 'F4'), {}).get('public_pick_pct', 0.5))
    f4m = float(lev_data.get((mp, 'F4'), {}).get('public_pick_pct', 0.5))
    t = f4w + f4m
    picks['F4_2'] = wp if np.random.random() < (f4w/t if t > 0 else 0.5) else mp
    n1, n2 = ncg_dist.get(picks['F4_1'], 0.001), ncg_dist.get(picks['F4_2'], 0.001)
    t = n1 + n2
    picks['NCG'] = picks['F4_1'] if np.random.random() < (n1/t if t > 0 else 0.5) else picks['F4_2']
    return picks

def gen_chalk_bracket():
    picks = {}
    for g in games:
        picks[g['mid']] = g['hi']
    ep, sp = picks.get('E_E8', 'Duke'), picks.get('S_E8', 'Florida')
    picks['F4_1'] = ep if float(prob_data[ep]['r5']) >= float(prob_data[sp]['r5']) else sp
    wp, mp = picks.get('W_E8', 'Arizona'), picks.get('MW_E8', 'Michigan')
    picks['F4_2'] = wp if float(prob_data[wp]['r5']) >= float(prob_data[mp]['r5']) else mp
    picks['NCG'] = picks['F4_1'] if float(prob_data[picks['F4_1']]['r6']) >= \
                   float(prob_data[picks['F4_2']]['r6']) else picks['F4_2']
    return picks

chalk_bracket = gen_chalk_bracket()

def run_sim(label, bracket, game_overrides=None, n_sims=N_SIMS):
    print(f"  Running [{label}]...", end='', flush=True)
    wins = 0; top10 = 0; scores = []; ranks = []; details = []
    for s in range(n_sims):
        actual = sim_tournament(game_overrides)
        our_score = score_bracket(bracket, actual)
        opp_scores = [score_bracket(gen_opponent_bracket(), actual) for _ in range(POOL_SIZE - 1)]
        rank = 1 + sum(1 for os in opp_scores if os > our_score)
        scores.append(our_score); ranks.append(rank)
        if rank == 1: wins += 1
        if rank <= 10: top10 += 1
        details.append({'our_score': our_score, 'rank': rank, 'max_opp': max(opp_scores), 'actual': actual})
        if (s + 1) % 10000 == 0: print(f" {s+1}", end='', flush=True)
    print(" done.")
    return {
        'label': label, 'win_rate': wins / n_sims, 'top10_rate': top10 / n_sims,
        'avg_score': np.mean(scores), 'avg_rank_pct': np.mean(ranks) / POOL_SIZE,
        'score_std': np.std(scores), 'score_median': np.median(scores),
    }, details

# ============================================================
# STEP 2 — BASE SIMULATION
# ============================================================
print("\n" + "=" * 90)
print("STEP 2 — BASE SIMULATION (unconstrained bracket)")
print("=" * 90)

unc_metrics, unc_details = run_sim('Unconstrained', unc_bracket)

# ============================================================
# STEP 3 — HEAD-TO-HEAD COMPARISON
# ============================================================
print("\n" + "=" * 90)
print("STEP 3 — HEAD-TO-HEAD: CONSTRAINED vs UNCONSTRAINED")
print("=" * 90)

# Load P8 metrics from 9A output
p8_metrics, _ = run_sim('P8 Constrained (3 upsets)', p8_bracket)
chalk_metrics, _ = run_sim('Pure Chalk (0 upsets)', chalk_bracket)

# Count upsets
p8_upset_count = sum(1 for mid, m in espn.items()
                     if mid in p8_bracket and m['round'] not in ('F4', 'NCG', 'NCG_CHAMP')
                     and p8_bracket[mid] != get_chalk(m))
unc_upset_count = len(unc_upsets)

print(f"\n{'Metric':<22} {'Constrained (3)':>18} {'Unconstrained':>18} {'Chalk (0)':>18} {'Delta Unc-Cnstr':>18}")
print("-" * 96)
for metric, key, fmt in [('Win rate', 'win_rate', '.2%'), ('Top 10% rate', 'top10_rate', '.2%'),
                          ('Avg score', 'avg_score', '.1f'), ('Avg rank pct', 'avg_rank_pct', '.1%'),
                          ('Score SD', 'score_std', '.1f')]:
    p8v = p8_metrics[key]; uv = unc_metrics[key]; cv = chalk_metrics[key]
    delta = uv - p8v
    print(f"  {metric:<20} {p8v:>18{fmt}} {uv:>18{fmt}} {cv:>18{fmt}} {delta:>+18{fmt}}")

print(f"  {'Upset count':<20} {p8_upset_count:>18} {unc_upset_count:>18} {'0':>18}")

wr_diff = unc_metrics['win_rate'] - p8_metrics['win_rate']
print(f"\n  Win rate difference: {wr_diff:+.3%}")
if abs(wr_diff) > 0.005:
    print(f"  MEANINGFUL: >{0.5:.1f}pp — unconstrained bracket is {'better' if wr_diff > 0 else 'worse'}")
else:
    print(f"  EQUIVALENT: <0.5pp — brackets are strategically equivalent, prefer constrained for theory")

# ============================================================
# STEP 4 — SENSITIVITY SIMULATIONS
# ============================================================
print("\n" + "=" * 90)
print("STEP 4 — SENSITIVITY SIMULATIONS")
print("=" * 90)

# S1: E8 uncorrected
e8_overrides = {g['mid']: e8_uncorrected[g['mid']] for g in games if g['round'] == 'E8'}
s1_metrics, _ = run_sim('S1: E8 Uncorrected', unc_bracket, game_overrides=e8_overrides)
s1_delta = unc_metrics['win_rate'] - s1_metrics['win_rate']
print(f"  S1 E8 Correction: baseline={unc_metrics['win_rate']:.3%}, uncorr={s1_metrics['win_rate']:.3%}, delta={s1_delta:+.3%}")

# S2: Alt path
alt_overrides = {}
for g in games:
    if g['round'] == 'E8':
        hi, lo = g['hi'], g['lo']
        if hi in path_dep_teams or lo in path_dep_teams:
            hi_r4a = float(prob_data[hi].get('r4_adjusted_alt', prob_data[hi]['r4_adjusted']))
            lo_r4a = float(prob_data[lo].get('r4_adjusted_alt', prob_data[lo]['r4_adjusted']))
            total = hi_r4a + lo_r4a
            alt_overrides[g['mid']] = hi_r4a / total if total > 0 else 0.5
s2_metrics, _ = run_sim('S2: Alt Path', unc_bracket, game_overrides=alt_overrides)
s2_delta = unc_metrics['win_rate'] - s2_metrics['win_rate']
print(f"  S2 Path Dep: baseline={unc_metrics['win_rate']:.3%}, alt={s2_metrics['win_rate']:.3%}, delta={s2_delta:+.3%}")
if abs(s2_delta) > 0.03: print(f"  *** MATERIAL: delta exceeds 3pp")

# S3: Single-source bounds
def make_conf_overrides(bound):
    ov = {}
    for g in games:
        hi, lo, rd = g['hi'], g['lo'], g['round']
        tier_col = {'R64': 'confidence_tier_r1', 'R32': 'confidence_tier_r2',
                    'S16': 'confidence_tier_r3', 'E8': 'confidence_tier_r4'}.get(rd)
        if tier_col:
            if prob_data[hi].get(tier_col, 'HIGH') == 'LOW' or prob_data[lo].get(tier_col, 'HIGH') == 'LOW':
                if bound == 'low': ov[g['mid']] = max(0.35, g['vp'] - 0.05)
                else: ov[g['mid']] = min(0.95, g['vp'] + 0.05)
    return ov

s3_lo_metrics, _ = run_sim('S3: Conf LOW', unc_bracket, game_overrides=make_conf_overrides('low'))
s3_hi_metrics, _ = run_sim('S3: Conf HIGH', unc_bracket, game_overrides=make_conf_overrides('high'))
s3_range = abs(s3_hi_metrics['win_rate'] - s3_lo_metrics['win_rate'])
print(f"  S3 Single-Source: low={s3_lo_metrics['win_rate']:.3%}, high={s3_hi_metrics['win_rate']:.3%}, range={s3_range:.3%}")
if s3_range > 0.03: print(f"  *** MATERIAL: range exceeds 3pp")

# S4: Scenario dependency (FIXED path-dep flag)
print(f"\n  S4 Scenario Dependency:")

# FIXED: path-dep flag fires ONLY when a path-dependent team wins their E8
# game AND our bracket picked the other team for that E8.
e8_mids = ['E_E8', 'S_E8', 'W_E8', 'MW_E8']
sorted_details = sorted(unc_details, key=lambda d: (d['rank'], -d['our_score']))
best_10 = sorted_details[:10]
worst_10 = sorted_details[-10:]

def describe_scenario_fixed(detail, bracket):
    actual = detail['actual']
    hits = [f"{mid}={actual[mid]}" for mid in ['E_E8', 'S_E8', 'W_E8', 'MW_E8', 'F4_1', 'F4_2', 'NCG']
            if bracket.get(mid) == actual.get(mid)]
    # FIXED: only flag path-dep teams at E8 level where bracket disagrees
    path_dep_flags = []
    for e8_mid in e8_mids:
        winner = actual.get(e8_mid, '')
        if winner in path_dep_teams and bracket.get(e8_mid) != winner:
            path_dep_flags.append(f"{winner} wins {e8_mid}")
    return actual.get('NCG', '?'), hits, path_dep_flags

print(f"\n  TOP 10 SCENARIOS:")
print(f"  {'Rank':>4} {'Score':>6} {'Champ':<16} {'Late-round Hits':<44} {'Path-Dep E8 Flags'}")
print("  " + "-" * 100)
for d in best_10:
    champ, hits, pdflags = describe_scenario_fixed(d, unc_bracket)
    print(f"  {d['rank']:>4} {d['our_score']:>6} {champ:<16} {', '.join(hits[-4:]):<44} {'; '.join(pdflags) if pdflags else 'none'}")

print(f"\n  BOTTOM 10 SCENARIOS:")
print(f"  {'Rank':>4} {'Score':>6} {'Champ':<16} {'Late-round Hits':<44} {'Path-Dep E8 Flags'}")
print("  " + "-" * 100)
for d in worst_10:
    champ, hits, pdflags = describe_scenario_fixed(d, unc_bracket)
    print(f"  {d['rank']:>4} {d['our_score']:>6} {champ:<16} {', '.join(hits[-4:]):<44} {'; '.join(pdflags) if pdflags else 'none'}")

# Fixed path-dep rate
path_dep_e8_count = 0
for d in unc_details:
    actual = d['actual']
    for e8_mid in e8_mids:
        winner = actual.get(e8_mid, '')
        if winner in path_dep_teams and unc_bracket.get(e8_mid) != winner:
            path_dep_e8_count += 1
            break
print(f"\n  Path-dep E8 contrary to bracket in {path_dep_e8_count}/{N_SIMS} sims ({path_dep_e8_count/N_SIMS:.1%})")

# ============================================================
# SENSITIVITY 5 — UPSET COUNT SWEEP
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY 5 — UPSET COUNT SWEEP (0-10 upsets)")
print("=" * 90)

# For each upset count k: build bracket with exactly k upsets
# Select highest-leverage upsets first (lr > 1.25 AND vegas > 0.35)
# that are not constrained away by sign-flip/Type C

# Build ranked list of eligible upset picks
eligible_upsets = []
for rd in ['R64', 'R32', 'S16', 'E8']:
    for m in [v for v in espn.values() if v['round'] == rd]:
        mid = m['matchup_id']
        chalk = get_chalk(m)
        underdog = get_underdog(m)
        ud_lev = lev_data.get((underdog, rd), {})
        if not ud_lev: continue
        lr = float(ud_lev.get('leverage_ratio', 0))
        vegas = float(ud_lev.get('vegas_prob', 0))
        abs_lev = abs(float(ud_lev.get('leverage', 0)))
        sf = (underdog, rd) in sign_flip_teams
        conf = ud_lev.get('confidence_type', 'NA')
        lo = float(ud_lev.get('leverage_low', '0'))
        hi = float(ud_lev.get('leverage_high', '0'))

        # Must pass basic thresholds and not be blocked
        if sf: continue
        if conf == 'C' and (lo <= 0 or hi <= 0): continue
        if not (abs_lev > 0.10 and lr > 1.25 and vegas > 0.35): continue

        # Must not conflict with champion path
        region = m['region']
        e8_mid_for_region = {'East': 'E_E8', 'South': 'S_E8', 'West': 'W_E8', 'Midwest': 'MW_E8'}.get(region, '')
        # Skip if this would upset the champion's path
        if rd == 'E8' and region == champ_region: continue

        eligible_upsets.append({
            'mid': mid, 'round': rd, 'underdog': underdog, 'chalk': chalk,
            'lr': lr, 'vegas': vegas, 'region': region,
        })

# Sort by leverage_ratio descending
eligible_upsets.sort(key=lambda x: -x['lr'])
print(f"\n  Eligible upsets (passing all thresholds): {len(eligible_upsets)}")
for u in eligible_upsets:
    print(f"    {u['round']:<4} {u['mid']:<12} {u['underdog']:<18} lr={u['lr']:.4f} vegas={u['vegas']:.4f}")

# Build bracket for given upset count
def build_sweep_bracket(target_upsets):
    """Build bracket with exactly target_upsets from the eligible list."""
    upset_picks = set()
    for u in eligible_upsets[:target_upsets]:
        upset_picks.add(u['mid'])

    # Start from chalk, then apply upsets and propagate
    bracket = {}
    # E8
    for mid, m in sorted(e8_matchups.items()):
        region = m['region']
        if region == champ_region:
            bracket[mid] = champ_name
        elif mid in upset_picks:
            bracket[mid] = get_underdog(m)
        else:
            bracket[mid] = get_chalk(m)

    f4p = {m['region']: bracket[m['matchup_id']] for mid, m in e8_matchups.items()}

    # S16
    for mid, m in sorted(s16_matchups.items()):
        region = m['region']
        e8_mid = {'East': 'E_E8', 'South': 'S_E8', 'West': 'W_E8', 'Midwest': 'MW_E8'}[region]
        e8_pick = bracket.get(e8_mid, '')
        if e8_pick in (m['team_1_name'], m['team_2_name']):
            bracket[mid] = e8_pick
        elif mid in upset_picks:
            bracket[mid] = get_underdog(m)
        else:
            bracket[mid] = get_chalk(m)

    # R32
    for mid, m in sorted(r32_matchups.items()):
        rp = mid.split('_R32_')[0]
        rn = int(mid.split('_R32_')[1])
        s16_mid = f"{rp}_S16_{(rn + 1) // 2}"
        s16_pick = bracket.get(s16_mid, '')
        if s16_pick in (m['team_1_name'], m['team_2_name']):
            bracket[mid] = s16_pick
        elif mid in upset_picks:
            bracket[mid] = get_underdog(m)
        else:
            bracket[mid] = get_chalk(m)

    # R64
    for mid, m in sorted(r64_matchups.items()):
        rp = mid.split('_R64_')[0]
        rn = int(mid.split('_R64_')[1])
        r32_mid = f"{rp}_R32_{(rn + 1) // 2}"
        r32_pick = bracket.get(r32_mid, '')
        if r32_pick in (m['team_1_name'], m['team_2_name']) and r32_pick != get_chalk(m):
            bracket[mid] = r32_pick
        elif mid in upset_picks:
            bracket[mid] = get_underdog(m)
        else:
            bracket[mid] = get_chalk(m)

    # F4/NCG
    east_f4 = bracket.get('E_E8', 'Duke'); south_f4 = bracket.get('S_E8', 'Florida')
    if champ_region in ('East', 'South'):
        bracket['F4_1'] = champ_name
    else:
        bracket['F4_1'] = east_f4 if float(prob_data[east_f4]['r5']) >= float(prob_data[south_f4]['r5']) else south_f4
    west_f4 = bracket.get('W_E8', 'Arizona'); mw_f4 = bracket.get('MW_E8', 'Michigan')
    if champ_region in ('West', 'Midwest'):
        bracket['F4_2'] = champ_name
    else:
        bracket['F4_2'] = west_f4 if float(prob_data[west_f4]['r5']) >= float(prob_data[mw_f4]['r5']) else mw_f4
    bracket['NCG'] = champ_name
    return bracket

# Run sweep
N_SWEEP_SIMS = 20000  # reduced for sweep speed
sweep_results = []

print(f"\n  Running upset count sweep (0-10, {N_SWEEP_SIMS} sims each)...")
for k in range(min(11, len(eligible_upsets) + 1)):
    bkt = build_sweep_bracket(k)
    metrics, _ = run_sim(f'Sweep k={k}', bkt, n_sims=N_SWEEP_SIMS)
    sweep_results.append((k, metrics['win_rate'], metrics['top10_rate'], metrics['avg_score']))

# Also run chalk reference at same sim count for fair comparison
chalk_sweep, _ = run_sim('Sweep chalk ref', chalk_bracket, n_sims=N_SWEEP_SIMS)
chalk_wr_ref = chalk_sweep['win_rate']

print(f"\n  UPSET COUNT SWEEP RESULTS:")
print(f"  {'Upsets':>7} {'Win Rate':>10} {'vs Chalk':>10} {'Top 10%':>10} {'Avg Score':>10} {'Bar'}")
print("  " + "-" * 70)
for k, wr, t10, avg in sweep_results:
    vs_chalk = wr - chalk_wr_ref
    bar = '#' * int(wr * 1000)
    print(f"  {k:>7} {wr:>9.2%} {vs_chalk:>+9.2%} {t10:>9.2%} {avg:>9.1f}  {bar}")

print(f"\n  Chalk reference: {chalk_wr_ref:.2%}")

# Find optimal
best_k, best_wr = max(sweep_results, key=lambda x: x[1])[:2]
print(f"  Optimal upset count: {best_k} ({best_wr:.2%})")
print(f"  vs Chalk: {best_wr - chalk_wr_ref:+.2%}")

# ============================================================
# SENSITIVITY DELTA TABLE
# ============================================================
print("\n" + "=" * 90)
print("SENSITIVITY DELTA TABLE (unconstrained bracket)")
print("=" * 90)

baseline_wr = unc_metrics['win_rate']
print(f"\n{'Sensitivity':<35} {'Win Rate':>10} {'Delta':>10} {'Flag'}")
print("-" * 70)
for label, wr in [('Baseline (Unconstrained)', baseline_wr),
                   ('S1: E8 Uncorrected', s1_metrics['win_rate']),
                   ('S2: Alt Path', s2_metrics['win_rate']),
                   ('S3: Conf LOW bound', s3_lo_metrics['win_rate']),
                   ('S3: Conf HIGH bound', s3_hi_metrics['win_rate'])]:
    delta = wr - baseline_wr
    flag = '*** >3pp' if abs(delta) > 0.03 else ''
    print(f"  {label:<33} {wr:>9.3%} {delta:>+9.3%} {flag}")

# ============================================================
# OUTPUT CSV
# ============================================================
csv_rows = []
for m in [unc_metrics, p8_metrics, chalk_metrics]:
    csv_rows.append({
        'bracket_type': m['label'], 'sensitivity': 'baseline',
        'win_rate': f"{m['win_rate']:.6f}", 'top10_rate': f"{m['top10_rate']:.6f}",
        'avg_score': f"{m['avg_score']:.2f}", 'avg_rank_percentile': f"{m['avg_rank_pct']:.4f}",
        'upset_count': '', 'vs_chalk_wr': '',
    })
for label, wr in [('S1: E8 Uncorrected', s1_metrics['win_rate']),
                   ('S2: Alt Path', s2_metrics['win_rate']),
                   ('S3: Conf LOW', s3_lo_metrics['win_rate']),
                   ('S3: Conf HIGH', s3_hi_metrics['win_rate'])]:
    csv_rows.append({
        'bracket_type': 'Unconstrained', 'sensitivity': label,
        'win_rate': f"{wr:.6f}", 'top10_rate': '', 'avg_score': '',
        'avg_rank_percentile': '', 'upset_count': '', 'vs_chalk_wr': '',
    })
for k, wr, t10, avg in sweep_results:
    csv_rows.append({
        'bracket_type': f'Sweep_{k}_upsets', 'sensitivity': 'upset_sweep',
        'win_rate': f"{wr:.6f}", 'top10_rate': f"{t10:.6f}",
        'avg_score': f"{avg:.2f}", 'avg_rank_percentile': '',
        'upset_count': str(k), 'vs_chalk_wr': f"{wr - chalk_wr_ref:.6f}",
    })

fields = ['bracket_type', 'sensitivity', 'win_rate', 'top10_rate', 'avg_score',
          'avg_rank_percentile', 'upset_count', 'vs_chalk_wr']
with open('stress_test_unconstrained_2026.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for row in csv_rows:
        w.writerow(row)
print(f"\nWrote stress_test_unconstrained_2026.csv")

print("\n" + "=" * 90)
print("9B COMPLETE")
print("=" * 90)
