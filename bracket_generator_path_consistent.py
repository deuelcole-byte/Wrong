#!/usr/bin/env python3
"""
bracket_generator_path_consistent.py

Path-consistent opponent bracket generator.  Anchors every opponent bracket
to a sampled champion so the simulated field clusters the way real pools do
(~29 % Duke, ~22 % Arizona, etc.).

Usage as module:
    from bracket_generator_path_consistent import generate_opponent_bracket
    bracket = generate_opponent_bracket()   # {matchup_id: team_picked}

Usage standalone (runs full validation):
    python bracket_generator_path_consistent.py
"""

import csv
import sys
import time
import numpy as np
from collections import defaultdict

# ============================================================
# MODULE-LEVEL STATE  (loaded lazily on first generate call)
# ============================================================
prob_data = {}
espn = {}
lev_data = {}
ncg_dist = {}
games = []
team_paths = {}
f4_dist = {}
champ_teams = []
champ_probs = None
team_region = {}
_initialized = False


def _flush(msg):
    print(msg, flush=True)


# ============================================================
# DATA LOADING
# ============================================================
def _load_data(verbose=False):
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

    _build_helpers(verbose)
    _initialized = True


def _higher_seed_first(m):
    s1, s2 = int(m['team_1_seed']), int(m['team_2_seed'])
    if s1 <= s2:
        return m['team_1_name'], m['team_2_name'], s1, s2
    return m['team_2_name'], m['team_1_name'], s2, s1


def _build_helpers(verbose=False):
    global games, team_paths, f4_dist, champ_teams, champ_probs, team_region

    # Region lookup
    team_region.update({t: d['region'] for t, d in prob_data.items()})

    # Game list — matches stress_test_9b.py exactly
    games.clear()
    for rd in ['R64', 'R32', 'S16', 'E8']:
        for m in [v for v in espn.values() if v['round'] == rd]:
            hi, lo, _, _ = _higher_seed_first(m)
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
            pub_hi = (float(m['team_1_pick_pct']) / 100.0
                      if m['team_1_name'] == hi
                      else float(m['team_2_pick_pct']) / 100.0)
            games.append({
                'round': rd, 'hi': hi, 'lo': lo,
                'mid': mid, 'vp': vp, 'pub_hi': pub_hi,
            })

    # Team-to-path mapping  (R64 → R32 → S16 → E8)
    team_paths.clear()
    for mid, m in espn.items():
        if m['round'] != 'R64':
            continue
        prefix = mid.split('_R64_')[0]
        r64_num = int(mid.split('_R64_')[1])
        r32_num = (r64_num + 1) // 2
        s16_num = (r32_num + 1) // 2
        for tk in ('team_1_name', 'team_2_name'):
            team_paths[m[tk]] = {
                'R64': mid,
                'R32': f'{prefix}_R32_{r32_num}',
                'S16': f'{prefix}_S16_{s16_num}',
                'E8':  f'{prefix}_E8',
                's16_side': s16_num,
                'region': m['region'],
            }
    if verbose:
        _flush(f"  Built team paths for {len(team_paths)} teams")

    # Per-region F4 distributions from leverage matrix
    f4_raw = defaultdict(lambda: {'teams': [], 'pcts': []})
    for (team, rd), entry in lev_data.items():
        if rd == 'F4':
            f4_raw[entry['region']]['teams'].append(team)
            f4_raw[entry['region']]['pcts'].append(float(entry['public_pick_pct']))
    f4_dist.clear()
    for region, data in f4_raw.items():
        pcts = np.array(data['pcts'])
        f4_dist[region] = {'teams': data['teams'], 'probs': pcts / pcts.sum()}
    if verbose:
        for r in ['East', 'South', 'West', 'Midwest']:
            top = sorted(zip(f4_dist[r]['teams'], f4_dist[r]['probs']),
                         key=lambda x: -x[1])[:3]
            _flush(f"    F4 dist {r}: {', '.join(f'{t} {p:.1%}' for t, p in top)}")

    # Champion sampling arrays
    champ_teams.clear()
    ct_probs = []
    for team, pct in ncg_dist.items():
        if pct > 0:
            champ_teams.append(team)
            ct_probs.append(pct)
    champ_probs = np.array(ct_probs)
    champ_probs /= champ_probs.sum()
    if verbose:
        _flush(f"  Champion pool: {len(champ_teams)} teams")


