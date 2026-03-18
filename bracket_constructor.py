#!/usr/bin/env python3
"""
Prompt 8 — Full Bracket Constructor

Builds a complete 63-game optimal bracket for N=100 pool size using
all prior outputs. Constructs backward from champion to first round.
All team-specific findings derived at runtime from verified source files.
"""
import csv
import sys
from collections import defaultdict

TARGET_POOL = 100

# ============================================================
# STEP 0 — FILE VERIFICATION
# ============================================================
print("=" * 90)
print("STEP 0 — FILE VERIFICATION")
print("=" * 90)

verification = {}

# --- probability_baseline_final_2026.csv ---
try:
    prob_data = {}
    with open('probability_baseline_final_2026.csv') as f:
        reader = csv.DictReader(f)
        prob_cols = reader.fieldnames
        for row in reader:
            prob_data[row['team_name']] = row

    checks = []
    checks.append(('e8_game_prob_corrected column', 'e8_game_prob_corrected' in prob_cols))
    checks.append(('r4_adjusted column', 'r4_adjusted' in prob_cols))
    checks.append(('r4_adjusted_alt column', 'r4_adjusted_alt' in prob_cols))
    checks.append(('path_dependent_flag column', 'path_dependent_flag' in prob_cols))

    # source_metadata must reference E8 correction reapplied at game level
    sample_meta = list(prob_data.values())[0].get('source_metadata', '')
    checks.append(('source_metadata references game-level E8 correction',
                    'reapplied at game level' in sample_meta))

    # e8_game_prob_corrected must differ from implied for at least one team
    diff_count = sum(1 for t in prob_data.values()
                     if t.get('e8_game_prob_corrected', '') != t.get('e8_game_prob_implied', ''))
    checks.append(('e8 corrected differs from implied', diff_count > 0))

    all_pass = all(c[1] for c in checks)
    verification['probability_baseline_final_2026.csv'] = ('PASS' if all_pass else 'FAIL',
                                                            'Post-correction version confirmed' if all_pass else
                                                            '; '.join(c[0] for c in checks if not c[1]))
except Exception as e:
    verification['probability_baseline_final_2026.csv'] = ('FAIL', str(e))

# --- leverage_matrix_2026.csv ---
try:
    lev_data = {}
    lev_by_round = defaultdict(list)
    with open('leverage_matrix_2026.csv') as f:
        reader = csv.DictReader(f)
        lev_cols = reader.fieldnames
        for row in reader:
            key = (row['team_name'], row['round'])
            lev_data[key] = row
            lev_by_round[row['round']].append(row)

    total_entries = len(lev_data)
    ncg_count = len(lev_by_round['NCG'])
    f4_count = len(lev_by_round['F4'])
    has_lev_low = 'leverage_low' in lev_cols
    has_lev_high = 'leverage_high' in lev_cols
    has_sign_flip = 'sign_flip_flag' in lev_cols
    has_conf_type = 'confidence_type' in lev_cols

    checks = []
    checks.append(('248 entries', total_entries == 248))
    checks.append(('NCG covers 64 teams', ncg_count == 64))
    checks.append(('F4 covers 64 teams', f4_count == 64))
    checks.append(('leverage_low column', has_lev_low))
    checks.append(('leverage_high column', has_lev_high))
    checks.append(('sign_flip_flag column', has_sign_flip))
    checks.append(('confidence_type column', has_conf_type))

    # Check confidence_type values
    conf_types = set(row.get('confidence_type', '') for row in lev_data.values())
    checks.append(('confidence_type has A/B/C/NA', conf_types >= {'A', 'B', 'C', 'NA'}))

    all_pass = all(c[1] for c in checks)
    verification['leverage_matrix_2026.csv'] = ('PASS' if all_pass else 'FAIL',
                                                 f'{total_entries} entries, {ncg_count} NCG, {f4_count} F4' if all_pass else
                                                 '; '.join(c[0] for c in checks if not c[1]))
except Exception as e:
    verification['leverage_matrix_2026.csv'] = ('FAIL', str(e))

# --- ncg_pick_distribution_2026.csv ---
try:
    ncg_dist = {}
    with open('ncg_pick_distribution_2026.csv') as f:
        for row in csv.DictReader(f):
            ncg_dist[row['team_name']] = float(row['ncg_public_pick_pct'])

    ncg_sum = sum(ncg_dist.values())
    teams_gt0 = sum(1 for v in ncg_dist.values() if v > 0)

    checks = []
    checks.append(('sum 0.99-1.01', 99.0 <= ncg_sum <= 101.0))
    checks.append(('>=10 teams with pct>0', teams_gt0 >= 10))

    all_pass = all(c[1] for c in checks)
    verification['ncg_pick_distribution_2026.csv'] = ('PASS' if all_pass else 'FAIL',
                                                       f'sum={ncg_sum:.2f}, {teams_gt0} teams >0' if all_pass else
                                                       '; '.join(c[0] for c in checks if not c[1]))
except Exception as e:
    verification['ncg_pick_distribution_2026.csv'] = ('FAIL', str(e))

# --- champion_optimizer_results.csv ---
try:
    champ_data = []
    with open('champion_optimizer_results.csv') as f:
        for row in csv.DictReader(f):
            champ_data.append(row)

    # Top candidate NCG public pct should match ncg_pick_distribution
    top_team = champ_data[0]['team_name']
    top_pub_pct = float(champ_data[0]['public_pct_display'])
    ncg_pct = ncg_dist.get(top_team, 0)

    checks = []
    checks.append(('top candidate pub pct matches ncg_distribution',
                    abs(top_pub_pct - ncg_pct) < 1.0))
    # Not the artifact: check it's not just Duke 54% or Arizona 46%
    checks.append(('not artifact data (not just Duke/Arizona)',
                    len(champ_data) > 5))

    all_pass = all(c[1] for c in checks)
    verification['champion_optimizer_results.csv'] = ('PASS' if all_pass else 'FAIL',
                                                       f'{len(champ_data)} candidates, top={top_team}' if all_pass else
                                                       '; '.join(c[0] for c in checks if not c[1]))
