"""最良戦略の、行動ごとの回数と得点への寄与を集計する。

ランダム戦略3人との4人戦。得点の由来（ledger）と行動回数（stats）から、
1回の行動あたりの得点も出す。
"""
import json
import random
from collections import defaultdict

import ga
from seti_sim import Genome, run

ACTION_OF_SOURCE = {
    "start": None,
    "orbit_first": "orbit", "land": "land",
    "scan_second_marker": "scan", "sector_win": "scan",
    "research_first": "research", "research_tech_bonus": "research",
    "trace_pink": "scan", "trace_purple": "scan",
    "trace_yellow": "land", "trace_blue": "analyze",
}

def load_best(seed=3):
    d = json.load(open(f"results/seed{seed}.json", encoding="utf-8"))
    return Genome(**d["best_genome"])

def main(n=1000, seed=11):
    best = load_best(3)
    rng = random.Random(seed)
    pts_by_src = defaultdict(float)
    cnt = defaultdict(float)
    total = 0.0
    wins = 0.0
    for _ in range(n):
        field = [ga.random_genome(rng) for _ in range(3)]
        order = list(range(4)); rng.shuffle(order)
        seats = [best] + field
        ordered = [seats[k] for k in order]
        scores, stats = run(ordered)
        pos = order.index(0)
        top = max(scores)
        if scores[pos] == top:
            wins += 1.0 / scores.count(top)
        total += scores[pos]
        st = stats[pos]
        for k, v in st["ledger"].items():
            pts_by_src[k] += v
        for k in ["launch", "orbit", "land", "scan", "analyze", "research", "move", "pass"]:
            cnt[k] += st[k]

    print(f"対戦数={n}  勝率={wins/n:.3f}  平均得点={total/n:.2f}")
    print("\n== 得点の由来（1ゲームあたり）")
    for k, v in sorted(pts_by_src.items(), key=lambda x: -x[1]):
        print(f"  {k:24s} {v/n:6.2f} 点  ({100*v/total:5.1f}%)")

    print("\n== 行動の回数（1ゲームあたり）と、その行動の得点寄与")
    per_src_action = defaultdict(float)
    for src, act in ACTION_OF_SOURCE.items():
        if act and src in pts_by_src:
            per_src_action[act] += pts_by_src[src]
    for act in ["launch", "orbit", "land", "scan", "analyze", "research", "move", "pass"]:
        c = cnt[act] / n
        p = per_src_action.get(act, 0.0) / n
        per = (per_src_action.get(act, 0.0) / cnt[act]) if cnt[act] else 0.0
        print(f"  {act:9s} 回数={c:5.2f}  得点寄与={p:5.2f}点  1回あたり={per:5.2f}点")

if __name__ == "__main__":
    main()
