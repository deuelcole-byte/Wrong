#!/usr/bin/env python3
"""
Prompt 2 — Leverage Calculation
Compute leverage (vegas - public) and leverage_ratio (vegas / public)
for every team and round. Apply round weights, detect systematic patterns,
and identify E8 sign-flip candidates.
"""
import csv
import sys

ROUNDS = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']
ROUND_WEIGHTS = {'r1': 10, 'r2': 20, 'r3': 40, 'r4': 80, 'r5': 160, 'r6': 320}

# Teams below seed 5 in r5/r6 get lower-confidence flag due to proportional
# normalization inflating longshot late-round probabilities.
PROP_NORM_SEED_THRESHOLD = 5


def load_master():
    teams = []
    with open('master_data_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = {
                'team_name': row['team_name'],
                'team_seed': int(row['team_seed']),
                'region': row['region'],
                'near_zero_flag': row['near_zero_flag'],
                'first_four_flag': row['first_four_flag'],
            }
            for r in ROUNDS:
                t[f'vegas_{r}'] = float(row[f'vegas_{r}'])
                t[f'public_{r}'] = float(row[f'public_{r}'])
            teams.append(t)
    return teams


def compute_leverage(teams):
    """Compute leverage, leverage_ratio, round_weighted_leverage for all team-rounds."""
    rows = []
    for t in teams:
        for r in ROUNDS:
            vegas = t[f'vegas_{r}']
            public = t[f'public_{r}']
            leverage = vegas - public
            if public == 0:
                leverage_ratio = None
                zero_ownership = 'Y'
            else:
                leverage_ratio = vegas / public
                zero_ownership = 'N'
            rwl = leverage * ROUND_WEIGHTS[r]

            high_signal = 'Y' if abs(leverage) > 0.10 else 'N'

            # Flag longshots (seed > 5) in late rounds (r5, r6) as lower
            # confidence due to proportional normalization artifact.
            prop_norm_flag = 'N'
            if t['team_seed'] > PROP_NORM_SEED_THRESHOLD and r in ('r5', 'r6'):
                prop_norm_flag = 'Y'

            rows.append({
                'team_name': t['team_name'],
                'team_seed': t['team_seed'],
                'region': t['region'],
                'round': r,
                'vegas_prob': vegas,
                'public_pick_pct': public,
                'leverage': leverage,
                'leverage_ratio': leverage_ratio,
                'round_weighted_leverage': rwl,
                'high_signal_flag': high_signal,
                'zero_ownership_flag': zero_ownership,
                'sign_flip_flag': '',
                'prop_norm_caution_flag': prop_norm_flag,
            })
    return rows


def systematic_pattern_check(leverage_rows):
    """Compute mean leverage, mean abs leverage, over/under-picked counts per round."""
    print("\n" + "=" * 80)
    print("TABLE 3: SYSTEMATIC PATTERN CHECK")
    print("=" * 80)
    print(f"{'Round':<6} {'Mean Lev':>10} {'Mean |Lev|':>11} {'N Over':>8} {'N Under':>9} {'Interpretation'}")
    print("-" * 80)

    high_champ_concentration = False
    champ_drivers = []

    for r in ROUNDS:
        rr = [row for row in leverage_rows if row['round'] == r]
        leverages = [row['leverage'] for row in rr]
        mean_lev = sum(leverages) / len(leverages)
        mean_abs = sum(abs(l) for l in leverages) / len(leverages)
        n_over = sum(1 for l in leverages if l < -0.05)
        n_under = sum(1 for l in leverages if l > 0.05)

        interp = ""
        if r == 'r6' and mean_lev < -0.10:
            high_champ_concentration = True
            interp = "HIGH CHAMP CONCENTRATION"
            champ_drivers = sorted(rr, key=lambda x: x['leverage'])[:5]

        print(f"{r:<6} {mean_lev:>+10.4f} {mean_abs:>11.4f} {n_over:>8} {n_under:>9}   {interp}")

    sys.stdout.flush()

    if high_champ_concentration:
        print("\n  high_championship_concentration = Y")
        print("  Drivers (most over-picked at r6):")
        for d in champ_drivers:
            print(f"    {d['team_name']:<18} vegas_r6={d['vegas_prob']:.4f}  "
                  f"public_r6={d['public_pick_pct']:.4f}  leverage={d['leverage']:+.4f}")
    else:
        print("\n  high_championship_concentration = N")
    sys.stdout.flush()

    return high_champ_concentration


