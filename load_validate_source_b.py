"""
Source B — Public Pick Percentages (All Rounds)
Load and validate public_picks_2026.csv
"""
import csv
import sys

PUBLIC_ROUNDS = ['public_r1', 'public_r2', 'public_r3', 'public_r4', 'public_r5', 'public_r6']

# Column mapping: source file → pipeline convention
COLUMN_MAP = {
    'Team': 'team_name',
    'Seed': 'team_seed',
    'Region': 'region',
    'R32': 'public_r1',   # Fraction picking team to advance to R32 = win R64
    'S16': 'public_r2',
    'E8': 'public_r3',
    'F4': 'public_r4',
    'CHAMP': 'public_r5',
    'WINNER': 'public_r6',
}

# Expected regional sums (same bracket math as Source A)
EXPECTED_SUMS = {
    'public_r1': 8.0, 'public_r2': 4.0, 'public_r3': 2.0,
    'public_r4': 1.0, 'public_r5': 0.5, 'public_r6': 0.25
}
WARN_THRESHOLD = 0.10  # Public picks: looser tolerance


def load_and_validate():
    teams = []
    with open('public_picks_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row['Team'].strip():
                continue
            team = {
                'team_name': row['Team'].strip(),
                'team_seed': int(row['Seed']),
                'region': row['Region'].strip(),
            }
            # Convert percentages to decimals
            for src_col, pipe_col in COLUMN_MAP.items():
                if pipe_col.startswith('public_'):
                    team[pipe_col] = float(row[src_col]) / 100.0
            teams.append(team)

    passed = True
    flags = {'monotonicity': [], 'sum_warnings': []}

    # B1 — Regional sum constraints (soft)
    regions = sorted(set(t['region'] for t in teams))
    b1_pass = True
    for region in regions:
        region_teams = [t for t in teams if t['region'] == region]
        for pr in PUBLIC_ROUNDS:
            actual = sum(t[pr] for t in region_teams)
            expected = EXPECTED_SUMS[pr]
            dev = abs(actual - expected)
            if dev > WARN_THRESHOLD:
                msg = f"B1 FLAG — {region} {pr}: sum={actual:.4f}, expected={expected:.4f}, dev={dev:.4f}"
                print(msg)
                flags['sum_warnings'].append(msg)
                b1_pass = False
    if b1_pass:
        print("B1 PASS — All regional sums within tolerance (0.10)")
    sys.stdout.flush()

    # B2 — Monotonicity: public_r1 >= public_r2 >= ... >= public_r6
    b2_pass = True
    for t in teams:
        for i in range(len(PUBLIC_ROUNDS) - 1):
            if t[PUBLIC_ROUNDS[i]] < t[PUBLIC_ROUNDS[i + 1]]:
                flags['monotonicity'].append(
                    f"  {t['team_name']}: {PUBLIC_ROUNDS[i]}={t[PUBLIC_ROUNDS[i]]:.4f} < "
                    f"{PUBLIC_ROUNDS[i+1]}={t[PUBLIC_ROUNDS[i+1]]:.4f}")
                b2_pass = False
                passed = False
    if flags['monotonicity']:
        print(f"B2 FAIL — Monotonicity violations ({len(flags['monotonicity'])}):")
        for v in flags['monotonicity']:
            print(v)
    else:
        print("B2 PASS — Monotonicity: all teams satisfy public_r1 >= ... >= public_r6")
    sys.stdout.flush()

    # B3 — Coverage: all 64 teams with non-null values
    b3_pass = True
    if len(teams) != 64:
        print(f"B3 FAIL — Expected 64 teams, found {len(teams)}")
        b3_pass = False
        passed = False
    null_issues = []
    for t in teams:
        for pr in PUBLIC_ROUNDS:
            if t[pr] is None:
                null_issues.append(f"  {t['team_name']}: {pr} is null")
    if null_issues:
        print(f"B3 FAIL — Null values found:")
        for n in null_issues:
            print(n)
        b3_pass = False
        passed = False
    if b3_pass:
        print(f"B3 PASS — All {len(teams)} teams present with non-null values")
    sys.stdout.flush()

    status = "PASS" if passed else "FAIL"
    print(f"Source B loaded: {len(teams)} teams, validation {status}")
    sys.stdout.flush()

    return teams, passed


if __name__ == '__main__':
    teams, passed = load_and_validate()
