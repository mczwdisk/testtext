"""SETI 簡易シミュレーター（コアアクションのみ）。

モデル化するもの:
  - 資源（クレジット・エネルギー・公表度・データプール・コンピューター）
  - 探査機の発射・移動・周回・着陸（惑星値は config.json のユーザー指定値）
  - スキャン（信号マーク、セクター勝利、2番目のマーカーの得点）
  - 解析（コンピューター満杯時のみ、生命痕跡）
  - テック研究（12スタック、最初の取得者に2点）
  - パス、ラウンド終了、ラウンド間の収入、5ラウンドの最終得点

モデル化しないもの（config.json の assumptions を参照）:
  - カード効果、異星種族、太陽系の回転、金のスコアリングタイル、衛星
  - 惑星の実際の位置関係（一直線に並ぶと仮定）

ゲーム自体は乱数を使わず決定論的。戦略（遺伝子）だけで結果が決まる。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

RING = CFG["ring_order"]
PLANETS = CFG["planets"]
R = CFG["rules_from_rulebook"]
A = CFG["assumptions"]
EARTH_IDX = RING.index("Earth")
NUM_SECTORS = A["sector_count"]
EARTH_SECTOR = 0
TECH_STACKS = 12  # 3 種類 × 4 技術（ルールブック p.5, p.16）
TECH_TYPES = A["tech_types"]
TECH_PER_TYPE = A["tech_per_type"]
ACTION_CAP_PER_ROUND = 12  # 安全装置（モデルの都合。ルールではない）


@dataclass
class Genome:
    """戦略の遺伝子。すべて実数（sector_mode, reserve は整数化して使う）。"""
    w_launch: float = 0.5
    w_move: float = 0.3
    w_orbit: float = 0.5
    w_land: float = 0.5
    w_scan: float = 0.5
    w_analyze: float = 0.5
    w_research: float = 0.5
    w_pass: float = 0.0
    move_reserve: float = 2.0      # この値以上のエネルギーがあるときだけ移動する
    sector_mode: float = 0.0       # 0..2.99 → 0:最多データ 1:自分の所 2:最少マーカー
    planet_pref: list = field(default_factory=lambda: [0.0] * len(RING))
    tech_pref: list = field(default_factory=lambda: [0.0] * TECH_TYPES)

    def copy(self) -> "Genome":
        return Genome(
            self.w_launch, self.w_move, self.w_orbit, self.w_land, self.w_scan,
            self.w_analyze, self.w_research, self.w_pass, self.move_reserve,
            self.sector_mode, list(self.planet_pref), list(self.tech_pref),
        )


@dataclass
class Player:
    seat: int
    genome: Genome
    cr: int = R["start_credits"]
    en: int = R["start_energy"]
    pub: int = R["start_publicity"]
    pts: int = R["start_points_by_seat"][0]
    pool: int = 0
    comp: int = 0
    probe_on_board: bool = False
    orbiters: list = field(default_factory=list)  # 惑星名
    landers: list = field(default_factory=list)
    traces: dict = field(default_factory=lambda: {"pink": 0, "yellow": 0, "blue": 0, "purple": 0})
    techs: set = field(default_factory=set)  # stack index
    passed: bool = False
    turns_this_round: int = 0
    # 統計
    stats: dict = field(default_factory=lambda: {
        "launch": 0, "orbit": 0, "land": 0, "scan": 0, "analyze": 0,
        "research": 0, "move": 0, "pass": 0, "sector_wins": 0,
    })

    @property
    def computer_slots(self) -> int:
        return A["computer_top_row_slots"]


class Game:
    def __init__(self, genomes: list[Genome]):
        n = len(genomes)
        self.players = []
        for i, g in enumerate(genomes):
            p = Player(seat=i, genome=g)
            p.pts = R["start_points_by_seat"][i]
            self.players.append(p)
        self.n = n
        # セクター: 残りデータ数・マーカー列（置かれた順）
        self.sector_data = [A["sector_data_per_sector"]] * NUM_SECTORS
        self.sector_markers: list[list[int]] = [[] for _ in range(NUM_SECTORS)]
        # 惑星の状態
        self.first_orbit_taken = {p: False for p in RING}
        self.first_land_taken = {p: False for p in RING}
        # テックスタック: 残り枚数と最初の取得者フラグ
        self.stack_left = [TECH_PER_TYPE] * TECH_STACKS
        self.stack_first_taken = [False] * TECH_STACKS
        # 探査機の位置（惑星インデックス）
        self.probe_pos: dict[int, int | None] = {p.seat: None for p in self.players}

    # ---------- 基本ユーティリティ ----------
    def gain_pub(self, p: Player, amount: int):
        p.pub = min(10, p.pub + amount)  # 上限10（ルールブック p.19 の注意）

    def add_data(self, p: Player, amount: int):
        for _ in range(amount):
            if p.pool < R["data_pool_max"]:
                p.pool += 1
            # 上限超過分は捨てる

    def fill_computer(self, p: Player):
        while p.pool > 0 and p.comp < p.computer_slots:
            p.pool -= 1
            p.comp += 1

    # ---------- 合法手の判定 ----------
    def probe_planet(self, p: Player) -> str | None:
        idx = self.probe_pos[p.seat]
        if idx is None:
            return None
        return RING[idx]

    def can_launch(self, p: Player) -> bool:
        return (not p.probe_on_board) and p.cr >= R["launch_cost_credits"]

    def can_scan(self, p: Player) -> bool:
        return p.cr >= 1 and p.en >= 2  # スキャンは1クレジット＋2エネルギー

    def can_analyze(self, p: Player) -> bool:
        return p.en >= 1 and p.comp >= p.computer_slots

    def can_research(self, p: Player) -> bool:
        if p.pub < R["research_cost_publicity"]:
            return False
        return any(
            (self.stack_left[s] > 0 and s not in p.techs) for s in range(TECH_STACKS)
        )

    def orbiter_exists(self, planet: str) -> bool:
        return any(planet in q.orbiters for q in self.players)

    def can_orbit(self, p: Player) -> bool:
        pl = self.probe_planet(p)
        if pl is None or pl == "Earth":
            return False
        return p.cr >= 1 and p.en >= 1

    def land_cost(self, p: Player) -> int | None:
        pl = self.probe_planet(p)
        if pl is None or pl == "Earth":
            return None
        return (R["land_cost_energy_with_orbiter"] if self.orbiter_exists(pl)
                else R["land_cost_energy"])

    def can_land(self, p: Player) -> bool:
        cost = self.land_cost(p)
        return cost is not None and p.en >= cost

    # ---------- アクション実行 ----------
    def do_launch(self, p: Player):
        p.cr -= R["launch_cost_credits"]
        p.probe_on_board = True
        self.probe_pos[p.seat] = EARTH_IDX
        p.stats["launch"] += 1

    def do_move(self, p: Player, step: int):
        """1エネルギーで1移動（フリーアクション）。step は ±1。"""
        idx = self.probe_pos[p.seat]
        new = idx + step
        if new < 0 or new >= len(RING):
            return False
        p.en -= A["move_cost_energy"]
        self.probe_pos[p.seat] = new
        planet = RING[new]
        if planet != "Earth":
            self.gain_pub(p, PLANETS[planet]["publicity"])
        p.stats["move"] += 1
        return True

    def do_orbit(self, p: Player):
        pl = self.probe_planet(p)
        pd = PLANETS[pl]
        p.cr -= R["orbit_cost"]["credits"]
        p.en -= R["orbit_cost"]["energy"]
        p.cr += pd["orbit_credit"]
        p.en += pd["orbit_energy"]
        if not self.first_orbit_taken[pl]:
            self.first_orbit_taken[pl] = True
            p.pts += R["first_orbit_points"]
        p.orbiters.append(pl)
        p.probe_on_board = False
        self.probe_pos[p.seat] = None
        p.stats["orbit"] += 1

    def do_land(self, p: Player):
        pl = self.probe_planet(p)
        pd = PLANETS[pl]
        p.en -= self.land_cost(p)
        p.pts += pd["land_points"]
        p.traces["yellow"] += pd["yellow_trace"]
        if not self.first_land_taken[pl]:
            self.first_land_taken[pl] = True
            self.add_data(p, pd["first_land_data"])
        p.landers.append(pl)
        p.probe_on_board = False
        self.probe_pos[p.seat] = None
        p.stats["land"] += 1

    def mark_signal(self, p: Player, sector: int):
        """1つの信号をマーク。データを1つ取り、マーカーを置く。"""
        if self.sector_data[sector] <= 0:
            return
        self.sector_data[sector] -= 1
        self.add_data(p, 1)
        markers = self.sector_markers[sector]
        markers.append(p.seat)
        if len(markers) == 2:
            p.pts += R["second_marker_points"]  # 2番目のマーカーで2点（p.13）

    def resolve_completed_sectors(self):
        for s in range(NUM_SECTORS):
            if self.sector_data[s] > 0:
                continue
            markers = self.sector_markers[s]
            if markers:
                # 最多マーカー。同数は後に置いた人が勝ち（p.13）
                counts: dict[int, int] = {}
                for seat in markers:
                    counts[seat] = counts.get(seat, 0) + 1
                best = max(counts.values())
                tied = [seat for seat, c in counts.items() if c == best]
                winner = None
                for seat in reversed(markers):  # 後に置いた順
                    if seat in tied:
                        winner = seat
                        break
                wp = self.players[winner]
                wp.pts += A["sector_win_points"]
                wp.stats["sector_wins"] += 1
                if A.get("sector_win_trace") == "purple":
                    wp.traces["purple"] += 1  # 仮決定（Ludex由来）
                for seat in set(markers):
                    self.gain_pub(self.players[seat],
                                  A["sector_win_publicity_contributors"])
            # リセット
            self.sector_markers[s] = []
            self.sector_data[s] = A["sector_data_per_sector"]

    def do_scan(self, p: Player):
        p.cr -= 1
        p.en -= 2
        p.stats["scan"] += 1
        p.traces["pink"] += A.get("scan_trace_pink", 1)
        # 信号1: 地球のセクター
        self.mark_signal(p, EARTH_SECTOR)
        # 信号2: 遺伝子で選ぶセクター
        target = self.pick_scan_sector(p)
        if target is not None:
            self.mark_signal(p, target)
        self.resolve_completed_sectors()

    def pick_scan_sector(self, p: Player) -> int | None:
        candidates = [s for s in range(NUM_SECTORS) if self.sector_data[s] > 0]
        if not candidates:
            return None
        mode = int(p.genome.sector_mode) % 3
        if mode == 0:  # 最多データ
            return max(candidates, key=lambda s: (self.sector_data[s], -s))
        if mode == 1:  # 自分のマーカーがあるセクター優先
            mine = [s for s in candidates if p.seat in self.sector_markers[s]]
            pool = mine or candidates
            return max(pool, key=lambda s: (self.sector_data[s], -s))
        # 最少マーカー
        return min(candidates, key=lambda s: (len(self.sector_markers[s]), -s))

    def do_analyze(self, p: Player):
        p.en -= R["analyze_cost_energy"]
        p.comp = 0
        p.traces[A["analyze_trace_type"]] += 1
        p.stats["analyze"] += 1

    def do_research(self, p: Player):
        p.pub -= R["research_cost_publicity"]
        # 遺伝子が好むタイプのスタックから、所持していないものを選ぶ
        best, best_v = None, None
        for s in range(TECH_STACKS):
            if self.stack_left[s] <= 0 or s in p.techs:
                continue
            t = s // TECH_PER_TYPE
            v = p.genome.tech_pref[t]
            if best_v is None or v > best_v:
                best, best_v = s, v
        if best is None:
            return
        self.stack_left[best] -= 1
        p.techs.add(best)
        if not self.stack_first_taken[best]:
            self.stack_first_taken[best] = True
            p.pts += R["first_research_points"]
        p.pts += A["tech_bonus_points_per_tech"]
        p.cr += A["tech_bonus_credit_per_tech"]
        p.stats["research"] += 1

    def do_pass(self, p: Player):
        p.passed = True
        p.stats["pass"] += 1

    # ---------- 方針決定 ----------
    def free_actions(self, p: Player):
        """手番の前に行うフリーアクション: データの配置と移動。"""
        self.fill_computer(p)
        g = p.genome
        if not p.probe_on_board:
            return
        idx = self.probe_pos[p.seat]
        if idx is None:
            return
        # 移動先: 好みの惑星（ユーザー値に対する遺伝子の重み）。
        # 1歩ずつ、好みの方向へ進む。予備エネルギーを下回る場合は動かない。
        best_idx, best_v = None, None
        for j, name in enumerate(RING):
            if j == idx:
                continue
            v = g.planet_pref[j] - 0.1 * abs(j - idx)
            if best_v is None or v > best_v:
                best_idx, best_v = j, v
        if best_idx is None or best_v is None or best_v <= 0:
            return
        while p.en - A["move_cost_energy"] >= g.move_reserve and idx != best_idx:
            step = 1 if best_idx > idx else -1
            if g.w_move <= 0:
                return
            if not self.do_move(p, step):
                return
            idx = self.probe_pos[p.seat]

    def choose_main(self, p: Player) -> str:
        g = p.genome
        options: list[tuple[float, str]] = []
        if self.can_launch(p):
            options.append((g.w_launch, "launch"))
        if self.can_orbit(p):
            pl = self.probe_planet(p)
            options.append((g.w_orbit + g.planet_pref[RING.index(pl)], "orbit"))
        if self.can_land(p):
            pl = self.probe_planet(p)
            options.append((g.w_land + g.planet_pref[RING.index(pl)], "land"))
        if self.can_scan(p):
            options.append((g.w_scan, "scan"))
        if self.can_analyze(p):
            options.append((g.w_analyze, "analyze"))
        if self.can_research(p):
            options.append((g.w_research, "research"))
        options.append((g.w_pass, "pass"))
        options.sort(key=lambda x: -x[0])
        return options[0][1]

    def take_turn(self, p: Player):
        self.free_actions(p)
        p.turns_this_round += 1
        if p.turns_this_round > ACTION_CAP_PER_ROUND:
            # 安全装置: 1ラウンドの手番が多すぎる場合は強制パス（モデルの都合）
            self.do_pass(p)
            return
        act = self.choose_main(p)
        if act == "launch":
            self.do_launch(p)
        elif act == "orbit":
            self.do_orbit(p)
        elif act == "land":
            self.do_land(p)
        elif act == "scan":
            self.do_scan(p)
        elif act == "analyze":
            self.do_analyze(p)
        elif act == "research":
            self.do_research(p)
        elif act == "pass":
            self.do_pass(p)
        self.fill_computer(p)

    # ---------- ラウンド・ゲーム進行 ----------
    def income(self):
        for p in self.players:
            p.cr += A["income_per_round"]["credits"]
            p.en += A["income_per_round"]["energy"]

    def play(self, max_turns: int = 2000) -> list[int]:
        turns = 0
        for rnd in range(R["rounds"]):
            for p in self.players:
                p.passed = False
                p.turns_this_round = 0
            start = rnd % self.n  # 先手は毎ラウンド左隣へ（p.19）
            order = [(start + k) % self.n for k in range(self.n)]
            while not all(p.passed for p in self.players):
                for seat in order:
                    p = self.players[seat]
                    if p.passed:
                        continue
                    self.take_turn(p)
                    turns += 1
                    if turns > max_turns:
                        raise RuntimeError("turn limit exceeded")
            if rnd < R["rounds"] - 1:
                self.income()
        # 生命痕跡の得点（仮定: 1痕跡につき trace_points_each 点。ルールブックの数値ではない）
        for p in self.players:
            p.pts += A["trace_points_each"] * sum(p.traces.values())
        return [p.pts for p in self.players]


def run(genomes: list[Genome]) -> tuple[list[int], list[dict]]:
    g = Game(genomes)
    scores = g.play()
    return scores, [p.stats for p in g.players]


if __name__ == "__main__":
    baseline = Genome()
    s, st = run([baseline, baseline, baseline])
    print("scores:", s)
    print("stats:", st)