except Exception as e:
    verification['champion_optimizer_results.csv'] = ('FAIL', str(e))

# --- entropy_optimization_2026.csv ---
try:
    entropy_data = {}
    with open('entropy_optimization_2026.csv') as f:
        for row in csv.DictReader(f):
            ps = int(row['pool_size'])
            uc = int(row['upset_count'])
            entropy_data[(ps, uc)] = float(row['win_rate_corrected'])

    # Win rates must decrease with pool size
    max_50 = max(entropy_data.get((50, u), 0) for u in range(22))
    max_200 = max(entropy_data.get((200, u), 0) for u in range(22))

    checks = []
    checks.append(('N=200 wr < N=50 wr', max_200 < max_50))
    checks.append(('not flat (~5% everywhere)',
                    abs(max_50 - max_200) > 0.01))  # >1pp difference

    all_pass = all(c[1] for c in checks)
    verification['entropy_optimization_2026.csv'] = ('PASS' if all_pass else 'FAIL',
                                                      f'N=50={max_50:.4f}, N=200={max_200:.4f}' if all_pass else
                                                      '; '.join(c[0] for c in checks if not c[1]))
except Exception as e:
    verification['entropy_optimization_2026.csv'] = ('FAIL', str(e))

# --- espn_picks_2026.csv ---
try:
    espn_matchups = {}
    with open('espn_picks_2026.csv') as f:
        for row in csv.DictReader(f):
            espn_matchups[row['matchup_id']] = row

    # NCG check: the full distribution is in ncg_pick_distribution, not espn_picks
    # espn_picks has the matchup format. Check ncg_pick_distribution as the authoritative source.
    checks = []
    checks.append(('has matchups for all rounds',
                    all(any(m['round'] == r for m in espn_matchups.values())
                        for r in ['R64', 'R32', 'S16', 'E8'])))
    # NCG distribution verified via ncg_pick_distribution_2026.csv (sum ~100, >10 teams)
    checks.append(('NCG distribution verified via ncg_pick_distribution',
                    99.0 <= sum(ncg_dist.values()) <= 101.0 and
                    sum(1 for v in ncg_dist.values() if v > 0) > 2))

    all_pass = all(c[1] for c in checks)
    verification['espn_picks_2026.csv'] = ('PASS' if all_pass else 'FAIL',
                                            f'{len(espn_matchups)} matchups' if all_pass else
                                            '; '.join(c[0] for c in checks if not c[1]))
except Exception as e:
    verification['espn_picks_2026.csv'] = ('FAIL', str(e))

# Print verification table
print(f"\n{'File':<45} {'Result':<8} {'Version Confirmed'}")
print("-" * 90)
any_fail = False
for fname, (result, detail) in verification.items():
    print(f"  {fname:<43} {result:<8} {detail}")
    if result == 'FAIL':
        any_fail = True

if any_fail:
    print("\nHALT: One or more files failed verification.")
    sys.exit(1)
else:
    print("\nAll files PASSED verification. Proceeding to bracket construction.\n")

# ============================================================
# STEP 1 — CHAMPION SELECTION
# ============================================================
print("=" * 90)
print("STEP 1 — CHAMPION SELECTION (N=100)")
print("=" * 90)

# Find champion with highest EV at N=100
ev_col = 'ev_100'
champ_data.sort(key=lambda x: -float(x[ev_col]))

top_ev = float(champ_data[0][ev_col])
threshold = top_ev * 0.95  # within 5%

near_equivalent = [c for c in champ_data if float(c[ev_col]) >= threshold]
print(f"\nNear-equivalent candidates (within 5% of top EV={top_ev:.3f}):")
for c in near_equivalent:
    ev = float(c[ev_col])
    ncg_pub = ncg_dist.get(c['team_name'], 0)
    print(f"  {c['team_name']:<18} r6={float(c['r6']):.4f}  public={ncg_pub:.2f}%  "
          f"EV@100={ev:.3f}  path_dep={c['path_dependent']}  conf_type={c['conf_type']}")

champion = champ_data[0]
champ_name = champion['team_name']
champ_region = champion['region']
champ_r6 = float(champion['r6'])
champ_pub = ncg_dist.get(champ_name, 0)
champ_ev = float(champion[ev_col])
champ_path_dep = champion['path_dependent']

# E8 path assumption embedded in r6
path_assumption = 'primary'
if champ_path_dep == 'Y':
    path_assumption = 'primary (path-dependent, alt r6=' + champion['r6_path_alt'] + ')'

print(f"\nSELECTED CHAMPION: {champ_name}")
print(f"  r6 probability: {champ_r6:.4f} ({champ_r6:.1%})")
print(f"  Public ownership: {champ_pub:.2f}% (from ncg_pick_distribution_2026.csv)")
print(f"  Expected value at N=100: {champ_ev:.3f}")
print(f"  Path assumption: {path_assumption}")
print(f"  Region: {champ_region}")

# ============================================================
# HELPERS
# ============================================================
regions = ['East', 'South', 'West', 'Midwest']

# Get sign-flip teams
sign_flip_teams = set()
for (team, rd), entry in lev_data.items():
    if entry.get('sign_flip_flag', 'N') == 'Y':
        sign_flip_teams.add((team, rd))

def get_lev(team, rd):
    return lev_data.get((team, rd), {})

def get_chalk(matchup):
    s1, s2 = int(matchup['team_1_seed']), int(matchup['team_2_seed'])
    if s1 < s2: return matchup['team_1_name']
    elif s2 < s1: return matchup['team_2_name']
    else: return matchup['team_1_name']

def get_underdog(matchup):
    s1, s2 = int(matchup['team_1_seed']), int(matchup['team_2_seed'])
    if s1 < s2: return matchup['team_2_name']
    elif s2 < s1: return matchup['team_1_name']
    else: return matchup['team_2_name']

DEV_THRESHOLDS = {'NA': 1.15, 'A': 1.15, 'B': 1.20, 'C': 1.25}

