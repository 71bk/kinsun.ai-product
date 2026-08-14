# 03智慧長照 AI 陪伴系統－Story Map v1.2.xlsx

> **2026-08-14 Target Domain Overlay**：後續 backlog 必須依 [ADR 0013](../adr/0013-separate-account-elder-enrollment-entitlement.md) 與 [Spec 17](17智慧長照%20AI%20陪伴系統－Account、Elder、Enrollment%20與%20Service%20Entitlement%20v0.1.md) 執行。新增的優先 Enablers 為 Account／Elder decoupling、Organization／Household context、Elder Enrollment、Service Entitlement、Staff-assisted Elder Session、single-Elder offboarding 與 Household continuation。這些工作不得被誤列為既有 Gate 1 已完成項目；Gate 1 的 Agent、ASR／TTS 與 CI 暫緩決策不因此改變。

## 工作表：00_總覽

| 智慧長照 AI 陪伴系統｜Story Map v1.2 |  |  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 產品策略：完整 Target Architecture 一次規劃到位；實作依風險與相依順序分 Wave 交付。第一條可演示薄切片跨 Wave 1 與最小 Wave 2，確保長者語音 → 事件／確認式記憶 → 再次引用 → 每日摘要 → 照護者時間軸與覆核能同時證明命題 A／B／C。 |  |  |  |  |  |  |  |  |  |
| Implementation Wave | 核心目標 | Product Stories | Enablers／NFR | 交付 Gate |  | 命題範圍 | Story Map 落點 | 第一條 Demo 證據 | 完成判定 |
| Wave 1 | 核心語音＋事件＋確認式記憶＋Graph 再次引用 | 11 | 21 | 記憶閉環可重跑 |  | 核心 A｜語音陪伴 | 開始語音互動＋理解與安全回應 | 國語／臺語對話與第二輪記憶引用 | 非固定腳本、可重試 |
| Wave 3 | RAG、陪伴需求、家屬報表與通知、主動陪伴與英文 | 18 | 7 | 可信關懷閉環可追溯 |  | 核心 B｜生活摘要 | 擷取事件＋摘要與照護者檢視 | 結構化事件與 AI 每日摘要 | 可追溯來源事件 |
| Wave 3 | RAG、陪伴需求、家屬通知、主動陪伴與英文 | 18 | 7 | 可信關懷閉環可追溯 |  | 核心 C｜照護者介面 | 摘要檢視＋覆核與關懷行動 | 詳情頁、時間軸、互動次數、修正 | 權限正確、可操作 |
| Wave 4 | 遊戲、積分、本土低資源語言、ASR 適應與持續改善 | 5 | 2 | 擴充能力不破壞核心 |  | 進階｜知識庫 | 理解與安全回應 | 來源過濾與引用 | 不足證據時不補完 |
|  |  |  |  |  |  | 進階｜家屬通知 | 家屬與主動陪伴 | 實際送出一次摘要通知 | 同意、靜默與重送 |
|  |  |  |  |  |  | 進階｜事件時間軸 | 再次引用與生活回顧 | 事件與摘要回到來源 | 去重且可篩選 |
| 第一條 Demo Gate | 15 個 Product Stories 的跨 Wave 薄切片 | 15 | TE-J01／J03／J04、MA01／MA02、GR01～GR03、VO01、H04／H06 | 完整跑通 A／B／C＋失敗路徑 |  | 加分｜低資源語言 | 開始語音互動 | 核心穩定後展示客語／原民語 | 不得破壞主流程 |
| 使用方式 |  |  |  |  |  |  |  |  |  |
| 1 | 先讀 01_Story Map：確認 Backbone 與 Wave |  |  |  | 4 | 再用 04_Enablers_NFR 補齊非功能工作 |  |  |  |
| 2 | 以 02_Story Backlog 作為 Product Story 單一清單 |  |  |  | 5 | 用 05_Demo Traceability 檢查命題與交付 |  |  |  |
| 3 | 先打通 03_Wave1 Vertical Slice，再擴大 Wave 2 |  |  |  | 6 | Owner／狀態欄保持可編輯，分工後再填 |  |  |  |
| 來源 | https://docs.google.com/document/d/1qb89I23zD8GJFzead_R_G6fXq2CZWgEsKBK7Q4o_F8A |  |  |  | 命題檔 | hackathon_challenge_ai_readable (1).json |  |  |  |
| Demo Persona 與場域 | 場域 | 語言 | 主要用途 | Demo 範圍 |  |  |  |  |  |
| 林阿嬤 | 幸福日照中心 | 臺語／國臺混語 | 語音、事件、記憶、Graph、摘要與覆核 | 主要端到端 Demo |  |  |  |  |  |
| 張阿姨 | 幸福日照中心 | 國語；客語待穩定度決定 | 多長者概覽、空狀態、資料隔離 | 輔助畫面與權限證據 |  |  |  |  |  |
| 陳伯伯 | 居家服務 | 國語 | 居服員派案／服務詳情、家屬每日／週／月報表與跨場域權限 | 權限與家屬端技術證據 |  |  |  |  |  |
| 場域決策 | Target Architecture 支援日照與居家；主要 Live Demo 採日照中心。三位 Persona 不需各自重跑完整主線。 |  |  |  |  |  |  |  |  |
| 家屬端決策 | App／Web 保存正式報表；LINE／Email 為通知與導流通路。 | 每日摘要、週報、月報、歷史事件、通知設定 | 只顯示已發布且已授權內容 | 不具專業覆核、記憶管理與待辦權限 |  |  |  |  |  |

## 工作表：01_Story Map

