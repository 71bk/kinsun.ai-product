# 家屬公開長照知識入口

2026-10-05。接續 PR #69；工作分支從已合併的 `65d389c` 建立。

## 實作與邊界

家屬登入後可在 `/family/knowledge` 輸入一般長照問題，閱讀回答及 1–5 筆官方來源。
此功能獨立於長輩報表，不需要選取長輩，也不建立對話、照護事件、記憶或 consent。
輸入畫面提醒不要輸入姓名、身分證字號或病歷。問句僅為本次檢索／生成使用，不由此功能存入資料庫。

`POST /api/v1/family/knowledge/questions` 僅接受 ACTIVE `FAMILY_MEMBER`，瀏覽器只能傳
`question`（1–2000 字元）與 `language`。拒絕額外角色、租戶、長輩、用途與 session 欄位。
Core 固定 `family_caregiver`，一般資訊與法規用途依既有 router 選擇；沒有任何轉入個人記憶或工具的路徑。
來源版本、內容 hash、受眾、用途、現行性、風險與安全判斷仍由既有 V3 gate 執行。
此入口受 `KNOWLEDGE_ROUTER_V2_ENABLED` 控制，production 拒絕呼叫；Agent V3 原有開關仍須啟用。

Service 依賴注入的 `PublicKnowledgeReader` 介面，不引用具體 adapter；HTTP 組合仍在 API 邊界。
Core 透過綁定 body／path／correlation 的 HMAC 呼叫私有 V3；沿用有限 deadline，
單次回應上限 1 MiB，失敗不重試、不回傳 provider 原文。只投影回答、來源標題、官方 URL、
定位與 current/unknown。完整 excerpt、分數及內部 provenance 不進入家屬 API。
官方連結限制為 HTTP(S) `.gov.tw`、無 credentials／空白／反斜線。

API 狀態為 ANSWER、PARTIAL、NO_DATA、CLARIFY、BLOCKED、UNAVAILABLE。
有回答時必須附來源，fallback 不附來源；PARTIAL 保留既有生成器在回答中的不足說明。
安全拒答與服務故障採固定雙語文案，不將未知故障當成醫療判斷。
前端先對原始 payload 執行 `assertNoRestrictedFields`，再驗證所有欄位及官方 URL。
PUBLISHED／WITHDRAWN 限制屬於個人報表，不套用到公開知識問答；既有報表可見性規則未更動。

## 畫面與驗收

沿用 family 設計 tokens、單欄版面、至少 48px 觸控區與中英語系；導覽新增「長照知識」。
送出期間禁止重複送出，離頁／切換語言取消請求，認證失效清除回答，文字以 React 純文字呈現。
AI 回答附核對官方來源提示，unknown 來源另顯示現行性未確認。

後端與架構邊界定向測試 56 項、家屬前端相關測試 57 項通過；Typecheck、定向 ESLint、Core Ruff、
靜態 contract validator、28 項 CI 規則（另含 74 subtests）通過。
真實 loopback BFF／Core／Agent 使用合成 demo 帳號驗證：申請問題 ANSWER（1 筆官方引用）、
未知未來年度 NO_DATA、停藥問題 BLOCKED、個人紀錄 NO_DATA；未登入 401、長者與照服員 404、
額外 scope 422、跨站 POST 403、登入登出均通過。沒有執行共用開發資料庫的 destructive integration。
完整 Core live contract verifier 與隔離 DB 整合由 GitHub CI 驗證，結果以 PR checks 為準。

Production build 後，Playwright 合成驗證共 34 組：中文 375／390／430／768／1024／1440、
英文 390／768，另以 family 字級 tokens 放大 200% 驗證英文 390；全部使用 reduced-motion。
390 中英文各涵蓋六種回應、HTTP 錯誤、等待、拒絕存取；其餘驗證空白與成功頁。
核對實際 CSS viewport、水平 overflow、48px 觸控區及官方來源連結；實際讀圖確認版面。
大字導覽原先單字切碎，已改為依字級自動換列，重建後重新跑完 34 組。
fullPage 截圖曾在捲動後把既有 fixed skip link 畫進頁面；回頁首再截即消失，屬截圖狀態而非產品修正。
本機證據位於 `.qa/family-knowledge-visual/`、`.qa/family-knowledge-smoke.json`；不含登入憑證。
另以真實瀏覽器串接 BFF／Core／Agent，家屬 demo 登入→提問→ANSWER（2 筆官方來源）→登出通過；
390px 無水平溢出，截圖 `live-family-answer.png` 已讀圖確認。兩次生成來源數不同，不當成固定答案驗收。
Windows MCP 曾有 viewport DPI 捨入，沿用已確認能精準設定 CSS viewport 的 Playwright Node context。
未涵蓋實體手機、真人輔具操作、Lighthouse 或知識品質統計。

合成測試不能當成知識語意準確率或真人覆核。
本批不包含專業問答入口、55 筆版面排除來源修復、production 啟用與新資料匯入。