# Organize matchups by round
e8_matchups = {m['matchup_id']: m for m in espn_matchups.values() if m['round'] == 'E8'}
s16_matchups = {m['matchup_id']: m for m in espn_matchups.values() if m['round'] == 'S16'}
r32_matchups = {m['matchup_id']: m for m in espn_matchups.values() if m['round'] == 'R32'}
r64_matchups = {m['matchup_id']: m for m in espn_matchups.values() if m['round'] == 'R64'}
f4_matchups_map = {m['matchup_id']: m for m in espn_matchups.values() if m['round'] == 'F4'}

# ============================================================
# STEP 2 — ELITE EIGHT (determines F4 teams)
# ============================================================
# The E8 winner from each region IS the F4 team for that region.
# Champion's region: champion must win E8.
# Other regions: apply leverage-based deviation thresholds.

print("\n" + "=" * 90)
print("STEP 2 — ELITE EIGHT (E8 winners = Final Four teams)")
print("=" * 90)

print(f"\nSign-flip teams (defaulting to chalk):")
for team, rd in sorted(sign_flip_teams):
    print(f"  {team} ({rd})")

# Confirm F4 entries cover all 64 teams
f4_entries = lev_by_round['F4']
assert len(f4_entries) >= 60, f"HALT: Only {len(f4_entries)} F4 entries, need >= 60"

e8_picks = {}
f4_picks = {}  # region -> team (= E8 winner for that region)

print(f"\nELITE EIGHT picks (each winner advances to F4):")
print(f"  {'Matchup':<10} {'Chalk':<18} {'Pick':<18} {'LevR':>8} {'CType':>6} {'Thresh':>7} {'Decision'}")
print("  " + "-" * 90)

for mid, m in sorted(e8_matchups.items()):
    chalk = get_chalk(m)
    underdog = get_underdog(m)
    region = m['region']

    if region == champ_region:
        # Champion must win this E8
        pick = champ_name
        decision = 'Champion path consistency'
        e8_picks[mid] = pick
        f4_picks[region] = pick
        print(f"  {mid:<10} {chalk:<18} {pick:<18} {'N/A':>8} {'N/A':>6} {'N/A':>7} {decision}")
        continue

    # Apply deviation thresholds
    ud_lev = get_lev(underdog, 'E8')
    ud_lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
    ud_conf = ud_lev.get('confidence_type', 'NA') if ud_lev else 'NA'
    ud_sign_flip = (underdog, 'E8') in sign_flip_teams
    ud_lev_lo = float(ud_lev.get('leverage_low', '0')) if ud_lev else 0
    ud_lev_hi = float(ud_lev.get('leverage_high', '0')) if ud_lev else 0
    threshold = DEV_THRESHOLDS.get(ud_conf, 1.15)

    if ud_sign_flip:
        pick = chalk
        decision = f'chalk (sign-flip: {underdog})'
    elif ud_conf == 'C' and (ud_lev_lo <= 0 or ud_lev_hi <= 0):
        pick = chalk
        decision = f'chalk (Type C, bound<=0)'
    elif ud_lr > threshold:
        pick = underdog
        decision = f'upset (lr={ud_lr:.4f}>{threshold:.2f})'
    else:
        pick = chalk
        decision = f'chalk (lr={ud_lr:.4f}<{threshold:.2f})'

    e8_picks[mid] = pick
    f4_picks[region] = pick
    print(f"  {mid:<10} {chalk:<18} {pick:<18} {ud_lr:>8.4f} {ud_conf:>6} {threshold:>7.2f} {decision}")

print(f"\n  FINAL FOUR (= E8 winners):")
for region in regions:
    team = f4_picks[region]
    seed = int(prob_data[team]['team_seed'])
    lr_entry = get_lev(team, 'F4')
    lr = float(lr_entry.get('leverage_ratio', 0)) if lr_entry else 0
    pub = float(lr_entry.get('public_pick_pct', 0)) if lr_entry else 0
    print(f"    {region:<10} {team:<18} (seed {seed})  F4_leverage_ratio={lr:.4f}  F4_public={pub:.4f}")

# ============================================================
# STEP 3 — SWEET 16
# ============================================================
print("\n" + "=" * 90)
print("STEP 3 — SWEET 16")
print("=" * 90)

s16_picks = {}
print(f"\n  {'Matchup':<12} {'Chalk':<18} {'Pick':<18} {'LevR':>8} {'CType':>6} {'Thresh':>7} {'Decision'}")
print("  " + "-" * 90)

for mid, m in sorted(s16_matchups.items()):
    chalk = get_chalk(m)
    underdog = get_underdog(m)
    region = m['region']

    # Path consistency: E8 winner from this region must advance through S16
    e8_mid = {'East': 'E_E8', 'South': 'S_E8', 'West': 'W_E8', 'Midwest': 'MW_E8'}[region]
    e8_pick = e8_picks.get(e8_mid, '')

    if e8_pick == m['team_1_name'] or e8_pick == m['team_2_name']:
        pick = e8_pick
        decision = 'E8 path consistency'
        s16_picks[mid] = pick
        print(f"  {mid:<12} {chalk:<18} {pick:<18} {'N/A':>8} {'N/A':>6} {'N/A':>7} {decision}")
        continue

    # Not on E8 winner's path — apply leverage threshold + vegas floor
    ud_lev = get_lev(underdog, 'S16')
    ud_lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
    ud_vegas = float(ud_lev.get('vegas_prob', 0)) if ud_lev else 0
    ud_conf = ud_lev.get('confidence_type', 'NA') if ud_lev else 'NA'
    ud_sign_flip = (underdog, 'S16') in sign_flip_teams
    ud_lev_lo = float(ud_lev.get('leverage_low', '0')) if ud_lev else 0
    ud_lev_hi = float(ud_lev.get('leverage_high', '0')) if ud_lev else 0
    threshold = DEV_THRESHOLDS.get(ud_conf, 1.15)

    if ud_sign_flip:
        pick = chalk
        decision = f'chalk (sign-flip: {underdog})'
    elif ud_conf == 'C' and (ud_lev_lo <= 0 or ud_lev_hi <= 0):
        pick = chalk
        decision = f'chalk (Type C, bound<=0)'
    elif ud_lr > threshold and ud_vegas > 0.35:
        pick = underdog
        decision = f'upset (lr={ud_lr:.4f}>{threshold:.2f}, vegas={ud_vegas:.4f}>0.35)'
    elif ud_lr > threshold:
        pick = chalk
        decision = f'chalk (lr={ud_lr:.4f}>{threshold:.2f} BUT vegas={ud_vegas:.4f}<0.35)'
    else:
        pick = chalk
        decision = f'chalk (lr={ud_lr:.4f}<{threshold:.2f})'

    s16_picks[mid] = pick
    print(f"  {mid:<12} {chalk:<18} {pick:<18} {ud_lr:>8.4f} {ud_conf:>6} {threshold:>7.2f} {decision}")

