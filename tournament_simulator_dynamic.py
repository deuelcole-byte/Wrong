#!/usr/bin/env python3
"""
tournament_simulator_dynamic.py

Dynamic tournament simulation engine that propagates winners round-by-round.
Fixes the dead-pick bug where the old fixed-matchup engine could never produce
non-chalk teams as later-round winners.

Usage as module:
    from tournament_simulator_dynamic import (
        simulate_tournament_dynamic, score_bracket_dynamic, load_data
    )
    load_data()
    outcome = simulate_tournament_dynamic()
    score = score_bracket_dynamic(my_bracket, outcome)
"""

import csv
import sys
import numpy as np
from collections import defaultdict

# ============================================================
# MODULE STATE
# ============================================================
prob_data = {}
espn = {}
lev_data = {}
ncg_dist = {}
_initialized = False

REGION_PREFIXES = ['E', 'S', 'W', 'MW']
POINTS = {'R64': 10, 'R32': 20, 'S16': 40, 'E8': 80, 'F4': 160, 'NCG': 320}


def _flush(msg):
    print(msg, flush=True)


def _higher_seed_first(m):
    s1, s2 = int(m['team_1_seed']), int(m['team_2_seed'])
    if s1 <= s2:
        return m['team_1_name'], m['team_2_name']
    return m['team_2_name'], m['team_1_name']


# ============================================================
# DATA LOADING
# ============================================================
def load_data(verbose=False):
    global prob_data, espn, lev_data, ncg_dist, _initialized
    if _initialized:
        return

    with open('probability_baseline_final_2026.csv') as f:
        for row in csv.DictReader(f):
            prob_data[row['team_name']] = row
    if verbose:
        _flush(f"  Loaded probability_baseline_final_2026.csv ({len(prob_data)} teams)")

    with open('espn_picks_2026.csv') as f:
        for row in csv.DictReader(f):
            espn[row['matchup_id']] = row
    if verbose:
        _flush(f"  Loaded espn_picks_2026.csv ({len(espn)} matchups)")

    with open('leverage_matrix_2026.csv') as f:
        for row in csv.DictReader(f):
            lev_data[(row['team_name'], row['round'])] = row
    if verbose:
        _flush(f"  Loaded leverage_matrix_2026.csv ({len(lev_data)} entries)")

    with open('ncg_pick_distribution_2026.csv') as f:
        for row in csv.DictReader(f):
            ncg_dist[row['team_name']] = float(row['ncg_public_pick_pct']) / 100.0
    if verbose:
        _flush(f"  Loaded ncg_pick_distribution_2026.csv ({len(ncg_dist)} teams)")

    _initialized = True


# ============================================================
# WIN PROBABILITY
# ============================================================
def compute_win_prob(team_a, team_b, round_name):
    """P(team_a beats team_b) at the given round.

    R64: use r1 (game-level prob for higher seed).
    R32-NCG: normalize advancement probabilities between the two teams.
    """
    if round_name == 'R64':
        seed_a = int(prob_data[team_a]['team_seed'])
        seed_b = int(prob_data[team_b]['team_seed'])
        if seed_a < seed_b:
            return float(prob_data[team_a]['r1'])
        elif seed_b < seed_a:
            return 1.0 - float(prob_data[team_b]['r1'])
        return 0.5

    col = {'R32': 'r2', 'S16': 'r3', 'E8': 'r4_adjusted',
           'F4': 'r5', 'NCG': 'r6'}[round_name]
    pa = float(prob_data[team_a][col])
    pb = float(prob_data[team_b][col])
    total = pa + pb
    return pa / total if total > 0 else 0.5


# ============================================================
# DYNAMIC SIMULATION
# ============================================================
def simulate_tournament_dynamic():
    """Simulate one tournament, propagating winners round-by-round.

    Returns {matchup_id: winning_team} for all 63 games.
    """
    if not _initialized:
        load_data()

    result = {}

    # --- R64: fixed matchups from ESPN bracket ---
    for mid, m in espn.items():
        if m['round'] != 'R64':
            continue
        hi, lo = _higher_seed_first(m)
        vp = float(prob_data[hi]['r1'])
        result[mid] = hi if np.random.random() < vp else lo

    # --- R32: winners of paired R64 games ---
    for pfx in REGION_PREFIXES:
        for n in range(1, 5):
            ta = result[f'{pfx}_R64_{n * 2 - 1}']
            tb = result[f'{pfx}_R64_{n * 2}']
            vp = compute_win_prob(ta, tb, 'R32')
            result[f'{pfx}_R32_{n}'] = ta if np.random.random() < vp else tb

    # --- S16: winners of paired R32 games ---
    for pfx in REGION_PREFIXES:
        for n in range(1, 3):
            ta = result[f'{pfx}_R32_{n * 2 - 1}']
            tb = result[f'{pfx}_R32_{n * 2}']
            vp = compute_win_prob(ta, tb, 'S16')
            result[f'{pfx}_S16_{n}'] = ta if np.random.random() < vp else tb

    # --- E8: winners of paired S16 games ---
    for pfx in REGION_PREFIXES:
        ta = result[f'{pfx}_S16_1']
        tb = result[f'{pfx}_S16_2']
        vp = compute_win_prob(ta, tb, 'E8')
        result[f'{pfx}_E8'] = ta if np.random.random() < vp else tb

    # --- F4 ---
    ta, tb = result['E_E8'], result['S_E8']
    vp = compute_win_prob(ta, tb, 'F4')
    result['F4_1'] = ta if np.random.random() < vp else tb

    ta, tb = result['W_E8'], result['MW_E8']
    vp = compute_win_prob(ta, tb, 'F4')
    result['F4_2'] = ta if np.random.random() < vp else tb

    # --- NCG ---
    ta, tb = result['F4_1'], result['F4_2']
    vp = compute_win_prob(ta, tb, 'NCG')
    result['NCG'] = ta if np.random.random() < vp else tb

    return result


