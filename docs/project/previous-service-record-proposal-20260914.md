# 上次服務紀錄：第一切片決策提案

日期：2026-09-14。基準：`main` `b20297b`。
狀態：`ACCEPTED`。Owner 於 2026-09-14 回覆 `ok` 核准下列跨居服員交接範圍。
本文保留決策依據；當次實作、驗證與未啟用限制見 [交付紀錄](previous-service-record-20260914.md)。

## 需求與現況

Persona：為陳伯伯提供居家服務的 HOME_CARE_WORKER。
對應 US-C01／US-C02、WF-05 與 NFR-H01：從本人有效派案取得服務所需的上一筆紀錄，降低交接成本。

來源：

- [User Stories：US-C01](../spec/02智慧長照%20AI%20陪伴系統－使用者故事與驗收條件%20v1.3.2.md)
- [Workflow：WF-05](../spec/05智慧長照%20AI%20陪伴系統－核心工作流、狀態機與錯誤恢復%20v0.1.md)
- [Security：逐請求派案授權與資料最小化](../spec/07智慧長照%20AI%20陪伴系統－Security、Privacy、NFR%20與%20Threat%20Model%20v0.1.md)
- [前一切片的待定規則](service-record-completion-20260911.md)

目前 `ServiceRecordService.get()` 僅讀取同派案、同 worker、v1、COMPLETED 的 SERVICE_NOTE，
且須為本人的有效 IN_PROGRESS 派案。紀錄的 COMPLETED 表示已提交，不代表派案完成；
不能把 DailySummary 當成上次服務紀錄，也不能用舊派案的 scope 延長歷史讀取權限。

## Owner 核准的產品範圍

允許接班居服員在本次服務開始後，查看同機構、同據點、同長者上一筆符合條件的人工紀錄，
包含其他居服員留下的紀錄；必須另有明確歷史讀取 scope。顯示標題為「上次服務紀錄」，
內容是有日期及來源的人工原文，不以 AI 改写或推論成摘要。

| 決策面向 | 建議第一版 |
| --- | --- |
| 目前服務入口 | 本人 IN_PROGRESS 且在服務時段內的指定派案 |
| 跨 worker | 允許同 tenant／care unit／elder 的交接，來源不限定本人 |
| 新授權 | 本次派案須同時具 `assignment:read` 與新 `service_record:history:read` |
| 授權來源 | 不由既有 `service_record:read`、`summary:read` 或同長者其他派案推導；既有派案不自動補 scope |
| 展示 | 最近一筆符合條件的人工原文，最多沿用既有 4,000 字限制，附服務日期與來源版本 |
| 開放時間 | 未開始、已完成、已過期、取消或撤權時不提供；無補登／離線存取 |
| 歷史瀏覽 | 第一版只有上一筆，不提供列表、搜尋、總筆數或任意 record ID 讀取 |
| 對外用途 | 僅專業服務交接，不傳入 Agent、Memory、家屬報表或通知 |

未採用僅讀本人來源的替代方案；本次核准涵蓋同機構、同據點、同長者的跨居服員交接。

## 範圍衝突與暫定解讀

WF-05 舊順序把摘要放在開始服務之前；2026-09-09 Owner 的行程預覽決策則明確禁止服務前
取得摘要。本次核准沿用較窄的 IN_PROGRESS＋服務時段 gate。這是第一切片收斂，
不宣稱覆蓋 WF-05 的全部服務前資訊需求。

前一切片明列「跨 worker 交接是否允許須明確定案，不能由現有 service_record:read 自動擴權」。
Owner 已核准跨 worker 規則；Spec 02／05／07 已同步，本次不回填任何既有派案的 scope。

## Domain 與查詢規則

1. 先用共用 `AssignmentAccessService` 重驗本次派案、Actor／Tenant／Elder／CareUnit ACTIVE、
   同角色 live membership、時窗及指定派案的新 scope；Client 只提供本次 assignment ID。
2. 來源紀錄及來源派案須同 tenant、elder，來源派案須同 care unit 且 COMPLETED；
   record.worker 必須對應來源 assignment.worker。只接受正式 v1 SERVICE_NOTE／COMPLETED，
   排除 legacy NULL version、未提交、未完成派案、當次及未來服務。