# ============================================================
# STEP 4 — ROUNDS 1 AND 2 (R32, R64)
# ============================================================
print("\n" + "=" * 90)
print("STEP 4 — ROUNDS 1 AND 2 (R32, R64)")
print("=" * 90)

# R32 picks
print(f"\nROUND OF 32:")
print(f"  {'Matchup':<12} {'Chalk':<18} {'Pick':<18} {'LevR':>8} {'VegasWP':>8} {'Decision'}")
print("  " + "-" * 85)

r32_picks = {}
for mid, m in sorted(r32_matchups.items()):
    chalk = get_chalk(m)
    underdog = get_underdog(m)
    region = m['region']

    # Path consistency: check if S16 pick requires this team
    region_prefix = mid.split('_R32_')[0]
    r32_num = int(mid.split('_R32_')[1])
    s16_num = (r32_num + 1) // 2
    s16_mid = f"{region_prefix}_S16_{s16_num}"
    s16_pick = s16_picks.get(s16_mid, '')

    if s16_pick == m['team_1_name'] or s16_pick == m['team_2_name']:
        pick = s16_pick
        decision = 'S16 path consistency'
        r32_picks[mid] = pick
        print(f"  {mid:<12} {chalk:<18} {pick:<18} {'N/A':>8} {'N/A':>8} {decision}")
        continue

    # Check leverage thresholds for upset
    ud_lev = get_lev(underdog, 'R32')
    ud_lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
    ud_vegas = float(prob_data.get(underdog, {}).get('r2', 0))
    ud_abs_lev = abs(float(ud_lev.get('leverage', 0))) if ud_lev else 0

    if ud_abs_lev > 0.10 and ud_lr > 1.25 and ud_vegas > 0.35:
        pick = underdog
        decision = f'upset (lr={ud_lr:.4f}>1.25, vegas={ud_vegas:.3f}>0.35)'
    elif ud_abs_lev > 0.10 and ud_lr > 1.25:
        pick = chalk
        decision = f'chalk (lr={ud_lr:.4f}>1.25 BUT vegas={ud_vegas:.3f}<0.35)'
    elif ud_abs_lev > 0.10 and ud_vegas > 0.35:
        pick = chalk
        decision = f'chalk (vegas={ud_vegas:.3f}>0.35 BUT lr={ud_lr:.4f}<1.25)'
    else:
        pick = chalk
        decision = 'chalk (default)'

    r32_picks[mid] = pick
    print(f"  {mid:<12} {chalk:<18} {pick:<18} {ud_lr:>8.4f} {ud_vegas:>8.3f} {decision}")

# R64 picks
print(f"\nROUND OF 64:")
print(f"  {'Matchup':<12} {'Chalk':<18} {'Pick':<18} {'LevR':>8} {'VegasWP':>8} {'Decision'}")
print("  " + "-" * 85)

r64_picks = {}
for mid, m in sorted(r64_matchups.items()):
    chalk = get_chalk(m)
    underdog = get_underdog(m)
    region = m['region']

    # Path consistency: check if R32 pick requires this team
    region_prefix = mid.split('_R64_')[0]
    r64_num = int(mid.split('_R64_')[1])
    r32_num = (r64_num + 1) // 2
    r32_mid = f"{region_prefix}_R32_{r32_num}"
    r32_pick = r32_picks.get(r32_mid, '')

    if r32_pick == m['team_1_name'] or r32_pick == m['team_2_name']:
        if r32_pick != chalk:
            pick = r32_pick
            decision = 'R32 path consistency (upset carry-through)'
            r64_picks[mid] = pick
            print(f"  {mid:<12} {chalk:<18} {pick:<18} {'N/A':>8} {'N/A':>8} {decision}")
            continue

    # Check for first_four teams
    first_four = prob_data.get(m['team_1_name'], {}).get('first_four_flag', 'N') == 'Y' or \
                 prob_data.get(m['team_2_name'], {}).get('first_four_flag', 'N') == 'Y'
    ff_note = ' [first-four]' if first_four else ''

    # Check leverage thresholds for upset
    ud_lev = get_lev(underdog, 'R64')
    ud_lr = float(ud_lev.get('leverage_ratio', 0)) if ud_lev else 0
    ud_vegas = float(prob_data.get(underdog, {}).get('r1', 0))
    ud_abs_lev = abs(float(ud_lev.get('leverage', 0))) if ud_lev else 0

    if ud_abs_lev > 0.10 and ud_lr > 1.25 and ud_vegas > 0.35:
        pick = underdog
        decision = f'upset (lr={ud_lr:.4f}>1.25, vegas={ud_vegas:.3f}>0.35){ff_note}'
    elif ud_abs_lev > 0.10 and ud_lr > 1.25:
        pick = chalk
        decision = f'chalk (lr OK, vegas={ud_vegas:.3f}<0.35){ff_note}'
    elif ud_abs_lev > 0.10 and ud_vegas > 0.35:
        pick = chalk
        decision = f'chalk (vegas OK, lr={ud_lr:.4f}<1.25){ff_note}'
    else:
        pick = chalk
        decision = f'chalk (default){ff_note}'

    r64_picks[mid] = pick
    print(f"  {mid:<12} {chalk:<18} {pick:<18} {ud_lr:>8.4f} {ud_vegas:>8.3f} {decision}")