| Story Map｜Backbone × Implementation Waves |  |  |  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Backbone 依使用者價值流排列；每個 Product Story 只有一個主要落點。紫色列是最先打通的 Demo 薄切片，會重複引用部分 Wave 1／2 故事，目的在於第一條流程即覆蓋命題 A／B／C。 |  |  |  |  |  |  |  |  |  |  |
| 實作層級 | 1. 設定與同意 | 2. 開始語音互動 | 3. 理解與安全回應 | 4. 擷取生活事件 | 5. 確認與管理記憶 | 6. 再次引用與生活回顧 | 7. 摘要與專業照護者檢視 | 8. 覆核與關懷行動 | 9. 家屬報表、通知與主動陪伴 | 10. 參與與持續改善 |
| 主要使用者任務 | 建立 Persona<br>設定資料用途、主動陪伴與頻率 | 開始錄音<br>辨識語言與語音<br>播放自然回覆 | 組合必要 Context<br>回答或安全降級<br>查詢可信知識 | 抽取生活／社交事件<br>建立候選記憶 | 詢問是否保存<br>更正、停用、刪除 | 檢索已確認記憶<br>查詢近期生活與時間軸 | 產生每日摘要<br>查看日照概覽、居服派案與長者詳情 | 修正事件／訊號<br>建立關懷待辦與追蹤 | 發布家屬報表與通知<br>判斷時機、排序話題、追蹤 | 遊戲、積分、題庫<br>品質評估與回饋 |
| Demo Gate 1<br>跨 Wave 薄切片 | [US-A06] 分層同意與資料用途控制 | [US-A01] 低操作負擔的語音入口<br>[US-A02] 國語與臺語語音辨識<br>[US-A03] 符合語言偏好的語音回覆<br>[US-A05] 對話失敗的安全降級 | [US-A04] 情境感知對話 | [US-B01] 自動擷取結構化生活與社交事件<br>[US-D01] 提出並分級 Memory Proposal | [US-B03] 照護者修正與覆核<br>[US-D02] MEDIUM 版本綁定確認 | [US-B04] 事件時間軸<br>[US-D03] Trusted Memory 檢索與個人化回應 | [US-B02] 每日 AI 摘要<br>[US-C01] 專業照護者概覽與派案入口（薄版本）<br>[US-C02] 長者詳情頁 |  |  |  |
| Wave 1<br>核心記憶 | [US-A06] 分層同意與資料用途控制 | [US-A01] 低操作負擔的語音入口<br>[US-A02] 國語與臺語語音辨識<br>[US-A03] 符合語言偏好的語音回覆<br>[US-A05] 對話失敗的安全降級 | [US-A04] 情境感知對話 | [US-B01] 自動擷取結構化生活與社交事件<br>[US-D01] 提出並分級 Memory Proposal | [US-D02] MEDIUM 版本綁定確認<br>[US-D04] 更正、停用與刪除記憶 | [US-D03] Trusted Memory 檢索與個人化回應 |  |  |  |  |
| Wave 2<br>照護者閉環 |  |  |  |  | [US-B03] 照護者修正與覆核 | [US-A07] 週期生活回顧<br>[US-B04] 事件時間軸 | [US-B02] 每日 AI 摘要<br>[US-C01] 專業照護者概覽與派案入口<br>[US-C02] 長者詳情頁 | [US-C04] 關懷待辦與追蹤<br>[US-F02] 照護者候選行動建議 |  |  |
| Wave 3<br>可信關懷 | [US-N01] 主動陪伴同意、時段與頻率偏好 |  | [US-E01] 生活化問題理解<br>[US-E02] 來源與適用範圍過濾<br>[US-E03] 有根據的衛教回答 | [US-K01] 擷取社交連結與陪伴需求事件 |  |  |  | [US-K02] 產生可解釋的陪伴需求訊號<br>[US-K03] 照護者覆核與關懷規劃<br>[US-K04] 標準量表校正與人工施測<br>[US-N06] 照護者可追溯、核准與後續行動 | [US-C03] 家屬摘要發布與 LINE／Email 通知<br>[US-F01] 個人化關懷候選主題生成<br>[US-N02] 適當時機與不打擾判斷<br>[US-N03] 個人化話題排序與動態開場<br>[US-N04] 拒絕、換題、暫停與稍後再聊<br>[US-N05] 跨日追蹤與提醒<br>[US-N07] 主動互動回饋與個人化改善 | [US-E04] 檢索品質評估 |
|  |  |  |  |  |  |  |  |  | [US-C03] 家屬摘要發布與 LINE／Email 通知<br>[US-C05] 家屬每日摘要與週／月報表中心<br>[US-F01] 個人化關懷候選主題生成<br>[US-N02] 適當時機與不打擾判斷<br>[US-N03] 個人化話題排序與動態開場<br>[US-N04] 拒絕、換題、暫停與稍後再聊<br>[US-N05] 跨日追蹤與提醒<br>[US-N07] 主動互動回饋與個人化改善 |  |
| Wave 4<br>擴充優化 |  |  |  |  |  |  |  |  |  | [US-L01] 語音互動知識小遊戲<br>[US-L02] 個人積分與成就<br>[US-L03] 友善匿名排行榜<br>[US-L04] 題庫來源與內容審查<br>[US-M01] 回答與訊號回饋 |

## 工作表：02_Story Backlog

