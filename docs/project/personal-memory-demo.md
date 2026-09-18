# 個人記憶錄影流程（2026-09-17）

本切片支援本人登入後的**文字陪伴**：一次同意自動保存，再於新對話回想一般偏好。
設計決策見 [ADR 0022](../adr/0022-self-stated-companion-memory.md)。

2026-09-18 增量已加入本人語音來源，需額外的語音保存同意；操作與驗證見
[語音新增個人記憶](voice-personal-memory.md)。以下保留 09-17 文字展示的範圍與驗證紀錄。

## 建議錄製 90 秒

1. 進入 `/elder/consent`，閱讀並開啟「長期記憶」。第一次使用也需開啟「語音與文字陪伴」。
2. 回首頁，切到「打字」，輸入 **我每天早餐喝豆漿**。
3. 拍到 Core 回傳的 **已記住：我每天早餐喝豆漿。**、本人自述來源與撤銷按鈕。
4. 點「開始新對話」，輸入 **我每天早餐習慣喝什麼？**。回答應根據記憶提到豆漿。
5. 打開「我的記憶」，修改成 **我每天早餐喝牛奶**。回首頁重新詢問，應改答牛奶。
6. 刪除這筆記憶，再開新對話詢問。小暖應坦白沒有紀錄。

可加錄的片段：輸入 **我喜歡聽老歌**，拍到保存提示後按「撤銷這筆記憶」；
或在同意設定停止長期記憶，展示新對話不再讀取／新增記憶。

旁白可說：「使用者同意後，小暖能記住清楚表達的日常偏好，在下一段對話使用。
這些會標示為本人自述，使用者隨時能修改、刪除或停止記憶。」

## 範圍與限制

- 目前採 Core 有界中文語法，不是任意句子理解。其他可用句子：`我喜歡聽民歌`、
  `我喜歡散步`、`我喜歡種花`、`請叫我小林`、`我喜歡喝豆漿`、`我每天早餐吃粥`。
- 同一類型以最新陳述取代，保留版本；重複陳述不新增資料。撤銷刪除目前這筆，並不恢復前一版本。
- 「昨天喝什麼」是有日期的事件查詢，這次沒有實作；「每天喝豆漿」不能證明昨天實際喝過。
- 語音自動記憶、任意語句擷取、多筆同類偏好並存不在本切片。正式照護事件仍需既有人工覆核。
- 舊 LONG_TERM_MEMORY 同意不默認升級；需先停止，再閱讀新說明重新開啟。
  停止不等於刪除資料；重新同意不會自動讓舊同意版本下的記憶進入 AI 背景。
- 功能預設關閉。需 `EVIDENCE_AWARE_MEMORY=true`、`PERSONAL_MEMORY_ENABLED=true`、
  新同意 scope `personal_memory_auto_save=true`、本人文字來源與 STANDARD profile 全部符合。

## 本機啟動

若使用 IDE 的一般 3000／8000／8001 開發環境，`scripts/ide/run-local.ps1` 不會自動
開啟個人記憶。需在本機、不提交的根目錄 `.env` 設定 `EVIDENCE_AWARE_MEMORY=true`
與 `PERSONAL_MEMORY_ENABLED=true`，再重啟 Core；帳號仍需新版 LONG_TERM_MEMORY 同意。
先前功能關閉時送出的句子不會回填，開啟後需重新送出並確認「已記住」receipt。
以下專用錄影 launcher 則會對自己的程序開啟這兩個 flags。

先備妥既有 `.env` 的開發資料庫、真實模型與登入設定，並在 `services/core-api` 執行
`alembic upgrade head`（增量 revision `b6d8f0a2c435`）。不改 baseline、不清空資料庫。
前端需已設定 `NEXT_PUBLIC_CONSENT_POLICY_VERSION` 為有效政策版本。

在 repository 根目錄執行 `npm run build --workspace @elderly-care/frontend`，然後開三個終端機分別執行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_personal_memory_demo.ps1 -Service core
powershell -ExecutionPolicy Bypass -File scripts/run_personal_memory_demo.ps1 -Service agent
powershell -ExecutionPolicy Bypass -File scripts/run_personal_memory_demo.ps1 -Service front
```

開啟 `http://localhost:3110/elder/start`。Core 使用 8010、Agent 使用 8011。
腳本只對目前程序設定功能旗標，不改共用 `.env`；停止時用各終端機的 Ctrl+C。
每次文字送出都建立新的 Core session；「開始新對話」另外清除畫面，不把前一輪輸入再傳給模型。

這次工作站另建立全新的合成錄影帳號，帳密只存忽略追蹤的
`.qa/local/personal-memory-demo.credentials.json`，成員資格七天有效至 2026-09-24。
沒有重啟過去已退役的展示帳號。重新使用前需先檢查期限，不應永久使用測試憑證。

## 已驗證的證據

- 真實表單登入 → BFF → Core → Supabase；透過畫面開啟新同意。
- 真實 Gemini 模型（回合記錄 model route `gemini-3.6-flash`）：豆漿跨新 session 回想、
  修改牛奶後只引用新版、嗜好撤銷後不再回想、刪除後不再回想、撤回同意後不再讀寫。
  工作站逐回合結果：`.qa/local/personal-demo-live-evidence.json`。
- 真實 PostgreSQL 生命週期測試使用全新合成資料並完整 rollback：重複不新增、無 Graph
  projection 仍可讀取、voice 來源被排除、跨 tenant 排除、舊同意 scope 排除、修正／過期版本
  拒絕／刪除、FOOD_PREFERENCE constraint、撤回同意。
- 一般 Core integration conftest 會重建 schema，本機沒有 disposable TEST_DATABASE_URL，
  因此**沒有在 Supabase 執行整套 integration 或 downgrade 測試**。migration lifecycle 測試已加入供 CI。
- 真機手感、正式部署、多語與語音記憶未驗證；本文件不宣稱 production-ready。

最終自動測試：Core unit **1,521 passed**、Agent Runtime **538 passed**、Frontend
**629 passed（66 files）**；TypeScript、production build、變更檔案 lint、靜態 contracts 驗證通過。
前端初次全跑曾遇一項既有測試逾時，限制兩個 workers 後完整重跑全部通過。

視覺驗證覆蓋保存提示與修改表單：375／390／430／1440px，另含 reduced-motion。
截圖在 `.qa/local/personal-demo-final-*.png`，DOM 尺寸記錄在
`.qa/local/personal-demo-visual-evidence.json`；未見水平溢出。
驗證後合成帳號已清除所有 ACTIVE 記憶、停止長期記憶，保留基本陪伴同意，可從上述第 1 步錄製。
