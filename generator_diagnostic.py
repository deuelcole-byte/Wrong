#!/usr/bin/env python3
"""
Structural audit of path-consistent bracket generator.

Checks whether forced picks place teams into matchup slots where they
are actually listed as participants in the simulation engine.
"""

import sys
import numpy as np
from collections import defaultdict

from bracket_generator_path_consistent import (
    generate_opponent_bracket,
    generate_opponent_bracket_independent,
    score_bracket,
    gen_chalk_bracket,
    _load_data, _flush,
    espn, prob_data, team_paths, team_region, games, ncg_dist,
)

np.random.seed(42)
_load_data(verbose=False)

# ============================================================
# BUILD VALID-TEAMS MAP
# ============================================================
# CRITICAL DISTINCTION:
#   R64, R32, S16, E8  — FIXED matchups in sim_tournament().
#     The simulation always picks between the two listed teams.
#     A pick naming any other team scores ZERO.  HARD dead picks.
#   F4_1, F4_2, NCG    — DYNAMIC in sim_tournament().
#     Derived from E8 winners → can be any team.  NOT dead picks.

valid_teams_fixed = {}   # R64-E8 only — the ones that matter
for mid, m in espn.items():
    if m['round'] in ('R64', 'R32', 'S16', 'E8'):
        valid_teams_fixed[mid] = {m['team_1_name'], m['team_2_name']}

# ============================================================
# SECTION 0 — MATCHUP PARTICIPANT MAP
# ============================================================
_flush("=" * 85)
_flush("SECTION 0 — MATCHUP PARTICIPANT MAP  (who can actually score at each slot)")
_flush("=" * 85)
_flush("\n  NOTE: F4 and NCG are DYNAMIC in the simulation (derived from E8 winners).")
_flush("  Only R64-E8 are fixed.  Invalid picks at R64-E8 are DEAD — can never score.")

for rd in ['E8', 'S16', 'R32']:
    _flush(f"\n  {rd} matchup participants (simulation ONLY produces these winners):")
    for mid, m in sorted(espn.items()):
        if m['round'] == rd:
            _flush(f"    {mid:<12}  {m['team_1_name']:<18} vs {m['team_2_name']:<18}")

# ============================================================
# SECTION 1 — STRUCTURAL VALIDITY AUDIT (1,000 brackets)
# ============================================================
_flush("\n" + "=" * 85)
_flush("SECTION 1 — STRUCTURAL VALIDITY AUDIT  (1,000 path-consistent brackets)")
_flush("=" * 85)

N = 1000
brackets = []
champ_counts = defaultdict(int)
invalid_at_round = defaultdict(int)
invalid_detail_counts = defaultdict(int)
total_invalid_brackets = 0
all_invalid_info = []

for i in range(N):
    b = generate_opponent_bracket()
    brackets.append(b)
    champ_counts[b['NCG']] += 1

    bracket_has_invalid = False
    inv_this = []
    for mid, pick in b.items():
        if mid in valid_teams_fixed and pick not in valid_teams_fixed[mid]:
            bracket_has_invalid = True
            rd = ('R64' if 'R64' in mid else 'R32' if 'R32' in mid else
                  'S16' if 'S16' in mid else 'E8')
            invalid_at_round[rd] += 1
            invalid_detail_counts[(pick, mid)] += 1
            inv_this.append((mid, pick, valid_teams_fixed[mid]))

    if bracket_has_invalid:
        total_invalid_brackets += 1
    all_invalid_info.append(inv_this)

_flush(f"\n  Brackets with at least one DEAD pick (R64-E8 only): "
       f"{total_invalid_brackets}/{N} ({total_invalid_brackets/N:.1%})")
_flush(f"  (F4/NCG excluded — simulation derives those dynamically from E8 winners)")

_flush(f"\n  Dead picks by round (FIXED matchups only — these can NEVER score):")
for rd in ['R64', 'R32', 'S16', 'E8']:
    ct = invalid_at_round.get(rd, 0)
    if ct > 0:
        _flush(f"    {rd:<6}  {ct:>5} dead picks across {N} brackets "
               f"({ct/N:.1%} of brackets)")

_flush(f"\n  Most common dead (team -> matchup) placements:")
_flush(f"    {'Team':<18} {'Matchup':<12} {'Count':>6}  "
       f"{'Sim only produces these two teams'}")
_flush("    " + "-" * 75)
for (team, mid), ct in sorted(invalid_detail_counts.items(),
                                key=lambda x: -x[1])[:15]:
    vt = valid_teams_fixed[mid]
    _flush(f"    {team:<18} {mid:<12} {ct:>6}  {' vs '.join(sorted(vt))}")