def e8_sign_flip_detection(teams, leverage_rows):
    """
    For E8 (r4), identify probable matchups and check for sign flips.
    Each region's E8 pits the top-half winner vs bottom-half winner.
    """
    print("\n" + "=" * 80)
    print("TABLE 4: E8 SIGN-FLIP DETECTION")
    print("=" * 80)

    # Standard bracket: seeds 1,8,5,12,4,13,6,11 on top half;
    #                   seeds 2,7,3,14,10,15 on bottom half
    # Top half = seeds whose R32 matchups are in the 1-seed quadrant
    top_half_seeds = {1, 8, 9, 16, 5, 12, 13, 4}
    bottom_half_seeds = {2, 7, 10, 15, 3, 14, 11, 6}

    sign_flip_teams = set()
    all_e8_analysis = []

    for region in ['East', 'South', 'West', 'Midwest']:
        region_teams = [t for t in teams if t['region'] == region]

        top = [t for t in region_teams if t['team_seed'] in top_half_seeds]
        bottom = [t for t in region_teams if t['team_seed'] in bottom_half_seeds]

        # Sort by vegas_r3 (probability of reaching E8) to find most likely E8 participants
        top_sorted = sorted(top, key=lambda x: -x['vegas_r3'])
        bottom_sorted = sorted(bottom, key=lambda x: -x['vegas_r3'])

        # Primary E8 matchup: top_sorted[0] vs bottom_sorted[0]
        # Secondary: check top_sorted[0] vs bottom_sorted[1] and top_sorted[1] vs bottom_sorted[0]
        primary_top = top_sorted[0] if top_sorted else None
        primary_bottom = bottom_sorted[0] if bottom_sorted else None
        secondary_top = top_sorted[1] if len(top_sorted) > 1 else None
        secondary_bottom = bottom_sorted[1] if len(bottom_sorted) > 1 else None

        if not primary_top or not primary_bottom:
            continue

        # Analyze matchup scenarios for each team
        scenarios = []

        # For the primary top-half team: vs primary bottom, vs secondary bottom
        for team_a, opponents in [
            (primary_top, [primary_bottom, secondary_bottom]),
            (primary_bottom, [primary_top, secondary_top]),
        ]:
            if not team_a:
                continue
            game_leverages = []
            for opp in opponents:
                if not opp:
                    continue
                vegas_a = team_a['vegas_r4']
                vegas_b = opp['vegas_r4']
                public_a = team_a['public_r4']
                public_b = opp['public_r4']

                denom_vegas = vegas_a + vegas_b
                denom_public = public_a + public_b

                if denom_vegas == 0 or denom_public == 0:
                    continue

                e8_game_implied = vegas_a / denom_vegas
                e8_public_game = public_a / denom_public
                e8_leverage_game = e8_game_implied - e8_public_game

                game_leverages.append({
                    'team': team_a['team_name'],
                    'team_seed': team_a['team_seed'],
                    'region': region,
                    'opponent': opp['team_name'],
                    'opp_seed': opp['team_seed'],
                    'e8_game_implied': e8_game_implied,
                    'e8_public_game': e8_public_game,
                    'e8_leverage_game': e8_leverage_game,
                })

            # Check for sign flip between scenarios
            if len(game_leverages) >= 2:
                signs = [gl['e8_leverage_game'] > 0 for gl in game_leverages]
                if signs[0] != signs[1]:
                    sign_flip_teams.add(team_a['team_name'])
                    for gl in game_leverages:
                        gl['sign_flip'] = True
                else:
                    for gl in game_leverages:
                        gl['sign_flip'] = False
            elif len(game_leverages) == 1:
                game_leverages[0]['sign_flip'] = False

            scenarios.extend(game_leverages)

        all_e8_analysis.extend(scenarios)

    # Print all E8 analysis
    print(f"\n{'Team':<18} {'Sd':>2} {'Region':<8} {'vs Opponent':<18} {'oSd':>3} "
          f"{'GameImpl':>8} {'PubGame':>8} {'GameLev':>8} {'Flip':>5}")
    print("-" * 100)
    for s in all_e8_analysis:
        flip_str = "YES" if s['sign_flip'] else ""
        print(f"{s['team']:<18} {s['team_seed']:>2} {s['region']:<8} "
              f"{s['opponent']:<18} {s['opp_seed']:>3} "
              f"{s['e8_game_implied']:>8.4f} {s['e8_public_game']:>8.4f} "
              f"{s['e8_leverage_game']:>+8.4f} {flip_str:>5}")
    sys.stdout.flush()

    # Print sign-flip summary
    if sign_flip_teams:
        print(f"\n  Sign-flip teams: {', '.join(sorted(sign_flip_teams))}")
    else:
        print("\n  No sign flips detected.")
    sys.stdout.flush()

    # Update leverage_rows with sign_flip_flag for r4
    for row in leverage_rows:
        if row['round'] == 'r4':
            row['sign_flip_flag'] = 'Y' if row['team_name'] in sign_flip_teams else 'N'

    return all_e8_analysis, sign_flip_teams