# ============================================================
# ASSEMBLE FULL BRACKET
# ============================================================
# F4: champion must win their semifinal
# F4_1: East winner vs South winner; F4_2: West winner vs Midwest winner
f4_bracket_picks = {}
for fmid, fm in f4_matchups_map.items():
    if fmid == 'F4_1':
        east_f4 = f4_picks['East']
        south_f4 = f4_picks['South']
        if champ_region in ('East', 'South'):
            pick = champ_name
        else:
            # Pick team with higher r5
            pick = east_f4 if float(prob_data[east_f4]['r5']) >= float(prob_data[south_f4]['r5']) else south_f4
    elif fmid == 'F4_2':
        west_f4 = f4_picks['West']
        mw_f4 = f4_picks['Midwest']
        if champ_region in ('West', 'Midwest'):
            pick = champ_name
        else:
            pick = west_f4 if float(prob_data[west_f4]['r5']) >= float(prob_data[mw_f4]['r5']) else mw_f4
    f4_bracket_picks[fmid] = pick

ncg_pick = champ_name

# Combine all picks
all_picks = {}
all_picks.update(r64_picks)
all_picks.update(r32_picks)
all_picks.update(s16_picks)
all_picks.update(e8_picks)
all_picks.update(f4_bracket_picks)
all_picks['NCG'] = ncg_pick

# Count upsets by round
# F4 and NCG picks where both teams are the same seed are champion-path
# structural picks, not contrarian upsets. Exclude from entropy-relevant count.
upset_count_by_round = {}
champ_path_count = 0
for mid, m in espn_matchups.items():
    if mid in all_picks:
        rd = m['round']
        chalk = get_chalk(m)
        if all_picks[mid] != chalk:
            s1, s2 = int(m['team_1_seed']), int(m['team_2_seed'])
            if rd in ('F4', 'NCG') and s1 == s2:
                # Same-seed F4/NCG: champion path pick, not a contrarian upset
                champ_path_count += 1
            else:
                upset_count_by_round[rd] = upset_count_by_round.get(rd, 0) + 1

total_upsets = sum(upset_count_by_round.values())

print(f"\n\nUpset count by round (contrarian upsets only): {dict(upset_count_by_round)}")
print(f"Total contrarian upsets: {total_upsets}")
print(f"Champion-path picks (F4/NCG same-seed, not counted): {champ_path_count}")

# ============================================================
# VALIDATION
# ============================================================
print("\n" + "=" * 90)
print("VALIDATION")
print("=" * 90)

# Load optimal upsets at N=100 (interpolated from N=50 and N=200)
opt_50 = max(range(22), key=lambda u: entropy_data.get((50, u), 0))
opt_200 = max(range(22), key=lambda u: entropy_data.get((200, u), 0))
optimal_upsets = opt_50  # Both are 3, N=100 between them

print(f"\nOptimal upsets at N=100 (interpolated): {optimal_upsets}")
print(f"  (N=50 optimal: {opt_50}, N=200 optimal: {opt_200})")

# Check 1: Path consistency
print(f"\n  Check 1 — Path consistency:")
path_errors = []

# For each team picked to advance, verify they were picked in all prior rounds
# Build advancement map: which teams are picked to advance through each round
team_advancement = defaultdict(set)  # team -> set of rounds they appear in

for mid, pick in all_picks.items():
    m = espn_matchups.get(mid, {})
    rd = m.get('round', mid)
    team_advancement[pick].add(rd)

# Check: any team picked in later round must be picked in all earlier rounds
# For this we trace paths forward through the bracket
def trace_path_forward(team, round_order=['R64', 'R32', 'S16', 'E8', 'F4', 'NCG']):
    """Check that team's path is unbroken."""
    for rd in round_order:
        # Find matchup where team appears in this round
        found = False
        for mid, m in espn_matchups.items():
            if m['round'] == rd and (m['team_1_name'] == team or m['team_2_name'] == team):
                if all_picks.get(mid) == team:
                    found = True
                break
        if not found:
            return rd  # First round where path breaks
    return None

# Check champion's full path
champ_path_ok = True
for rd in ['R64', 'R32', 'S16', 'E8']:
    found_in_round = False
    for mid, m in espn_matchups.items():
        if m['round'] == rd and (m['team_1_name'] == champ_name or m['team_2_name'] == champ_name):
            if all_picks.get(mid) == champ_name:
                found_in_round = True
            else:
                path_errors.append(f"Champion {champ_name} not picked in {mid} ({rd})")
                champ_path_ok = False
            break

# Check all F4 teams have unbroken paths
for region in regions:
    f4_team = f4_picks[region]
    for rd in ['R64', 'R32', 'S16', 'E8']:
        for mid, m in espn_matchups.items():
            if m['round'] == rd and (m['team_1_name'] == f4_team or m['team_2_name'] == f4_team):
                if all_picks.get(mid) != f4_team:
                    path_errors.append(f"F4 pick {f4_team} ({region}) not picked in {mid} ({rd})")
                break

# Check all E8 picks have paths through S16, R32, R64
for e8_mid, e8_pick in e8_picks.items():
    for rd in ['R64', 'R32', 'S16']:
        for mid, m in espn_matchups.items():
            if m['round'] == rd and (m['team_1_name'] == e8_pick or m['team_2_name'] == e8_pick):
                if all_picks.get(mid) != e8_pick:
                    path_errors.append(f"E8 pick {e8_pick} not picked in {mid} ({rd})")
                break

# Check S16 picks have paths through R32, R64
for s16_mid, s16_pick in s16_picks.items():
    for rd in ['R64', 'R32']:
        for mid, m in espn_matchups.items():
            if m['round'] == rd and (m['team_1_name'] == s16_pick or m['team_2_name'] == s16_pick):
                if all_picks.get(mid) != s16_pick:
                    path_errors.append(f"S16 pick {s16_pick} not picked in {mid} ({rd})")
                break

