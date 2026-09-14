# 上次服務紀錄：人工交接第一切片

日期：2026-09-14。基準：`main` `b20297b`，分支 `feat/previous-service-record`。
Owner 已核准[決策範圍](previous-service-record-proposal-20260914.md)。
狀態：PR #44 已合併為 `4556e57`，main CI `34813366993` 成功；本機 real-auth 驗收已補齊，未部署。
程式驗證基準：`f4b2847`，CI run `34811244713`；後續文件收尾不改動此程式基準。

## 行為與授權

US-C01／US-C02／WF-05／NFR-H01：居服員開始服務後，可按需展開「上次服務紀錄」，
查看同機構、據點、長者最近一筆符合條件的人工原文，包含其他居服員留下的內容。
僅顯示保存的日期、時區、版本及原文，不以 AI 或 Daily Summary 改寫。

`GET /api/v1/home-care/assignments/{assignment_id}/previous-service-record` 只接受本次派案 ID。
Core 共用 `AssignmentAccessService`，在讀取前後重驗本次本人 IN_PROGRESS 派案、服務時窗、
active Actor／Tenant／Elder／CareUnit 與 live HOME_CARE_WORKER membership，須同時具
`assignment:read`／`service_record:history:read`。scope 不能從其他派案、舊派案、
`service_record:read` 或 `summary:read` 借用；既有派案不自動加權限。
派案鎖取得後才檢查目前時間。無權及不存在均回 404，且無權時不查詢來源內容。

來源必須同 tenant／elder，來源派案須同 care unit、COMPLETED 且非當次。
只接受 SERVICE_NOTE／COMPLETED／version 1、作者與來源派案 worker 一致，
`1 <= record.assignment_version < source.version`；排除 legacy。
來源 `service_end <= current.service_start`，紀錄完成時間在來源時窗內且早於當次開始。
依來源 service_end、service_start、record.completed_at、record UUID 依序降冪 LIMIT 1；
沒有歷史列表、搜尋、總筆數或繞過本次 gate 的來源連結。
`completed_at` 是紀錄提交時間，不是派案完成時間；日期使用紀錄保存的 local day。

任何同 tenant／elder 非 CANCELLED deletion request，或以 elder ID／subject hash 命中的
tombstone 都讓結果為空，不揭露排除原因。包括已完成刪除、較窄 request.scope 及 legal hold；
不因 marker 到期或保留 row 恢復使用。這是完整人工紀錄 retention／刪除流程未定案前的
保守讀取限制，不設定永久保存、也不延長保存期限。

沒有合格來源回 canonical envelope `data: { assignment_id, record: null }`；正常來源只包含
record ID、source assignment ID、日期／時區、completed_at、version、content，strict schema
拒絕多餘作者或 tenant 欄位。HTTP／BFF no-store，不產生 Domain 寫入或 Outbox。
既有索引及表足以支援此有界查詢，本次無 migration；未做 production 資料量 query-plan 壓測。

## 前端生命週期

沿用 `/staff/assignments` 卡片與 CSS Modules、雙語。僅點擊後讀取，內容只存於元件記憶體。
關閉、分頁隱藏、到期、登出、卡片卸載及 401／403／404 後清除；拒絕後重驗派案列表。
展開時每 30 秒及回到前景重查，先清掉舊內容；錯誤提供重試，延遲回應由 request sequence／
AbortController 丟棄。沒有撤權推播：伺服器撤權後下一請求拒絕，畫面依輪詢／前景重驗收斂。
完成服務時隨卡片移除結束存取；不使用 localStorage、離線 cache、Agent 或家屬分享。

## 當次驗證

