"""1シードのGAを実行し、最良個体の勝率を大量の対戦で推定する。

使い方: python3 final_eval.py <seed>
出力: results/seed<seed>.json（最良個体、GA適応度、評価の勝率と95%信頼区間）
"""
import json
import math
import os
import random
import sys
from dataclasses import asdict

import ga
from seti_sim import run

EVAL_GAMES = int(os.environ.get("EVAL_GAMES", 4000))


def win_rate_vs_random_field(best, rng: random.Random, n: int):
    """最良個体1人 + 進化させていない乱数の戦略3人 で n 回対戦した勝率。"""
    wins = 0.0
    for _ in range(n):
        field = [ga.random_genome(rng) for _ in range(3)]
        seats = [best] + field
        order = list(range(4))
        rng.shuffle(order)
        ordered = [seats[k] for k in order]
        scores, _ = run(ordered)
        top = max(scores)
        pos = order.index(0)  # 最良個体の席
        if scores[pos] == top:
            wins += 1.0 / scores.count(top)
    p = wins / n
    se = math.sqrt(p * (1 - p) / n)
    return p, 1.96 * se


if __name__ == "__main__":
    seed = int(sys.argv[1])
    final, fits = ga.evolve(seed=seed)
    best = final[0]
    rng = random.Random(10_000 + seed)
    p, ci = win_rate_vs_random_field(best, rng, EVAL_GAMES)
    out = {
        "seed": seed,
        "ga_fitness": round(fits[0], 4),
        "eval_win_rate_vs_random_field": round(p, 4),
        "eval_95ci_half_width": round(ci, 4),
        "eval_games": EVAL_GAMES,
        "pop": ga.POP, "gens": ga.GENS, "games_per_eval": ga.GAMES_PER_EVAL,
        "best_genome": asdict(best),
    }
    os.makedirs("results", exist_ok=True)
    with open(f"results/seed{seed}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ["seed", "ga_fitness",
                                          "eval_win_rate_vs_random_field",
                                          "eval_95ci_half_width"]}))