# ============================================================
# PATH-CONSISTENT GENERATOR  (primary export)
# ============================================================
def generate_opponent_bracket():
    """Return one path-consistent opponent bracket.

    Returns
    -------
    dict  {matchup_id: team_picked}  — 63 entries covering R64–NCG.
    """
    if not _initialized:
        _load_data()

    picks = {}

    # --- Step 1: sample champion ---
    idx = np.random.choice(len(champ_teams), p=champ_probs)
    champion = champ_teams[idx]
    champ_rgn = team_region[champion]

    # --- Step 2: sample F4 team per region ---
    f4_teams = {}
    for region in ('East', 'South', 'West', 'Midwest'):
        if region == champ_rgn:
            f4_teams[region] = champion
        else:
            d = f4_dist[region]
            f4_teams[region] = d['teams'][np.random.choice(len(d['teams']),
                                                            p=d['probs'])]

    # --- Steps 3-4: force E8, S16, and champion R32/R64 ---
    for region in ('East', 'South', 'West', 'Midwest'):
        f4t = f4_teams[region]
        path = team_paths[f4t]

        # Force E8 and S16 on this team's side
        picks[path['E8']]  = f4t
        picks[path['S16']] = f4t

        # Champion also forced at R32 and R64
        if f4t == champion:
            picks[path['R32']] = f4t
            picks[path['R64']] = f4t

        # Sample the *other* S16 game in this region
        prefix = path['E8'].split('_E8')[0]
        other_side = 3 - path['s16_side']
        other_mid  = f'{prefix}_S16_{other_side}'
        if other_mid not in picks and other_mid in espn:
            m = espn[other_mid]
            p1 = float(m['team_1_pick_pct']) / 100.0
            picks[other_mid] = (m['team_1_name']
                                if np.random.random() < p1
                                else m['team_2_name'])

    # --- Step 5: sample remaining R32 / R64 independently ---
    for g in games:
        if g['mid'] not in picks and g['round'] in ('R32', 'R64'):
            picks[g['mid']] = (g['hi']
                               if np.random.random() < g['pub_hi']
                               else g['lo'])

    # --- F4 games ---
    east_f4,  south_f4 = f4_teams['East'],  f4_teams['South']
    west_f4,  mw_f4    = f4_teams['West'],  f4_teams['Midwest']

    if champ_rgn in ('East', 'South'):
        picks['F4_1'] = champion
    else:
        ep = float(lev_data.get((east_f4, 'F4'), {}).get('public_pick_pct', 0.001))
        sp = float(lev_data.get((south_f4, 'F4'), {}).get('public_pick_pct', 0.001))
        picks['F4_1'] = east_f4 if np.random.random() < ep / (ep + sp) else south_f4

    if champ_rgn in ('West', 'Midwest'):
        picks['F4_2'] = champion
    else:
        wp = float(lev_data.get((west_f4, 'F4'), {}).get('public_pick_pct', 0.001))
        mp = float(lev_data.get((mw_f4, 'F4'), {}).get('public_pick_pct', 0.001))
        picks['F4_2'] = west_f4 if np.random.random() < wp / (wp + mp) else mw_f4

    # --- NCG: champion wins ---
    picks['NCG'] = champion
    return picks


# ============================================================
# INDEPENDENT GENERATOR  (baseline comparison)
# ============================================================
def generate_opponent_bracket_independent():
    """Return one independent opponent bracket (no champion anchor).

    Matches gen_opponent_bracket() in stress_test_9b.py exactly.
    """
    if not _initialized:
        _load_data()

    picks = {}
    for g in games:
        picks[g['mid']] = g['hi'] if np.random.random() < g['pub_hi'] else g['lo']

    ep = picks.get('E_E8', 'Duke')
    sp = picks.get('S_E8', 'Florida')
    f4e = float(lev_data.get((ep, 'F4'), {}).get('public_pick_pct', 0.5))
    f4s = float(lev_data.get((sp, 'F4'), {}).get('public_pick_pct', 0.5))
    t = f4e + f4s
    picks['F4_1'] = ep if np.random.random() < (f4e / t if t > 0 else 0.5) else sp

    wp = picks.get('W_E8', 'Arizona')
    mp = picks.get('MW_E8', 'Michigan')
    f4w = float(lev_data.get((wp, 'F4'), {}).get('public_pick_pct', 0.5))
    f4m = float(lev_data.get((mp, 'F4'), {}).get('public_pick_pct', 0.5))
    t = f4w + f4m
    picks['F4_2'] = wp if np.random.random() < (f4w / t if t > 0 else 0.5) else mp

    n1 = ncg_dist.get(picks['F4_1'], 0.001)
    n2 = ncg_dist.get(picks['F4_2'], 0.001)
    t = n1 + n2
    picks['NCG'] = picks['F4_1'] if np.random.random() < (n1 / t if t > 0 else 0.5) else picks['F4_2']
    return picks


