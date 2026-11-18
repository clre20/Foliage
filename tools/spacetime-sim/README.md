# 時空光錐模擬器

用伺服器錄下來的資料，比較四種切分方式能切出幾個「時空」（可平行執行的區域），以及理論上能加速多少：

| 方式 | 說明 |
|---|---|
| Paper | 整台伺服器一條時間線 |
| 每世界 | 每個世界一條時間線 |
| Folia | 16×16 區塊為一個 section，建立／合併半徑 1 個 section |
| 光錐 | 依範圍內最快物體的速度決定影響半徑，加上遲滯避免來回切換 |

## 環境建置
只需要 Python 3.10 以上，不用安裝任何套件。

**Windows**
1. 到 https://www.python.org/downloads/ 下載 Python 3.12 以上，安裝時勾選「Add python.exe to PATH」。
2. 開「命令提示字元」，輸入 `python --version`，看到版本號就完成。

**Linux / macOS**
```bash
python3 --version   # 3.10 以上即可；沒有就用套件管理員安裝 python3
```

## 使用
進到這個資料夾（`tools/spacetime-sim`）：

```bash
# 1. 還沒有錄製資料時，先用假資料跑通（15 人、60 分鐘）
python gen_synthetic.py --players 15 --minutes 60 --out synthetic.jsonl

# 2. 執行模擬（預設 K=20 tick、r_min=32 格、緩衝 32 格、連續 5 次才解耦）
python simulate.py synthetic.jsonl

# 3. 掃描參數組合，找出「違反 = 0」中時空數最多、合併拆分最少的一組
python simulate.py synthetic.jsonl --sweep

# 4. 輸出每秒明細，可以用 Excel 開
python simulate.py synthetic.jsonl --csv detail.csv
```
Linux / macOS 把 `python` 換成 `python3`。

## 輸出怎麼看
| 欄位 | 意思 |
|---|---|
| 平均時空數 | 平均同時有幾條時間線，越多代表能用越多核心 |
| 每時空玩家 | 越接近 1 越好（每人一個時空） |
| 理論加速 | 總負載 ÷ 最重那個時空的負載，上限是時空數和核心數；沒有計入合併成本與插件鎖，是上限值 |
| 合併＋拆分／分 | 光錐的耦合與解耦次數，太高代表切太細的反作用 |
| 因果違反 | 兩個時空在範圍已經相接時才耦合（太晚），必須是 0 |

## 參數
| 參數 | 預設 | 調大 | 調小 |
|---|---|---|---|
| `--k` 重新判斷間隔（tick） | 20 | 省運算，但光錐要畫更大 | 切得細，但更常重算 |
| `--rmin` 固定互動距離（格） | 32 | 安全，時空數變少 | 切得細，違反風險變高 |
| `--buffer` 解耦遲滯緩衝（格） | 32 | 合併拆分變少 | 拆得快，容易來回抖動 |
| `--hold` 解耦需連續次數 | 5 | 同上 | 同上 |
| `--sim-dist` 模擬距離（區塊） | 10 | 資料沒寫 `sim_dist` 時使用，請設成伺服器的 `simulation-distance` |
| `--cores` 核心數 | 24 | 加速上限 |

## 資料格式（錄製插件的輸出）
JSON Lines，每秒一次，同一個時間點每個有玩家的世界各一行：
```json
{"t":1794935631129,"world":"world_survive","sim_dist":10,
 "players":[{"id":"p1","x":123.4,"z":-55.0,"tp":false}],
 "chunks":[{"x":7,"z":-4,"vmax":0.42,"cost":12}]}
```
| 欄位 | 說明 |
|---|---|
| `t` | 毫秒時間戳 |
| `players[].x/z` | 玩家方塊座標；`id` 可用雜湊，不需要真實 UUID |
| `players[].tp` | 這一秒有傳送、換世界或剛登入（傳送不需要因果同步，不算違反） |
| `chunks[]` | 只列有活動的區塊（區塊座標） |
| `chunks[].vmax` | 區塊內最快實體（含玩家、箭、TNT）的水平速度，單位 格/tick |
| `chunks[].cost` | 負載，tick 耗時（毫秒）或實體數，只用來比較相對大小 |
