"""
Merge Source A (Vegas) and Source B (Public Picks)
Save as master_data_2026.csv
"""
import csv
import sys

from load_validate_source_a import load_and_validate as load_a
from load_validate_source_b import load_and_validate as load_b
from load_validate_source_c import load_and_validate as load_c

# Name mapping: Source B name → Source A name
# Standardize to Source A naming convention
NAME_MAP_B_TO_A = {
    'Michigan State': 'Michigan St',
    'Cal Baptist': 'CA Baptist',
    'North Dakota St': 'N Dakota St',
    'Hawaii': "Hawai'i",
    'Prairie View': 'PV/LEH',
    'LIU': 'Long Island',
    'SMU': 'M-OH/SMU',
    'Wright State': 'Wright St',
    'Kennesaw State': 'Kennesaw St',
    'Tennessee State': 'Tennessee St',
    'St. John\'s': 'St John\'s',
    'Miami (FL)': 'Miami',
}

VEGAS_ROUNDS = ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']
PUBLIC_ROUNDS = ['public_r1', 'public_r2', 'public_r3', 'public_r4', 'public_r5', 'public_r6']
FIRST_FOUR_TEAMS = {'M-OH/SMU', 'PV/LEH'}


def main():
    print("=" * 60)
    print("LOADING AND VALIDATING ALL DATA SOURCES")
    print("=" * 60)
    sys.stdout.flush()

    # Source A
    print("\n--- SOURCE A: Vegas Probability Baseline ---")
    sys.stdout.flush()
    teams_a, flags_a, passed_a = load_a()

    # Source B
    print("\n--- SOURCE B: Public Pick Percentages ---")
    sys.stdout.flush()
    teams_b, passed_b = load_b()

    # Source C
    print("\n--- SOURCE C: Matchup-Level ESPN Picks ---")
    sys.stdout.flush()
    matchups_c, passed_c = load_c()

    # Merge A and B
    print("\n" + "=" * 60)
    print("MERGING SOURCE A AND SOURCE B")
    print("=" * 60)
    sys.stdout.flush()

    # Build lookup from Source A
    a_by_name = {t['team_name']: t for t in teams_a}

    # Map Source B names to Source A names and merge
    name_mappings_used = []
    unmatched = []
    merged = []

    for tb in teams_b:
        b_name = tb['team_name']
        a_name = NAME_MAP_B_TO_A.get(b_name, b_name)

        if b_name != a_name:
            name_mappings_used.append(f"  '{b_name}' → '{a_name}'")

        if a_name in a_by_name:
            ta = a_by_name.pop(a_name)
            row = {
                'team_name': ta['team_name'],
                'team_seed': ta['team_seed'],
                'region': ta['region'],
            }
            for vr in VEGAS_ROUNDS:
                row[f'vegas_{vr}'] = ta[vr]
            for pr in PUBLIC_ROUNDS:
                row[pr] = tb[pr]
            row['near_zero_flag'] = 'Y' if ta['team_name'] in [f for f in flags_a.get('near_zero', [])] else 'N'
            row['first_four_flag'] = 'Y' if ta['team_name'] in FIRST_FOUR_TEAMS else 'N'
            merged.append(row)
        else:
            unmatched.append(b_name)

    # Check for Source A teams not matched
    remaining_a = list(a_by_name.keys())

    print(f"\nTeams matched: {len(merged)} / 64")
    if name_mappings_used:
        print(f"Name mappings applied ({len(name_mappings_used)}):")
        for nm in name_mappings_used:
            print(nm)
    if unmatched:
        print(f"UNMATCHED Source B teams: {unmatched}")
    if remaining_a:
        print(f"UNMATCHED Source A teams: {remaining_a}")
    sys.stdout.flush()

    # Save merged file
    out_cols = (
        ['team_name', 'team_seed', 'region']
        + [f'vegas_{r}' for r in VEGAS_ROUNDS]
        + PUBLIC_ROUNDS
        + ['near_zero_flag', 'first_four_flag']
    )

    with open('master_data_2026.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out_cols)
        writer.writeheader()
        for row in merged:
            writer.writerow(row)

    print(f"\nSaved master_data_2026.csv ({len(merged)} rows)")
    sys.stdout.flush()

    # Print first 5 rows
    print("\nFirst 5 rows of merged file:")
    print(f"{'team_name':<18} {'seed':>4} {'region':<8} "
          f"{'vegas_r1':>8} {'vegas_r6':>8} {'pub_r1':>8} {'pub_r6':>8} "
          f"{'nz':>3} {'ff':>3}")
    print("-" * 85)
    for row in merged[:5]:
        print(f"{row['team_name']:<18} {row['team_seed']:>4} {row['region']:<8} "
              f"{row['vegas_r1']:>8.4f} {row['vegas_r6']:>8.4f} "
              f"{row['public_r1']:>8.4f} {row['public_r6']:>8.4f} "
              f"{row['near_zero_flag']:>3} {row['first_four_flag']:>3}")
    sys.stdout.flush()

    print("\n" + "=" * 60)
    print("ALL SOURCES LOADED AND MERGED SUCCESSFULLY")
    print("=" * 60)
    sys.stdout.flush()


if __name__ == '__main__':
    main()
