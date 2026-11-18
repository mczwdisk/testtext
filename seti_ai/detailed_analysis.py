"""最良戦略の詳細分析。

1. 行動の内訳: 1ゲームあたりの平均行動回数（ランダム戦略3人との4人戦）
2. 感度分析: 仮定の値（config.json の assumptions）を変えたとき、
   同じ戦略の勝率がどう変わるか。
   進化はやり直さず、固定した最良戦略の強さだけを比べる。

結論の頑健さ（仮定を変えても同じ結論か）を確かめるのが目的。
"""
import copy
import json
import glob
import random
import statistics

import seti_sim
from seti_sim import Genome, run, A, RING
import ga

N = 1000  # 1設定あたりの対戦数


def load_bests():
    out = []
    for f in sorted(glob.glob("results/seed*.json")):
        d = json.load(open(f, encoding="utf-8"))
        out.append((d["seed"], Genome(**d["best_genome"])))
    return out


def evaluate(best: Genome, n: int, seed: int):
    """ランダム戦略3人との4人戦。勝率（同点は割り勘）と平均得点・行動を返す。"""
    rng = random.Random(seed)
    wins = 0.0
    pts = []
    acts = {k: 0 for k in ["launch", "orbit", "land", "scan", "analyze",
                           "research", "move", "pass", "sector_wins"]}
    for _ in range(n):
        field = [ga.random_genome(rng) for _ in range(3)]
        order = list(range(4))
        rng.shuffle(order)
        seats = [best] + field
        ordered = [seats[k] for k in order]
        scores, stats = run(ordered)
        pos = order.index(0)
        top = max(scores)
        if scores[pos] == top:
            wins += 1.0 / scores.count(top)
        pts.append(scores[pos])
        for k in acts:
            acts[k] += stats[pos][k]
    return wins / n, statistics.mean(pts), {k: round(v / n, 2) for k, v in acts.items()}


def set_assumption(name, value):
    A[name] = value


SENSITIVITY = {
    "sector_win_points": [1, 3, 5],          # 仮定: セクター勝者の得点（基準3）
    "tech_bonus_points_per_tech": [0, 1, 2],  # 仮定: テック1枚あたりの得点（基準1）
    "computer_top_row_slots": [3, 4, 5],      # 仮定: コンピューター枠（基準4）
    "sector_data_per_sector": [3, 4, 5],      # 仮定: セクターのデータ数（基準4）
}
# 注: 生命痕跡の得点（trace_points_each）はシミュレーターで最終得点に加算していない。
#     そのため感度分析の対象にしない（別途、モデルの修正が必要）。


def main():
    bests = load_bests()
    base = copy.deepcopy(A)

    print("== 1. 行動の内訳（基準の仮定、ランダム3人との4人戦）")
    for seed, g in bests:
        wr, mp, acts = evaluate(g, N, seed=7)
        print(f"seed{seed}: 勝率={wr:.3f} 平均得点={mp:.1f} 行動={json.dumps(acts)}")

    print("\n== 2. 感度分析（各仮定を1つずつ変更、他は基準）")
    print("仮定の変更により、勝率が変わるか（5シードの平均勝率）")
    for name, values in SENSITIVITY.items():
        row = []
        for v in values:
            A.clear(); A.update(copy.deepcopy(base))
            set_assumption(name, v)
            wrs = [evaluate(g, N // 2, seed=7)[0] for _, g in bests]
            row.append((v, round(statistics.mean(wrs), 3), round(min(wrs), 3), round(max(wrs), 3)))
        A.clear(); A.update(copy.deepcopy(base))
        print(f"{name}:")
        for v, m, lo, hi in row:
            print(f"   値={v}  平均勝率={m}  最小={lo}  最大={hi}")

    print("\n== 3. 研究を禁止したときの勝率（研究の重要性を確かめる）")
    for seed, g in bests:
        g2 = g.copy()
        g2.w_research = -10.0
        wr_base, _, _ = evaluate(g, N // 2, seed=7)
        wr_no, _, _ = evaluate(g2, N // 2, seed=7)
        print(f"seed{seed}: 研究あり={wr_base:.3f}  研究なし={wr_no:.3f}")


if __name__ == "__main__":
    main()