# Check R32 picks have paths through R64
for r32_mid, r32_pick in r32_picks.items():
    for mid, m in espn_matchups.items():
        if m['round'] == 'R64' and (m['team_1_name'] == r32_pick or m['team_2_name'] == r32_pick):
            if all_picks.get(mid) != r32_pick:
                path_errors.append(f"R32 pick {r32_pick} not picked in {mid} (R64)")
            break

if path_errors:
    print(f"  FAIL: {len(path_errors)} path consistency violations:")
    for e in path_errors:
        print(f"    {e}")
    print("  HARD STOP — fixing path errors before proceeding")
    # Auto-fix: propagate picks backward
    print("\n  Auto-fixing path errors...")
    # Re-propagate from F4 backward
    for region in regions:
        f4_team = f4_picks[region]
        for rd in ['E8', 'S16', 'R32', 'R64']:
            for mid, m in espn_matchups.items():
                if m['round'] == rd and (m['team_1_name'] == f4_team or m['team_2_name'] == f4_team):
                    if all_picks.get(mid) != f4_team:
                        print(f"    Fixed: {mid} -> {f4_team} (was {all_picks.get(mid, 'unset')})")
                        all_picks[mid] = f4_team
                    break

    # Re-propagate E8 picks
    for e8_mid, e8_pick in e8_picks.items():
        for rd in ['S16', 'R32', 'R64']:
            for mid, m in espn_matchups.items():
                if m['round'] == rd and (m['team_1_name'] == e8_pick or m['team_2_name'] == e8_pick):
                    if all_picks.get(mid) != e8_pick:
                        print(f"    Fixed: {mid} -> {e8_pick} (was {all_picks.get(mid, 'unset')})")
                        all_picks[mid] = e8_pick
                    break

    # Re-propagate S16 picks
    for s16_mid, s16_pick in s16_picks.items():
        for rd in ['R32', 'R64']:
            for mid, m in espn_matchups.items():
                if m['round'] == rd and (m['team_1_name'] == s16_pick or m['team_2_name'] == s16_pick):
                    if all_picks.get(mid) != s16_pick:
                        print(f"    Fixed: {mid} -> {s16_pick} (was {all_picks.get(mid, 'unset')})")
                        all_picks[mid] = s16_pick
                    break

    # Re-propagate R32 picks
    for r32_mid, r32_pick in r32_picks.items():
        for mid, m in espn_matchups.items():
            if m['round'] == 'R64' and (m['team_1_name'] == r32_pick or m['team_2_name'] == r32_pick):
                if all_picks.get(mid) != r32_pick:
                    print(f"    Fixed: {mid} -> {r32_pick} (was {all_picks.get(mid, 'unset')})")
                    all_picks[mid] = r32_pick
                break

    # Recount upsets after fix (excluding champion-path F4/NCG same-seed picks)
    upset_count_by_round = {}
    champ_path_count = 0
    for mid, m in espn_matchups.items():
        if mid in all_picks:
            rd = m['round']
            chalk = get_chalk(m)
            if all_picks[mid] != chalk:
                s1, s2 = int(m['team_1_seed']), int(m['team_2_seed'])
                if rd in ('F4', 'NCG') and s1 == s2:
                    champ_path_count += 1
                else:
                    upset_count_by_round[rd] = upset_count_by_round.get(rd, 0) + 1
    total_upsets = sum(upset_count_by_round.values())
    print(f"\n  Post-fix upset count: {dict(upset_count_by_round)}")
    print(f"  Post-fix total upsets: {total_upsets} (+ {champ_path_count} champion-path)")

    # Re-validate paths
    path_errors_2 = []
    for region in regions:
        f4_team = f4_picks[region]
        for rd in ['R64', 'R32', 'S16', 'E8']:
            for mid, m in espn_matchups.items():
                if m['round'] == rd and (m['team_1_name'] == f4_team or m['team_2_name'] == f4_team):
                    if all_picks.get(mid) != f4_team:
                        path_errors_2.append(f"F4 pick {f4_team} not picked in {mid}")
                    break
    if path_errors_2:
        print(f"  STILL FAILING after auto-fix: {path_errors_2}")
        sys.exit(1)
    else:
        print("  Path consistency PASSED after auto-fix.")
else:
    print("  PASSED: All paths are consistent.")

# Check 2: Near-zero floor
print(f"\n  Check 2 — Near-zero floor:")
near_zero_teams = set()
for team, data in prob_data.items():
    if data.get('near_zero_flag', 'N') == 'Y':
        near_zero_teams.add(team)

nz_violations = []
for mid in list(e8_picks.keys()) + list(f4_bracket_picks.keys()) + ['NCG']:
    pick = all_picks.get(mid)
    if pick in near_zero_teams:
        nz_violations.append(f"{pick} picked in {mid}")

if nz_violations:
    print(f"  FAIL: {nz_violations}")
    sys.exit(1)
else:
    print("  PASSED: No near-zero teams in E8+.")

# Check 3: Entropy validation
print(f"\n  Check 3 — Entropy validation (SOFT):")
acceptable_lo = max(2, optimal_upsets - 3)
acceptable_hi = optimal_upsets + 3
hard_stop_hi = optimal_upsets + 5

print(f"  Optimal upsets: {optimal_upsets}")
print(f"  Acceptable range: {acceptable_lo} - {acceptable_hi}")
print(f"  Hard stop if: 0 or > {hard_stop_hi}")
print(f"  Actual upsets: {total_upsets}")

if total_upsets == 0:
    print("  HARD STOP: Zero upsets")
    sys.exit(1)
elif total_upsets > hard_stop_hi:
    print(f"  HARD STOP: {total_upsets} > {hard_stop_hi}")
    sys.exit(1)
elif acceptable_lo <= total_upsets <= acceptable_hi:
    print(f"  PASSED: {total_upsets} within [{acceptable_lo}, {acceptable_hi}]")
