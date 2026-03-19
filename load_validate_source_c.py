"""
Source C — Matchup-Level ESPN Picks
Load and validate espn_picks_2026.csv
"""
import csv
import sys


def load_and_validate():
    matchups = []
    with open('espn_picks_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get('team_1_name', '').strip():
                continue
            matchup = {
                'round': row['round'].strip(),
                'region': row['region'].strip(),
                'team_1_name': row['team_1_name'].strip(),
                'team_1_seed': int(row['team_1_seed']) if row['team_1_seed'].strip() else None,
                'team_1_pick_pct': float(row['team_1_pick_pct']) / 100.0,
                'team_2_name': row['team_2_name'].strip() if row['team_2_name'].strip() else None,
                'team_2_seed': int(row['team_2_seed']) if row.get('team_2_seed', '').strip() else None,
                'team_2_pick_pct': float(row['team_2_pick_pct']) / 100.0 if row.get('team_2_pick_pct', '').strip() else None,
                'matchup_id': row['matchup_id'].strip(),
            }
            matchups.append(matchup)

    passed = True

    # C1 — Pick percentages sum to ~1.0 for each matchup
    c1_pass = True
    c1_flags = []
    for m in matchups:
        if m['team_2_name'] is None or m['team_2_pick_pct'] is None:
            continue  # Skip NCG_CHAMP rows (single-team entries)
        total = m['team_1_pick_pct'] + m['team_2_pick_pct']
        if total < 0.99 or total > 1.01:
            c1_flags.append(
                f"  {m['matchup_id']}: {m['team_1_name']} ({m['team_1_pick_pct']:.4f}) + "
                f"{m['team_2_name']} ({m['team_2_pick_pct']:.4f}) = {total:.4f}")
            c1_pass = False
            passed = False
    if c1_flags:
        print(f"C1 FAIL — Pick pct sum violations ({len(c1_flags)}):")
        for f_item in c1_flags:
            print(f_item)
    else:
        print("C1 PASS — All matchup pick percentages sum to ~1.0")
    sys.stdout.flush()

    # C2 — R64 matchups cover all 64 teams (32 matchups)
    r64_matchups = [m for m in matchups if m['round'] == 'R64']
    r64_teams = set()
    for m in r64_matchups:
        r64_teams.add(m['team_1_name'])
        if m['team_2_name']:
            r64_teams.add(m['team_2_name'])

    c2_pass = True
    if len(r64_matchups) != 32:
        print(f"C2 FLAG — Expected 32 R64 matchups, found {len(r64_matchups)}")
        c2_pass = False
    if len(r64_teams) != 64:
        print(f"C2 FLAG — Expected 64 unique teams in R64, found {len(r64_teams)}")
        c2_pass = False
        passed = False
    if c2_pass:
        print(f"C2 PASS — R64: {len(r64_matchups)} matchups covering {len(r64_teams)} teams")
    sys.stdout.flush()

    # Count only actual matchups (exclude NCG_CHAMP single-team entries)
    actual_matchups = [m for m in matchups if m['team_2_name'] is not None]
    status = "PASS" if passed else "FAIL"
    print(f"Source C loaded: {len(actual_matchups)} matchups, validation {status}")
    sys.stdout.flush()

    return matchups, passed


if __name__ == '__main__':
    matchups, passed = load_and_validate()