def print_top_tables(leverage_rows):
    """Print top 15 under-picked and top 15 over-picked by round_weighted_leverage."""

    # Table 1: Top 15 under-picked (positive leverage, highest first)
    print("=" * 80)
    print("TABLE 1: TOP 15 UNDER-PICKED TEAMS (positive leverage = public undervalues)")
    print("=" * 80)
    positive = sorted(
        [r for r in leverage_rows if r['leverage'] > 0],
        key=lambda x: -x['round_weighted_leverage']
    )[:15]
    print(f"{'Team':<18} {'Sd':>2} {'Region':<8} {'Rnd':<4} "
          f"{'Vegas':>7} {'Public':>7} {'Lev':>7} {'Ratio':>6} {'RWL':>8} {'Caution':>7}")
    print("-" * 80)
    for r in positive:
        ratio_str = f"{r['leverage_ratio']:.2f}" if r['leverage_ratio'] is not None else "null"
        caution = r.get('prop_norm_caution_flag', 'N')
        caution_str = "*PNORM" if caution == 'Y' else ""
        print(f"{r['team_name']:<18} {r['team_seed']:>2} {r['region']:<8} {r['round']:<4} "
              f"{r['vegas_prob']:>7.4f} {r['public_pick_pct']:>7.4f} "
              f"{r['leverage']:>+7.4f} {ratio_str:>6} {r['round_weighted_leverage']:>+8.2f} {caution_str:>7}")
    sys.stdout.flush()

    # Table 2: Top 15 over-picked (negative leverage, most negative first)
    print("\n" + "=" * 80)
    print("TABLE 2: TOP 15 OVER-PICKED TEAMS (negative leverage = public overvalues)")
    print("=" * 80)
    negative = sorted(
        [r for r in leverage_rows if r['leverage'] < 0],
        key=lambda x: x['round_weighted_leverage']
    )[:15]
    print(f"{'Team':<18} {'Sd':>2} {'Region':<8} {'Rnd':<4} "
          f"{'Vegas':>7} {'Public':>7} {'Lev':>7} {'Ratio':>6} {'RWL':>8}")
    print("-" * 80)
    for r in negative:
        ratio_str = f"{r['leverage_ratio']:.2f}" if r['leverage_ratio'] is not None else "null"
        print(f"{r['team_name']:<18} {r['team_seed']:>2} {r['region']:<8} {r['round']:<4} "
              f"{r['vegas_prob']:>7.4f} {r['public_pick_pct']:>7.4f} "
              f"{r['leverage']:>+7.4f} {ratio_str:>6} {r['round_weighted_leverage']:>+8.2f}")
    sys.stdout.flush()


def save_leverage_matrix(leverage_rows):
    out_cols = [
        'team_name', 'team_seed', 'region', 'round',
        'vegas_prob', 'public_pick_pct',
        'leverage', 'leverage_ratio', 'round_weighted_leverage',
        'high_signal_flag', 'zero_ownership_flag', 'sign_flip_flag',
        'prop_norm_caution_flag',
    ]
    with open('leverage_matrix_2026.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_cols, extrasaction='ignore')
        writer.writeheader()
        for row in leverage_rows:
            out = dict(row)
            out['leverage'] = round(out['leverage'], 6)
            if out['leverage_ratio'] is not None:
                out['leverage_ratio'] = round(out['leverage_ratio'], 4)
            else:
                out['leverage_ratio'] = ''
            out['round_weighted_leverage'] = round(out['round_weighted_leverage'], 4)
            out['vegas_prob'] = round(out['vegas_prob'], 6)
            out['public_pick_pct'] = round(out['public_pick_pct'], 6)
            writer.writerow(out)
    print(f"\nSaved leverage_matrix_2026.csv ({len(leverage_rows)} rows)")
    sys.stdout.flush()


def main():
    print("=" * 80)
    print("PROMPT 2 — LEVERAGE CALCULATION")
    print("=" * 80)
    sys.stdout.flush()

    teams = load_master()
    print(f"Loaded {len(teams)} teams from master_data_2026.csv")
    sys.stdout.flush()

    # Compute leverage for all team-round combinations
    leverage_rows = compute_leverage(teams)
    print(f"Computed {len(leverage_rows)} leverage entries ({len(teams)} teams × {len(ROUNDS)} rounds)")
    sys.stdout.flush()

    # Tables 1 & 2: Top under-picked and over-picked
    print_top_tables(leverage_rows)

    # Table 3: Systematic pattern check
    systematic_pattern_check(leverage_rows)

    # Table 4: E8 sign-flip detection
    e8_analysis, sign_flip_teams = e8_sign_flip_detection(teams, leverage_rows)

    # Save output
    save_leverage_matrix(leverage_rows)

    print("\n" + "=" * 80)
    print("PROMPT 2 COMPLETE")
    print("=" * 80)
    sys.stdout.flush()


if __name__ == '__main__':
    main()
