#!/usr/bin/env python3
"""
Foliage 時空光錐模擬器

讀取伺服器錄下來的取樣資料（JSON Lines），用三種方式切分「時空」（可平行的區域）並比較：
  paper   整台伺服器只有一條時間線
  folia   Folia 的固定區域：16x16 區塊為一個 section，建立／合併半徑 1 個 section
  cone    時空光錐：依區域內最快物體的速度決定影響半徑，加上遲滯避免來回切換

只用 Python 標準函式庫，不需要安裝任何套件。

資料格式（每行一筆，同一個時間點每個有玩家的世界各一行）：
{"t": 1794935631129, "world": "world_survive", "sim_dist": 10,
 "players": [{"id": "p1", "x": 123.4, "z": -55.0, "tp": false}],
 "chunks":  [{"x": 7, "z": -4, "vmax": 0.42, "cost": 12}]}
  t        毫秒時間戳
  sim_dist 模擬距離（區塊），省略時用 --sim-dist
  players  玩家方塊座標；tp = 這段期間有傳送、換世界或剛登入（傳送不需要因果同步，不算違反）
  chunks   有活動的區塊（區塊座標）；vmax = 區塊內最快實體（含玩家、投射物）的水平速度，單位 格/tick；
           cost = 負載（tick 耗時毫秒或實體數，只用來比較相對大小）

用法：
  python simulate.py data.jsonl
  python simulate.py recordings/                    # FoliageRecorder 的錄製資料夾（讀全部 .jsonl.gz）
  python simulate.py recordings/2026-11-2*.jsonl.gz # 指定日期
  python simulate.py data.jsonl --k 20 --rmin 32 --buffer 32 --hold 5
  python simulate.py data.jsonl --sweep            # 掃描參數組合
  python simulate.py data.jsonl --csv out.csv      # 輸出每個時間點的明細
"""
from __future__ import annotations

import argparse
import csv
import glob
import gzip
import itertools
import json
import math
import os
import sys
import zlib
from collections import defaultdict
from dataclasses import dataclass, field


# ---------------------------------------------------------------- 資料讀取

@dataclass
class Player:
    id: str
    cx: int
    cz: int
    tp: bool = False


@dataclass
class WorldSample:
    world: str
    sim_dist: int
    players: list[Player]
    vmax: dict[tuple[int, int], float]
    cost: dict[tuple[int, int], float]


def _lines(path: str):
    """逐行讀取 .jsonl 或 .jsonl.gz；當機留下的不完整 gzip 讀到能讀的部分為止。"""
    opener = gzip.open if path.endswith(".gz") else open
    try:
        with opener(path, "rt", encoding="utf-8") as f:
            for line in f:
                yield line
    except (EOFError, gzip.BadGzipFile, zlib.error) as e:
        print(f"{path} 結尾不完整（可能是當機或正在錄製），只讀到這裡：{e}", file=sys.stderr)


def expand(paths: list[str]) -> list[str]:
    """支援資料夾與萬用字元（Windows 的命令列不會自動展開 *）。"""
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(glob.glob(os.path.join(p, "*.jsonl*")))
        elif any(ch in p for ch in "*?["):
            out += sorted(glob.glob(p))
        else:
            out.append(p)
    return out


def _parse(d: dict, default_sim: int) -> WorldSample:
    players = [Player(str(p["id"]), math.floor(float(p["x"])) >> 4, math.floor(float(p["z"])) >> 4, bool(p.get("tp", False)))
               for p in d.get("players", [])]
    vmax, cost = {}, {}
    for c in d.get("chunks", []):
        key = (int(c["x"]), int(c["z"]))
        vmax[key] = max(vmax.get(key, 0.0), float(c.get("vmax", 0.0)))
        cost[key] = cost.get(key, 0.0) + float(c.get("cost", 0.0))
    return WorldSample(str(d["world"]), int(d.get("sim_dist", default_sim)), players, vmax, cost)


def iter_samples(paths: list[str], default_sim: int):
    """逐筆讀取，同一個時間戳的各世界合成一組 (t, [WorldSample])；不會把整個檔案讀進記憶體。
    錄製檔本來就依時間順序寫入；檔案依檔名（日期）排序。"""
    cur_t, cur = None, []
    for path in sorted(expand(paths)):
        for n, line in enumerate(_lines(path), 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                t = int(d["t"])
                ws = _parse(d, default_sim)
            except (KeyError, ValueError, TypeError) as e:
                print(f"{path} 第 {n} 行格式錯誤，略過：{e}", file=sys.stderr)
                continue
            if cur_t is not None and t != cur_t:
                if t < cur_t:
                    continue  # 時間倒退（不應發生），略過
                yield cur_t, cur
                cur = []
            cur_t = t
            cur.append(ws)
    if cur_t is not None:
        yield cur_t, cur


# ---------------------------------------------------------------- 工具

class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, a: int) -> int:
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb

    def groups(self) -> list[list[int]]:
        g: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.p)):
            g[self.find(i)].append(i)
        return list(g.values())


