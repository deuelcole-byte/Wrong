#!/usr/bin/env python3
"""
Path-probability-weighted E8 leverage for path-dependent teams.
Weights each E8 leverage scenario by the probability that each opponent
reaches the E8 (using their r3 values as a proxy).
"""
import csv
import sys


def load_master():
    teams = {}
    with open('master_data_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = {k: row[k] for k in row}
            for k in ['vegas_r3', 'vegas_r4', 'vegas_r4_adjusted', 'vegas_r4_adjusted_alt',
                       'public_r4', 'e8_game_implied', 'e8_game_corrected']:
                t[k] = float(t[k]) if t[k] else 0.0
            t['team_seed'] = int(t['team_seed'])
            teams[row['team_name']] = t
    return teams


def load_espn_bracket():
    """Return top-half and bottom-half team sets per region from R64."""
    top_half = {}
    bottom_half = {}
    with open('espn_picks_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['round'] != 'R64':
                continue
            region = row['region']
            mid = row['matchup_id']
            t1 = row['team_1_name'].strip()
            t2 = row['team_2_name'].strip()
            if region not in top_half:
                top_half[region] = set()
                bottom_half[region] = set()
            num = int(mid.split('_')[-1])
            if num <= 4:
                top_half[region].update([t1, t2])
            else:
                bottom_half[region].update([t1, t2])
    return top_half, bottom_half


def main():
    print("=" * 90)
    print("PATH-PROBABILITY-WEIGHTED E8 LEVERAGE")
    print("=" * 90)

    teams = load_master()
    top_half, bottom_half = load_espn_bracket()

    # Path-dependent teams from Prompt 3
    pd_teams = [name for name, t in teams.items() if t.get('path_dependent_flag') == 'Y']
    print(f"Path-dependent teams: {', '.join(pd_teams)}\n")

    # For each region, identify the two most likely E8 participants per half
    # (same logic as Prompt 3)
    regions = {'East', 'South', 'West', 'Midwest'}
    region_opponents = {}  # team_name -> [(opp_name, opp_r3), (alt_opp_name, alt_opp_r3)]

    for region in regions:
        region_teams = {n: t for n, t in teams.items() if t['region'] == region}
        top = sorted([n for n in region_teams if n in top_half.get(region, set())],
                     key=lambda x: -teams[x]['vegas_r3'])
        bot = sorted([n for n in region_teams if n in bottom_half.get(region, set())],
                     key=lambda x: -teams[x]['vegas_r3'])

        top1, top2 = (top[0] if len(top) > 0 else None), (top[1] if len(top) > 1 else None)
        bot1, bot2 = (bot[0] if len(bot) > 0 else None), (bot[1] if len(bot) > 1 else None)

        # Top-half teams face bottom-half opponents
        if top1:
            region_opponents[top1] = {'primary': bot1, 'alt': bot2}
        if top2:
            region_opponents[top2] = {'primary': bot1, 'alt': bot2}
        # Bottom-half teams face top-half opponents
        if bot1:
            region_opponents[bot1] = {'primary': top1, 'alt': top2}
        if bot2:
            region_opponents[bot2] = {'primary': top1, 'alt': top2}

    print(f"{'Team':<18} {'Sd':>2} {'Region':<10} "
          f"{'OppA':<14} {'OppA_r3':>7} {'LevA':>8} {'pA':>6} | "
          f"{'OppB':<14} {'OppB_r3':>7} {'LevB':>8} {'pB':>6} | "
          f"{'WtdLev':>8} {'Verdict'}")
    print("-" * 130)

    for name in sorted(pd_teams, key=lambda x: teams[x]['region']):
        t = teams[name]
        opps = region_opponents.get(name)
        if not opps or not opps['primary'] or not opps['alt']:
            continue

        opp_a_name = opps['primary']
        opp_b_name = opps['alt']
        opp_a = teams[opp_a_name]
        opp_b = teams[opp_b_name]

        # Probability each opponent reaches E8 (conditional on one of them making it)
        r3_a = opp_a['vegas_r3']
        r3_b = opp_b['vegas_r3']
        denom = r3_a + r3_b
        p_a = r3_a / denom if denom > 0 else 0.5
        p_b = 1.0 - p_a

        # Leverage under each scenario
        # Scenario A: team faces opp_a -> uses vegas_r4_adjusted
        # Scenario B: team faces opp_b -> uses vegas_r4_adjusted_alt
        lev_a = t['vegas_r4_adjusted'] - t['public_r4']
        lev_b = t['vegas_r4_adjusted_alt'] - t['public_r4']

        weighted_lev = lev_a * p_a + lev_b * p_b

        if abs(weighted_lev) < 0.01:
            verdict = "~NEUTRAL"
        elif weighted_lev > 0.03:
            verdict = "UNDER-PICKED"
        elif weighted_lev < -0.03:
            verdict = "OVER-PICKED"
        else:
            verdict = "LEAN " + ("under" if weighted_lev > 0 else "over")

        print(f"{name:<18} {t['team_seed']:>2} {t['region']:<10} "
              f"{opp_a_name:<14} {r3_a:>7.4f} {lev_a:>+8.4f} {p_a:>6.3f} | "
              f"{opp_b_name:<14} {r3_b:>7.4f} {lev_b:>+8.4f} {p_b:>6.3f} | "
              f"{weighted_lev:>+8.4f} {verdict}")

    print()
    sys.stdout.flush()


if __name__ == '__main__':
    main()
