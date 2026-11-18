#!/usr/bin/env python3
"""
產生假的取樣資料，用來在還沒有錄製插件之前先跑通模擬器。

模擬的伺服器配置（依實際伺服器）：
  world_lobby    大廳：玩家聚在出生點
  world_superior 空島：每人一座島，島距 --island-spacing 格
  world_survive  生存：每人一個家，離出生點 300~3000 格，部分玩家住得近；會走路、偶爾鞘翅飛行或 TNT 大砲
  world_arena    副本／小場地：偶爾有一群人進去

用法：
  python gen_synthetic.py --players 15 --minutes 60 --out synthetic.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", type=int, default=12)
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--sim-dist", type=int, default=10)
    ap.add_argument("--island-spacing", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="synthetic.jsonl")
    a = ap.parse_args()
    rnd = random.Random(a.seed)

    worlds = ["world_lobby", "world_superior", "world_survive", "world_arena"]
    weights = [0.1, 0.3, 0.5, 0.1]
    players = []
    for i in range(a.players):
        # 生存的家：三成玩家住在別人附近（同一個聚落）
        if players and rnd.random() < 0.3:
            base = rnd.choice(players)["home"]
            home = (base[0] + rnd.uniform(-150, 150), base[1] + rnd.uniform(-150, 150))
        else:
            r, th = rnd.uniform(300, 3000), rnd.uniform(0, 2 * math.pi)
            home = (r * math.cos(th), r * math.sin(th))
        gx, gz = i % 5, i // 5
        island = (gx * a.island_spacing, gz * a.island_spacing)
        players.append({"id": f"p{i + 1}", "home": home, "island": island, "world": rnd.choices(worlds, weights)[0],
                        "x": 0.0, "z": 0.0, "mode": "idle", "mode_left": 0, "tp": True})

    def place(p):
        w = p["world"]
        if w == "world_lobby":
            p["x"], p["z"] = rnd.uniform(-20, 20), rnd.uniform(-20, 20)
        elif w == "world_superior":
            p["x"], p["z"] = p["island"][0] + rnd.uniform(-30, 30), p["island"][1] + rnd.uniform(-30, 30)
        elif w == "world_survive":
            p["x"], p["z"] = p["home"][0] + rnd.uniform(-20, 20), p["home"][1] + rnd.uniform(-20, 20)
        else:
            p["x"], p["z"] = rnd.uniform(-40, 40), rnd.uniform(-40, 40)
        p["tp"] = True

    for p in players:
        place(p)

    t0 = 1794935631129
    with open(a.out, "w", encoding="utf-8") as f:
        for sec in range(a.minutes * 60):
            for p in players:
                p["tp"] = False
                if rnd.random() < 1 / 600:  # 平均 10 分鐘換一次世界
                    p["world"] = rnd.choices(worlds, weights)[0]
                    place(p)
                    continue
                speed = 0.0  # 格/tick
                if p["world"] == "world_survive":
                    if p["mode_left"] <= 0:
                        p["mode"] = rnd.choices(["idle", "walk", "elytra", "cannon"], [0.6, 0.35, 0.049, 0.001])[0]
                        p["mode_left"] = {"idle": 60, "walk": 30, "elytra": 40, "cannon": 3}[p["mode"]]
                        p["dir"] = rnd.uniform(0, 2 * math.pi)
                    p["mode_left"] -= 1
                    speed = {"idle": 0.0, "walk": 0.2, "elytra": 1.7, "cannon": 10.0}[p["mode"]]
                    if p["mode"] == "walk" and math.dist((p["x"], p["z"]), p["home"]) > 200:
                        p["dir"] = math.atan2(p["home"][1] - p["z"], p["home"][0] - p["x"])
                    p["x"] += math.cos(p["dir"]) * speed * 20
                    p["z"] += math.sin(p["dir"]) * speed * 20
                elif p["world"] in ("world_lobby", "world_arena"):
                    speed = 0.2
                    p["x"] = max(-60, min(60, p["x"] + rnd.uniform(-4, 4)))
                    p["z"] = max(-60, min(60, p["z"] + rnd.uniform(-4, 4)))
                p["speed"] = speed

            for w in worlds:
                here = [p for p in players if p["world"] == w]
                if not here:
                    continue
                chunks = {}
                for p in here:
                    pcx, pcz = math.floor(p["x"]) >> 4, math.floor(p["z"]) >> 4
                    # 玩家所在區塊（速度＝玩家速度）
                    key = (pcx, pcz)
                    chunks[key] = max(chunks.get(key, (0, 0))[0], p["speed"]), chunks.get(key, (0, 0))[1] + 1
                    # 周圍生物：生存世界比較多，偶爾有射箭的骷髏（箭約 3 格/tick）
                    mobs = 25 if w == "world_survive" else 5
                    for _ in range(mobs):
                        c = (pcx + rnd.randint(-8, 8), pcz + rnd.randint(-8, 8))
                        v = 3.0 if rnd.random() < 0.01 else rnd.uniform(0, 0.3)
                        old = chunks.get(c, (0, 0))
                        chunks[c] = (max(old[0], v), old[1] + 1)
                    # 家裡的農場：固定負載
                    if w == "world_survive":
                        h = (math.floor(p["home"][0]) >> 4, math.floor(p["home"][1]) >> 4)
                        old = chunks.get(h, (0, 0))
                        chunks[h] = (max(old[0], 0.1), old[1] + 40)
                f.write(json.dumps({
                    "t": t0 + sec * 1000, "world": w, "sim_dist": a.sim_dist,
                    "players": [{"id": p["id"], "x": round(p["x"], 1), "z": round(p["z"], 1), "tp": p["tp"]} for p in here],
                    "chunks": [{"x": k[0], "z": k[1], "vmax": round(v[0], 3), "cost": v[1]} for k, v in chunks.items()],
                }, separators=(",", ":")) + "\n")
    print(f"已產生 {a.out}（{a.players} 人、{a.minutes} 分鐘）")


if __name__ == "__main__":
    main()
