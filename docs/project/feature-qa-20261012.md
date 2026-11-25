# 各功能 QA — 2026-10-12

基準：本機 `main` 的 `efd6ab8`；開始時工作區乾淨。本次完成各元件自動回歸、七組真實 PostgreSQL／HTTP 回滾流程、契約驗證，以及 production frontend 的合成瀏覽器 QA。發現並修正兩處手機英文導覽的單字斷行。最終變更只有兩份導覽 CSS 與本報告／索引。

測試執行於 2026-10-12，文件與環境收尾於 2026-10-13（Asia/Taipei）。

## 結果與測試層級

| 功能 | 本次驗證 | 結果 |
| --- | --- | --- |
| 登入、註冊、角色與邀請 | Core／BFF 回歸、未登入拒絕、三角色登入畫面、註冊分頁、鍵盤焦點 | 通過；表單瀏覽器 QA 使用合成 API，未重新執行真實帳密登入 campaign |
| 本人同意 | 用途／版本／撤回回歸；長者同意頁與已授予狀態 | 通過 |
| 陪伴與安全 | Agent 全套、provider 失敗／期限／安全拒答、Core companion 回歸、平板文字回合畫面 | 通過；本次沒有真實 LLM 回覆品質評分 |
| 個人記憶 | 文字、ALLOWED 語音、CONFIRMED 語音三組 SQL 生命週期；記憶頁、修正／刪除／撤回回歸 | 通過 |
| 派案、服務紀錄與交班 | Core／前端相關回歸、派案清單与工作台相關元件測試 | 通過；本次 SQL 七組不包含 committed_session 的派案併發測試 |
| 照護事件、摘要與待辦 | Core／Agent／前端回歸；照護詳情各分頁、資料不足與拒絕頁面 | 通過 |
| 長者基本資料與 Care Profile | 真實 SQL／HTTP 維護生命週期、獨立權限／版本／歷史／撤權；維護頁面 | 通過 |
| 收案管理 | 真實 SQL／HTTP 暫停／恢復／結案與失效；瀏覽器確認、取消不送出、暫停與撤權清除 | 通過 |
| 無帳號長者與平板交接 | 真實 SQL／HTTP 語音生命週期；配對無效、首次說明、陪伴、停止確認、建立與交付平板 | 通過；音訊／Agent 為合成，不代表真人收音或聽感驗收 |
| 家屬日報 | 真實 SQL／HTTP 草稿→發布→讀取→撤回及授權反例；家屬首頁／列表／詳情、資料缺口提示 | 通過 |
| 家屬資料紅線 | 合成草稿與撤回內容不得出現在 DOM；前端 redline／角色隔離回歸 | 通過 |
| 家屬／照服員公開問答 | 六種回應狀態、引用顯示、過期後清除答案；Core／Agent／RAG 回歸及公開契約 | 通過；沒有重新呼叫真實 embedding／generation provider |

SQL 與瀏覽器結果分別代表其所列層級，不合併宣稱本次已完成真人語音或真實 UI→BFF→Core→模型的完整 E2E。

## 自動回歸與契約

| 檢查 | 最終結果 |
| --- | --- |
| Core unit | 1,826 passed |
| Agent Runtime | 899 passed |
| Speech Gateway | 91 passed |
| RAG Ingestion | 首輪 605 passed／2 failed；恢復 LF 後，失敗兩項定向重驗 2 passed |
| Frontend | 修復缺失依賴後，88 files／824 passed，無未處理測試錯誤 |
| Python lint／format | 四個元件全部通過 |
| Frontend lint／typecheck | 通過 |
| 靜態 contracts／Agent live contracts | 通過 |
| Core live contracts | 119 runtime operations 與公開契約一致，拒絕邊界與各回應 envelope 通過 |
| CI instrumentation／impact 規則 | 通過 |
| 最後 CSS 修正後定向回歸 | FamilySurface／CareSurface／SharedDesignFoundation，53 passed |
| 最後 production build | 通過，含 TypeScript；page data／static generation 使用 1 worker |

合計 4,247 個不同測試案例獲得通過證據；53 項定向回歸是重驗既有案例，不另加進總數。RAG 的 607 個案例來自首輪通過的 605 項與修復後重驗的 2 項，並非另一輪完整 suite 的分數。

各測試依序執行，child process 使用 Windows BelowNormal；Vitest 限制一個 worker 且停用檔案並行，建置亦限制單 worker。沒有同時執行多套本機測試。

## 真實 SQL／HTTP

唯讀 preflight 確認 development revision `f0b2c4d6e879`。直接載入選定 integration test functions，避免 integration conftest 的 migration／TRUNCATE 行為。