# ============================================================
# SECTION 2 — CHAMPION FREQUENCY
# ============================================================
_flush("\n" + "=" * 85)
_flush("SECTION 2 — CHAMPION FREQUENCY DISTRIBUTION  (1,000 brackets)")
_flush("=" * 85)

top_teams = sorted(ncg_dist.keys(), key=lambda t: -ncg_dist[t])[:10]
_flush(f"\n  {'Team':<18} {'Target':>8} {'Observed':>10} {'Delta':>8}")
_flush("  " + "-" * 48)
for team in top_teams:
    tgt = ncg_dist[team]
    obs = champ_counts.get(team, 0) / N
    _flush(f"  {team:<18} {tgt:>7.2%} {obs:>9.2%} {obs - tgt:>+7.2%}")

# ============================================================
# SECTION 3 — FIRST 5 BRACKETS IN FULL DETAIL
# ============================================================
_flush("\n" + "=" * 85)
_flush("SECTION 3 — FIRST 5 PATH-CONSISTENT BRACKETS  (full structure)")
_flush("=" * 85)

REGION_PREFIXES = {'East': 'E', 'South': 'S', 'West': 'W', 'Midwest': 'MW'}

for idx in range(5):
    b = brackets[idx]
    champion = b['NCG']
    champ_rgn = team_region[champion]
    champ_seed = int(prob_data[champion]['team_seed'])
    inv = all_invalid_info[idx]

    _flush(f"\n  --- Bracket #{idx+1}  Champion: {champion} "
           f"(seed {champ_seed}, {champ_rgn}) ---")

    _flush(f"    NCG:   {b['NCG']}")
    _flush(f"    F4_1:  {b.get('F4_1','?'):<18}  (East vs South)  "
           f"[dynamic — can score]")
    _flush(f"    F4_2:  {b.get('F4_2','?'):<18}  (West vs Midwest) "
           f"[dynamic — can score]")

    _flush(f"    E8 picks (FIXED in simulation):")
    for region in ['East', 'South', 'West', 'Midwest']:
        pfx = REGION_PREFIXES[region]
        e8_mid = f'{pfx}_E8'
        e8_pick = b.get(e8_mid, '?')
        vt = valid_teams_fixed.get(e8_mid, set())
        if e8_pick in vt:
            flag = 'OK — can score'
        else:
            flag = f'DEAD — sim only produces {" or ".join(sorted(vt))}'
        _flush(f"      {e8_mid:<8}  {e8_pick:<18}  {flag}")

    _flush(f"    S16 picks (FIXED in simulation):")
    for region in ['East', 'South', 'West', 'Midwest']:
        pfx = REGION_PREFIXES[region]
        for side in [1, 2]:
            s16_mid = f'{pfx}_S16_{side}'
            s16_pick = b.get(s16_mid, '?')
            vt = valid_teams_fixed.get(s16_mid, set())
            if s16_pick in vt:
                flag = 'OK'
            else:
                flag = f'DEAD — sim only produces {" or ".join(sorted(vt))}'
            _flush(f"      {s16_mid:<10}  {s16_pick:<18}  {flag}")

    if inv:
        _flush(f"    DEAD PICKS IN R64-E8 ({len(inv)}):")
        for mid, pick, vt in inv:
            _flush(f"      {mid}: picked '{pick}' — sim only has "
                   f"{' vs '.join(sorted(vt))}")
    else:
        _flush(f"    All R64-E8 picks structurally valid.")

# ============================================================
# SECTION 4 — SCORE DISTRIBUTION
# ============================================================
_flush("\n" + "=" * 85)
_flush("SECTION 4 — SCORE DISTRIBUTION  (scored vs modal/chalk tournament outcome)")
_flush("=" * 85)

chalk = gen_chalk_bracket()
modal_outcome = {}
for g in games:
    modal_outcome[g['mid']] = g['hi']
modal_outcome['F4_1'] = chalk['F4_1']
modal_outcome['F4_2'] = chalk['F4_2']
modal_outcome['NCG']  = chalk['NCG']

_flush(f"\n  Modal outcome champion: {modal_outcome['NCG']}")
_flush(f"  Modal outcome F4: {modal_outcome['F4_1']} vs {modal_outcome['F4_2']}")

pc_scores = [score_bracket(b, modal_outcome) for b in brackets]
pc_scores_arr = np.array(pc_scores)

_flush(f"\n  Path-consistent brackets (N={N}) scored vs modal outcome:")
_flush(f"    Mean:   {pc_scores_arr.mean():.1f}   Median: {np.median(pc_scores_arr):.0f}   "
       f"Std: {pc_scores_arr.std():.1f}")
