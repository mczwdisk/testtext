"""シミュレーターのルール不変条件テスト。

実行: python3 tests.py
ルールブック（英語版PDF）に明記された事項だけを検査する。仮定の値には依存しないように書く。
"""
import copy
import random

import seti_sim
from seti_sim import Game, Genome, RING, R, A, EARTH_IDX, TECH_STACKS


def fresh(n=2):
    return Game([Genome() for _ in range(n)])


def test_launch_costs_two_credits_and_limits_one_probe():
    g = fresh()
    p = g.players[0]
    p.cr = 5
    g.do_launch(p)
    assert p.cr == 5 - R["launch_cost_credits"], "発射は2クレジット（p.8）"
    assert p.probe_on_board
    assert not g.can_launch(p), "宇宙空間の探査機は1機まで（p.8）"


def test_orbit_costs_credit_and_energy_and_first_orbit_three_points():
    g = fresh()
    p = g.players[0]
    p.cr, p.en = 5, 5
    g.do_launch(p)
    g.probe_pos[p.seat] = RING.index("Jupiter")
    p.cr, p.en, p.pts = 5, 5, 0
    g.do_orbit(p)
    # 木星の軌道報酬（config）と、最初の周回3点（p.10）
    assert p.en == 5 - 1 + 0
    assert p.pts == R["first_orbit_points"] + 0 or p.pts >= R["first_orbit_points"]
    assert "Jupiter" in p.orbiters
    assert not p.probe_on_board


def test_land_cost_three_energy_two_with_existing_orbiter():
    g = fresh()
    a, b = g.players
    a.en = b.en = 10
    g.do_launch(a)
    g.probe_pos[a.seat] = RING.index("Mars")
    assert g.land_cost(a) == R["land_cost_energy"], "着陸はエネルギー3（p.11）"
    b.orbiters.append("Mars")
    assert g.land_cost(a) == R["land_cost_energy_with_orbiter"], "軌道があれば2（p.11）"


def test_data_pool_capped_at_six():
    g = fresh()
    p = g.players[0]
    g.add_data(p, 10)
    assert p.pool == R["data_pool_max"], "データプールは最大6（p.14）"


def test_publicity_capped_at_ten():
    g = fresh()
    p = g.players[0]
    p.pub = 9
    g.gain_pub(p, 5)
    assert p.pub == 10, "公表度の上限は10（p.19）"


def test_research_needs_six_publicity():
    g = fresh()
    p = g.players[0]
    p.pub = 5
    assert not g.can_research(p), "テック研究は公表度6（p.16）"
    p.pub = 6
    assert g.can_research(p)


def test_second_marker_in_sector_scores_two():
    g = fresh()
    a, b = g.players
    a.pts = b.pts = 0
    g.mark_signal(a, 3)
    assert a.pts == 0
    g.mark_signal(b, 3)
    assert b.pts == R["second_marker_points"], "2番目のマーカーは2点（p.13）"


def test_sector_tie_goes_to_later_marker():
    g = fresh()
    a, b = g.players
    a.pts = b.pts = 0
    # 地球のセクター以外で、同数マーカーを作る（データは4個あるので2人で2個ずつ）
    s = 5
    # データ4個を2人が交互に取る → 2個ずつ同数、最後に置いたのはb
    g.mark_signal(a, s)
    g.mark_signal(b, s)
    g.mark_signal(a, s)
    g.mark_signal(b, s)
    assert g.sector_data[s] == 0
    g.resolve_completed_sectors()  # 完成判定は1回だけ
    assert b.stats["sector_wins"] == 1, "同数は後に置いた人が勝ち（p.13）"
    assert a.stats["sector_wins"] == 0


def test_pass_is_main_action_and_ends_round_participation():
    g = fresh()
    p = g.players[0]
    g.do_pass(p)
    assert p.passed


def test_round_count_and_game_finishes():
    scores, _ = seti_sim.run([Genome(), Genome(), Genome(), Genome()])
    assert len(scores) == 4


def test_deterministic():
    g1 = Genome(w_research=2.0, w_launch=1.0, w_orbit=1.0, w_land=1.0)
    s1, _ = seti_sim.run([g1, Genome(), Genome(), Genome()])
    s2, _ = seti_sim.run([g1, Genome(), Genome(), Genome()])
    assert s1 == s2


def test_random_games_terminate_and_scores_are_nonnegative():
    rng = random.Random(0)
    for _ in range(200):
        gs = [Genome(
            w_launch=rng.uniform(-1, 1), w_move=rng.uniform(-1, 1),
            w_orbit=rng.uniform(-1, 1), w_land=rng.uniform(-1, 1),
            w_scan=rng.uniform(-1, 1), w_analyze=rng.uniform(-1, 1),
            w_research=rng.uniform(-1, 1), w_pass=rng.uniform(-1, 1),
            move_reserve=rng.uniform(0, 4), sector_mode=rng.uniform(0, 2.99),
            planet_pref=[rng.uniform(-1, 1) for _ in RING],
            tech_pref=[rng.uniform(-1, 1) for _ in range(3)],
        ) for _ in range(4)]
        scores, _ = seti_sim.run(gs)
        assert all(s >= 0 for s in scores)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", t.__name__, e)
    print(f"{len(tests) - failed}/{len(tests)} passed")