# ============================================================
# SCORING
# ============================================================
def score_bracket_dynamic(picks, actual):
    """Score a bracket against a dynamically simulated tournament outcome."""
    score = 0
    for mid, winner in actual.items():
        if mid in picks and picks[mid] == winner:
            if 'R64' in mid:           score += 10
            elif 'R32' in mid:         score += 20
            elif 'S16' in mid:         score += 40
            elif 'E8' in mid:          score += 80
            elif mid.startswith('F4'): score += 160
            elif mid == 'NCG':         score += 320
    return score


# ============================================================
# CHALK BRACKET
# ============================================================
def gen_chalk_bracket():
    """Pure chalk bracket — higher seed wins every game."""
    if not _initialized:
        load_data()
    picks = {}
    for mid, m in espn.items():
        if m['round'] in ('R64', 'R32', 'S16', 'E8'):
            hi, _ = _higher_seed_first(m)
            picks[mid] = hi
    ep, sp = picks['E_E8'], picks['S_E8']
    picks['F4_1'] = ep if float(prob_data[ep]['r5']) >= float(prob_data[sp]['r5']) else sp
    wp, mp = picks['W_E8'], picks['MW_E8']
    picks['F4_2'] = wp if float(prob_data[wp]['r5']) >= float(prob_data[mp]['r5']) else mp
    picks['NCG'] = (picks['F4_1']
                    if float(prob_data[picks['F4_1']]['r6']) >= float(prob_data[picks['F4_2']]['r6'])
                    else picks['F4_2'])
    return picks


# ============================================================
# TEAM PATH AND GENERATOR HELPERS
# ============================================================
def build_team_paths():
    """Map each team to their bracket path (R64 → R32 → S16 → E8)."""
    paths = {}
    for mid, m in espn.items():
        if m['round'] != 'R64':
            continue
        prefix = mid.split('_R64_')[0]
        r64_num = int(mid.split('_R64_')[1])
        r32_num = (r64_num + 1) // 2
        s16_num = (r32_num + 1) // 2
        for tk in ('team_1_name', 'team_2_name'):
            paths[m[tk]] = {
                'R64': mid,
                'R32': f'{prefix}_R32_{r32_num}',
                'S16': f'{prefix}_S16_{s16_num}',
                'E8': f'{prefix}_E8',
                'prefix': prefix,
                's16_side': s16_num,
                'region': m['region'],
            }
    return paths


def build_espn_pcts():
    """ESPN pick percentages for each matchup: {mid: {hi, lo, pub_hi}}."""
    pcts = {}
    for mid, m in espn.items():
        if m['round'] in ('NCG_CHAMP', 'F4', 'NCG'):
            continue
        hi, lo = _higher_seed_first(m)
        pub_hi = (float(m['team_1_pick_pct']) / 100.0
                  if m['team_1_name'] == hi
                  else float(m['team_2_pick_pct']) / 100.0)
        pcts[mid] = {'hi': hi, 'lo': lo, 'pub_hi': pub_hi}
    return pcts


def build_f4_distributions():
    """Per-region F4 probability distributions from leverage matrix."""
    f4_raw = defaultdict(lambda: {'teams': [], 'pcts': []})
    for (team, rd), entry in lev_data.items():
        if rd == 'F4':
            f4_raw[entry['region']]['teams'].append(team)
            f4_raw[entry['region']]['pcts'].append(float(entry['public_pick_pct']))
    f4d = {}
    for region, data in f4_raw.items():
        pcts = np.array(data['pcts'])
        f4d[region] = {'teams': data['teams'], 'probs': pcts / pcts.sum()}
    return f4d


def build_champion_distribution():
    """Champion sampling arrays from NCG pick distribution."""
    teams, probs = [], []
    for team, pct in ncg_dist.items():
        if pct > 0:
            teams.append(team)
            probs.append(pct)
    probs = np.array(probs)
    return teams, probs / probs.sum()