| Story ID | EPIC | 主要角色 | Backbone Activity | Story 標題 | 使用者故事／價值 | Product Priority | Implementation Wave | 命題對應 | Demo Gate 1 | 關鍵驗收 1 | 關鍵驗收 2 | 主要相依 | 備註／切片策略 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US-A01 | EPIC A｜長者語音互動陪伴 | 長者 | 開始語音互動 | 低操作負擔的語音入口 | 身為長者，我希望用一個明顯的大按鈕就能開始說話，讓我不必打字或操作複雜介面。 | MUST SHIP | Wave 1 | 核心 A｜語音互動陪伴 | 是 | 首頁可在一個主要操作內開始錄音。 | 錄音、處理、播放與錯誤狀態都有清楚的視覺及語音提示。 | US-A06 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-A02 | EPIC A｜長者語音互動陪伴 | 長者 | 開始語音互動 | 國語與臺語語音辨識 | 身為習慣國語、臺語或國臺混語的長者，我希望系統聽得懂我的說法，讓我不必刻意改用標準國語。 | MUST SHIP | Wave 1 | 核心 A｜語音互動陪伴 | 是 | 系統可依語言偏好或自動判斷選擇適當 ASR 路徑。 | Demo 測試集至少涵蓋國語、臺語及一組國臺混語。 | US-A01；TE-VO01；TE-I01 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-A03 | EPIC A｜長者語音互動陪伴 | 長者 | 開始語音互動 | 符合語言偏好的語音回覆 | 身為長者，我希望 AI 用我熟悉的語言、稱呼與回覆長度回應，讓對話自然且容易理解。 | MUST SHIP | Wave 1 | 核心 A｜語音互動陪伴 | 是 | Persona 可設定主要語言、稱呼方式及預設回覆長度。 | 回覆預設不超過三個重點，避免過長語音造成理解負擔。 | US-A02 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-A04 | EPIC A｜長者語音互動陪伴 | 長者 | 理解與安全回應 | 情境感知對話 | 身為長者，我希望 AI 能理解現在的時間、近期事件與我已確認的偏好，讓它不像固定腳本。 | MUST SHIP | Wave 1 | 核心 A｜語音互動陪伴 | 是 | 每輪只注入與當前問題相關的時間、情境、近期摘要及已確認記憶。 | 未確認的候選記憶及陪伴需求推估不得當成事實使用。 | US-D03；TE-J02 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-A05 | EPIC A｜長者語音互動陪伴 | 長者 | 開始語音互動 | 對話失敗的安全降級 | 身為長者，我希望系統聽不清楚或服務暫時失敗時仍能簡單引導我，避免我以為自己操作錯誤。 | MUST SHIP | Wave 1 | 核心 A｜語音互動陪伴 | 是 | ASR、LLM 或 TTS 逾時時提供簡短且可重試的提示。 | 同一輪最多自動重試一次，不得無限循環。 | US-A01；TE-J04 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-A06 | EPIC A｜長者語音互動陪伴 | 長者 | 設定與同意 | 分層同意與資料用途控制 | 身為長者，我希望知道系統會保存與分析什麼，並能分別決定是否同意。 | MUST SHIP | Wave 1 | 核心 A｜語音互動陪伴 | 是 | 第一次使用前以白話說明錄音、逐字稿、生活事件、長期記憶、陪伴需求分析、家屬通知及資料保存期限。 | 使用者可分別同意或拒絕長期記憶、陪伴需求分析與家屬通知。 | NFR-H01～H03 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-A07 | EPIC A｜長者語音互動陪伴 | 長者 | 再次引用與生活回顧 | 週期生活回顧 | 身為長者，我希望用語音詢問最近一週的生活情況，了解自己的睡眠、飲食、活動與社交紀錄。 | COMMITTED INNOVATION | Wave 2 | 核心 A｜語音互動陪伴 | 否 | 長者可用生活化語句查詢最近七日紀錄。 | 結果同時提供文字及語音。 | US-B02；US-D03 | 依 Wave 交付 |
| US-B01 | EPIC B｜生活記錄與每日摘要 | 照護者 | 擷取生活事件 | 自動擷取結構化生活與社交事件 | 身為照護者，我希望系統自動從對話中擷取飲食、活動、睡眠、用藥陳述、情緒表達與社交事件，減少人工抄寫。 | MUST SHIP | Wave 1 | 核心 B｜生活記錄與智慧摘要 | 是 | 事件輸出通過固定 Schema 驗證後才能寫入正式資料庫。 | 用藥欄位只記錄「長者陳述」，不得推論服藥是否正確。 | US-A02；TE-J03 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-B02 | EPIC B｜生活記錄與每日摘要 | 照護者 | 摘要與照護者檢視 | 每日 AI 摘要 | 身為照護者，我希望每天看到一份精簡且可追溯的生活摘要，快速掌握長者近況。 | MUST SHIP | Wave 2 | 核心 B｜生活記錄與智慧摘要 | 是 | 摘要涵蓋飲食、活動、睡眠、用藥陳述、社交互動及重要事件。 | 沒有資料的欄位明確標示「未提及」。 | US-B01；US-B03 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-B03 | EPIC B｜生活記錄與每日摘要 | 照護者 | 確認與管理記憶 | 照護者修正與覆核 | 身為照護者，我希望修正 AI 擷取錯誤，讓後續摘要、記憶與陪伴需求分析更可靠。 | MUST SHIP | Wave 2 | 核心 B｜生活記錄與智慧摘要 | 是 | 後台可編輯事件內容、事件類型、事件時間及 review_status。 | 可標記 ASR 聽錯、事件誤判、裝置故障、外出或其他排除原因。 | US-B01；TE-GR03 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-B04 | EPIC B｜生活記錄與每日摘要 | 照護者 | 再次引用與生活回顧 | 事件時間軸 | 身為照護者，我希望按時間查看長者的重要互動與生活事件，快速理解變化。 | COMMITTED INNOVATION | Wave 2 | 核心 B｜生活記錄與智慧摘要 | 是 | 可依日期、事件類型、來源及審查狀態篩選。 | 同一事件不因重新摘要而重複顯示。 | US-B01；US-B03 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-C01 | EPIC C｜照護者與家屬介面 | 專業照護人員 | 摘要與專業照護者檢視 | 專業照護者概覽與派案入口 | 身為專業照護人員，我希望依工作場域看到同據點長者或被派案長者的摘要、行程與待處理事項，降低切換與交接成本。 | MUST SHIP | Wave 2 | 核心 C｜照護者資訊介面 | 是 | 日照模式顯示最後互動、今日互動、摘要與待覆核；居服模式顯示今日服務時段、派案狀態、上次服務摘要與待追蹤事項。 | Demo 至少顯示林阿嬤與張阿姨；居服員只顯示有效派案長者，未授權資料不得出現在列表、搜尋或統計。 | US-B02；US-C02；NFR-H01 | Demo Gate 1 只演日照薄版本；居服派案入口以陳伯伯作權限與 UX 證據。 |
| US-C02 | EPIC C｜照護者與家屬介面 | 專業照護人員 | 摘要與專業照護者檢視 | 長者詳情頁 | 身為專業照護人員，我希望查看被授權長者的基本資料、每日摘要、時間軸、已確認記憶及陪伴需求訊號。 | MUST SHIP | Wave 2 | 核心 C｜照護者資訊介面 | 是 | 頁面明確區分基本資料、AI 擷取事件、已確認記憶、陪伴需求訊號及衛教內容。 | 由日照長者卡、居服服務行程或單一有效派案進入時可直接開啟詳情，但不得放寬 elder_id／tenant_id／assignment 權限。 | US-B02；US-B04；US-D03；NFR-H01 | 共用詳情元件；依日照照服員、居服員角色收斂欄位與操作。 |
| US-C03 | EPIC C｜照護者與家屬介面 | 家屬 | 家屬報表、通知與主動陪伴 | 家屬摘要發布與 LINE／Email 通知 | 身為家屬，我希望系統先將經授權的近況保存於家屬端，再依偏好透過 LINE／Email 通知我查看。 | MUST SHIP | Wave 3 | 進階｜家屬推播通知 | 否 | Demo 先發布一筆正式摘要至家屬 App／Web，再實際透過 LINE 或 Email 送出通知。 | App／Web、LINE 與 Email 共用 report_id；通知失敗不影響已發布報表。 | US-A06；US-B02；US-C05；TE-PRO01 | LINE／Email 為通知通路，不是正式資料保存來源。 |
| US-C04 | EPIC C｜照護者與家屬介面 | 專業照護人員 | 覆核與關懷行動 | 關懷待辦與追蹤 | 身為專業照護人員，我希望把需要關心的事件轉成可追蹤待辦，避免重要事項只停留在摘要中。 | MUST SHIP | Wave 2 | 核心 C｜照護者資訊介面 | 否 | 可建立聯繫長者、確認家屬聯繫、邀請活動及設定追蹤日期等待辦。 | 每項待辦顯示觸發原因、相關事件、建立者、期限及狀態。 | US-C02；US-B03 | 依角色與派案／據點權限限制操作。 |
| US-C05 | EPIC C｜照護者與家屬介面 | 家屬 | 家屬報表、通知與主動陪伴 | 家屬每日摘要與週／月報表中心 | 身為經授權的家屬，我希望在 App／Web 查看每日摘要、每週與每月報表及歷史重要事件，持續了解長者近況。 | MUST SHIP | Wave 3 | 核心 C／進階｜家屬資訊介面 | 否 | 只顯示 Published 且在分享授權範圍內的報表；沒有資料時標示未提及或資料不足。 | 報表保存 report_id、期間、版本、來源事件、發布狀態與時間；家屬不得查看逐字稿、未覆核事件或專業內部資料。 | US-A06；US-B02；US-C03；NFR-H01～H03 | 家屬端保存正式資料；撤回授權後停止新報表、通知與安全連結存取。 |
| US-D01 | EPIC D｜風險分級且可控的 AI 長期記憶 | 長者 | 擷取生活事件 | 提出並分級 Memory Proposal | 身為長者，我希望 AI 能記得我的偏好與生活習慣，但不要將每句話都永久保存。 | MUST SHIP | Wave 1 | 核心 A/B｜情境記憶＋生活資料 | 是 | Agent 只提案；Core 依 Consent、verified Speaker、內容、來源與 versioned policy 決定 LOW／MEDIUM／HIGH。 | LOW 須 all-of；MEDIUM 建固定版本 Candidate；HIGH 零 Memory row；Event 不自動 promotion。 | US-B01；TE-J03；Spec 18 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-D02 | EPIC D｜風險分級且可控的 AI 長期記憶 | 長者 | 確認與管理記憶 | MEDIUM 版本綁定確認 | 身為長者，我希望重要事項只在我確認精確內容後保存，且不會被他人代為同意。 | MUST SHIP | Wave 1 | 核心 A/B｜情境記憶＋生活資料 | 是 | UI／Voice 確認綁 memory version、content digest、consent 與 policy version。 | 模糊／低信心／拒絕不得 ACTIVE；witness 不能取代 Elder consent。 | US-D01；US-A06；Spec 18 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-D03 | EPIC D｜風險分級且可控的 AI 長期記憶 | 長者 | 再次引用與生活回顧 | Trusted Memory 檢索與個人化回應 | 身為長者，我希望 AI 在適當時機只引用目前仍可信的記憶，避免重複詢問或引用失效內容。 | MUST SHIP | Wave 1 | 核心 A/B｜情境記憶＋生活資料 | 是 | Core 每次 Context 組合重新檢查 ACTIVE、current version、Consent、Speaker、verification、validity 與 scope。 | Cross-elder／tenant、legacy 缺 evidence、expired／inactive／deleted 或 stale confirmation 全部排除。 | US-D02；TE-GR01；Spec 18 | 先做最薄可演示版本，再依原 Wave 擴充完整驗收 |
| US-D04 | EPIC D｜風險分級且可控的 AI 長期記憶 | 長者／授權照護者 | 確認與管理記憶 | 更正、停用與刪除記憶 | 身為長者或授權照護者，我希望能夠更正或刪除錯誤的記憶內容。 | MUST SHIP | Wave 1 | 核心 A/B｜情境記憶＋生活資料 | 否 | 更正建立新 version 並重新 policy；MEDIUM 新版本重新確認。 | 已過期、刪除、停用或舊確認綁定的版本不得被檢索。 | US-D02；TE-GR03；Spec 18 | 依 Wave 交付 |
| US-E01 | EPIC E｜可信知識查詢與 RAG | 長者 | 理解與安全回應 | 生活化問題理解 | 身為長者，我希望用生活化說法提問，也能找到適用的衛教或長照資源。 | COMMITTED INNOVATION | Wave 3 | 進階｜知識庫建置 | 否 | 系統保留原始問題並產生檢索查詢。 | 查詢改寫不得改變疾病、地區、服務類型、日期及否定詞等關鍵條件。 | TE-G01～G03 | 依 Wave 交付 |
| US-E02 | EPIC E｜可信知識查詢與 RAG | 照護者 | 理解與安全回應 | 來源與適用範圍過濾 | 身為照護者，我希望系統依來源、地區、適用對象、日期與審查狀態過濾資料，避免提供不適用內容。 | MUST SHIP | Wave 3 | 進階｜知識庫建置 | 否 | 可依 source_agency、region、service_type、effective_date、review_status 等欄位過濾。 | needs_review、來源不明及已失效資料不得以權威答案呈現。 | TE-G01～G03 | 依 Wave 交付 |
| US-E03 | EPIC E｜可信知識查詢與 RAG | 長者／照護者 | 理解與安全回應 | 有根據的衛教回答 | 身為長者或照護者，我希望知道回答來自哪份可信資料。 | MUST SHIP | Wave 3 | 進階｜知識庫建置 | 否 | 回答顯示來源名稱、發布機關或可追溯識別。 | 找不到足夠證據時不自行補完。 | US-E01；US-E02；TE-J03 | 依 Wave 交付 |
| US-E04 | EPIC E｜可信知識查詢與 RAG | 開發團隊 | 參與與持續改善 | 檢索品質評估 | 身為開發團隊，我希望量化檢索方法的改善，證明技術選擇有實際價值。 | COMMITTED INNOVATION | Wave 3 | 進階｜知識庫建置 | 否 | 建立人工標註的查詢與相關文件測試集。 | 至少比較基礎檢索與最終方案。 | US-E01～E03 | 依 Wave 交付 |
| US-F01 | EPIC F｜個人化關懷與下一步行動 | 長者 | 家屬與主動陪伴 | 個人化關懷候選主題生成 | 身為長者，我希望系統根據近期生活與已確認偏好準備合適的候選主題，供回應式或主動式互動使用。 | COMMITTED INNOVATION | Wave 3 | 核心 C｜照護協作 | 否 | 候選主題可來自近期事件、已確認記憶、時間情境與明確偏好。 | 排序不得依未確認健康推測、孤獨推估或敏感標籤決定。 | US-D03；US-B04 | 依 Wave 交付 |
| US-F02 | EPIC F｜個人化關懷與下一步行動 | 照護者 | 覆核與關懷行動 | 照護者候選行動建議 | 身為照護者，我希望系統整理可以採取的下一步，而不是替我做醫療或照護決定。 | MUST SHIP | Wave 2 | 核心 C｜照護協作 | 否 | 建議限定為查看、確認、聯繫、活動邀請及追蹤等工作流。 | 不得建議改藥、停藥、做疾病診斷或自動改變正式照護計畫。 | US-C02；US-B03 | 依 Wave 交付 |
| US-K01 | EPIC K｜日常互動陪伴需求訊號 | 照護者 | 擷取生活事件 | 擷取社交連結與陪伴需求事件 | 身為照護者，我希望系統從經同意的日常互動中擷取社交聯繫、活動參與及陪伴需求相關事件，讓我不需閱讀全部逐字稿。 | MUST SHIP | Wave 3 | 創新｜個人化互動＋社會應用 | 否 | 擷取家人或朋友聯繫、預期聯繫未發生、活動參與、活動取消、明確孤單或想找人聊天的表達。 | 每筆事件顯示來源句、時間、ASR 信心、擷取信心及審查狀態。 | US-A06；US-B01 | 依 Wave 交付 |
| US-K02 | EPIC K｜日常互動陪伴需求訊號 | 照護者 | 覆核與關懷行動 | 產生可解釋的陪伴需求訊號 | 身為照護者，我希望系統整理長者近期互動模式的變化與證據，讓我判斷是否需要進一步關心。 | MUST SHIP | Wave 3 | 創新｜個人化互動＋社會應用 | 否 | 使用同一位長者的個人歷史基準，不與其他長者比較。 | 首版分析規則比較最近七天與過去二十八天的個人歷史基準；時間窗口由版本化 Policy 設定。 | US-K01；TE-J05；TE-G04 | 依 Wave 交付 |
| US-K03 | EPIC K｜日常互動陪伴需求訊號 | 照護者 | 覆核與關懷行動 | 照護者覆核與關懷規劃 | 身為照護者，我希望查看陪伴需求訊號、確認正確性並建立後續行動，讓 AI 協助整理但不代替我決策。 | MUST SHIP | Wave 3 | 創新｜個人化互動＋社會應用 | 否 | 可查看證據、確認需要關懷、排除訊號、修正事件、建立聯繫待辦、安排活動及設定追蹤日。 | 排除時可記錄裝置故障、外出、誤判或資料不足等原因。 | US-K02；US-C04 | 依 Wave 交付 |
| US-K04 | EPIC K｜日常互動陪伴需求訊號 | 照護者 | 覆核與關懷行動 | 標準量表校正與人工施測 | 身為照護者，我希望必要時使用經審查的簡短量表確認長者主觀感受，讓日常互動訊號有額外參考依據。 | COMMITTED INNOVATION | Wave 3 | 創新｜個人化互動＋社會應用 | 否 | 正式量表必須由長者實際回答，不得從自由對話猜測答案。 | 計分由固定程式執行，不由 LLM 自由計算。 | TE-G04；US-K03 | 依 Wave 交付 |
| US-L01 | EPIC L｜互動遊戲、成就與參與 | 長者 | 參與與持續改善 | 語音互動知識小遊戲 | 身為長者，我希望透過簡單、有趣的語音問答與 AI 互動，讓日常陪伴更有趣。 | COMMITTED INNOVATION | Wave 4 | 擴充｜參與體驗 | 否 | 長者可用語音說「我要玩遊戲」開始。 | 每局預設三至五題，可隨時停止。 | US-A01～A05；US-L04 | 依 Wave 交付 |
| US-L02 | EPIC L｜互動遊戲、成就與參與 | 長者 | 參與與持續改善 | 個人積分與成就 | 身為長者，我希望完成互動或遊戲後獲得積分與成就，感受到參與及進步。 | COMMITTED INNOVATION | Wave 4 | 擴充｜參與體驗 | 否 | 完成遊戲、互動或學習活動可獲得積分。 | 積分不只依答對數計算，完成參與也可獲得基本分數。 | US-L01 | 依 Wave 交付 |
| US-L03 | EPIC L｜互動遊戲、成就與參與 | 長者 | 參與與持續改善 | 友善匿名排行榜 | 身為選擇參加團體活動的長者，我希望看到自己與團體的活動成果，增加共同參與的樂趣。 | BONUS IF STABLE | Wave 4 | 擴充｜參與體驗 | 否 | 排行榜預設關閉，由長者或授權照護者主動加入。 | 只顯示暱稱或虛擬名稱。 | US-L02；US-A06 | 依 Wave 交付 |
| US-L04 | EPIC L｜互動遊戲、成就與參與 | 內容管理者 | 參與與持續改善 | 題庫來源與內容審查 | 身為內容管理者，我希望遊戲題目具有來源、版本與適用對象，避免提供錯誤或不適合的內容。 | COMMITTED INNOVATION | Wave 4 | 擴充｜參與體驗 | 否 | 保存題目來源、版本、語言、難度、適用對象及審查狀態。 | 未審查題目不得進入正式衛教遊戲。 | TE-G01～G03 | 依 Wave 交付 |
| US-M01 | EPIC M｜回饋與持續改善 | 長者／照護者 | 參與與持續改善 | 回答與訊號回饋 | 身為長者或照護者，我希望回報回答是否有幫助或訊號是否誤判，讓系統能持續改善。 | COMMITTED INNOVATION | Wave 4 | 品質｜持續改善 | 否 | 長者可提供簡單的有幫助／沒有幫助回饋。 | 照護者可標記回答錯誤、來源不適用、事件誤判或陪伴需求訊號誤判。 | US-E03；US-K03；US-N07 | 依 Wave 交付 |
| US-N01 | EPIC N｜AI 主動式個人化陪伴與對話發起 | 長者 | 設定與同意 | 主動陪伴同意、時段與頻率偏好 | 身為長者，我希望自己決定 AI 是否能主動找我、何時可以找我及一天最多幾次，避免被打擾。 | COMMITTED INNOVATION | Wave 3 | 創新｜AI 記憶＋個人化互動 | 否 | 主動陪伴預設須取得獨立同意，不能只沿用一般對話同意。 | 可設定允許時段、靜默時段、每日上限、最短間隔、允許通路與暫停期限。 | US-A06；TE-PRO01 | 依 Wave 交付 |
| US-N02 | EPIC N｜AI 主動式個人化陪伴與對話發起 | 長者 | 家屬與主動陪伴 | 適當時機與不打擾判斷 | 身為長者，我希望 AI 只在適合的時間主動互動，活動取消、裝置離線或我正在忙時不要播放。 | COMMITTED INNOVATION | Wave 3 | 創新｜AI 記憶＋個人化互動 | 否 | Trigger 可來自排程、活動到期、長者要求稍後提醒、裝置進入、照護者安排及核准的關懷事件。 | Eligibility Gate 以確定性程式檢查同意、靜默時段、每日上限、cooldown、裝置、Session、拒絕紀錄與來源事件狀態。 | US-N01；TE-PRO01 | 依 Wave 交付 |
| US-N03 | EPIC N｜AI 主動式個人化陪伴與對話發起 | 長者 | 家屬與主動陪伴 | 個人化話題排序與動態開場 | 身為長者，我希望 AI 的主動開場有生活脈絡、簡短自然，而且只引用我已確認的資訊。 | COMMITTED INNOVATION | Wave 3 | 創新｜AI 記憶＋個人化互動 | 否 | 候選話題可來自近期已覆核事件、已確認記憶、時間情境、未完成追蹤與照護者核准活動。 | 排序保存分數、reason_codes、來源 event_id／memory_id、Policy 版本與重複抑制結果。 | US-N02；US-D03；US-B04 | 依 Wave 交付 |
| US-N04 | EPIC N｜AI 主動式個人化陪伴與對話發起 | 長者 | 家屬與主動陪伴 | 拒絕、換題、暫停與稍後再聊 | 身為長者，我希望能隨時說不想聊、換一個、停止或晚點再說，系統不會一直追問。 | COMMITTED INNOVATION | Wave 3 | 創新｜AI 記憶＋個人化互動 | 否 | 國語、臺語與英文路徑均需辨識拒絕、換題、停止及稍後再聊的核心指令；其他語言依 Wave 4 測試結果開放。 | 拒絕後立即停止追問並更新近期推薦限制，不因拒絕產生負面診斷。 | US-N03；TE-VO01 | 依 Wave 交付 |
| US-N05 | EPIC N｜AI 主動式個人化陪伴與對話發起 | 長者 | 家屬與主動陪伴 | 跨日追蹤與提醒 | 身為長者，我希望 AI 能在我要求的時間提醒，或在已記錄的活動後延續關心，不必每天重新解釋。 | COMMITTED INNOVATION | Wave 3 | 創新｜AI 記憶＋個人化互動 | 否 | follow_up_plan 支援 scheduled、completed、postponed、cancelled 與 expired 狀態。 | 同一來源事件不得重複建立相同追蹤，需有 idempotency_key 與 expires_at。 | US-N04；TE-PRO01 | 依 Wave 交付 |
| US-N06 | EPIC N｜AI 主動式個人化陪伴與對話發起 | 照護者 | 覆核與關懷行動 | 照護者可追溯、核准與後續行動 | 身為照護者，我希望知道 AI 為何主動互動、使用哪些資料，以及是否需要建立待辦或通知家屬。 | COMMITTED INNOVATION | Wave 3 | 創新｜AI 記憶＋個人化互動 | 否 | 後台可查看 Trigger、Eligibility、Topic、Context、來源事件、已確認記憶、模型、Policy、安全結果與 trace_id。 | 涉及陪伴需求變化、家庭衝突、健康、財務或創傷的敏感話題，主動播放前必須依 Policy 要求人工核准或完全禁止。 | US-N03；US-C04 | 依 Wave 交付 |
| US-N07 | EPIC N｜AI 主動式個人化陪伴與對話發起 | 長者／照護者 | 家屬與主動陪伴 | 主動互動回饋與個人化改善 | 身為長者或照護者，我希望回饋話題是否合適與時間是否適合，讓未來互動更貼近需求。 | COMMITTED INNOVATION | Wave 3 | 創新｜AI 記憶＋個人化互動 | 否 | 支援有幫助、沒幫助、不要再聊、時間不適合、內容重複與人工誤判回饋。 | 回饋進入審查與統計流程，不得直接改動正式知識、醫療規則或模型。 | US-N03；US-N06 | 依 Wave 交付 |