_flush(f"    Min:    {pc_scores_arr.min()}     Max: {pc_scores_arr.max()}")

# Champion match vs mismatch
champ_match = [sc for b, sc in zip(brackets, pc_scores) if b['NCG'] == modal_outcome['NCG']]
champ_miss  = [sc for b, sc in zip(brackets, pc_scores) if b['NCG'] != modal_outcome['NCG']]
cm = np.array(champ_match) if champ_match else np.array([0])
cn = np.array(champ_miss)  if champ_miss  else np.array([0])

_flush(f"\n  Score split by champion match to modal champion ({modal_outcome['NCG']}):")
_flush(f"    Champion MATCHES  (N={len(champ_match):>4}):  "
       f"mean={cm.mean():.1f}  median={np.median(cm):.0f}  std={cm.std():.1f}")
_flush(f"    Champion DIFFERS  (N={len(champ_miss):>4}):  "
       f"mean={cn.mean():.1f}  median={np.median(cn):.0f}  std={cn.std():.1f}")

_flush(f"\n  Score histogram:")
bins = [0, 200, 400, 600, 800, 1000, 1200, 1400, 1600, 1920]
hist, _ = np.histogram(pc_scores_arr, bins=bins)
for i in range(len(hist)):
    bar = '#' * (hist[i] // 3)
    _flush(f"    {bins[i]:>5}-{bins[i+1]:<5}  {hist[i]:>5}  {bar}")

# ============================================================
# SECTION 5 — SCORING IMPACT OF DEAD PICKS
# ============================================================
_flush("\n" + "=" * 85)
_flush("SECTION 5 — SCORING IMPACT OF DEAD PICKS  (R64-E8 only)")
_flush("=" * 85)

valid_scores   = [sc for sc, inv in zip(pc_scores, all_invalid_info) if not inv]
invalid_scores = [sc for sc, inv in zip(pc_scores, all_invalid_info) if inv]
v_arr = np.array(valid_scores)   if valid_scores   else np.array([0])
i_arr = np.array(invalid_scores) if invalid_scores else np.array([0])

_flush(f"\n  Brackets with ALL R64-E8 valid  (N={len(valid_scores):>4}):  "
       f"mean={v_arr.mean():.1f}  median={np.median(v_arr):.0f}")
_flush(f"  Brackets with DEAD R64-E8 picks (N={len(invalid_scores):>4}):  "
       f"mean={i_arr.mean():.1f}  median={np.median(i_arr):.0f}")
_flush(f"  Scoring gap: {v_arr.mean() - i_arr.mean():+.1f} points")

dead_pts = {'R64': 10, 'R32': 20, 'S16': 40, 'E8': 80}
total_dead = 0
dead_by_round = defaultdict(int)
for inv_list in all_invalid_info:
    for mid, pick, vt in inv_list:
        for r in ['R64', 'R32', 'S16', 'E8']:
            if r in mid:
                dead_by_round[r] += dead_pts[r]
                total_dead += dead_pts[r]
                break

_flush(f"\n  Dead points (can NEVER score) across {N} brackets:")
_flush(f"    Total: {total_dead}   Per bracket avg: {total_dead/N:.1f}")
for rd in ['R64', 'R32', 'S16', 'E8']:
    if dead_by_round[rd] > 0:
        _flush(f"      {rd:<4}: {dead_by_round[rd]:>6} total  "
               f"({dead_by_round[rd]/N:.1f} per bracket)")

# ============================================================
# SECTION 6 — INDEPENDENT BRACKET CHAMPION METHOD
# ============================================================
_flush("\n" + "=" * 85)
_flush("SECTION 6 — INDEPENDENT BRACKET: HOW IS THE CHAMPION IDENTIFIED?")
_flush("=" * 85)

_flush("""
  METHOD: The independent generator does NOT sample a champion from
  ncg_pick_distribution_2026.csv up front.  Instead it:

    1. Samples each R64-E8 game independently using ESPN public pick
       percentages (pub_hi for each matchup).
    2. Takes the E8 winners as F4 participants:
         F4_1 entrants = picks['E_E8'] vs picks['S_E8']
         F4_2 entrants = picks['W_E8'] vs picks['MW_E8']
    3. Samples F4 winners using each entrant's F4 public_pick_pct
       from leverage_matrix_2026.csv, normalized to sum to 1.
    4. Samples NCG winner between the two F4 winners using each team's
       ncg_public_pick_pct, normalized to sum to 1.

  The effective champion is DERIVED by following picks forward.
  It is NOT drawn from the NCG distribution directly.

  Because each R64-E8 game is sampled independently at high pick pcts
  (1-seeds at 97-98% R64, 95-96% R32, etc.), the derived champion is
  heavily biased toward top seeds.  The NCG distribution weighting in
  step 4 only chooses BETWEEN the two F4 winners.

  STRUCTURAL VALIDITY:  Independent brackets have ZERO dead picks at
  R64-E8 because they only pick between the two listed teams in each
  matchup.  Every pick can potentially score.""")

_flush("\n  Empirical verification (1,000 independent brackets):")
ind_champ = defaultdict(int)
ind_brackets = []
for _ in range(N):
    b = generate_opponent_bracket_independent()
    ind_brackets.append(b)
    ind_champ[b['NCG']] += 1

# Verify structural validity
ind_dead = 0
for b in ind_brackets:
    for mid, pick in b.items():
        if mid in valid_teams_fixed and pick not in valid_teams_fixed[mid]:
            ind_dead += 1
            break

_flush(f"\n  {'Team':<18} {'NCG Dist':>9} {'Ind Obs':>9} {'Inflation':>10}")
_flush("  " + "-" * 50)
for team in top_teams:
    tgt = ncg_dist[team]
    obs = ind_champ.get(team, 0) / N
    _flush(f"  {team:<18} {tgt:>8.2%} {obs:>8.2%} "
           f"{obs/tgt if tgt > 0 else 0:>9.1f}x")

_flush(f"\n  Independent brackets with dead R64-E8 picks: "
       f"{ind_dead}/{N} ({ind_dead/N:.1%})")

# Score independent brackets against modal outcome
ind_scores = [score_bracket(b, modal_outcome) for b in ind_brackets]
ind_arr = np.array(ind_scores)
_flush(f"\n  Independent brackets scored vs modal outcome:")
_flush(f"    Mean: {ind_arr.mean():.1f}   Median: {np.median(ind_arr):.0f}   "
       f"Std: {ind_arr.std():.1f}")
_flush(f"  Path-consistent (for comparison):")
_flush(f"    Mean: {pc_scores_arr.mean():.1f}   Median: {np.median(pc_scores_arr):.0f}   "
       f"Std: {pc_scores_arr.std():.1f}")
_flush(f"  Gap: {ind_arr.mean() - pc_scores_arr.mean():+.1f} points "
       f"(independent score HIGHER)")

# ============================================================
# SECTION 7 — ROOT CAUSE DIAGNOSIS
# ============================================================
_flush("\n" + "=" * 85)
_flush("SECTION 7 — ROOT CAUSE DIAGNOSIS")
_flush("=" * 85)

pct_dead = total_invalid_brackets / N * 100
pct_3plus = sum(1 for b in brackets
                if int(prob_data[b['NCG']]['team_seed']) >= 3) / N * 100
avg_dead_affected = total_dead / max(1, total_invalid_brackets)

_flush(f"""
  THE BUG: SIMULATION-GENERATOR INCOMPATIBILITY

  The simulation engine (sim_tournament) treats R64-E8 as FIXED contests
  between the two teams listed in espn_picks_2026.csv.  For example:

    S_E8 always produces Florida or Houston.  Never Illinois.
    E_E8 always produces Duke or UConn.  Never Michigan St.

  The path-consistent generator forces F4 teams into these slots.
  When the F4 team is one of the two listed participants, the pick can
  score.  When it is NOT (e.g., Illinois forced into S_E8), the pick
  is DEAD — it can never match the simulation and always scores 0.

  IMPACT:
    {pct_dead:.0f}% of path-consistent brackets have at least one dead pick
    Average {avg_dead_affected:.0f} dead points per affected bracket
    {pct_3plus:.0f}% of brackets have a 3+ seed champion (most dead picks
      come from these — their S16/E8 slots don't list them)

  WHY CHALK DOES BETTER AGAINST PATH-CONSISTENT OPPONENTS:
    Path-consistent brackets with unlikely champions contain dead late-round
    picks worth 40-80 points that can never score.  These brackets are
    systematically weaker, making chalk's rank-1 rate artificially high.

    Independent brackets have ZERO dead picks — every pick can score.
    They are uniformly stronger opponents.

  IMPLICATION FOR METRIC C:
    The -0.60pp delta (chalk does BETTER against PC opponents) is an
    artifact of this structural bug, not evidence that clustering doesn't
    matter.  The Metric C comparison is INVALID — it measured the scoring
    penalty of dead picks, not the clustering effect.

  TO FIX:
    The simulation engine must propagate winners through rounds (the R32
    winner plays in S16, the S16 winner plays in E8, etc.) instead of
    using fixed matchups.  Only then can the path-consistent generator
    be fairly compared to independent sampling.
""")

_flush("=" * 85)
_flush("DIAGNOSTIC COMPLETE")
_flush("=" * 85)
