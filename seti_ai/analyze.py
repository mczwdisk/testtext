"""複数シードでGAを回し、最良個体の傾向と、その個体の行動統計を出す。"""
import json, statistics
from dataclasses import asdict
import ga
from seti_sim import Genome, run, RING

summary = []
bests = []
for seed in [1, 2, 3]:
    final, fits = ga.evolve(seed=seed)
    bests.append(final[0])
    summary.append({"seed": seed, "best_fitness": round(fits[0], 3)})
print(json.dumps(summary, ensure_ascii=False))

# 最良個体同士・ベースラインとの対戦で行動統計を取る
def play_stats(g, opp, n=50):
    import random
    rng = random.Random(0)
    agg = {k: 0 for k in ["launch","orbit","land","scan","analyze","research","move","pass","sector_wins"]}
    win = 0
    for _ in range(n):
        seats = [g, opp, opp, opp]
        scores, st = run(seats)
        top = max(scores)
        if scores[0] == top: win += 1
        for k in agg: agg[k] += st[0][k]
    return win / n, {k: round(v / n, 2) for k, v in agg.items()}

for i, g in enumerate(bests):
    wr, st = play_stats(g, bests[(i+1) % len(bests)])
    print(f"seed{i+1} vs other-best: win_rate={wr:.2f}", json.dumps(st))
    print("  planet_pref:", {RING[j]: round(v,2) for j, v in enumerate(g.planet_pref)})
    print("  w: launch=%.2f move=%.2f orbit=%.2f land=%.2f scan=%.2f analyze=%.2f research=%.2f pass=%.2f" % (
        g.w_launch, g.w_move, g.w_orbit, g.w_land, g.w_scan, g.w_analyze, g.w_research, g.w_pass))
    print("  move_reserve=%.2f sector_mode=%.2f tech_pref=%s" % (g.move_reserve, g.sector_mode, [round(x,2) for x in g.tech_pref]))