3. 第一版排除重疊時段：來源 `service_end <= current.service_start`，
   紀錄 `completed_at < current.service_start`；不把 record.completed_at 冒充派案完成時間。
   依來源 service_end、service_start、record.completed_at、record ID 依序降冪，固定取一筆。
   時間比較用 UTC，顯示使用紀錄保存的 service_date／service_timezone。
4. 不新增摘要表或寫入 projection。完整人工紀錄 retention／刪除流程尚未定案，
   第一版使用既有 gate 保守排除：同 tenant／elder 的任何非 CANCELLED deletion request、
   或以 elder ID／subject hash 命中的 tombstone，都讓歷史結果為空，包括已完成請求與 legal hold。
   不因 request.scope 較窄、marker 到期或 v1 row 保留而恢復交接，不改寫保存期限。
   紀錄完成時間還須在來源服務時段內，且其 assignment_version 小於來源已完成派案版本。
5. 已授權但沒有符合條件的紀錄：正常 envelope 回空結果；不存在／無權的本次派案統一 404。
   空結果不透露排除原因或其他資料是否存在；未授權請求不查詢來源內容。

已實作 API：
`GET /api/v1/home-care/assignments/{assignment_id}/previous-service-record`。
回應只包含所需來源 ID／version、服務日期／時區與人工內容；不回傳作者帳號、聯絡資料、
tenant 或不必要的來源派案 scopes。不提供繞過本次派案 gate 的歷史連結。

## 前端與驗收

在既有 `/staff/assignments` 派案卡提供按需展開入口，避免首頁批次預取全文。
使用既有 staff layout、CSS Modules、tokens 與 zh-Hant／en；記錄僅保留於目前元件記憶體，
不使用 localStorage、離線 cache 或 service worker 儲存；HTTP／BFF 回應禁止快取。

完成派案、服務時段結束、切換派案或登出時清除；401／403／404 清除內容並重驗當前派案。
分頁隱藏時清除，回到分頁須重新授權取用；新請求的回應不能被先前延遲回應覆蓋。
不要宣稱沒有撤權推播時能即時得知伺服器端變更；下一次請求必須拒絕，既有畫面須有有限
重驗機制與可測試的到期清除行為。

| Test Gate | 必須驗證 |
| --- | --- |
| 正常交接 | 同據點跨 worker、本人來源、固定排序、跨午夜及時區、空結果 |
| 授權隔離 | 跨 tenant／elder／care unit、非本人當次派案、角色或 membership 失效、缺新 scope、借別次派案 scope |
| 來源隔離 | legacy、未完成／取消來源派案、重疊／未來服務、來源欄位不一致、退場資料 |
| 時間與狀態 | 尚未開始、過期、完成、撤權、等鎖後時窗失效；無權與不存在回應一致 |
| HTTP／Contract | strict schema、無憑證／拒絕 HTTP 回歸、空結果、最小回應、快取與敏感 log |
| Frontend | loading／empty／error、access loss 清除、延遲回應丟棄、到期、重驗、keyboard、雙語與 375／390／430 px |
| DB integration | CI disposable PostgreSQL 上驗證真正 join／scope／排序；Supabase development 不做 fixture rebuild |

## 實作與交付順序

1. 將 Owner 決策與例外寫入 Spec 02／05／07 及 traceability；對齊 retention gate。
2. 從最新 origin/main 建新分支，完成 Core scope、bounded repository query、service 與 HTTP 回歸。
3. 實作後才更新 executable contracts／examples／static 與 live verifier；按實際查詢需求評估 additive index，
   不先宣稱一定無 migration，也不改已套用 migration。
4. 接入現有派案 UI，完成 synthetic Browser QA 與安全負向測試；跑受影響元件及 CI impact tests。
5. PR／disposable DB CI 通過後結案。development scope grant、真實登入交接 E2E 與 production
   activation 另列實際證據，不用 synthetic 測試代替。

Owner 核准後已實作程式與契約；沒有寫入 development database 或授予任何派案 scope。
是否通過 CI、Browser QA 及尚未解除的 activation 邊界，以交付紀錄的當次證據為準。