| Gate | 結果 |
| --- | --- |
| Core unit | 1,375 passed |
| Core Ruff check／format | 通過，415 files already formatted |
| Frontend 全套 | 本機 571 passed＋最後相關 38 passed；修正後 CI 全套 572 passed |
| Frontend lint／typecheck | 通過（測試 cleanup 回傳型別修正後） |
| Static contracts | all contract checks passed |
| Core live contract | all live contract checks passed，93 operations；Supabase readiness 僅 SELECT 1 |
| Frontend production build／Browser QA | 通過；14 組 viewport／state，截圖與 DOM 檢查完成 |
| CI impact／instrumentation | 26 passed |
| DB gate | CI 20 migration／204 integration passed，包含新增 27 cases；本機不對 Supabase rebuild |
| PR CI | [PR #44](https://github.com/71bk/kinsun.ai-product/pull/44)；[run 34811244713](https://github.com/71bk/kinsun.ai-product/actions/runs/34811244713) 全部 10 jobs success |
| 其他 CI workers | Agent 538、Speech 91、RAG 328 passed；三支契約 verifier 與五輪 synthetic cross-service 通過 |

Core 單元涵蓋角色、scope、時窗、無權時零查詢、讀取後再授權、最小／空回應及 HTTP gate。
DB integration 驗證真正 join、同／跨 worker、固定排序、local day、跨 tenant／elder／unit、
來源欄位／版本／時窗不符、當次失效及不得借其他派案 scope、退場資料。
前端測試涵蓋按需讀取、雙語、空結果、重試、拒絕清除、分頁隱藏、到期與延遲回應。

## Synthetic Browser QA

使用本機 production build，所有 auth／Core 回應皆為合成 fixture，無真實資料寫入。
腳本 `.qa/previous-record-browser.js`；截圖 `.qa/previous-record-{locale}-{width}-{state}.png`。
繁中人工原文：375／390／430／768／1440；英文：390／768。
英文 390 另驗 empty、error→retry、loading→loaded、denied、noScope、keyboard、reduced motion。
14 張截圖均已逐張檢視；長英文無空格字串正常換行，日期／時區／版本完整，鍵盤 focus ring 可見。
所有 `scrollWidth == clientWidth`；本機 browser 的 innerWidth 為請求手機寬度＋1 px，
768／1440 則完全一致，clientWidth 另扣 15 px scrollbar，未以 CLI window size 冒充 viewport。
無 scope 0 次歷史請求；其餘按需 1 次，錯誤重試共 2 次；關閉後內容清除、404 後卡片移除。
初次腳本將拒絕畫面誤預期為「當日沒有派案」，實際符合既有「Content is unavailable」流程；
修正測試預期後全套重跑通過，無產品 layout bug。沒有真機／真人滾動或 Lighthouse 證據。

Contract exporter 曾重排既有 paths 並移除人工描述；最終僅加入新 operation（54 行），
程式化比較確認原有 contract 語意與文字保留，重新 static validation 通過。
此專案地雷已同步 AGENTS.md／CLAUDE.md。

首輪 DB CI 的 membership 過期案例只把新 fixture 的 effective_to 設成 now−1 秒，
早於預設 effective_from，先被 `ck_membership_period` 擋下，尚未走到 HTTP 授權。
已改為明確的合法過去期間，保留原本的 404／不可借用其他派案 scope 斷言；沒有修改產品邏輯
或資料庫約束。此 fixture 地雷亦補入 AGENTS.md／CLAUDE.md，失敗 run 34810612170 保留供追溯；
修正後 run 34811244713 的 204 integration 與完整 aggregate 已全部通過。

## 尚未驗證與啟用邊界

同日已在全新隔離 synthetic campaign 授予最長四小時 scope，完成 real-auth 跨 worker
Browser → BFF → Core → DB 交接、UI 提交並完成與撤權清除；測試授權及憑證已全部撤銷。
詳見 [real-auth 驗收](previous-service-record-real-auth-20260914.md)。沒有 production activation、
真機測試或效能保證。完整 retention／note deletion 與 runtime
least-privilege activation 仍須後續工作；本切片不等於完整 US-C01 或 Wave 2 完成。
本次保留其他既有工作樹變更與 .qa artifacts；沒有 reset 或既有資料回填。
原切片的 synthetic QA 沒有外部寫入；後續 real-auth campaign 的 development 寫入另按上述報告核對。
