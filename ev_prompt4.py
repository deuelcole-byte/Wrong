#!/usr/bin/env python3
"""
Prompt 4 — Expected Value Championship Analysis
EV = vegas_r6 * N * (1 - public_r6)
"""
import csv
import sys

POOL_SIZES = [10, 25, 50, 100, 250, 500, 1000]
UNCERTAINTY_PP = 0.03  # ±3 percentage points


def load_master():
    teams = []
    with open('master_data_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = {k: row[k] for k in row}
            for k in ['vegas_r1', 'vegas_r2', 'vegas_r3', 'vegas_r4', 'vegas_r5', 'vegas_r6',
                       'vegas_r4_adjusted', 'vegas_r4_adjusted_alt',
                       'public_r1', 'public_r2', 'public_r3', 'public_r4', 'public_r5', 'public_r6',
                       'e8_game_implied', 'e8_game_corrected', 'vegas_r4_original']:
                t[k] = float(t[k]) if t[k] else 0.0
            t['team_seed'] = int(t['team_seed'])
            teams.append(t)
    return teams


def load_leverage_signflips():
    """Load sign_flip_flag = Y teams from leverage matrix (r4 only)."""
    flips = set()
    with open('leverage_matrix_2026.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('sign_flip_flag') == 'Y':
                flips.add(row['team_name'])
    return flips


def compute_ev(vegas_r6, public_r6, n):
    return vegas_r6 * n * (1.0 - public_r6)


def main():
    print("=" * 100)
    print("PROMPT 4 — EXPECTED VALUE CHAMPIONSHIP ANALYSIS")
    print("=" * 100)
    sys.stdout.flush()

    teams = load_master()
    sign_flip_teams = load_leverage_signflips()
    print(f"Loaded {len(teams)} teams, {len(sign_flip_teams)} sign-flip teams: {sign_flip_teams}")
    sys.stdout.flush()

    # --- Ownership classification and floor application ---
    floor_applied = []
    candidates = []

    for t in teams:
        if t['near_zero_flag'] == 'Y':
            continue

        pub_r6 = t['public_r6']
        vegas_r6 = t['vegas_r6']

        # Apply floor
        if vegas_r6 > 0.01 and pub_r6 == 0:
            floor_applied.append(t['team_name'])
            pub_r6 = 0.001
            t['public_r6_effective'] = pub_r6
        else:
            t['public_r6_effective'] = pub_r6

        # Ownership classification
        if pub_r6 > 0.10:
            t['ownership_class'] = 'HIGH'
        elif pub_r6 >= 0.01:
            t['ownership_class'] = 'MODERATE'
        else:
            t['ownership_class'] = 'LOW'
            t['low_ownership_flag'] = 'Y'

        t['low_ownership_flag'] = t.get('low_ownership_flag', 'N')
        candidates.append(t)

    if floor_applied:
        print(f"\nFloor applied (public_r6 set to 0.001): {', '.join(floor_applied)}")
    else:
        print("\nNo floor applications needed.")
    sys.stdout.flush()

    # --- Compute EV at all pool sizes ---
    for t in candidates:
        t['ev'] = {}
        for n in POOL_SIZES:
            t['ev'][n] = compute_ev(t['vegas_r6'], t['public_r6_effective'], n)

    # --- Path dependency check ---
    print("\n" + "=" * 100)
    print("PATH-DEPENDENCY CHECK")
    print("=" * 100)

    pd_candidates = [t for t in candidates if t.get('path_dependent_flag') == 'Y']
    for t in pd_candidates:
        r4_adj = t['vegas_r4_adjusted']
        r4_alt = t['vegas_r4_adjusted_alt']
        if r4_adj > 0:
            scale = r4_alt / r4_adj
        else:
            scale = 1.0
        t['vegas_r6_alt'] = t['vegas_r6'] * scale
        t['ev_alt'] = {}
        for n in POOL_SIZES:
            t['ev_alt'][n] = compute_ev(t['vegas_r6_alt'], t['public_r6_effective'], n)

        # Check if EV changes by more than 15%
        ev_base = t['ev'][100]
        ev_alt = t['ev_alt'][100]
        if ev_base > 0:
            pct_change = abs(ev_alt - ev_base) / ev_base * 100
        else:
            pct_change = 0
        t['ev_path_pct_change'] = pct_change
        t['ev_path_flag'] = 'Y' if pct_change > 15 else 'N'

    if pd_candidates:
        print(f"{'Team':<18} {'Sd':>2} {'v_r6':>7} {'v_r6_alt':>8} {'EV@100':>8} {'EV_alt':>8} {'%Chg':>6} {'Flag':>5}")
        print("-" * 70)
        for t in sorted(pd_candidates, key=lambda x: -x['ev'][100]):
            print(f"{t['team_name']:<18} {t['team_seed']:>2} {t['vegas_r6']:>7.4f} "
                  f"{t['vegas_r6_alt']:>8.4f} {t['ev'][100]:>8.3f} {t['ev_alt'][100]:>8.3f} "
                  f"{t['ev_path_pct_change']:>5.1f}% {t['ev_path_flag']:>5}")
    else:
        print("  No path-dependent candidates.")
    sys.stdout.flush()

    # --- Sign-flip check ---
    print("\n" + "=" * 100)
    print("SIGN-FLIP CHECK")
    print("=" * 100)
    sf_candidates = [t for t in candidates if t['team_name'] in sign_flip_teams]
    if sf_candidates:
        for t in sf_candidates:
            ev_base = t['ev'].get(100, 0)
            ev_alt = t.get('ev_alt', {}).get(100, ev_base)
            print(f"  {t['team_name']}: EV@100 = {ev_base:.3f}, EV_alt@100 = {ev_alt:.3f}")
    else:
        print("  No sign-flip teams in champion candidate list.")
    sys.stdout.flush()

    # --- Uncertainty check ---
    print("\n" + "=" * 100)
    print("UNCERTAINTY CHECK (±3pp on vegas_r6)")
    print("=" * 100)

    for t in candidates:
        t['vegas_r6_lo'] = max(0, t['vegas_r6'] - UNCERTAINTY_PP)
        t['vegas_r6_hi'] = t['vegas_r6'] + UNCERTAINTY_PP
        t['ev_lo'] = {}
        t['ev_hi'] = {}
        for n in POOL_SIZES:
            t['ev_lo'][n] = compute_ev(t['vegas_r6_lo'], t['public_r6_effective'], n)
            t['ev_hi'][n] = compute_ev(t['vegas_r6_hi'], t['public_r6_effective'], n)

    # Check if optimal pick changes at any pool size
    print(f"\n{'N':>6} {'Optimal (base)':<18} {'EV':>8} {'Optimal (lo)':<18} {'EV_lo':>8} "
          f"{'Optimal (hi)':<18} {'EV_hi':>8} {'Stable':>6}")
    print("-" * 100)
    any_instability = False
    for n in POOL_SIZES:
        best_base = max(candidates, key=lambda x: x['ev'][n])
        best_lo = max(candidates, key=lambda x: x['ev_lo'][n])
        best_hi = max(candidates, key=lambda x: x['ev_hi'][n])
        stable = 'YES' if best_base['team_name'] == best_lo['team_name'] == best_hi['team_name'] else 'NO'
        if stable == 'NO':
            any_instability = True
        print(f"{n:>6} {best_base['team_name']:<18} {best_base['ev'][n]:>8.3f} "
              f"{best_lo['team_name']:<18} {best_lo['ev_lo'][n]:>8.3f} "
              f"{best_hi['team_name']:<18} {best_hi['ev_hi'][n]:>8.3f} {stable:>6}")
    sys.stdout.flush()

    # --- TABLE 1: Full EV ranking at N=100 ---
    print("\n" + "=" * 100)
    print("TABLE 1: FULL EV RANKING AT N=100")
    print("=" * 100)
    ranked = sorted(candidates, key=lambda x: -x['ev'][100])
    print(f"{'Rk':>3} {'Team':<18} {'Sd':>2} {'Region':<10} {'v_r6':>7} {'pub_r6':>7} "
          f"{'EV@100':>8} {'OwnClass':>8} {'PathDep':>7} {'SignFlip':>8} {'LowOwn':>6}")
    print("-" * 100)
    for i, t in enumerate(ranked[:30], 1):
        sf = 'Y' if t['team_name'] in sign_flip_teams else 'N'
        pd = t.get('path_dependent_flag', 'N')
        print(f"{i:>3} {t['team_name']:<18} {t['team_seed']:>2} {t['region']:<10} "
              f"{t['vegas_r6']:>7.4f} {t['public_r6_effective']:>7.4f} "
              f"{t['ev'][100]:>8.3f} {t['ownership_class']:>8} {pd:>7} {sf:>8} "
              f"{t['low_ownership_flag']:>6}")
    sys.stdout.flush()

    # --- TABLE 2: Pool size sensitivity matrix ---
    print("\n" + "=" * 100)
    print("TABLE 2: POOL SIZE SENSITIVITY — OPTIMAL CHAMPION AT EACH N")
    print("=" * 100)
    print(f"{'N':>6} {'Optimal Pick':<18} ", end='')
    for n in POOL_SIZES:
        print(f"{'EV@'+str(n):>10}", end='')
    print()
    print("-" * 90)

    # Show top 5 teams across all pool sizes
    top5 = ranked[:5]
    for t in top5:
        print(f"{'':>6} {t['team_name']:<18} ", end='')
        for n in POOL_SIZES:
            print(f"{t['ev'][n]:>10.3f}", end='')
        print()

    print("\n  Optimal pick at each N:")
    for n in POOL_SIZES:
        best = max(candidates, key=lambda x: x['ev'][n])
        print(f"    N={n:<5}: {best['team_name']:<18} EV={best['ev'][n]:.3f}")

    # Check invariance
    optimal_names = set()
    for n in POOL_SIZES:
        best = max(candidates, key=lambda x: x['ev'][n])
        optimal_names.add(best['team_name'])

    print("\n" + "-" * 100)
    if len(optimal_names) == 1:
        winner = optimal_names.pop()
        print(f"  RANKING IS INVARIANT TO POOL SIZE.")
        print(f"  Optimal pick is {winner} at every N.")
        print(f"\n  Mathematical reason: EV = vegas_r6 * N * (1 - public_r6).")
        print(f"  When comparing two teams A and B:")
        print(f"    EV_A > EV_B  iff  vegas_r6_A * (1 - public_r6_A) > vegas_r6_B * (1 - public_r6_B)")
        print(f"  N appears as a common multiplicative factor on both sides and cancels.")
        print(f"  The ranking depends only on vegas_r6 * (1 - public_r6), which is independent of N.")
    else:
        print(f"  WARNING: Ranking varies by pool size. Optimal picks: {optimal_names}")
    sys.stdout.flush()

    # --- TABLE 3: Plain-language recommendation ---
    print("\n" + "=" * 100)
    print("TABLE 3: CHAMPION RECOMMENDATION (N=100)")
    print("=" * 100)
    best = ranked[0]
    sf = 'Y' if best['team_name'] in sign_flip_teams else 'N'
    pd = best.get('path_dependent_flag', 'N')

    stability = "STABLE"
    caveats = []
    if pd == 'Y':
        stability = "PATH-CONDITIONAL"
        caveats.append(f"Path-dependent: EV changes by {best.get('ev_path_pct_change', 0):.1f}% under alt E8 path")
    if sf == 'Y':
        stability = "SIGN-FLIP CONDITIONAL"
        caveats.append("Sign-flip team: leverage direction depends on E8 opponent")
    if any_instability:
        caveats.append("Uncertainty check: optimal pick changes under ±3pp bounds at some pool sizes")

    print(f"  Team:                  {best['team_name']}")
    print(f"  Seed:                  {best['team_seed']}")
    print(f"  Region:                {best['region']}")
    print(f"  vegas_r6:              {best['vegas_r6']:.4f} ({best['vegas_r6']*100:.2f}%)")
    print(f"  public_r6:             {best['public_r6_effective']:.4f} ({best['public_r6_effective']*100:.2f}%)")
    print(f"  EV@100:                {best['ev'][100]:.3f}")
    print(f"  Ownership class:       {best['ownership_class']}")
    print(f"  Recommendation status: {stability}")
    if caveats:
        for c in caveats:
            print(f"  Caveat:                {c}")

    # Runner-up
    if len(ranked) > 1:
        ru = ranked[1]
        print(f"\n  Runner-up:             {ru['team_name']} (EV@100={ru['ev'][100]:.3f}, "
              f"vegas_r6={ru['vegas_r6']:.4f}, public_r6={ru['public_r6_effective']:.4f})")
    sys.stdout.flush()

    # --- TABLE 4: Invariance statement ---
    print("\n" + "=" * 100)
    print("TABLE 4: POOL SIZE INVARIANCE")
    print("=" * 100)
    if len(optimal_names) <= 1:
        print("  The team ranking under EV = vegas_r6 * N * (1 - public_r6) is")
        print("  MATHEMATICALLY INVARIANT to pool size N.")
        print()
        print("  Reason: N is a scalar multiplier applied uniformly to every team's EV.")
        print("  Comparing team A vs team B:")
        print("    EV_A > EV_B")
        print("    vegas_r6_A * N * (1 - pub_r6_A) > vegas_r6_B * N * (1 - pub_r6_B)")
        print("    vegas_r6_A * (1 - pub_r6_A) > vegas_r6_B * (1 - pub_r6_B)    [divide both sides by N]")
        print()
        print("  The quantity vegas_r6 * (1 - public_r6) is the 'EV density' — it ranks teams")
        print("  identically regardless of whether N is 10 or 1,000. Pool size only scales the")
        print("  absolute EV magnitude, not the relative ordering.")
    sys.stdout.flush()

    print("\n" + "=" * 100)
    print("PROMPT 4 COMPLETE")
    print("=" * 100)
    sys.stdout.flush()


if __name__ == '__main__':
    main()