# ============================================================
# SCORING / SIMULATION HELPERS
# ============================================================
def score_bracket(picks, actual):
    score = 0
    for mid, winner in actual.items():
        if mid in picks and picks[mid] == winner:
            if 'R64' in mid:        score += 10
            elif 'R32' in mid:      score += 20
            elif 'S16' in mid:      score += 40
            elif 'E8' in mid:       score += 80
            elif mid.startswith('F4'): score += 160
            elif mid == 'NCG':      score += 320
    return score


def _f4_game_prob(t1, t2):
    r1 = float(prob_data[t1]['r5'])
    r2 = float(prob_data[t2]['r5'])
    return r1 / (r1 + r2) if (r1 + r2) > 0 else 0.5


def sim_tournament():
    """Simulate one tournament outcome using Vegas probabilities."""
    result = {}
    for g in games:
        result[g['mid']] = g['hi'] if np.random.random() < g['vp'] else g['lo']
    ew, sw = result.get('E_E8', 'Duke'), result.get('S_E8', 'Florida')
    ww, mw = result.get('W_E8', 'Arizona'), result.get('MW_E8', 'Michigan')
    p1 = _f4_game_prob(ew, sw)
    result['F4_1'] = ew if np.random.random() < p1 else sw
    p2 = _f4_game_prob(ww, mw)
    result['F4_2'] = ww if np.random.random() < p2 else mw
    pn = _f4_game_prob(result['F4_1'], result['F4_2'])
    result['NCG'] = result['F4_1'] if np.random.random() < pn else result['F4_2']
    return result


def gen_chalk_bracket():
    """Pure chalk bracket — higher seed wins every game."""
    if not _initialized:
        _load_data()
    picks = {}
    for g in games:
        picks[g['mid']] = g['hi']
    ep, sp = picks.get('E_E8', 'Duke'), picks.get('S_E8', 'Florida')
    picks['F4_1'] = ep if float(prob_data[ep]['r5']) >= float(prob_data[sp]['r5']) else sp
    wp, mp = picks.get('W_E8', 'Arizona'), picks.get('MW_E8', 'Michigan')
    picks['F4_2'] = wp if float(prob_data[wp]['r5']) >= float(prob_data[mp]['r5']) else mp
    picks['NCG'] = (picks['F4_1']
                    if float(prob_data[picks['F4_1']]['r6']) >= float(prob_data[picks['F4_2']]['r6'])
                    else picks['F4_2'])
    return picks


