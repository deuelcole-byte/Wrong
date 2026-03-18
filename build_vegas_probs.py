#!/usr/bin/env python3
"""
Build vegas_raw_2026.csv from ESPN/DraftKings moneyline and futures odds.
Devig using additive method for game-level probabilities.
Convert futures to implied probabilities for round-by-round advancement.
"""
import csv
import math

def american_to_implied(odds):
    """Convert American odds to raw implied probability."""
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)

def devig_pair(odds_a, odds_b):
    """Devig a moneyline pair using additive method. Returns (prob_a, prob_b)."""
    imp_a = american_to_implied(odds_a)
    imp_b = american_to_implied(odds_b)
    total = imp_a + imp_b
    return imp_a / total, imp_b / total

def futures_to_prob(odds):
    """Convert futures odds (American) to implied probability (no devig — futures books are multi-way)."""
    return american_to_implied(odds)

# ============================================================
# First-round moneylines from ESPN/DraftKings
# Format: (team_a, seed_a, region, odds_a, team_b, seed_b, odds_b)
# ============================================================
first_round = [
    # EAST
    ("Duke", 1, "East", -20000, "Siena", 16, 3500),
    ("Ohio State", 8, "East", -142, "TCU", 9, 120),
    ("St John's", 5, "East", -600, "Northern Iowa", 12, 450),
    ("Kansas", 4, "East", -1200, "CA Baptist", 13, 750),
    ("Louisville", 6, "East", -225, "South Florida", 11, 185),
    ("Michigan St", 3, "East", -1800, "N Dakota St", 14, 1000),
    ("UCLA", 7, "East", -250, "UCF", 10, 205),
    ("UConn", 2, "East", -4500, "Furman", 15, 1700),
    # SOUTH
    ("Florida", 1, "South", -5000, "PV/LEH", 16, 2000),  # estimated from similar 1v16
    ("Clemson", 8, "South", 114, "Iowa", 9, -135),
    ("Vanderbilt", 5, "South", -700, "McNeese", 12, 500),
    ("Nebraska", 4, "South", -1000, "Troy", 13, 650),
    ("North Carolina", 6, "South", -142, "VCU", 11, 120),
    ("Illinois", 3, "South", -6500, "Penn", 14, 2000),
    ("Saint Mary's", 7, "South", -162, "Texas A&M", 10, 136),
    ("Houston", 2, "South", -8000, "Idaho", 15, 2200),
    # WEST
    ("Arizona", 1, "West", -100000, "Long Island", 16, 5000),
    ("Villanova", 8, "West", 105, "Utah State", 9, -125),
    ("Wisconsin", 5, "West", -500, "High Point", 12, 380),
    ("Arkansas", 4, "West", -1450, "Hawai'i", 13, 850),
    ("BYU", 6, "West", -148, "Texas", 11, 124),
    ("Gonzaga", 3, "West", -3200, "Kennesaw St", 14, 1400),
    ("Miami", 7, "West", -130, "Missouri", 10, 110),
    ("Purdue", 2, "West", -8000, "Queens", 15, 2200),
    # MIDWEST
    ("Michigan", 1, "Midwest", -50000, "Howard", 16, 4000),
    ("Georgia", 8, "Midwest", -148, "Saint Louis", 9, 124),
    ("Texas Tech", 5, "Midwest", -340, "Akron", 12, 270),  # seed corrected: Akron=12 per bracket
    ("Alabama", 4, "Midwest", -800, "Hofstra", 13, 550),
    ("Tennessee", 6, "Midwest", -310, "M-OH/SMU", 11, 250),  # SMU line as proxy
    ("Virginia", 3, "Midwest", -2800, "Wright St", 14, 1300),
    ("Kentucky", 7, "Midwest", -162, "Santa Clara", 10, 136),
    ("Iowa State", 2, "Midwest", -8000, "Tennessee St", 15, 2200),
]