## 工作表：03_Wave1 Vertical Slice

| 第一條端到端 Vertical Slice｜核心記憶＋日照概覽＋最小專業照護者閉環 |  |  |  |  |  |  |  |  |  |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 目標：先用最薄的 Wave 2 畫面把 A／B／C 串起來。Gate 通過條件：林阿嬤完成語音、事件、記憶、Graph、再次引用與每日摘要；日照照服員從林阿嬤、張阿姨概覽進入林阿嬤詳情並覆核。居服員派案入口與家屬 App／Web 報表、LINE／Email 通知列為 Wave 3／權限技術證據，不要求重跑林阿嬤主線。 |  |  |  |  |  |  |  |  |  |
| 順序 | Actor | 使用者／系統步驟 | 系統行為 | Stories／Requirements | 主要元件／Agent | 資料／狀態 | 完成證據 | 失敗／安全處理 | Owner |
| 1 | 長者 | 進入虛擬 Persona 並確認資料用途 | 載入語言、稱呼、記憶與家屬通知同意 | US-A06；NFR-H06 | Identity／Consent | persona_id、consent_version | 同意狀態可回讀；僅使用模擬資料 | 拒絕長期記憶時仍可繼續基本陪伴 |  |
| 2 | 長者 | 按一次大按鈕開始說話 | 顯示錄音狀態並取得語音 | US-A01 | Web／Audio Capture | audio_session_id | 桌面與行動裝置均可完成 | 未授權麥克風時白話引導 |  |
| 3 | 系統 | 辨識國語／臺語／混語內容 | Speech Router 選擇 ASR 並輸出 final transcript | US-A02；TE-VO01 | Speech Router／ASR | transcript、confidence、model_version | 固定語音測試集可重跑；保留關鍵人物與日期 | 低信心時要求重說，不假裝理解 |  |
| 4 | 系統 | 路由至 Companion 與 Memory 流程 | Orchestrator 依版本化 Intent／Policy 執行固定節點 | TE-J01；TE-MA01 | Orchestrator | trace_id、intent、policy_version | 單輪同步 Agent 步驟不超過 3 | 逾時或節點失敗走安全降級 |  |
| 5 | AI | 產生簡短、符合語言偏好的回覆 | 只注入必要情境與已確認記憶 | US-A03；US-A04；TE-J02 | Companion Agent | context_bundle、draft_response | 回覆不超過三個重點；未確認資訊不當事實 | 無可信資料時明確說不知道 |  |
| 6 | 系統 | 擷取生活事件與候選記憶 | 以固定 Schema 產出人物、活動、時間、關係與來源 | US-B01；US-D01 | Memory Agent | event_candidate、memory_candidate | Schema 驗證通過；保留來源句與信心 | 用藥只記長者陳述，不推論正確性 |  |
| 7 | 系統 | 驗證輸出與醫療邊界 | 顯示、TTS、寫入前通過 Safety Evaluator | TE-J03；TE-MA02；NFR-H04 | Safety Evaluator | safety_result、reason_codes | 安全規則測試通過並保存 trace | 修正最多一次，再失敗使用固定安全回覆 |  |
| 8 | 長者 | 確認 MEDIUM 固定版本記憶 | 以 candidate-specific 短句詢問；接受、拒絕或稍後處理 | US-D02 | Companion／Memory | version-bound confirmation、speaker evidence | 拒絕或 stale version 時不建立正式記憶 | 辨識不清時維持 pending；witness 不代為同意 |  |
| 9 | 系統 | 寫入交易事實並建立 Outbox | RDS 保存正式狀態；同一事件具冪等鍵 | TE-GR03 | RDS／Transactional Outbox | event_id、memory_id、idempotency_key | 重送不產生重複資料 | 失敗可重試並進入 DLQ |  |
| 10 | 系統 | 同步人物、事件與關係投影 | 只把已確認或已覆核資料寫入 Graph DB | TE-GR01；TE-GR02 | Graph Projector／Graph DB | node、edge、source_event_id | 可跑兩層關係查詢並回到來源事件 | 禁止未保護雙寫與跨 elder 查詢 |  |
| 11 | 長者 | 下一輪對話被自然再次引用 | 檢索少量相關已確認記憶後生成回覆 | US-D03；US-A04 | Memory Retrieval／Companion | retrieved_memory_ids | 只引用同一位長者的 active 記憶 | 查不到時不虛構 |  |
| 12 | 系統 | 日終產生結構化生活摘要 | 彙整已記錄事件，未提及欄位保持未提及 | US-B02 | Summary Workflow | daily_summary、source_event_ids | 可追溯到事件；非人工填寫 | 排程失敗重試並告警 |  |
| 13 | 機構照服員 | 查看幸福日照中心的多長者概覽並選擇林阿嬤 | 只顯示同 tenant 且已授權的林阿嬤與張阿姨；顯示最後互動、互動次數、摘要狀態與待覆核數量 | US-C01；NFR-H01 | Caregiver Web／Authorization | elder_list、tenant_id、authorization_scope | 可由概覽點擊林阿嬤進入詳情；居家服務員／居服員帳號不顯示多長者概覽 | 未授權或不同 tenant 長者不得出現在列表、搜尋與統計中 |  |
| 14 | 照護者 | 查看長者詳情與事件時間軸 | 顯示基本資料、摘要、互動次數、記憶與事件證據 | US-C02；US-B04 | Caregiver Web | elder_view、timeline | 核心 A/B/C 同一條 Demo 流程可見 | 權限不足不顯示資料 |  |
| 15 | 照護者 | 覆核或修正 AI 擷取結果 | 更新事件、排除原因與 review_status | US-B03 | Review Workflow | review_status、correction | 更正後摘要／Graph 投影可重建 | 保留修改人、時間與版本 |  |
| 16 | 團隊／評審 | 查看技術證據 | 展示 ASR 指標、Agent trace、Graph 查詢與安全攔截 | TE-I03；TE-J04；NFR-Q04 | Observability／Eval | metrics、trace_id、test_case_id | 可重複演示正常與失敗路徑 | 日誌不保存不必要完整逐字稿 |  |

