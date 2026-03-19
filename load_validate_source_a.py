"""
Source A — Probability Baseline
Load and validate vegas_raw_2026.csv
"""
import csv
import sys

ROUNDS = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']

# Expected regional sums per round (correct bracket math:
# 16 teams per region, 8 R64 games => 8 advance, etc.)
# Note: task spec listed half these values; using mathematically correct sums.
EXPECTED_SUMS = {
    'r1': 8.0, 'r2': 4.0, 'r3': 2.0,
    'r4': 1.0, 'r5': 0.5, 'r6': 0.25
}
WARN_THRESHOLD = 0.01
HALT_THRESHOLD = 0.05

FIRST_FOUR_TEAMS = {'M-OH/SMU', 'PV/LEH'}


def load_and_validate():
    teams = []
    with open('vegas_raw_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row['team_name'].strip():
                continue
            team = {
                'team_name': row['team_name'].strip(),
                'team_seed': int(row['team_seed']),
                'region': row['region'].strip(),
                'vegas_prob_game': float(row['vegas_prob_game']),
            }
            for r in ROUNDS:
                team[r] = float(row[r])
            teams.append(team)

    passed = True
    flags = {'near_zero': [], 'first_four': [], 'monotonicity': []}

    # A1 — Monotonicity: r1 >= r2 >= ... >= r6
    for t in teams:
        for i in range(len(ROUNDS) - 1):
            if t[ROUNDS[i]] < t[ROUNDS[i + 1]]:
                flags['monotonicity'].append(
                    f"  {t['team_name']}: {ROUNDS[i]}={t[ROUNDS[i]]:.4f} < {ROUNDS[i+1]}={t[ROUNDS[i+1]]:.4f}")
                passed = False
    if flags['monotonicity']:
        print(f"A1 FAIL — Monotonicity violations ({len(flags['monotonicity'])}):")
        for v in flags['monotonicity']:
            print(v)
    else:
        print("A1 PASS — Monotonicity: all teams satisfy r1 >= r2 >= ... >= r6")
    sys.stdout.flush()

    # A2 — Regional sum constraints
    regions = sorted(set(t['region'] for t in teams))
    a2_pass = True
    halt = False
    for region in regions:
        region_teams = [t for t in teams if t['region'] == region]
        for r in ROUNDS:
            actual = sum(t[r] for t in region_teams)
            expected = EXPECTED_SUMS[r]
            dev = abs(actual - expected)
            if dev > HALT_THRESHOLD:
                print(f"A2 HALT — {region} {r}: sum={actual:.4f}, expected={expected:.4f}, dev={dev:.4f}")
                halt = True
                a2_pass = False
            elif dev > WARN_THRESHOLD:
                print(f"A2 FLAG — {region} {r}: sum={actual:.4f}, expected={expected:.4f}, dev={dev:.4f}")
                a2_pass = False
    if a2_pass:
        print("A2 PASS — All regional sums within tolerance")
    if halt:
        print("A2 WARNING — Deviations exceed halt threshold (0.05) in some round-regions")
        passed = False
    sys.stdout.flush()

    # A3 — Near-zero flag: r6 < 0.0005
    for t in teams:
        if t['r6'] < 0.0005:
            flags['near_zero'].append(t['team_name'])
    if flags['near_zero']:
        print(f"A3 INFO — Near-zero teams (r6 < 0.0005): {', '.join(flags['near_zero'])}")
    else:
        print("A3 INFO — No near-zero teams found")
    sys.stdout.flush()

    # A4 — First Four teams
    for t in teams:
        if t['team_name'] in FIRST_FOUR_TEAMS:
            flags['first_four'].append(t['team_name'])
    if flags['first_four']:
        print(f"A4 INFO — First Four teams: {', '.join(flags['first_four'])}")
    else:
        print("A4 INFO — No First Four teams flagged")
    sys.stdout.flush()

    status = "PASS" if passed else "FAIL"
    print(f"Source A loaded: {len(teams)} teams, validation {status}")
    sys.stdout.flush()

    return teams, flags, passed


if __name__ == '__main__':
    teams, flags, passed = load_and_validate()