# ============================================================
# Round-by-round futures odds from ESPN/DraftKings
# Format: team, seed, region, R64_odds, S16_odds(=Sweet16), E8_odds, F4_odds(=Semis), Finals_odds, Champ_odds
# Using the table: Round of 64, Sweet 16, Elite Eight, Semis, Finals, Championship
# ============================================================
futures_data = [
    # 1 seeds
    ("Duke", 1, "East", -20000, -600, -255, -135, 140, 360),
    ("Michigan", 1, "Midwest", -50000, -900, -380, -130, 155, 370),
    ("Arizona", 1, "West", -100000, -800, -275, -120, 175, 380),
    ("Florida", 1, "South", -5000, -450, -160, 165, 350, 750),
    # 2 seeds
    ("Houston", 2, "South", -8000, -280, 110, 250, 475, 1200),
    ("Iowa State", 2, "Midwest", -8000, -400, -130, 245, 750, 1800),
    ("Purdue", 2, "West", -8000, -330, 105, 360, 900, 2500),
    ("UConn", 2, "East", -4500, -200, 170, 600, 1300, 2500),
    # 3 seeds
    ("Illinois", 3, "South", -6500, -400, 120, 310, 800, 2200),
    ("Michigan St", 3, "East", -1800, -135, 200, 700, 1700, 5500),
    ("Gonzaga", 3, "West", -3200, -225, 160, 500, 1800, 6000),
    ("Virginia", 3, "Midwest", -2800, -125, 310, 1100, 3000, 7500),
    # 4 seeds
    ("Arkansas", 4, "West", -1450, -120, 450, 1100, 3000, 6000),
    ("Kansas", 4, "East", -1200, 125, 650, 1500, 3000, 6000),
    ("Nebraska", 4, "South", -1000, -105, 400, 1100, 4000, 12000),
    ("Alabama", 4, "Midwest", -800, -120, 750, 2200, 6000, 18000),
    # 5 seeds
    ("St John's", 5, "East", -600, -105, 475, 900, 2000, 7500),
    ("Vanderbilt", 5, "South", -700, -110, 350, 1100, 3000, 7500),
    ("Wisconsin", 5, "West", -500, 120, 550, 1500, 3500, 10000),
    ("Texas Tech", 5, "Midwest", -340, 105, 600, 1700, 3500, 13000),
    # 6 seeds
    ("Tennessee", 6, "Midwest", -310, 130, 400, 1300, 4000, 13000),  # R64 line from SMU matchup
    ("Louisville", 6, "East", -225, 150, 360, 1300, 3000, 15000),
    ("North Carolina", 6, "South", -142, 250, 600, 6000, 18000, 30000),  # corrected: R64 odds not 20-1
    ("BYU", 6, "West", -148, 250, 400, 6000, 13000, 35000),  # corrected similarly
    # 7 seeds
    ("UCLA", 7, "East", -250, 200, 550, 2200, 5500, 18000),
    ("Kentucky", 7, "Midwest", -162, 250, 550, 4500, 9000, 25000),  # corrected
    ("Saint Mary's", 7, "South", -162, 250, 360, 3500, 7500, 30000),  # corrected
    ("Miami", 7, "West", -130, 250, 400, 5000, 12000, 50000),  # corrected
    # 8 seeds
    ("Ohio State", 8, "East", -142, 700, 1100, 2500, 6000, 25000),
    ("Clemson", 8, "South", 114, 500, 750, 6500, 11000, 50000),  # corrected
    ("Villanova", 8, "West", 105, 500, 950, 7500, 18000, 50000),  # corrected
    ("Georgia", 8, "Midwest", -148, 500, 900, 6500, 20000, 50000),  # corrected
    # 9 seeds
    ("TCU", 9, "East", 120, 1600, 3500, 13000, 35000, 50000),  # corrected from weird data
    ("Iowa", 9, "South", -135, 450, 700, 4500, 14000, 30000),
    ("Utah State", 9, "West", -125, 400, 1000, 9000, 20000, 50000),
    ("Saint Louis", 9, "Midwest", 124, 1500, 3000, 17000, 30000, 80000),  # corrected
    # 10 seeds
    ("UCF", 10, "East", 205, 1400, 5000, 45000, 60000, 80000),
    ("Texas A&M", 10, "South", 136, 900, 4000, 14000, 40000, 50000),  # corrected
    ("Missouri", 10, "West", 110, 1100, 3000, 13000, 25000, 50000),  # corrected
    ("Santa Clara", 10, "Midwest", 136, 1200, 800, 7500, 20000, 50000),  # corrected
    # 11 seeds
    ("South Florida", 11, "East", 185, 800, 2000, 8000, 20000, 40000),
    ("VCU", 11, "South", 120, 750, 3000, 15000, 30000, 50000),  # corrected
    ("Texas", 11, "West", 124, 600, 650, 7000, 20000, 40000),
    ("M-OH/SMU", 11, "Midwest", 250, 4500, 10000, 18000, 25000, 50000),  # combined play-in
    # 12 seeds
    ("Northern Iowa", 12, "East", 450, 1200, 4000, 25000, 35000, 200000),
    ("McNeese", 12, "South", 500, 2000, 5000, 30000, 40000, 100000),
    ("High Point", 12, "West", 380, 3000, 6000, 40000, 60000, 200000),
    ("Akron", 12, "Midwest", 270, 2000, 5000, 50000, 70000, 100000),
    # 13 seeds
    ("CA Baptist", 13, "East", 750, 2200, 7500, 50000, 100000, 200000),
    ("Troy", 13, "South", 650, 5500, 6500, 50000, 80000, 200000),
    ("Hawai'i", 13, "West", 850, 6000, 8500, 50000, 80000, 200000),
    ("Hofstra", 13, "Midwest", 550, 2500, 5500, 40000, 60000, 200000),
    # 14 seeds
    ("N Dakota St", 14, "East", 1000, 5000, 10000, 50000, 40000, 200000),
    ("Penn", 14, "South", 2000, 11000, 20000, 70000, 100000, 150000),
    ("Kennesaw St", 14, "West", 1400, 12000, 14000, 60000, 100000, 200000),
    ("Wright St", 14, "Midwest", 1300, 10000, 13000, 80000, 100000, 200000),
    # 15 seeds
    ("Furman", 15, "East", 1700, 12000, 17000, 80000, 100000, 200000),
    ("Idaho", 15, "South", 2200, 9000, 22000, 60000, 100000, 200000),
    ("Queens", 15, "West", 2200, 20000, 22000, 60000, 100000, 200000),
    ("Tennessee St", 15, "Midwest", 2200, 30000, 22000, 80000, 100000, 200000),
    # 16 seeds
    ("Siena", 16, "East", 3500, 20000, 35000, 80000, 100000, 200000),
    ("PV/LEH", 16, "South", 2000, 50000, 40000, 80000, 100000, 200000),
    ("Long Island", 16, "West", 5000, 40000, 50000, 100000, 100000, 200000),
    ("Howard", 16, "Midwest", 4000, 20000, 40000, 60000, 100000, 200000),
]

