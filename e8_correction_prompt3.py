#!/usr/bin/env python3
"""
Prompt 3 — E8 Correction
Derive game-level E8 probabilities, apply conservative shrinkage,
propagate to r4, and update master_data and leverage_matrix.
"""
import csv
import sys

ROUNDS = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']
ROUND_WEIGHTS = {'r1': 10, 'r2': 20, 'r3': 40, 'r4': 80, 'r5': 160, 'r6': 320}

# Bracket halves derived from ESPN R64 matchup structure.
# R64 matchups 1-4 = top half, 5-8 = bottom half per region.
# Top half seeds: 1,16,8,9,5,12,4,13
# Bottom half seeds: 6,11,3,14,7,10,2,15
# But we'll use S16 structure directly for clarity:
#   S16_1 feeds from R64 matchups 1-2 and 3-4 (top half)
#   S16_2 feeds from R64 matchups 5-6 and 7-8 (bottom half)


def load_espn_bracket():
    """Load ESPN bracket to determine bracket half assignments."""
    top_half = {}  # region -> set of team names
    bottom_half = {}  # region -> set of team names

    with open('espn_picks_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rnd = row['round']
            region = row['region']
            if rnd != 'S16':
                continue
            mid = row['matchup_id']
            t1 = row['team_1_name'].strip()
            t2 = row['team_2_name'].strip()

            if region not in top_half:
                top_half[region] = set()
                bottom_half[region] = set()

            # S16_1 = top half of bracket, S16_2 = bottom half
            if mid.endswith('_1'):
                top_half[region].add(t1)
                top_half[region].add(t2)
            elif mid.endswith('_2'):
                bottom_half[region].add(t1)
                bottom_half[region].add(t2)

    # Now extend: any team that could reach S16 on the same side belongs
    # to that half. Load R64 to get all teams per region per half.
    all_top = {}
    all_bottom = {}
    with open('espn_picks_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rnd = row['round']
            region = row['region']
            if rnd != 'R64':
                continue
            mid = row['matchup_id']
            t1 = row['team_1_name'].strip()
            t2 = row['team_2_name'].strip()

            if region not in all_top:
                all_top[region] = set()
                all_bottom[region] = set()

            # R64 matchups 1-4 = top half, 5-8 = bottom half
            matchup_num = int(mid.split('_')[-1])
            if matchup_num <= 4:
                all_top[region].add(t1)
                all_top[region].add(t2)
            else:
                all_bottom[region].add(t1)
                all_bottom[region].add(t2)

    return all_top, all_bottom


def load_master():
    teams = []
    with open('master_data_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = {'team_name': row['team_name'], 'team_seed': int(row['team_seed']),
                 'region': row['region']}
            for r in ROUNDS:
                t[f'vegas_{r}'] = float(row[f'vegas_{r}'])
                t[f'vegas_{r}_raw'] = float(row[f'vegas_{r}_raw'])
                t[f'public_{r}'] = float(row[f'public_{r}'])
            t['near_zero_flag'] = row['near_zero_flag']
            t['first_four_flag'] = row['first_four_flag']
            teams.append(t)
    return teams


def load_leverage():
    rows = []
    with open('leverage_matrix_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            row['vegas_prob'] = float(row['vegas_prob'])
            row['public_pick_pct'] = float(row['public_pick_pct'])
            row['leverage'] = float(row['leverage'])
            row['leverage_ratio'] = float(row['leverage_ratio']) if row['leverage_ratio'] else None
            row['round_weighted_leverage'] = float(row['round_weighted_leverage'])
            rows.append(row)
    return rows


def step1_assess_structure(teams, top_half, bottom_half):
    """Identify most likely E8 matchups per region."""
    print("=" * 90)
    print("STEP 1 — ASSESS E8 STRUCTURE")
    print("=" * 90)

    regions = ['East', 'South', 'West', 'Midwest']
    matchups = {}  # region -> {'primary': (top_team, bottom_team), 'alt_top': ..., 'alt_bottom': ...}

    for region in regions:
        region_teams = [t for t in teams if t['region'] == region]
        top_teams = [t for t in region_teams if t['team_name'] in top_half.get(region, set())]
        bottom_teams = [t for t in region_teams if t['team_name'] in bottom_half.get(region, set())]

        # Sort by vegas_r3 descending
        top_sorted = sorted(top_teams, key=lambda x: -x['vegas_r3'])
        bottom_sorted = sorted(bottom_teams, key=lambda x: -x['vegas_r3'])

        matchups[region] = {
            'top1': top_sorted[0] if len(top_sorted) > 0 else None,
            'top2': top_sorted[1] if len(top_sorted) > 1 else None,
            'bot1': bottom_sorted[0] if len(bottom_sorted) > 0 else None,
            'bot2': bottom_sorted[1] if len(bottom_sorted) > 1 else None,
        }

        t1, b1 = matchups[region]['top1'], matchups[region]['bot1']
        if t1 and b1:
            denom = t1['vegas_r4'] + b1['vegas_r4']
            impl_t = t1['vegas_r4'] / denom if denom > 0 else 0
            impl_b = b1['vegas_r4'] / denom if denom > 0 else 0
            matchups[region]['primary_impl_top'] = impl_t
            matchups[region]['primary_impl_bot'] = impl_b

    print(f"\n{'Region':<10} {'Top Half':<18} {'Sd':>2} {'r3':>7} {'r4':>7} | "
          f"{'Bottom Half':<18} {'Sd':>2} {'r3':>7} {'r4':>7} | "
          f"{'GameImpl':>8} {'GameImpl':>8}")
    print("-" * 110)
    for region in regions:
        m = matchups[region]
        t, b = m['top1'], m['bot1']
        if t and b:
            print(f"{region:<10} {t['team_name']:<18} {t['team_seed']:>2} "
                  f"{t['vegas_r3']:>7.4f} {t['vegas_r4']:>7.4f} | "
                  f"{b['team_name']:<18} {b['team_seed']:>2} "
                  f"{b['vegas_r3']:>7.4f} {b['vegas_r4']:>7.4f} | "
                  f"{m['primary_impl_top']:>8.4f} {m['primary_impl_bot']:>8.4f}")
    sys.stdout.flush()

    return matchups


def step2_assess_correction(matchups):
    """Assess whether correction is warranted using r3 strength ratio."""
    print("\n" + "=" * 90)
    print("STEP 2 — ASSESS WHETHER CORRECTION IS WARRANTED")
    print("=" * 90)

    print(f"\n{'Region':<10} {'Favorite':<18} {'Underdog':<18} "
          f"{'GameImpl':>8} {'r3Ratio':>8} {'ExpImpl':>8} {'Gap':>8} {'OverPrice':>9}")
    print("-" * 100)

    assessments = {}
    regions = ['East', 'South', 'West', 'Midwest']

    for region in regions:
        m = matchups[region]
        t, b = m['top1'], m['bot1']
        if not t or not b:
            continue

        impl_t = m['primary_impl_top']
        impl_b = m['primary_impl_bot']

        # Determine favorite
        if impl_t >= impl_b:
            fav, dog = t, b
            fav_impl, dog_impl = impl_t, impl_b
        else:
            fav, dog = b, t
            fav_impl, dog_impl = impl_b, impl_t

        # r3 strength ratio as proxy for relative quality
        r3_ratio = fav['vegas_r3'] / dog['vegas_r3'] if dog['vegas_r3'] > 0 else float('inf')

        # Expected game implied from r3 ratio: fav_share = ratio / (1 + ratio)
        expected_impl = r3_ratio / (1 + r3_ratio)

        gap = fav_impl - expected_impl
        over_priced = 'YES' if fav_impl > 0.70 else ('WATCH' if gap > 0.05 else 'NO')

        assessments[region] = {
            'fav': fav, 'dog': dog,
            'fav_impl': fav_impl, 'dog_impl': dog_impl,
            'r3_ratio': r3_ratio, 'expected_impl': expected_impl,
            'gap': gap, 'over_priced': over_priced,
        }

        print(f"{region:<10} {fav['team_name']:<18} {dog['team_name']:<18} "
              f"{fav_impl:>8.4f} {r3_ratio:>8.2f} {expected_impl:>8.4f} "
              f"{gap:>+8.4f} {over_priced:>9}")

    sys.stdout.flush()
    return assessments


def step3_apply_shrinkage(matchups):
    """Apply 25% shrinkage toward 50/50 for all E8 matchups."""
    print("\n" + "=" * 90)
    print("STEP 3 — APPLY CONSERVATIVE SHRINKAGE (25% toward 50/50)")
    print("=" * 90)

    corrections = {}  # team_name -> {e8_game_implied, e8_game_corrected, ...}
    regions = ['East', 'South', 'West', 'Midwest']

    for region in regions:
        m = matchups[region]
        t, b = m['top1'], m['bot1']
        if not t or not b:
            continue

        impl_t = m['primary_impl_top']
        impl_b = m['primary_impl_bot']

        # Determine favorite and apply shrinkage
        if impl_t >= 0.55:
            corr_t = impl_t * 0.75 + 0.50 * 0.25
            corr_b = 1.0 - corr_t
        elif impl_b >= 0.55:
            corr_b = impl_b * 0.75 + 0.50 * 0.25
            corr_t = 1.0 - corr_b
        else:
            # Neither is favorite at 0.55+, no shrinkage needed
            corr_t = impl_t
            corr_b = impl_b

        corrections[t['team_name']] = {
            'e8_game_implied': impl_t,
            'e8_game_corrected': corr_t,
            'region': region,
            'opponent': b['team_name'],
            'half': 'top',
        }
        corrections[b['team_name']] = {
            'e8_game_implied': impl_b,
            'e8_game_corrected': corr_b,
            'region': region,
            'opponent': t['team_name'],
            'half': 'bottom',
        }

        # Also compute alt matchup corrections
        # Alt 1: top1 vs bot2
        t2, b2 = m.get('top2'), m.get('bot2')

        # top1 vs bot2
        if t and b2:
            denom = t['vegas_r4'] + b2['vegas_r4']
            if denom > 0:
                alt_impl_t = t['vegas_r4'] / denom
                alt_impl_b2 = b2['vegas_r4'] / denom
                if alt_impl_t >= 0.55:
                    alt_corr_t = alt_impl_t * 0.75 + 0.50 * 0.25
                    alt_corr_b2 = 1.0 - alt_corr_t
                elif alt_impl_b2 >= 0.55:
                    alt_corr_b2 = alt_impl_b2 * 0.75 + 0.50 * 0.25
                    alt_corr_t = 1.0 - alt_corr_b2
                else:
                    alt_corr_t = alt_impl_t
                    alt_corr_b2 = alt_impl_b2
                corrections[t['team_name']]['alt_opponent'] = b2['team_name']
                corrections[t['team_name']]['alt_game_implied'] = alt_impl_t
                corrections[t['team_name']]['alt_game_corrected'] = alt_corr_t
                corrections[b2['team_name']] = corrections.get(b2['team_name'], {
                    'region': region, 'half': 'bottom',
                })
                corrections[b2['team_name']]['alt_opponent'] = t['team_name']
                corrections[b2['team_name']]['alt_game_implied'] = alt_impl_b2
                corrections[b2['team_name']]['alt_game_corrected'] = alt_corr_b2

        # top2 vs bot1
        if t2 and b:
            denom = t2['vegas_r4'] + b['vegas_r4']
            if denom > 0:
                alt_impl_t2 = t2['vegas_r4'] / denom
                alt_impl_b = b['vegas_r4'] / denom
                if alt_impl_b >= 0.55:
                    alt_corr_b = alt_impl_b * 0.75 + 0.50 * 0.25
                    alt_corr_t2 = 1.0 - alt_corr_b
                elif alt_impl_t2 >= 0.55:
                    alt_corr_t2 = alt_impl_t2 * 0.75 + 0.50 * 0.25
                    alt_corr_b = 1.0 - alt_corr_t2
                else:
                    alt_corr_t2 = alt_impl_t2
                    alt_corr_b = alt_impl_b
                corrections[b['team_name']]['alt_opponent'] = t2['team_name']
                corrections[b['team_name']]['alt_game_implied'] = alt_impl_b
                corrections[b['team_name']]['alt_game_corrected'] = alt_corr_b
                corrections[t2['team_name']] = corrections.get(t2['team_name'], {
                    'region': region, 'half': 'top',
                })
                corrections[t2['team_name']]['alt_opponent'] = b['team_name']
                corrections[t2['team_name']]['alt_game_implied'] = alt_impl_t2
                corrections[t2['team_name']]['alt_game_corrected'] = alt_corr_t2

    print(f"\n{'Team':<18} {'Region':<10} {'Implied':>8} {'Corrected':>9} {'Delta':>8} "
          f"| {'AltOpp':<18} {'AltImpl':>8} {'AltCorr':>9}")
    print("-" * 110)
    for name in sorted(corrections.keys(), key=lambda x: -corrections[x].get('e8_game_implied', 0)):
        c = corrections[name]
        if 'e8_game_implied' not in c:
            continue
        alt_opp = c.get('alt_opponent', '-')
        alt_impl = c.get('alt_game_implied', 0)
        alt_corr = c.get('alt_game_corrected', 0)
        delta = c['e8_game_corrected'] - c['e8_game_implied']
        print(f"{name:<18} {c['region']:<10} {c['e8_game_implied']:>8.4f} "
              f"{c['e8_game_corrected']:>9.4f} {delta:>+8.4f} | "
              f"{alt_opp:<18} {alt_impl:>8.4f} {alt_corr:>9.4f}")
    sys.stdout.flush()

    return corrections


def step4_propagate(teams, corrections, matchups):
    """Propagate corrected game probabilities to r4."""
    print("\n" + "=" * 90)
    print("STEP 4 — PROPAGATE TO R4")
    print("=" * 90)

    team_lookup = {t['team_name']: t for t in teams}

    for t in teams:
        name = t['team_name']
        c = corrections.get(name)

        t['vegas_r4_original'] = t['vegas_r4']
        t['e8_game_implied'] = ''
        t['e8_game_corrected'] = ''
        t['vegas_r4_adjusted'] = t['vegas_r4']
        t['vegas_r4_adjusted_alt'] = t['vegas_r4']
        t['path_dependent_flag'] = 'N'

        if c and 'e8_game_corrected' in c:
            t['e8_game_implied'] = c['e8_game_implied']
            t['e8_game_corrected'] = c['e8_game_corrected']
            t['vegas_r4_adjusted'] = t['vegas_r3'] * c['e8_game_corrected']

            # Alt scenario
            if 'alt_game_corrected' in c:
                t['vegas_r4_adjusted_alt'] = t['vegas_r3'] * c['alt_game_corrected']
            else:
                t['vegas_r4_adjusted_alt'] = t['vegas_r4_adjusted']

            if abs(t['vegas_r4_adjusted'] - t['vegas_r4_adjusted_alt']) > 0.05:
                t['path_dependent_flag'] = 'Y'

    # Table 1: E8 corrections
    print(f"\n{'Region':<10} {'Team':<18} {'Sd':>2} {'r4_orig':>8} {'GameImpl':>8} "
          f"{'GameCorr':>8} {'r4_adj':>8} {'Delta':>8}")
    print("-" * 90)
    regions = ['East', 'South', 'West', 'Midwest']
    for region in regions:
        m = matchups[region]
        for key in ['top1', 'bot1']:
            team = m[key]
            if team:
                t = team_lookup[team['team_name']]
                # Refresh from updated teams list
                for ut in teams:
                    if ut['team_name'] == team['team_name']:
                        t = ut
                        break
                delta = t['vegas_r4_adjusted'] - t['vegas_r4_original']
                impl = t['e8_game_implied']
                corr = t['e8_game_corrected']
                impl_s = f"{impl:.4f}" if impl != '' else '-'
                corr_s = f"{corr:.4f}" if corr != '' else '-'
                print(f"{region:<10} {t['team_name']:<18} {t['team_seed']:>2} "
                      f"{t['vegas_r4_original']:>8.4f} {impl_s:>8} {corr_s:>8} "
                      f"{t['vegas_r4_adjusted']:>8.4f} {delta:>+8.4f}")

    # Table 2: Path dependent teams
    print("\n" + "-" * 90)
    print("PATH-DEPENDENT TEAMS (|r4_adj - r4_adj_alt| > 0.05)")
    print("-" * 90)
    pd_teams = [t for t in teams if t['path_dependent_flag'] == 'Y']
    if pd_teams:
        print(f"{'Team':<18} {'Sd':>2} {'Region':<10} {'r4_adj':>8} {'r4_adj_alt':>10} {'Range':>8}")
        for t in pd_teams:
            rng = abs(t['vegas_r4_adjusted'] - t['vegas_r4_adjusted_alt'])
            print(f"{t['team_name']:<18} {t['team_seed']:>2} {t['region']:<10} "
                  f"{t['vegas_r4_adjusted']:>8.4f} {t['vegas_r4_adjusted_alt']:>10.4f} {rng:>8.4f}")
    else:
        print("  No teams flagged as path-dependent.")
    sys.stdout.flush()

    return teams


def step5_update_files(teams, leverage_rows):
    """Update master_data_2026.csv and leverage_matrix_2026.csv."""
    print("\n" + "=" * 90)
    print("STEP 5 — UPDATE FILES")
    print("=" * 90)

    # Update master_data_2026.csv
    out_cols = (
        ['team_name', 'team_seed', 'region']
        + [f'vegas_{r}' for r in ROUNDS]
        + [f'vegas_{r}_raw' for r in ROUNDS]
        + ['public_r1', 'public_r2', 'public_r3', 'public_r4', 'public_r5', 'public_r6']
        + ['near_zero_flag', 'first_four_flag']
        + ['e8_game_implied', 'e8_game_corrected',
           'vegas_r4_original', 'vegas_r4_adjusted', 'vegas_r4_adjusted_alt',
           'path_dependent_flag']
    )

    with open('master_data_2026.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_cols, extrasaction='ignore')
        writer.writeheader()
        for t in teams:
            row = {}
            for col in out_cols:
                val = t.get(col, '')
                if isinstance(val, float):
                    row[col] = round(val, 6)
                else:
                    row[col] = val
            writer.writerow(row)
    print(f"  Updated master_data_2026.csv ({len(teams)} rows, {len(out_cols)} columns)")

    # Update leverage_matrix_2026.csv: replace r4 vegas_prob with adjusted, recompute leverage
    team_lookup = {t['team_name']: t for t in teams}
    sign_flip_teams = set()

    for row in leverage_rows:
        if row['round'] == 'r4':
            t = team_lookup.get(row['team_name'])
            if t and t['vegas_r4_adjusted'] != t.get('vegas_r4_original', t['vegas_r4']):
                row['vegas_prob'] = t['vegas_r4_adjusted']
                public = row['public_pick_pct']
                row['leverage'] = row['vegas_prob'] - public
                if public == 0:
                    row['leverage_ratio'] = None
                    row['zero_ownership_flag'] = 'Y'
                else:
                    row['leverage_ratio'] = row['vegas_prob'] / public
                    row['zero_ownership_flag'] = 'N'
                row['round_weighted_leverage'] = row['leverage'] * ROUND_WEIGHTS['r4']
                row['high_signal_flag'] = 'Y' if abs(row['leverage']) > 0.10 else 'N'

            # Sign flip: check if leverage changes sign between adjusted and alt
            if t:
                lev_primary = t['vegas_r4_adjusted'] - row['public_pick_pct']
                lev_alt = t['vegas_r4_adjusted_alt'] - row['public_pick_pct']
                if (lev_primary > 0 and lev_alt < 0) or (lev_primary < 0 and lev_alt > 0):
                    row['sign_flip_flag'] = 'Y'
                    sign_flip_teams.add(row['team_name'])
                else:
                    row['sign_flip_flag'] = 'N'

    # Save leverage matrix
    lev_cols = [
        'team_name', 'team_seed', 'region', 'round',
        'vegas_prob', 'public_pick_pct',
        'leverage', 'leverage_ratio', 'round_weighted_leverage',
        'high_signal_flag', 'zero_ownership_flag', 'sign_flip_flag',
        'prop_norm_caution_flag',
    ]
    with open('leverage_matrix_2026.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=lev_cols, extrasaction='ignore')
        writer.writeheader()
        for row in leverage_rows:
            out = dict(row)
            out['leverage'] = round(float(out['leverage']), 6)
            if out['leverage_ratio'] is not None:
                out['leverage_ratio'] = round(float(out['leverage_ratio']), 4)
            else:
                out['leverage_ratio'] = ''
            out['round_weighted_leverage'] = round(float(out['round_weighted_leverage']), 4)
            out['vegas_prob'] = round(float(out['vegas_prob']), 6)
            out['public_pick_pct'] = round(float(out['public_pick_pct']), 6)
            writer.writerow(out)
    print(f"  Updated leverage_matrix_2026.csv ({len(leverage_rows)} rows)")

    # Table 3: Sign flip teams
    print("\n" + "-" * 90)
    print("SIGN-FLIP TEAMS (leverage changes sign between primary and alt E8 opponent)")
    print("  These teams default to chalk in bracket construction regardless of leverage.")
    print("-" * 90)
    if sign_flip_teams:
        print(f"{'Team':<18} {'Sd':>2} {'Region':<10} {'r4_adj':>8} {'r4_adj_alt':>10} "
              f"{'Public_r4':>9} {'Lev_pri':>8} {'Lev_alt':>8}")
        for name in sorted(sign_flip_teams):
            t = team_lookup[name]
            pub = t['public_r4']
            lp = t['vegas_r4_adjusted'] - pub
            la = t['vegas_r4_adjusted_alt'] - pub
            print(f"{name:<18} {t['team_seed']:>2} {t['region']:<10} "
                  f"{t['vegas_r4_adjusted']:>8.4f} {t['vegas_r4_adjusted_alt']:>10.4f} "
                  f"{pub:>9.4f} {lp:>+8.4f} {la:>+8.4f}")
    else:
        print("  No sign-flip teams detected.")
    sys.stdout.flush()


def main():
    print("=" * 90)
    print("PROMPT 3 — E8 CORRECTION")
    print("=" * 90)
    sys.stdout.flush()

    top_half, bottom_half = load_espn_bracket()
    teams = load_master()
    leverage_rows = load_leverage()
    print(f"Loaded {len(teams)} teams, {len(leverage_rows)} leverage rows")
    sys.stdout.flush()

    # Step 1
    matchups = step1_assess_structure(teams, top_half, bottom_half)

    # Step 2
    assessments = step2_assess_correction(matchups)

    # Step 3
    corrections = step3_apply_shrinkage(matchups)

    # Step 4
    teams = step4_propagate(teams, corrections, matchups)

    # Step 5
    step5_update_files(teams, leverage_rows)

    print("\n" + "=" * 90)
    print("PROMPT 3 COMPLETE")
    print("=" * 90)
    sys.stdout.flush()


if __name__ == '__main__':
    main()