# ============================================================
# VALIDATION  (runs when executed directly)
# ============================================================
if __name__ == '__main__':
    np.random.seed(42)
    t0 = time.time()

    # ==================================================================
    # STEP 1 — BUILD GENERATOR
    # ==================================================================
    _flush("\n" + "=" * 80)
    _flush("STEP 1 — LOAD DATA AND BUILD GENERATOR")
    _flush("=" * 80)

    _load_data(verbose=True)
    chalk_bracket = gen_chalk_bracket()
    chalk_champ = chalk_bracket['NCG']
    _flush(f"  Chalk bracket champion: {chalk_champ}")
    _flush(f"  Total games in game list: {len(games)}")
    _flush(f"  Total team paths built: {len(team_paths)}")

    # Quick smoke test: generate one bracket
    b = generate_opponent_bracket()
    _flush(f"  Smoke test: generated bracket with {len(b)} picks, champion = {b['NCG']}")
    _flush(f"\nStep 1 complete: generate_opponent_bracket() function built  "
           f"({time.time()-t0:.1f}s)")

    # ==================================================================
    # STEP 2 — COHERENCE VALIDATION  (100 brackets)
    # ==================================================================
    _flush("\n" + "=" * 80)
    _flush("STEP 2 — COHERENCE VALIDATION (100 brackets)")
    _flush("=" * 80)

    N_COH = 100
    check1_pass = 0
    check2_pass = 0
    failures = []

    for i in range(N_COH):
        b = generate_opponent_bracket()
        champion = b['NCG']
        path = team_paths[champion]
        champ_rgn = team_region[champion]

        # Check 1: champion at every round in their path
        ok1 = True
        for rk in ('R64', 'R32', 'S16', 'E8'):
            if b.get(path[rk]) != champion:
                ok1 = False
                failures.append(f"Bracket {i}: {champion} missing at {rk} "
                                f"({path[rk]}={b.get(path[rk])})")
                break
        # F4
        if champ_rgn in ('East', 'South'):
            if b.get('F4_1') != champion:
                ok1 = False
                failures.append(f"Bracket {i}: {champion} missing at F4_1")
        else:
            if b.get('F4_2') != champion:
                ok1 = False
                failures.append(f"Bracket {i}: {champion} missing at F4_2")
        if ok1:
            check1_pass += 1

        # Check 2: each region has exactly one F4 rep from correct region
        ok2 = True
        for region in ('East', 'South', 'West', 'Midwest'):
            prefix = {'East': 'E', 'South': 'S', 'West': 'W', 'Midwest': 'MW'}[region]
            e8_mid = f'{prefix}_E8'
            winner = b.get(e8_mid)
            if winner is None or team_region.get(winner) != region:
                ok2 = False
                failures.append(f"Bracket {i}: {region} E8 winner "
                                f"'{winner}' not from {region}")
                break
        if ok2:
            check2_pass += 1

    _flush(f"  Check 1 — Champion path consistency: {check1_pass}/{N_COH}")
    _flush(f"  Check 2 — F4 regional consistency:   {check2_pass}/{N_COH}")
    if failures:
        _flush(f"  FAILURES ({len(failures)}):")
        for f_msg in failures[:10]:
            _flush(f"    {f_msg}")

    coherence_ok = (check1_pass == N_COH and check2_pass == N_COH)
    if not coherence_ok:
        _flush("  *** HARD STOP: coherence < 100%.  Fix generator before proceeding.")
        sys.exit(1)

    _flush(f"\nStep 2 complete: coherence rate {check1_pass}/{N_COH} "
           f"({time.time()-t0:.1f}s)")

    # ==================================================================
    # STEP 3 — DISTRIBUTION ALIGNMENT  (1,000 brackets)
    # ==================================================================
    _flush("\n" + "=" * 80)
    _flush("STEP 3 — DISTRIBUTION ALIGNMENT (1,000 brackets)")
    _flush("=" * 80)

    N_DIST = 1000
    dist_counts = defaultdict(int)
    for _ in range(N_DIST):
        b = generate_opponent_bracket()
        dist_counts[b['NCG']] += 1

    # Top 5 by target pick pct
    top5_teams = sorted(ncg_dist.keys(), key=lambda t: -ncg_dist[t])[:5]
    dist_ok = True
    _flush(f"\n  {'Team':<18} {'Target':>8} {'Observed':>10} {'Delta':>8} {'OK':>4}")
    _flush("  " + "-" * 52)
    for team in top5_teams:
        target = ncg_dist[team]
        obs = dist_counts.get(team, 0) / N_DIST
        delta = obs - target
        ok = abs(delta) <= 0.03
        if not ok:
            dist_ok = False
        _flush(f"  {team:<18} {target:>7.2%} {obs:>9.2%} {delta:>+7.2%} "
               f"{'Y' if ok else 'N':>4}")

    _flush(f"\n  Distribution alignment: {'PASS' if dist_ok else 'FAIL'} "
           f"(all top-5 within 3pp)")
    _flush(f"\nStep 3 complete: distribution alignment check done  "
           f"({time.time()-t0:.1f}s)")

    # ==================================================================
    # STEP 4 — CONCENTRATION COMPARISON AND DECISION GATE
    # ==================================================================
    _flush("\n" + "=" * 80)
    _flush("STEP 4 — CONCENTRATION COMPARISON AND DECISION GATE")
    _flush("=" * 80)

    N_CONC = 1000

    # --- Generate bracket sets ---
    _flush(f"\n  Generating {N_CONC} path-consistent brackets...")
    pc_brackets = [generate_opponent_bracket() for _ in range(N_CONC)]
    pc_champ = defaultdict(int)
    for b in pc_brackets:
        pc_champ[b['NCG']] += 1

    _flush(f"  Generating {N_CONC} independent brackets...")
    ind_brackets = [generate_opponent_bracket_independent() for _ in range(N_CONC)]
    ind_champ = defaultdict(int)
    for b in ind_brackets:
        ind_champ[b['NCG']] += 1

    # --- Metric A: score variance ---
    _flush(f"\n  Metric A — Score variance")
    # Score each set against 50 tournament draws for stable variance
    N_TOURNEY_A = 50
    pc_scores = []
    ind_scores = []
    for _ in range(N_TOURNEY_A):
        actual = sim_tournament()
        for b in pc_brackets:
            pc_scores.append(score_bracket(b, actual))
        for b in ind_brackets:
            ind_scores.append(score_bracket(b, actual))

    pc_var  = float(np.var(pc_scores))
    ind_var = float(np.var(ind_scores))
    _flush(f"    Path-consistent score variance: {pc_var:,.1f}")
    _flush(f"    Independent score variance:     {ind_var:,.1f}")
    _flush(f"    Ratio (PC / Ind):               {pc_var / ind_var:.3f}")

    # --- Metric B: champion co-occurrence ---
    _flush(f"\n  Metric B — Champion co-occurrence")
    _flush(f"    {'Team':<18} {'NCG Dist':>9} {'PC Obs':>9} {'Ind Obs':>9}")
    _flush("    " + "-" * 47)
    for team in top5_teams:
        tgt = ncg_dist[team]
        pc_obs  = pc_champ.get(team, 0)  / N_CONC
        ind_obs = ind_champ.get(team, 0) / N_CONC
        _flush(f"    {team:<18} {tgt:>8.2%} {pc_obs:>8.2%} {ind_obs:>8.2%}")

    # --- Metric C: chalk win rate test (PRIMARY DECISION GATE) ---
    _flush(f"\n  Metric C — Chalk win rate test  (PRIMARY DECISION GATE)")
    N_SIMS_C   = 2000
    POOL_SIZE   = 100
    N_OPP       = POOL_SIZE - 1

    _flush(f"    Simulating {N_SIMS_C} tournaments, {N_OPP} opponents each, "
           f"both methods...")

    # Pre-generate tournament outcomes for paired comparison
    _flush(f"    Pre-generating {N_SIMS_C} tournament outcomes...", )
    tourney_outcomes = [sim_tournament() for _ in range(N_SIMS_C)]

    # Path-consistent opponents
    _flush(f"    Scoring chalk vs path-consistent opponents...", )
    pc_wins = 0
    for si, actual in enumerate(tourney_outcomes):
        our = score_bracket(chalk_bracket, actual)
        opp = [score_bracket(generate_opponent_bracket(), actual) for _ in range(N_OPP)]
        rank = 1 + sum(1 for s in opp if s > our)
        if rank == 1:
            pc_wins += 1
        if (si + 1) % 500 == 0:
            _flush(f"      ...{si+1}/{N_SIMS_C}")
    pc_chalk_wr = pc_wins / N_SIMS_C

    # Independent opponents
    _flush(f"    Scoring chalk vs independent opponents...", )
    ind_wins = 0
    for si, actual in enumerate(tourney_outcomes):
        our = score_bracket(chalk_bracket, actual)
        opp = [score_bracket(generate_opponent_bracket_independent(), actual)
               for _ in range(N_OPP)]
        rank = 1 + sum(1 for s in opp if s > our)
        if rank == 1:
            ind_wins += 1
        if (si + 1) % 500 == 0:
            _flush(f"      ...{si+1}/{N_SIMS_C}")
    ind_chalk_wr = ind_wins / N_SIMS_C

    delta_wr = ind_chalk_wr - pc_chalk_wr
    delta_pp = delta_wr * 100

    _flush(f"\n  {'='*60}")
    _flush(f"  METRIC C RESULTS — PRIMARY DECISION GATE")
    _flush(f"  {'='*60}")
    _flush(f"    Chalk P(rank 1) vs independent opponents:      {ind_chalk_wr:.3%}")
    _flush(f"    Chalk P(rank 1) vs path-consistent opponents:  {pc_chalk_wr:.3%}")
    _flush(f"    Delta (ind - PC):  {delta_wr:+.3%}  ({delta_pp:+.2f}pp)")
    _flush(f"  {'='*60}")

    if delta_wr > 0.005:
        decision = "PROCEED TO 7d"
        decision_reason = (f"Delta {delta_pp:+.2f}pp > 0.5pp — independent sampling "
                           f"artifact CONFIRMED.  Path-consistent sampling mandatory.")
    else:
        decision = "USE EXISTING 9B RESULTS"
        decision_reason = (f"Delta {delta_pp:+.2f}pp <= 0.5pp — clustering effect "
                           f"not material at N=100.  Independent sampling results stand.")

    _flush(f"    DECISION: {decision}")
    _flush(f"    Reason:   {decision_reason}")

    _flush(f"\nStep 4 complete  ({time.time()-t0:.1f}s)")

    # ==================================================================
    # STEP 5 — SAVE OUTPUTS
    # ==================================================================
    _flush("\n" + "=" * 80)
    _flush("STEP 5 — SAVE OUTPUTS")
    _flush("=" * 80)

    # --- Validation results file ---
    val_lines = []
    val_lines.append("PATH-CONSISTENT BRACKET GENERATOR — VALIDATION RESULTS")
    val_lines.append("=" * 70)
    val_lines.append("")
    val_lines.append("CHECK 1 — Champion Path Consistency")
    val_lines.append(f"  Result: {check1_pass}/{N_COH} ({check1_pass/N_COH:.0%})")
    val_lines.append(f"  Status: {'PASS' if check1_pass == N_COH else 'FAIL'}")
    val_lines.append("")
    val_lines.append("CHECK 2 — F4 Regional Consistency")
    val_lines.append(f"  Result: {check2_pass}/{N_COH} ({check2_pass/N_COH:.0%})")
    val_lines.append(f"  Status: {'PASS' if check2_pass == N_COH else 'FAIL'}")
    val_lines.append("")
    val_lines.append("CHECK 3 — Champion Distribution Alignment (1,000 brackets)")
    for team in top5_teams:
        tgt = ncg_dist[team]
        obs = dist_counts.get(team, 0) / N_DIST
        val_lines.append(f"  {team:<18} target={tgt:.4f}  observed={obs:.4f}  "
                         f"delta={obs-tgt:+.4f}")
    val_lines.append(f"  Status: {'PASS' if dist_ok else 'FAIL'} (within 3pp)")
    val_lines.append("")
    val_lines.append("CHECK 5A — Metric A: Score Variance")
    val_lines.append(f"  Path-consistent variance: {pc_var:,.1f}")
    val_lines.append(f"  Independent variance:     {ind_var:,.1f}")
    val_lines.append(f"  Ratio (PC / Ind):         {pc_var/ind_var:.3f}")
    val_lines.append("")
    val_lines.append("CHECK 5B — Metric B: Champion Co-occurrence")
    val_lines.append(f"  {'Team':<18} {'NCG Dist':>9} {'PC':>9} {'Ind':>9}")
    val_lines.append("  " + "-" * 47)
    for team in top5_teams:
        tgt = ncg_dist[team]
        pc_obs  = pc_champ.get(team, 0)  / N_CONC
        ind_obs = ind_champ.get(team, 0) / N_CONC
        val_lines.append(f"  {team:<18} {tgt:>8.4f} {pc_obs:>8.4f} {ind_obs:>8.4f}")
    val_lines.append("")
    val_lines.append("CHECK 5C — Metric C: Chalk Win Rate (PRIMARY DECISION GATE)")
    val_lines.append(f"  Chalk P(rank 1) vs independent opponents:     {ind_chalk_wr:.4%}")
    val_lines.append(f"  Chalk P(rank 1) vs path-consistent opponents: {pc_chalk_wr:.4%}")
    val_lines.append(f"  Delta (ind - PC): {delta_wr:+.4%}  ({delta_pp:+.2f}pp)")
    val_lines.append(f"  Threshold: 0.50pp")
    val_lines.append("")
    val_lines.append(f"DECISION GATE: {decision}")
    val_lines.append(f"  {decision_reason}")

    with open('generator_validation_2026.txt', 'w') as f:
        f.write('\n'.join(val_lines) + '\n')
    _flush("  Wrote generator_validation_2026.txt")

    _flush(f"\nStep 5 complete: all outputs saved  ({time.time()-t0:.1f}s)")

    # ==================================================================
    # FINAL SUMMARY
    # ==================================================================
    _flush("\n" + "=" * 80)
    _flush("FINAL SUMMARY")
    _flush("=" * 80)
    _flush(f"  Generator coherence:      {'PASS' if coherence_ok else 'FAIL'}")
    _flush(f"  Distribution alignment:   {'PASS' if dist_ok else 'FAIL'}")
    _flush(f"  Chalk P(rank 1) vs PC:    {pc_chalk_wr:.3%}")
    _flush(f"  Chalk P(rank 1) vs Ind:   {ind_chalk_wr:.3%}")
    _flush(f"  Delta:                    {delta_pp:+.2f}pp")
    _flush(f"  Decision:                 {decision}")
    _flush(f"\n  Total runtime: {time.time()-t0:.1f}s")
    _flush("=" * 80)