## 工作表：04_Enablers_NFR

| ID | 分類 | 標題 | Implementation Wave | Product Priority | 主要支援階段 | 支援 Stories／能力 | 關鍵規則 1 | 關鍵規則 2 | 完成證據 | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TE-G01 | 資料治理／RAG | 可信來源登錄 | Wave 3 | MUST SHIP | 可信知識／治理 | US-E02、E03、L04 | 每個來源建立 manifest 或 Structured Record。 | 至少記錄來源機關、標題、版本／日期、地區、授權、公開來源資訊與審查狀態。 | 來源登錄、版本、Chunk／Policy 證據 |  | 待實作 |
| TE-G02 | 資料治理／RAG | 文件切片與審查 | Wave 3 | MUST SHIP | 可信知識／治理 | US-E02、E03、E04 | 流程為來源登錄、解析清理、切片、Metadata、審查、Embedding／Index。 | Sheet 不存完整 chunk_text，只保存檔名、索引及審查資訊。 | 來源登錄、版本、Chunk／Policy 證據 |  | 待實作 |
| TE-G03 | 資料治理／RAG | 版本與失效管理 | Wave 3 | COMMITTED INNOVATION | 可信知識／治理 | US-E02、E03 | Chunk 可追溯至來源文件版本。 | 來源更新後可重建索引並標記舊版本失效。 | 來源登錄、版本、Chunk／Policy 證據 |  | 待實作 |
| TE-G04 | 資料治理／RAG | 量表與分析規則版本管理 | Wave 3 | COMMITTED INNOVATION | 覆核與關懷行動 | US-K02～K04 | 保存量表或規則的來源、名稱、版本、語言、適用族群、施測方式、計分規則、授權狀態、審查狀態及生效日期。 | 量表說明文件可進入 RAG；正式題目與計分規則另存於結構化 Policy Registry。 | 來源登錄、版本、Chunk／Policy 證據 |  | 待實作 |
| TE-I01 | ASR 測試／適應 | 建立長者語音測試集 | Wave 1 | MUST SHIP | 開始語音互動 | US-A02 | 測試集依語言、說話者、語速、噪音及混語情境分層。 | 訓練、驗證及測試說話者不得不當重疊。 | 測試集、指標報告或模型版本 |  | 待實作 |
| TE-I02 | ASR 測試／適應 | 長者語音 ASR 適應 | Wave 4 | COMMITTED INNOVATION | 開始語音互動 | US-A02 | 保存訓練資料版本、模型產物、超參數、Checkpoint 及程式版本。 | 優先採黑客松時限內可完成的方法。 | 測試集、指標報告或模型版本 |  | 待實作 |
| TE-I03 | ASR 測試／適應 | ASR 品質報告 | Wave 1 | MUST SHIP | 開始語音互動 | US-A02；Demo 證據 | 至少報告 CER、WER、關鍵事件保留率與代表性失敗案例。 | 依國語、臺語及混語情境切分結果。 | 測試集、指標報告或模型版本 |  | 待實作 |
| TE-I04 | ASR 測試／適應 | 即時與批次推論分流 | Wave 4 | BONUS IF STABLE | 開始語音互動 | US-A02；離線評估 | 即時對話使用低延遲推論路徑。 | 大量測試音檔可使用離線批次流程。 | 測試集、指標報告或模型版本 |  | 待實作 |
| TE-J01 | Workflow／可觀測性 | 受控 Multi-Agent 與確定性工作流協調 | Wave 1 | MUST SHIP | 理解與安全回應 | A／B／D／E／K／N 流程 | Orchestrator 依意圖路由至 Companion、Memory、Knowledge、Care Insight 等專責 Agent；Agent 不進行自由協商。 | 每個節點有明確輸入、輸出、Schema、權限、逾時、重試及失敗處理。 | trace、Schema、安全與失敗路徑 |  | 待實作 |
| TE-J02 | Workflow／可觀測性 | Context Engineering | Wave 1 | MUST SHIP | 理解與安全回應 | US-A04、D03、E03、N03 | Context 由 System Prompt、Persona、近期摘要、已確認記憶、情境及檢索結果動態組成。 | 不把全部逐字稿、全部記憶或整份 PDF 塞入模型。 | trace、Schema、安全與失敗路徑 |  | 待實作 |
| TE-J03 | Workflow／可觀測性 | 輸出驗證與安全檢查 | Wave 1 | MUST SHIP | 理解與安全回應 | 所有顯示、寫入與通知 | 結構化輸出必須通過 Schema 驗證。 | 對話回覆需經醫療邊界、安全與敏感資料檢查。 | trace、Schema、安全與失敗路徑 |  | 待實作 |
| TE-J04 | Workflow／可觀測性 | 監控與追蹤 | Wave 1 | MUST SHIP | 全旅程 | 所有核心故事 | 記錄延遲、錯誤率、ASR 失敗、檢索空結果、模型逾時、訊號分析失敗及通知失敗。 | 日誌不得直接保存完整敏感逐字稿。 | trace、Schema、安全與失敗路徑 |  | 待實作 |
| TE-J05 | Workflow／可觀測性 | 陪伴需求背景分析工作流 | Wave 3 | MUST SHIP | 覆核與關懷行動 | US-K01～K04 | 每日或每週由排程觸發。 | Agent 預設讀取結構化事件與互動統計，不無限制讀取全部逐字稿。 | trace、Schema、安全與失敗路徑 |  | 待實作 |
| TE-MA01 | 受控 Multi-Agent | Orchestrator 與專責 Agent 路由 | Wave 1 | MUST SHIP | 理解與安全回應 | A／B／D／E／K／N 流程 | Orchestrator 只依版本化 Intent／Policy 路由至 Companion、Memory、Knowledge、Care Insight 與 Safety Evaluator。 | 每個 Agent 僅能使用白名單 Tool、最小必要資料與明確 JSON Schema。 | trace、Schema、安全與失敗路徑 |  | 待實作 |
| TE-MA02 | 受控 Multi-Agent | Safety Evaluator 與輸出閘門 | Wave 1 | MUST SHIP | 理解與安全回應 | 所有顯示、寫入與通知 | 對話顯示、TTS 播放、家屬通知、正式寫入與高風險行動前，均須通過適用的安全與權限檢查。 | Evaluator 失敗最多修正一次，再失敗使用安全降級內容並保留 trace。 | trace、Schema、安全與失敗路徑 |  | 待實作 |
| TE-GR01 | 資料治理／RAG | 確認式人物、事件與關係 Graph | Wave 1 | COMMITTED INNOVATION | 確認與管理記憶 | US-D02、D03、B04 | 只有已確認人物／偏好／關係與已覆核事件，才能寫入 Graph DB 的正式投影。 | RDS 保存同意、權限、任務、正式狀態與交易紀錄；Graph DB 保存人物、事件、偏好與關係投影，RDS 為交易事實來源。 | 來源登錄、版本、Chunk／Policy 證據 |  | 待實作 |
| TE-GR02 | 資料治理／RAG | 關係查詢與可證明的 Graph 價值 | Wave 1 | COMMITTED INNOVATION | 再次引用與生活回顧 | US-D03、K02、N03 | 至少實作一個兩層關係查詢，例如「林阿嬤 → 女兒小美 → 每週日通話 → 最近未聯絡」。 | 查詢只回傳同一 tenant／elder 權限範圍內的 active 關係，並可追溯到來源事件。 | 來源登錄、版本、Chunk／Policy 證據 |  | 待實作 |
| TE-GR03 | 資料治理／RAG | RDS 與 Graph DB 一致性 | Wave 1 | MUST SHIP | 確認與管理記憶 | US-D04、B03 | 以 Transactional Outbox、冪等鍵、重試與 dead-letter queue 將 RDS 事件同步為 Graph 投影，禁止無保護雙寫。 | 記憶或事件更正、停用、撤回與刪除時，同步更新 Graph node／edge 與搜尋索引。 | 來源登錄、版本、Chunk／Policy 證據 |  | 待實作 |
| TE-VO01 | 多語語音 | 多語 Speech Router | Wave 1 | MUST SHIP | 開始語音互動 | US-A02、A03、N04 | 依 Persona 偏好、長者明確切換指令與 Session 狀態選擇 ASR／TTS 路徑，不為每句短語重新偵測語言。 | 國語、臺語、客語與英文共用相同 Agent、記憶、安全與資料治理流程；差異只存在於語音供應者、模型與評估資料。 | 語言切換與語音測試 |  | 待實作 |
| TE-PRO01 | 主動互動狀態機 | Trigger／Eligibility／Follow-up 狀態機 | Wave 3 | COMMITTED INNOVATION | 家屬與主動陪伴 | US-N01～N07、C03 | Trigger、Eligibility、Session、Topic、Follow-up 與 Care Action 都有 owner、狀態、expires_at、idempotency_key 與版本。 | 排程、日期、頻率、重試、取消與權限由確定性程式控制，LLM 只負責語意理解與自然語言生成。 | 狀態、冪等、排程與取消測試 |  | 待實作 |
| NFR-H01 | 安全／隱私／醫療邊界 | 角色權限與資料隔離 | Wave 1 | MUST SHIP | 全旅程 | 角色權限與資料隔離 | 每筆資料依 elder_id、tenant_id 與角色權限隔離。 | 任一使用者不得透過搜尋、報表或 API 取得其他長者資料。 | 權限、隱私、安全與紅隊測試 |  | 待實作 |
| NFR-H02 | 安全／隱私／醫療邊界 | 傳輸與儲存保護 | Wave 1 | MUST SHIP | 全旅程 | 資料傳輸與儲存 | API 全程使用 HTTPS。 | 主要儲存與必要日誌使用加密機制。 | 權限、隱私、安全與紅隊測試 |  | 待實作 |
| NFR-H03 | 安全／隱私／醫療邊界 | 資料保留、衍生資料與刪除 | Wave 1 | MUST SHIP | 設定與同意 | US-A06、D04 | 分別定義錄音、逐字稿、事件、摘要、記憶、陪伴需求訊號、量表回答、待辦及稽核資料的保存期限。 | 刪除請求同步處理主要儲存、搜尋索引、記憶資料及衍生分析結果。 | 權限、隱私、安全與紅隊測試 |  | 待實作 |
| NFR-H04 | 安全／隱私／醫療邊界 | 醫療安全護欄 | Wave 1 | MUST SHIP | 理解與安全回應 | 所有生成式輸出 | 攔截診斷、停藥、改藥、治療決策及未經驗證的疾病機率描述。 | 不得輸出「已確診重度孤獨」「有百分之多少機率憂鬱」等診斷式內容。 | 權限、隱私、安全與紅隊測試 |  | 待實作 |
| NFR-H05 | 安全／隱私／醫療邊界 | 一般關懷與緊急事件分流 | Wave 1 | MUST SHIP | 覆核與關懷行動 | US-K02、K03 | 一般孤單表達、活動下降與互動變化進入照護者覆核流程。 | 明確即刻危險、跌倒或無法求助等內容進入固定安全指引與人工求助流程。 | 權限、隱私、安全與紅隊測試 |  | 待實作 |
| NFR-H06 | 安全／隱私／醫療邊界 | 展示資料去識別化 | Wave 1 | MUST SHIP | 全旅程 | Demo 資料 | 使用二至三位虛擬 Persona，不使用真實長者個資。 | 音檔、姓名、電話、地址及健康資訊均為模擬或去識別化資料。 | 權限、隱私、安全與紅隊測試 |  | 待實作 |
| NFR-Q01 | 效能／評估門檻 | 語音與頁面效能 | Wave 1 | MUST SHIP | 全旅程 | 語音與頁面效能 | 語音結束至 ASR final：P95 不高於 2.5 秒；ASR timeout 5 秒。 | Agent 產生首段可播放內容：P95 不高於 5 秒；LLM timeout 10 秒。 | P50／P95、失敗率與固定評估集 |  | 待實作 |
| NFR-Q02 | 效能／評估門檻 | Context、Agent 與 Graph 限制 | Wave 1 | MUST SHIP | 理解與安全回應 | Agent、Context、Graph | 每輪最多帶入 8 筆已確認記憶與 12 筆近期事件；超出時依相關性與新鮮度截斷。 | 同一輪最多三個同步 Agent 步驟，超出部分改為非同步，不建立無上限遞迴。 | P50／P95、失敗率與固定評估集 |  | 待實作 |
| NFR-Q03 | 效能／評估門檻 | 背景工作、通知與刪除 | Wave 2–3 | MUST SHIP | 摘要／通知 | US-B02、C03、D04 | 每日摘要在排程後 15 分鐘內完成；失敗最多重試三次，之後進入 dead-letter queue 並告警。 | 家屬通知最多重送三次，使用退避策略；仍失敗時顯示人工處理狀態，不得重複發送成功訊息。 | P50／P95、失敗率與固定評估集 |  | 待實作 |
| NFR-Q04 | 效能／評估門檻 | 評估資料最低門檻 | Wave 1 | MUST SHIP | 全旅程 | 評估與 Demo Gate | Demo 固定測試至少包含 3 位虛擬 Persona、每種核心語言 30 句、正常／噪音／混語／否定／日期人物事件案例。 | ASR 報告至少包含 CER、WER、Key-slot Accuracy、Negation Accuracy、關鍵事件保留率及 final latency。 | P50／P95、失敗率與固定評估集 |  | 待實作 |