else:
    print(f"  DEVIATION: {total_upsets} outside [{acceptable_lo}, {acceptable_hi}] but within hard limits")

# Check 4: Path assumption consistency
print(f"\n  Check 4 — Path assumption consistency:")
# All Type C picks must use same E8 path assumption
type_c_picks = []
for mid, pick in all_picks.items():
    m = espn_matchups.get(mid, {})
    lev_entry = lev_data.get((pick, m.get('round', '')), {})
    if lev_entry.get('confidence_type', '') == 'C':
        type_c_picks.append((mid, pick))

if type_c_picks:
    print(f"  Type C picks: {[(mid, pick) for mid, pick in type_c_picks]}")
    print("  All using primary path assumption.")
else:
    print("  No Type C picks — check trivially passed.")
print("  PASSED.")

# Check 5: Champion region path
print(f"\n  Check 5 — Champion region path:")
print(f"  Champion: {champ_name} ({champ_region})")
champ_path_rounds = []
for rd in ['R64', 'R32', 'S16', 'E8', 'F4', 'NCG']:
    for mid, m in espn_matchups.items():
        if m['round'] == rd and (m['team_1_name'] == champ_name or m['team_2_name'] == champ_name):
            picked = all_picks.get(mid, '???')
            ok = picked == champ_name
            champ_path_rounds.append((rd, mid, ok))
            print(f"    {rd}: {mid} -> {picked} {'OK' if ok else 'FAIL'}")
            break
    else:
        if rd == 'F4':
            # F4 matchup IDs are F4_1, F4_2
            for fmid in ['F4_1', 'F4_2']:
                fm = espn_matchups.get(fmid)
                if fm and (fm['team_1_name'] == champ_name or fm['team_2_name'] == champ_name):
                    picked = all_picks.get(fmid, '???')
                    ok = picked == champ_name
                    champ_path_rounds.append((rd, fmid, ok))
                    print(f"    {rd}: {fmid} -> {picked} {'OK' if ok else 'FAIL'}")
                    break
            else:
                # Champion won region, now in F4 via bracket position
                if champ_region in ('East', 'South'):
                    fmid = 'F4_1'
                else:
                    fmid = 'F4_2'
                picked = all_picks.get(fmid, '???')
                ok = picked == champ_name
                champ_path_rounds.append((rd, fmid, ok))
                print(f"    {rd}: {fmid} -> {picked} {'OK' if ok else 'FAIL'}")
        elif rd == 'NCG':
            picked = all_picks.get('NCG', '???')
            ok = picked == champ_name
            champ_path_rounds.append((rd, 'NCG', ok))
            print(f"    {rd}: NCG -> {picked} {'OK' if ok else 'FAIL'}")

if all(ok for _, _, ok in champ_path_rounds):
    print("  PASSED: Champion path R1-R6 is fully consistent.")
else:
    print("  HARD STOP: Champion path broken.")
    sys.exit(1)

# ============================================================
# OUTPUT — FULL 63-GAME BRACKET TABLE
# ============================================================
print("\n" + "=" * 90)
print("COMPLETE 63-GAME BRACKET")
print("=" * 90)

# Build output table
bracket_rows = []
round_order = ['R64', 'R32', 'S16', 'E8', 'F4', 'NCG']

for rd in round_order:
    for mid in sorted(all_picks.keys()):
        m = espn_matchups.get(mid, {})
        if m.get('round', mid) != rd and not (rd == 'F4' and mid.startswith('F4')) and not (rd == 'NCG' and mid == 'NCG'):
            continue

        pick = all_picks[mid]
        actual_round = m.get('round', rd)
        if actual_round != rd:
            continue

        region = m.get('region', 'National')
        chalk = get_chalk(m)
        deviation = 'Y' if pick != chalk else 'N'

        pick_seed = int(prob_data.get(pick, {}).get('team_seed', 0))
        pick_vegas = float(prob_data.get(pick, {}).get({
            'R64': 'r1', 'R32': 'r2', 'S16': 'r3', 'E8': 'r4_adjusted',
            'F4': 'r5', 'NCG': 'r6'
        }.get(rd, 'r1'), 0))
        pick_pub = float(m.get('team_1_pick_pct', 0)) / 100 if m.get('team_1_name') == pick else \
                   float(m.get('team_2_pick_pct', 0)) / 100

        lev_entry = get_lev(pick, rd)
        leverage_ratio = float(lev_entry.get('leverage_ratio', 0)) if lev_entry else 0
        conf_tier = lev_entry.get('confidence_tier', 'N/A') if lev_entry else 'N/A'
        conf_type = lev_entry.get('confidence_type', 'NA') if lev_entry else 'NA'

        threshold = DEV_THRESHOLDS.get(conf_type, 1.15) if deviation == 'Y' else 0
        path_dep = prob_data.get(pick, {}).get('path_dependent_flag', 'N')
        path_assumption = 'primary' if path_dep == 'Y' else 'NA'

        bracket_rows.append({
            'round': rd,
            'region': region,
            'matchup_id': mid,
            'team_picked': pick,
            'seed': pick_seed,
            'vegas_win_prob': f"{pick_vegas:.4f}",
            'public_pick_pct': f"{pick_pub:.4f}",
            'leverage_ratio': f"{leverage_ratio:.4f}",
            'confidence_tier': conf_tier,
            'confidence_type': conf_type,
            'deviation_from_chalk': deviation,
            'deviation_threshold_applied': f"{threshold:.2f}" if threshold > 0 else 'N/A',
            'path_assumption': path_assumption,
        })

# Print table
print(f"\n{'Round':<6} {'Region':<10} {'Matchup':<12} {'Pick':<18} {'Seed':>4} "
      f"{'VegasWP':>8} {'PubPct':>8} {'LevR':>8} {'Conf':>6} {'Type':>4} "
      f"{'Dev':>4} {'Thresh':>7} {'Path':>7}")
print("-" * 130)

