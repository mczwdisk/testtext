"""遺伝的アルゴリズムで戦略（Genome）を進化させ、勝ちパターンを調べる。

適応度: 4人対戦で、勝った割合（同点は割り勘）。
対戦相手は、現在の集団からランダムに選ぶ（決定論的な乱数シード）。
"""
from __future__ import annotations

import json
import os
import random
import sys
from dataclasses import asdict

from seti_sim import Genome, RING, TECH_TYPES, run

N_PLAYERS = 4
POP = int(os.environ.get("GA_POP", 100))
GENS = int(os.environ.get("GA_GENS", 60))
GAMES_PER_EVAL = int(os.environ.get("GA_GAMES", 40))  # 1個体あたり、世代ごとの対戦数
ELITE = 5
MUT_RATE = 0.2
MUT_SIGMA = 0.5


def random_genome(rng: random.Random) -> Genome:
    return Genome(
        w_launch=rng.uniform(-1, 1),
        w_move=rng.uniform(-1, 1),
        w_orbit=rng.uniform(-1, 1),
        w_land=rng.uniform(-1, 1),
        w_scan=rng.uniform(-1, 1),
        w_analyze=rng.uniform(-1, 1),
        w_research=rng.uniform(-1, 1),
        w_pass=rng.uniform(-1, 1),
        move_reserve=rng.uniform(0, 4),
        sector_mode=rng.uniform(0, 2.99),
        planet_pref=[rng.uniform(-1, 1) for _ in RING],
        tech_pref=[rng.uniform(-1, 1) for _ in range(TECH_TYPES)],
    )


def mutate(g: Genome, rng: random.Random) -> Genome:
    c = g.copy()

    def mut(v):
        return v + rng.gauss(0, MUT_SIGMA) if rng.random() < MUT_RATE else v

    for name in ["w_launch", "w_move", "w_orbit", "w_land", "w_scan",
                 "w_analyze", "w_research", "w_pass"]:
        setattr(c, name, mut(getattr(c, name)))
    c.move_reserve = min(4.0, max(0.0, mut(c.move_reserve)))
    c.sector_mode = min(2.99, max(0.0, mut(c.sector_mode)))
    c.planet_pref = [mut(v) for v in c.planet_pref]
    c.tech_pref = [mut(v) for v in c.tech_pref]
    return c


def crossover(a: Genome, b: Genome, rng: random.Random) -> Genome:
    def pick(x, y):
        return x if rng.random() < 0.5 else y

    names = ["w_launch", "w_move", "w_orbit", "w_land", "w_scan",
             "w_analyze", "w_research", "w_pass", "move_reserve", "sector_mode"]
    kwargs = {n: pick(getattr(a, n), getattr(b, n)) for n in names}
    kwargs["planet_pref"] = [pick(x, y) for x, y in zip(a.planet_pref, b.planet_pref)]
    kwargs["tech_pref"] = [pick(x, y) for x, y in zip(a.tech_pref, b.tech_pref)]
    return Genome(**kwargs)


def evaluate(pop: list[Genome], rng_seed: int) -> list[float]:
    """各個体の適応度（勝率）を、ランダムな対戦で推定する。"""
    rng = random.Random(rng_seed)
    wins = [0.0] * len(pop)
    games = [0] * len(pop)
    for _ in range(GAMES_PER_EVAL):
        for i in range(len(pop)):
            others = rng.sample([j for j in range(len(pop)) if j != i], N_PLAYERS - 1)
            seats = [i] + others
            rng.shuffle(seats)
            scores, _ = run([pop[s] for s in seats])
            top = max(scores)
            winners = [k for k, sc in enumerate(scores) if sc == top]
            share = 1.0 / len(winners)
            for k, s in enumerate(seats):
                if k in winners:
                    wins[s] += share
                games[s] += 1
    return [wins[i] / games[i] if games[i] else 0.0 for i in range(len(pop))]


def evolve(seed: int = 1) -> tuple[list[Genome], list[float]]:
    rng = random.Random(seed)
    pop = [random_genome(rng) for _ in range(POP)]
    best_hist = []
    for gen in range(GENS):
        fit = evaluate(pop, rng_seed=seed * 1000 + gen)
        order = sorted(range(POP), key=lambda i: -fit[i])
        best_hist.append(fit[order[0]])
        print(f"gen {gen:02d}  best {fit[order[0]]:.3f}  mean {sum(fit)/POP:.3f}",
              file=sys.stderr)
        elites = [pop[i].copy() for i in order[:ELITE]]
        nxt = list(elites)
        while len(nxt) < POP:
            # トーナメント選択（3人）
            def tour():
                cand = rng.sample(range(POP), 3)
                return pop[max(cand, key=lambda i: fit[i])]
            a, b = tour(), tour()
            nxt.append(mutate(crossover(a, b, rng), rng))
        pop = nxt
    fit = evaluate(pop, rng_seed=seed * 1000 + GENS)
    order = sorted(range(POP), key=lambda i: -fit[i])
    return [pop[i] for i in order], [fit[i] for i in order]


if __name__ == "__main__":
    final, fits = evolve(seed=1)
    best = final[0]
    out = {"best_fitness": fits[0], "best_genome": asdict(best)}
    with open("best_genome.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))
