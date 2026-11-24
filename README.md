# Foliage

以 [Paper](https://github.com/PaperMC/Paper) 為基礎的 Minecraft 伺服器核心，目標是在**不修改任何 Paper 插件**的前提下，把主執行緒的工作分散到多核心。

> 目前與 Paper 26.3 build 257 行為相同，只加上品牌與更新檢查，作為之後多核心修改的基底。

## 規劃
| 階段 | 內容 |
|---|---|
| 1 | 錄製伺服器實際資料（玩家位置、各區塊負載），用 [時空光錐模擬器](tools/spacetime-sim) 估算可切分的時空數 |
| 2 | 世界與區域平行 tick，加上 Paper 插件相容層（插件全域鎖、跨區操作排程） |
| 3 | 依實體最大速度動態決定區域範圍（時空光錐） |

## 普通方式（序列模式）
`main` 分支預設開啟。所有區域與全域只用一條 tick 執行緒依序執行，插件呼叫到其他區域的實體、方塊、區塊、物品欄或世界座標時，會暫時切換到該區域執行，效果與 Paper 相同：
- 所有 Paper 插件都能載入（不需要標示 folia-supported）。
- BukkitScheduler 同步排程、同步傳送、計分板、建立與卸載世界都可以使用。
- 這些包裝由 Foliage 在載入插件時改寫插件的位元組碼完成，插件本身不用修改。

測試用 `-Dfoliage.serial-mode=false` 可以關閉（之後只有標示 folia-supported 的插件能載入）。相容層的回歸測試插件在 [tools/compat-test](tools/compat-test)。

## 下載與安裝
1. 到 [Releases](https://github.com/clre20/Foliage/releases) 下載 `Foliage-<Minecraft 版本>-<build>.jar`，例如 `Foliage-26.3-12.jar`。
2. 取代原本的 Paper jar，啟動參數不變（需要 Java 25）。
3. 所有 Paper 插件、設定檔與世界直接沿用。

## 指令
| 指令 | 說明 |
|---|---|
| `/version` | 顯示 Foliage 版本，並向 GitHub Releases 比對同一個 Minecraft 版本的最新 build（結果快取 10 分鐘） |

開服時也會非同步檢查一次；兩者都可用 `paper-global.yml` 的 `update-checker.enabled` 關閉。

## 相容性
- 對插件回報的品牌為 `clre20:foliage`，但 `ServerBuildInfo#isBrandCompatible(papermc:paper)` 仍回傳 `true`，檢查 Paper 的插件可正常運作。
- 支援的 Minecraft 版本：26.3。

## 分支與版本
| 分支 | 用途 | 推送後 |
|---|---|---|
| `main` | 最新開發 | 自動建置，jar 放在 Actions 的 Artifacts |
| `26.3` | Minecraft 26.3 穩定版 | 自動建置並發布 Release，標籤 `v26.3-<build>`，jar `Foliage-26.3-<build>.jar` |

build 號碼是 GitHub Actions 的執行次數，每次建置自動加一。正式服使用 `26.3` 分支的 Release。

## 建置環境
需要 **JDK 25** 與 **Git**（Gradle 會自動下載，不用另外安裝）。

**Windows**
1. 安裝 JDK 25：https://adoptium.net/temurin/releases/?version=25 （選 Windows x64 的 `.msi`，安裝時勾選「Set JAVA_HOME」）。
2. 安裝 Git：https://git-scm.com/download/win
3. 開新的命令提示字元確認：`java -version` 顯示 25、`git --version` 有版本號。

**Linux**
```bash
# Debian / Ubuntu（套件庫沒有 25 時改用 adoptium.net 的 tar.gz）
sudo apt install git openjdk-25-jdk
```

**建置**
```bash
git config --global user.name "你的名字"
git config --global user.email "你的信箱"
./gradlew applyAllPatches                     # Windows: gradlew.bat applyAllPatches
./gradlew :foliage-server:createPaperclipJar
# 產物：foliage-server/build/libs/foliage-paperclip-26.3.build.0-local.jar（本地建置的 build 號碼是 0）
```
第一次建置會下載 Minecraft 與相依套件，約需 10～20 分鐘、4 GB 以上記憶體。

**修改 Paper 原始碼**
1. 先執行 `applyAllPatches`，修改 `paper-server/` 裡的檔案。
2. 在 `paper-server/` 裡 `git commit`。
3. 回到專案根目錄執行 `./gradlew :foliage-server:rebuildPaperServerPatches`，補丁會寫進 `foliage-server/paper-patches/`。

## 授權
GPL-3.0，詳見 [LICENSE](LICENSE)。本專案包含 Paper 與 Folia 的建置設定。