# ============================================================
# Build devigged first-round game probabilities
# ============================================================
game_probs = {}  # team -> devigged R1 win prob
for (ta, sa, ra, oa, tb, sb, ob) in first_round:
    pa, pb = devig_pair(oa, ob)
    game_probs[ta] = pa
    game_probs[tb] = pb

# ============================================================
# Build round-by-round implied probabilities from futures
# Each futures line implies P(reach at least round X).
# r1 = P(win R64), r2 = P(reach S16), r3 = P(reach E8),
# r4 = P(reach F4), r5 = P(reach Finals), r6 = P(win title)
# ============================================================
rows = []
for (team, seed, region, r64_odds, s16_odds, e8_odds, f4_odds, finals_odds, champ_odds) in futures_data:
    # Convert each futures line to implied probability
    # These are "to advance past" that round, so they represent cumulative advancement
    r1 = futures_to_prob(r64_odds)   # P(win first round)
    r2 = futures_to_prob(s16_odds)   # P(reach Sweet 16)
    r3 = futures_to_prob(e8_odds)    # P(reach Elite 8)
    r4 = futures_to_prob(f4_odds)    # P(reach Final Four)
    r5 = futures_to_prob(finals_odds)  # P(reach Finals)
    r6 = futures_to_prob(champ_odds)  # P(win championship)

    # Use devigged game prob for R1 if available (more accurate than futures)
    if team in game_probs:
        r1 = game_probs[team]

    # Ensure monotonicity: each round prob <= previous round prob
    probs = [r1, r2, r3, r4, r5, r6]
    for i in range(1, len(probs)):
        if probs[i] > probs[i-1]:
            probs[i] = probs[i-1]

    rows.append({
        'team_name': team,
        'team_seed': seed,
        'region': region,
        'vegas_prob_game': round(game_probs.get(team, r1), 4),
        'r1': round(probs[0], 4),
        'r2': round(probs[1], 4),
        'r3': round(probs[2], 4),
        'r4': round(probs[3], 4),
        'r5': round(probs[4], 4),
        'r6': round(probs[5], 4),
    })

# Sort by championship probability descending
rows.sort(key=lambda x: -x['r6'])

# Write CSV
with open('vegas_raw_2026.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'team_name', 'team_seed', 'region', 'vegas_prob_game',
        'r1', 'r2', 'r3', 'r4', 'r5', 'r6'
    ])
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} teams to vegas_raw_2026.csv")
print("\nTop 10 by championship probability:")
print(f"{'Team':<20} {'Seed':<5} {'Region':<10} {'R1':>6} {'R2(S16)':>8} {'R3(E8)':>8} {'R4(F4)':>8} {'R5(Fin)':>8} {'R6(Ch)':>8}")
for r in rows[:10]:
    print(f"{r['team_name']:<20} {r['team_seed']:<5} {r['region']:<10} {r['r1']:>6.1%} {r['r2']:>8.1%} {r['r3']:>8.1%} {r['r4']:>8.1%} {r['r5']:>8.1%} {r['r6']:>8.1%}")

# Also print devigged first-round game probabilities
print("\n\nDevigged first-round game probabilities:")
print(f"{'Team A':<20} {'Prob A':>7} | {'Team B':<20} {'Prob B':>7}")
print("-" * 60)
for (ta, sa, ra, oa, tb, sb, ob) in first_round:
    pa, pb = devig_pair(oa, ob)
    print(f"{ta:<20} {pa:>6.1%} | {tb:<20} {pb:>6.1%}")