def zone_chunks(p: Player, sd: int):
    for dx in range(-sd, sd + 1):
        for dz in range(-sd, sd + 1):
            yield (p.cx + dx, p.cz + dz)


def gap_blocks(a: Player, b: Player, sd: int) -> float:
    """兩個玩家模擬範圍（正方形）邊緣之間的距離（格）；重疊或相鄰為 0。"""
    gx = abs(a.cx - b.cx) - 2 * sd - 1
    gz = abs(a.cz - b.cz) - 2 * sd - 1
    return max(gx, gz, 0) * 16


def group_cost(members: list[Player], ws: WorldSample) -> float:
    seen = set()
    for p in members:
        seen.update(zone_chunks(p, ws.sim_dist))
    return sum(ws.cost.get(c, 0.0) for c in seen)


# ---------------------------------------------------------------- 三種切分方式

def folia_groups(ws: WorldSample, shift: int = 4, merge_radius: int = 1) -> list[list[int]]:
    """Folia：每個玩家佔用的 section 範圍往外擴 merge_radius 個 section，有交集就同一區。"""
    n = len(ws.players)
    uf = UnionFind(n)
    boxes = []
    for p in ws.players:
        sd = ws.sim_dist
        boxes.append(((p.cx - sd) >> shift, (p.cz - sd) >> shift, (p.cx + sd) >> shift, (p.cz + sd) >> shift))
    for i, j in itertools.combinations(range(n), 2):
        a, b = boxes[i], boxes[j]
        if a[0] - merge_radius <= b[2] and b[0] - merge_radius <= a[2] and a[1] - merge_radius <= b[3] and b[1] - merge_radius <= a[3]:
            uf.union(i, j)
    return uf.groups()


@dataclass
class ConeState:
    coupled: set = field(default_factory=set)          # 目前耦合中的 (world, id1, id2)
    apart: dict = field(default_factory=dict)          # 已達解耦條件的連續取樣次數


def cone_radius(p: Player, ws: WorldSample, k: int, rmin: float) -> float:
    """玩家範圍內最快物體在 k tick 內能移動的距離，最少 rmin 格，最多到模擬範圍邊界（讀取邊界當障壁）。"""
    sd = ws.sim_dist
    v = 0.0
    for c in zone_chunks(p, sd):
        vv = ws.vmax.get(c)
        if vv is not None and vv > v:
            v = vv
    return min(max(rmin, v * k), (sd + 1) * 16 * 2)


def cone_groups(ws: WorldSample, state: ConeState, k: int, rmin: float, buffer: float, hold: int, prev_present: set):
    """回傳 (時空分組, 合併次數, 拆分次數, 太晚耦合次數)。
    太晚耦合：兩人上一個取樣都在、當時沒耦合，這次才耦合但範圍已經相接 → 中間可能已經有東西跨過去（因果違反）。"""
    n = len(ws.players)
    uf = UnionFind(n)
    radius = [cone_radius(p, ws, k, rmin) for p in ws.players]
    merges = splits = late = 0
    for i, j in itertools.combinations(range(n), 2):
        a, b = ws.players[i], ws.players[j]
        key = (ws.world,) + tuple(sorted((a.id, b.id)))
        g = gap_blocks(a, b, ws.sim_dist)
        reach = max(radius[i], radius[j])
        if key in state.coupled:
            if g > reach + buffer:
                state.apart[key] = state.apart.get(key, 0) + 1
                if state.apart[key] >= hold:
                    state.coupled.discard(key)
                    state.apart.pop(key, None)
                    splits += 1
                    continue
            else:
                state.apart.pop(key, None)
            uf.union(i, j)
        elif g <= reach:
            state.coupled.add(key)
            merges += 1
            if g == 0 and not a.tp and not b.tp and (ws.world, a.id) in prev_present and (ws.world, b.id) in prev_present:
                late += 1
            uf.union(i, j)
    return uf.groups(), merges, splits, late


# ---------------------------------------------------------------- 模擬