七組通過：assisted voice、elder profile、enrollment、staff/family report、personal text memory、ALLOWED voice memory、CONFIRMED voice memory。每組使用新 UUID 合成資料、外層 transaction、有限 lock／statement timeout，最後核對回滾及 connection 不再持有交易。未執行 reset、truncate、downgrade 或 migration upgrade。

機器證據：[SQL workflows](../../.qa/local/feature-qa-20261012/sql-workflows.json)。

## 瀏覽器与版面

使用 production build 的專用 `127.0.0.1:3105`。原生登入只對該 QA 程序啟用；前端 API responses 皆為合成 fixture。沒有改寫 `.env` 或 committed default flags。

最後一輪共 266 個畫面／狀態：

- 375／390／430／1440 目標寬度：每個 53 項，合計 212。
- 768／1024 平板：照護詳情、家屬報表及兩角色公開問答，每個 26 項，合計 52。
- 390 目標寬度的家屬／照護頁，200% 根字級各一項。

全部使用 reduced-motion；每次導航加 query cache bust，等待字型，再檢查 document scrollWidth、clientWidth、來源／資料紅線與導覽單字的矩形。最後沒有水平溢出、導覽單字斷行、未知 fixture route 或 harness error。代表截圖已目視核對登入、照護維護、收案撤權、家屬報表、記憶／同意、平板陪伴及交付畫面。

Windows DPI 造成部分 native browser resize 的 CSS 寬度只能取鄰近值；保存了每張實際 innerWidth：375、768、1024、1440 均精確，390 為 389／391，430 為 429／431。沒有以 CLI window size 冒充實際 CSS 寬度。200% 測試是 CSS root 字級模擬，尚未驗證作業系統字級或真機瀏覽器 zoom。

機器證據：[最終 266 項](../../.qa/local/feature-qa-20261012/browser-final-results.json)、[總表](../../.qa/local/feature-qa-20261012/qa-summary.json)。圖片及詳細 logs 留在本機 ignored `.qa/local/feature-qa-20261012/`。

## 發現与修正

1. 英文家屬導覽的 `information` 在窄螢幕拆開單字。FamilyNav 限制 span 為正常單字換行，手機改為圖示／文字直排並縮減水平內距。
2. 英文照護導覽的 `Assignments` 在 375 目標寬度拆開最後字母。DOM Range 確認有兩條實際文字行；CareSidebar 套用相同的文字／手機內距修正，桌面 sidebar 與兩種平板尺寸均已重驗。
3. 前端 node_modules 缺少 lockfile 中 15 個必要套件，導致 33 個 jsdom 初始化錯誤。以 `npm install --ignore-scripts --no-audit --no-fund --no-save --prefer-offline` 補齊；package.json／package-lock.json 無變更，完整 824 項重驗通過。
4. 部分 Windows 工作樹檔案為 CRLF，違反既有 LF attributes。只恢復換成 LF 後與 HEAD bytes 完全一致的檔案；跳過含其他內容差異的歷史 XML。55 個 unchanged 路徑刷新 Git stat，已暫存內容完全不變；RAG 失敗兩項重驗通過。

測試本身另修正了缺 PyYAML 的 verifier 執行方式、QA server 的 hoisted Next 路徑、登入開关、確認按鈕選擇器與家屬文本匹配。這些是環境／harness 問題，不列為產品故障。Core verifier 依 AGENTS.md 改用 service-specific `uv run --with pyyaml --with jsonschema --with referencing`。

修復前後證據：[家屬修復前](../../.qa/local/feature-qa-20261012/screenshots/before-family-nav-word-wrap-390-en.png)、[家屬修復後](../../.qa/local/feature-qa-20261012/screenshots/family-knowledge-ANSWER-390-en.png)、[照護修復後](../../.qa/local/feature-qa-20261012/screenshots/staff-dashboard-375-en.png)。

另觀察到英文單數提示仍使用 `1 care events are waiting...`；數量正確，屬低優先文案潤飾，本次未擴大修改文案。

## 未驗證範圍

- 真人麥克風、ASR 品質、喇叭聽感、真機操作及插話。
- 本輪真實登入／邀請 campaign、模型回答品質、固定 RAG 16 題、live provider 延遲與負載。
- 完整 disposable Core integration／migration lifecycle／committed_session 併發 suite；本機不以共享 development DB 執行這些破壞性 fixtures。
- 真實 Google／LINE OIDC、正式寄信、LINE 通知／外部 deletion adapters、production 部署及維運驗收。
- 全面 WCAG／Lighthouse、200% OS 字級及瀏覽器 zoom。

Production gate、needs_review 狀態、來源資料及向量均未改動。本次結果限定於 development QA；變更未 commit／push。專用 QA server 與測試 browser contexts 在收尾時關閉。