## 工作表：05_Demo Traceability

| Requirement ID | 類型 | 命題／交付要求 | 權重／加分 | Product Stories | Enablers／NFR | Demo／文件證據 | 目前狀態 | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CORE-A1 | 必做核心 A | 至少支援中文及臺語之一即時語音對話 |  | US-A01～A03 | TE-VO01；TE-I01；TE-I03 | 現場語音對話＋ASR 報告 | 待實作 |  |
| CORE-A2 | 必做核心 A | 長者以口語互動，無需文字輸入或複雜觸控 |  | US-A01 | NFR-Q01 | 一鍵錄音與語音回覆 | 待實作 |  |
| CORE-A3 | 必做核心 A | 依時間、天氣、過往記憶調整回應 |  | US-A04；US-D03 | TE-J02；TE-GR01～GR02 | 第二輪引用已確認記憶 | 待實作 |  |
| CORE-A4 | 必做核心 A | 不得只是固定腳本式回覆 |  | US-A04 | TE-J01；TE-MA01 | 動態 Context＋生成式回覆 trace | 待實作 |  |
| CORE-B1 | 必做核心 B | 自動擷取飲食、活動、睡眠、用藥等生活資訊 |  | US-B01 | TE-J03 | 結構化事件與來源句 | 待實作 |  |
| CORE-B2 | 必做核心 B | 每日自動生成結構化生活摘要 |  | US-B02 | NFR-Q03 | 排程生成摘要 | 待實作 |  |
| CORE-B3 | 必做核心 B | 摘要供照護人員快速掌握近況 |  | US-B02；US-C02 | NFR-Q01 | 照護者詳情頁 | 待實作 |  |
| CORE-B4 | 必做核心 B | 摘要由 AI 自動歸納，非人工填寫 |  | US-B02 | TE-J01；TE-J03 | 摘要來源 event_id | 待實作 |  |
| CORE-C1 | 必做核心 C | 後台包含長者基本資料 |  | US-C01；US-C02 | NFR-H01 | 多長者概覽 → 點擊林阿嬤 → 長者詳情頁 | 待實作 |  |
| CORE-C2 | 必做核心 C | 後台包含 AI 每日摘要 |  | US-C02；US-B02 | NFR-Q03 | 摘要歷史 | 待實作 |  |
| CORE-C3 | 必做核心 C | 後台包含互動次數 |  | US-C01；US-C02 | TE-J04 | 幸福日照中心的林阿嬤與張阿姨顯示不同今日互動次數 | 待實作 |  |
| ADV-KB | 進階模組 | 知識庫建置與可信衛教回應 |  | US-E01～E04 | TE-G01～G03 | 來源、Chunk、檢索與引用 | 待實作 |  |
| ADV-PUSH | 進階模組 | 定時發布摘要並透過 LINE／Email 通知家屬 |  | US-C03 | TE-PRO01；NFR-Q03 | 家屬 App／Web 先顯示正式摘要，再實際送出一次通知 | 待實作 |  |
| FAMILY-REPORT | 產品能力 | 家屬可在 App／Web 查看每日摘要、週報、月報與歷史重要事件 |  | US-C05 | NFR-H01～H03；NFR-Q03 | Published 報表、歷史列表、資料不足、撤回授權與跨 elder 阻擋 | 待實作 |  |
| ADV-TIMELINE | 進階模組 | 以時間軸檢視每日事件與重要紀錄 |  | US-B04；US-C02 | TE-GR01～GR03 | 事件時間軸＋來源 | 待實作 |  |
| BONUS-LANG | 加分 | 支援客語或原住民族語等本土低資源語言 | 5% | US-A02 | TE-VO01；TE-I02～I03 | 穩定後展示客語語音或文字互動 | Wave 4 |  |
| BONUS-KIRO | 加分 | 使用 Kiro 進行開發或架構設計 | 5% | — | 開發流程與 README 證據 | Kiro 規格／紀錄／畫面 | 待實作 |  |
| PII-1 | 隱私 | 不得使用真實長者個人資料 |  | US-A06 | NFR-H06 | 林阿嬤、張阿姨、陳伯伯三位虛擬 Persona | 待驗證 |  |
| PII-2 | 隱私 | 展示資料為模擬或去識別化資料 |  | US-A06 | NFR-H06 | Demo 資料清單 | 待驗證 |  |
| PII-3 | 隱私 | 說明蒐集、儲存、傳輸加密與存取控制 |  | US-A06 | NFR-H01～H02 | 架構圖＋權限測試 | 待驗證 |  |
| PII-4 | 隱私 | 語音／對話需同意機制與資料保留政策 |  | US-A06；US-D04 | NFR-H03 | 同意畫面＋刪除測試 | 待驗證 |  |
| MED-1 | 醫療邊界 | 僅供生活陪伴與健康資訊參考 |  | US-E03；US-F02 | NFR-H04 | 固定非診斷提示 | 待驗證 |  |
| MED-2 | 醫療邊界 | 不得提供醫療診斷或治療建議 |  | US-F02；US-K02 | NFR-H04～H05 | 紅隊案例攔截 | 待驗證 |  |
| SCORE-30 | 評分 | 完成度與 Demo 體驗 | 30% | Gate 1 薄切片 | NFR-Q01 | 同一情境完整跑通 A／B／C | 核心 Gate |  |
| SCORE-25F | 評分 | 技術可行性 | 25% | US-D02～D03；US-B02 | TE-J01～J04；TE-GR03 | 可重試、可追蹤、可部署 | 核心 Gate |  |
| SCORE-25I | 評分 | AI 記憶、多語言、個人化等創意 | 25% | US-D01～D04；US-N01～N07 | TE-GR01～GR02；TE-VO01 | 確認式記憶＋Graph＋主動陪伴 | 差異化 |  |
| SCORE-20 | 評分 | 社會應用性與真實旅程 | 20% | US-B01～B04；US-C01～C05；US-K01～K03 | NFR-H01～H06 | 長者＋專業照護者＋家屬資訊閉環 | 核心 Gate |  |
| DELIV-1 | 最終交付 | Live Demo：完整使用者情境 |  | Gate 1 薄切片 | TE-J04 | 可重跑的現場情境 | 待完成 |  |
| DELIV-2 | 最終交付 | 生成式 AI 技術與資料應用說明 |  | 全部核心故事 | TE-J01～J05；TE-G01～G04 | 技術說明頁 | 待完成 |  |
| DELIV-3 | 最終交付 | 長者＋專業照護者＋家屬端到端使用者旅程 |  | US-A01→US-C01→US-C02 | — | Persona 文件＋Story Map＋UX Flow | 本文件完成 Story Map |  |
| AUTH-1 | 權限 | 跨 Persona／tenant 資料與介面隔離 |  | US-C01；US-C02；US-D03 | NFR-H01；TE-GR02 | 機構帳號只看林阿嬤／張阿姨；居服員只看有效派案長者；家屬只看已授權報表；跨 elder 查詢被拒絕 | 待驗證 |  |
| DELIV-5 | 最終交付 | AWS 部署架構設計圖 |  | — | 全部 Technical Enablers | 架構圖 | 下一階段 |  |
| DELIV-6 | 最終交付 | GitHub 原始碼與 README |  | — | DoD／Release | Repo、部署與操作說明 | 待完成 |  |
