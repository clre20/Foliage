# compat-test

測試 Foliage 序列模式（普通方式）相容層的插件。放進測試服的 `plugins` 後開服，約 10 秒後後台會輸出：

```
[CompatTest] RESULT ok=<數量> fail=0
```

`fail` 必須是 0。每一項的結果以 `PASS` / `FAIL` 開頭。

測試內容：計分板、啟動時建立世界、全域排程強制載入兩個相距 2000 格的區域、跨區生怪與改名、跨區改方塊與讀方塊、跨區箱子物品、同區與跨區傳送、在事件中存取另一區的實體、統計實體、刪除實體。

建置（需要 JDK 25 與 Maven）：
```bash
mvn package
# 產物：target/CompatTest-1.0.0.jar
```