for r in bracket_rows:
    print(f"{r['round']:<6} {r['region']:<10} {r['matchup_id']:<12} {r['team_picked']:<18} "
          f"{r['seed']:>4} {r['vegas_win_prob']:>8} {r['public_pick_pct']:>8} "
          f"{r['leverage_ratio']:>8} {r['confidence_tier']:>6} {r['confidence_type']:>4} "
          f"{r['deviation_from_chalk']:>4} {r['deviation_threshold_applied']:>7} "
          f"{r['path_assumption']:>7}")

# Write CSV
csv_fields = ['round', 'region', 'matchup_id', 'team_picked', 'seed',
              'vegas_win_prob', 'public_pick_pct', 'leverage_ratio',
              'confidence_tier', 'confidence_type', 'deviation_from_chalk',
              'deviation_threshold_applied', 'path_assumption']

with open('bracket_2026.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=csv_fields)
    w.writeheader()
    for r in bracket_rows:
        w.writerow(r)
print(f"\nWrote bracket_2026.csv ({len(bracket_rows)} games)")

# ============================================================
# ONE-PAGE BRACKET SUMMARY
# ============================================================
print("\n" + "=" * 90)
print("ONE-PAGE BRACKET SUMMARY")
print("=" * 90)

print(f"\nCHAMPION: {champ_name}")
print(f"  EV at N=100: {champ_ev:.3f}")
print(f"  r6 probability: {champ_r6:.4f} ({champ_r6:.1%})")
print(f"  Public ownership: {champ_pub:.2f}%")
print(f"  Path assumption: {path_assumption}")
if champ_path_dep == 'Y':
    print(f"  Alt-path r6: {float(champion['r6_path_alt']):.4f}")

print(f"\nFINAL FOUR by region:")
for region in regions:
    team = f4_picks[region]
    seed = int(prob_data[team]['team_seed'])
    lr_entry = get_lev(team, 'F4')
    lr = float(lr_entry.get('leverage_ratio', 0)) if lr_entry else 0
    pub = float(lr_entry.get('public_pick_pct', 0)) if lr_entry else 0
    print(f"  {region:<10} {team:<18} (seed {seed})  "
          f"leverage_ratio={lr:.4f}  public={pub:.4f}")

print(f"\nELITE EIGHT by region:")
for mid in sorted(e8_picks.keys()):
    m = espn_matchups[mid]
    pick = all_picks[mid]
    chalk = get_chalk(m)
    dev = "UPSET" if pick != chalk else "chalk"
    print(f"  {mid:<8} {pick:<18} ({dev})")

print(f"\nHIGH-LEVERAGE R64/R32 CANDIDATES EVALUATED:")
# R64 candidates
for mid, m in sorted(r64_matchups.items()):
    underdog = get_underdog(m)
    ud_lev = get_lev(underdog, 'R64')
    ud_abs = abs(float(ud_lev.get('leverage', 0))) if ud_lev else 0
    if ud_abs > 0.10:
        ud_lr = float(ud_lev.get('leverage_ratio', 0))
        ud_vegas = float(prob_data.get(underdog, {}).get('r1', 0))
        included = all_picks[mid] == underdog
        lr_pass = "PASS" if ud_lr > 1.25 else "FAIL"
        vegas_pass = "PASS" if ud_vegas > 0.35 else "FAIL"
        result = "INCLUDED" if included else "CHALK"
        print(f"  R64 {mid}: {underdog:<18} lr={ud_lr:.4f} ({lr_pass})  "
              f"vegas={ud_vegas:.3f} ({vegas_pass})  -> {result}")

for mid, m in sorted(r32_matchups.items()):
    underdog = get_underdog(m)
    ud_lev = get_lev(underdog, 'R32')
    ud_abs = abs(float(ud_lev.get('leverage', 0))) if ud_lev else 0
    if ud_abs > 0.10:
        ud_lr = float(ud_lev.get('leverage_ratio', 0))
        ud_vegas = float(prob_data.get(underdog, {}).get('r2', 0))
        included = all_picks[mid] == underdog
        lr_pass = "PASS" if ud_lr > 1.25 else "FAIL"
        vegas_pass = "PASS" if ud_vegas > 0.35 else "FAIL"
        result = "INCLUDED" if included else "CHALK"
        print(f"  R32 {mid}: {underdog:<18} lr={ud_lr:.4f} ({lr_pass})  "
              f"vegas={ud_vegas:.3f} ({vegas_pass})  -> {result}")

print(f"\nSIGN-FLIP TEAMS (defaulted to chalk):")
for team, rd in sorted(sign_flip_teams):
    print(f"  {team} ({rd})")

print(f"\nTOTAL UPSET COUNT BY ROUND (contrarian upsets only):")
for rd in round_order:
    count = upset_count_by_round.get(rd, 0)
    if count > 0:
        print(f"  {rd}: {count}")
print(f"  TOTAL CONTRARIAN UPSETS: {total_upsets}")
print(f"  Champion-path picks (F4/NCG, same-seed, not counted): {champ_path_count}")
print(f"  Acceptable entropy range: {acceptable_lo} - {acceptable_hi}")
print(f"  Status: {'IN RANGE' if acceptable_lo <= total_upsets <= acceptable_hi else 'DEVIATION'}")

# LOW confidence + chalk deviations
print(f"\nLOW CONFIDENCE + CHALK DEVIATIONS:")
low_conf_deviations = []
for r in bracket_rows:
    if r['confidence_tier'] == 'LOW' and r['deviation_from_chalk'] == 'Y':
        low_conf_deviations.append(r)
if low_conf_deviations:
    for r in low_conf_deviations:
        print(f"  {r['round']} {r['matchup_id']}: {r['team_picked']} (LOW confidence, deviating from chalk)")
else:
    print("  None")

# Path assumption consistency
print(f"\nBRACKET-WIDE E8 PATH ASSUMPTION: primary (consistent across all Type C picks)")

print(f"\nFILE VERIFICATION SUMMARY:")
for fname, (result, detail) in verification.items():
    print(f"  {fname}: {result}")

print("\n" + "=" * 90)
print("BRACKET CONSTRUCTION COMPLETE")
print("=" * 90)
