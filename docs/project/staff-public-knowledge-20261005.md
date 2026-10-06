# 專業公開長照知識入口

2026-10-05。PR #70 的 10 項 CI 通過後已合併，工作分支從最新 main `01165c3` 建立。

## 入口與權限

`/staff/knowledge` 提供長照服務、申請資訊及法規問答，沿用 care 設計 tokens 與專業側欄／手機導覽。
`POST /api/v1/staff/knowledge/questions` 限 ACTIVE `DAYCARE_CARE_WORKER`、`HOME_CARE_WORKER`。
ADMIN、FAMILY_MEMBER、ELDER 均拒絕；角色由既有 session authenticator 取得，不能由輸入指定。
公開知識入口不需要選取長輩、派案或照護單位，不查詢或放寬任何個人照護資料的權限。

Core 固定 `care_professional` 受眾。輸入僅接受 question 與 language，拒絕額外 audience、purpose、
actor、elder、tenant、session 等欄位。依既有 router 決定 general_information 或 legal_reference，
後者沿用 V3 的現行法規與安全准入；不新增用途、不改來源審核、內容 hash、風險或 PDF 版面規則。
個人紀錄／停止查詢走固定 fallback；其他問題經原有檢索、生成與安全 gate，不儲存對話或寫照護事件。
既有 `KNOWLEDGE_ROUTER_V2_ENABLED` 及 Agent V3 開關仍生效，production 不開放。

## 共用實作

抽出 PublicKnowledge DTO、注入式 service、前端 client 與 KnowledgePage。家屬保留原 API／型別相容名稱，
並透過固定 family_caregiver 的 wrapper 呼叫共用 service；家屬與專業角色不能互用對方 endpoint。
JSON Schema 的 PublicKnowledge 名稱以 `$ref` 重用已發布形狀，避免維護兩份同義約束。
官方引用、最小輸出、固定 fallback、逾時／大小限制、取消行為與 family raw-payload redline guard 保留。
專業公開入口也拒絕 private record 欄位，不將其當成讀取個案資料的通道。

共用 UI 保留六種回應狀態、雙語說明、官方來源、unknown 現行性提醒及 AI 核對提示。
專業頁使用獨立權限提示與法規問題範例；手機導覽依文字大小換列，側欄沿用現有版型。

## 驗證

本機單工、BelowNormal：後端與架構回歸 74 項、前端相關 83 項、Typecheck、定向 ESLint、
Core Ruff lint／format、靜態 contracts、28 項 CI 規則（74 subtests）通過。
live contract verifier 同時檢查家屬／專業匿名拒絕與各六種合成回應，完整執行交給 CI 的隔離 DB。
Production build 通過；Playwright 專業頁 34 組、家屬回歸 34 組通過，涵蓋中文
375／390／430／768／1024／1440、英文 390／768、390 英文 200% 字級與 reduced motion。
六種狀態、載入／錯誤／無權限、官方來源連結、48px 點擊範圍及無水平溢出均已驗證；
另目視檢查手機、平板、桌面及放大字級截圖。最後共用 schema 匯入調整後，61 項邊界／架構測試再通過。

真實本機 BFF → Core → Agent，使用合成 demo 帳號：匿名 401、長者／家屬 404、偽造
scope 422、CSRF 403 通過。申請問題回 ANSWER／2 個官方來源；未來額度、個人紀錄回
NO_DATA，停藥問題回 BLOCKED；三種帳號均已登出。

初次「長照法第二條如何定義長期照顧服務？」回 NO_DATA，未達原先預期 ANSWER，
瀏覽器初測也未取得答案；保留此失敗，不計為全綠 smoke。僅輸出固定狀態碼的診斷確認為
GROUNDED_INSUFFICIENT，並非逾時或服務失敗。直接查詢「長照法第二條」回 SUCCESS／
GROUNDED_ANSWER，真實瀏覽器重驗取得 ANSWER／1 個官方來源，390px 無溢出。
原範例預設第二條包含服務定義，已改為中性法條查詢；沒有放寬證據門檻或修改資料以強迫回答。

合成測試與回答成功不代表知識語意準確率或人工覆核。日照角色以 API 單元測試驗證，
真實帳號瀏覽器驗收使用既有居服 demo；不宣稱兩種角色都已完成真實登入驗收。

本批不包含 55 筆版面來源修復、新資料匯入、個人資料查詢、診斷／個案資格判定或 production 啟用。