def run(samples, k: int, rmin: float, buffer: float, hold: int, cores: int, csv_rows=None):
    state = ConeState()
    tot = defaultdict(float)
    prev_present: set = set()
    n_samples = 0
    first_t = last_t = None
    for t, worlds in samples:
        n_samples += 1
        if first_t is None:
            first_t = t
        last_t = t
        counts = {"paper": 1 if any(w.players for w in worlds) else 0, "world": 0, "folia": 0, "cone": 0}
        loads = {"paper": [], "world": [], "folia": [], "cone": []}
        players_total = 0
        violations = 0
        merges = splits = 0
        present: set = set()
        all_cost = 0.0
        for ws in worlds:
            if not ws.players:
                continue
            players_total += len(ws.players)
            wcost = group_cost(ws.players, ws)
            all_cost += wcost
            counts["world"] += 1
            loads["world"].append(wcost)

            fg = folia_groups(ws)
            counts["folia"] += len(fg)
            loads["folia"] += [group_cost([ws.players[i] for i in g], ws) for g in fg]

            cg, m, s, late = cone_groups(ws, state, k, rmin, buffer, hold, prev_present)
            merges += m
            splits += s
            violations += late
            counts["cone"] += len(cg)
            loads["cone"] += [group_cost([ws.players[i] for i in g], ws) for g in cg]
            present.update((ws.world, p.id) for p in ws.players)
        loads["paper"].append(all_cost)
        prev_present = present

        tot["players"] += players_total
        tot["merges"] += merges
        tot["splits"] += splits
        tot["violations"] += violations
        for key in counts:
            tot["count_" + key] += counts[key]
            heaviest = max(loads[key], default=0.0)
            speedup = (all_cost / heaviest) if heaviest > 0 else 1.0
            tot["speedup_" + key] += min(speedup, cores, max(counts[key], 1))
        if csv_rows is not None:
            csv_rows.append({"t": t, "players": players_total, **{"spacetimes_" + k2: v for k2, v in counts.items()},
                             "merges": merges, "splits": splits, "violations": violations})

    if n_samples == 0:
        return None
    duration_min = max((last_t - first_t) / 60000.0, 1e-9)
    res = {"samples": n_samples, "avg_players": tot["players"] / n_samples,
           "merge_split_per_min": (tot["merges"] + tot["splits"]) / duration_min,
           "violations": int(tot["violations"])}
    for key in ("paper", "world", "folia", "cone"):
        res["avg_spacetimes_" + key] = tot["count_" + key] / n_samples
        res["avg_speedup_" + key] = tot["speedup_" + key] / n_samples
    return res


def print_report(r, k, rmin, buffer, hold):
    print(f"取樣數 {r['samples']}，平均線上 {r['avg_players']:.1f} 人")
    print(f"參數：K={k} tick, r_min={rmin} 格, 遲滯緩衝={buffer} 格, 解耦需連續 {hold} 次")
    print()
    print(f"{'方式':<8}{'平均時空數':>10}{'每時空玩家':>10}{'理論加速':>10}")
    names = {"paper": "Paper", "world": "每世界", "folia": "Folia", "cone": "光錐"}
    for key in ("paper", "world", "folia", "cone"):
        st = r["avg_spacetimes_" + key]
        per = r["avg_players"] / st if st else 0
        print(f"{names[key]:<8}{st:>12.2f}{per:>12.2f}{r['avg_speedup_' + key]:>11.2f}x")
    print()
    print(f"光錐合併＋拆分：每分鐘 {r['merge_split_per_min']:.2f} 次")
    print(f"因果違反（範圍相接時才耦合，太晚）：{r['violations']} 次")
    print("\n理論加速 = 總負載 ÷ 最重那個時空的負載（上限為時空數與 --cores），沒有計入合併成本與插件鎖。")


def main():
    ap = argparse.ArgumentParser(description="Foliage 時空光錐模擬器")
    ap.add_argument("data", nargs="+", help="取樣檔（.jsonl 或 .jsonl.gz）、資料夾或萬用字元，可多個")
    ap.add_argument("--k", type=int, default=20, help="重新判斷間隔（tick），預設 20")
    ap.add_argument("--rmin", type=float, default=32, help="固定互動距離下限（格），預設 32")
    ap.add_argument("--buffer", type=float, default=32, help="解耦遲滯緩衝（格），預設 32")
    ap.add_argument("--hold", type=int, default=5, help="解耦需連續達成的取樣次數，預設 5")
    ap.add_argument("--sim-dist", type=int, default=10, help="資料沒寫 sim_dist 時用的模擬距離，預設 10")
    ap.add_argument("--cores", type=int, default=24, help="可用核心數（加速上限），預設 24")
    ap.add_argument("--sweep", action="store_true", help="掃描 K / r_min / 緩衝的組合")
    ap.add_argument("--csv", help="輸出每個時間點明細的 CSV 路徑")
    a = ap.parse_args()

    if not expand(a.data):
        sys.exit("找不到取樣檔")
    samples = lambda: iter_samples(a.data, a.sim_dist)

    if a.sweep:
        print(f"{'K':>4}{'r_min':>7}{'緩衝':>6}{'光錐時空數':>10}{'加速':>8}{'合併拆分/分':>12}{'違反':>6}")
        for k, rmin, buf in itertools.product((10, 20, 40), (16, 32, 48), (16, 32, 64)):
            r = run(samples(), k, rmin, buf, a.hold, a.cores)
            print(f"{k:>4}{rmin:>7}{buf:>6}{r['avg_spacetimes_cone']:>13.2f}{r['avg_speedup_cone']:>9.2f}x"
                  f"{r['merge_split_per_min']:>13.2f}{r['violations']:>7}")
        return

    rows = [] if a.csv else None
    r = run(samples(), a.k, a.rmin, a.buffer, a.hold, a.cores, rows)
    if r is None:
        sys.exit("沒有可用的取樣")
    print_report(r, a.k, a.rmin, a.buffer, a.hold)
    if rows:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n明細已寫入 {a.csv}")


if __name__ == "__main__":
    main()
