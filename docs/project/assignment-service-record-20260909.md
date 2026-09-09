# 派案服務紀錄：Core API 第一切片

日期：2026-09-09。分支 `feat/assignment-service-record`，基於 `origin/main` 的 `5e9f142`。
本次是 API／資料層前置實作，供 PR 審查；不是完整 UI、WF-05 或上次服務摘要完成。

## 範圍與規則

依 Spec 06 §6.14、Spec 05 WF-05 與本次 Owner 同意，先保存派案綁定的人工專業紀錄。
DailySummary 是每日資料，不能冒充一次居服紀錄。

- 第一切片僅正式提交 SERVICE_NOTE，內容 1–4000 字元。無 AI 生成、草稿、離線、更正、
  作廢、家屬分享或 Agent context。COMPLETED 表示紀錄提交，不表示派案完成或 Verified Event。
- 僅本人 IN_PROGRESS 且 `service_start <= server_now < service_end` 的指定派案可讀寫。
  比規格「有效或剛完成」更窄；未定義補登寬限，不放寬原有時段授權。
- 日期使用派案開始時間在 Elder.timezone 的日期，跨午夜仍屬同次服務；錯誤 timezone
  拒絕新提交。worker、elder、tenant、日期、狀態與紀錄版本由伺服器決定。
- 一派案僅一筆正式 SERVICE_NOTE，保存 assignment_version，自身 version=1。無覆寫命令。
- 不改既有 assignment complete 指令；紀錄與完成派案的原子整合、UI 與上次服務摘要另行交付。

## API／交易邊界

GET／POST `/api/v1/home-care/assignments/{assignment_id}/service-record`。
POST 必填 Idempotency-Key、expected_assignment_version、content；record_type 僅 SERVICE_NOTE。
GET 需 `assignment:read`＋`service_record:read`，POST 需 `assignment:read`＋`service_record:write`。
兩個 scope 都必須來自同一指定派案，不能借別次服務授權；不自動授予任何既有派案。

每次（含 replay）檢查 actor role/status、assignment tenant/worker/status/time、ACTIVE
Actor／Tenant／Elder／CareUnit，以及有效同角色 membership（含 care-unit 限定）。
不存在、未授權、過期與 legacy-only GET 均 404。先鎖定 assignment，再 claim idempotency，
等鎖後重驗；版本錯誤、不同 payload 重用 key、另一 key 重複提交都 409。

紀錄、idempotency snapshot、`care.service_record.completed.v1` outbox 共用 request transaction，
任一步失敗一起 rollback。事件只含 record/assignment ID、version/status，不含 note。
完成／取消／過期／撤權後，即使原成功 key 也不能取得舊 snapshot content。

## Baseline 與 migration

全套 schema drift 測試發現舊 baseline 已有 service_record 表，最初建表草案已在本機替換，
從未套用 DB。最終 `e3a5c7d9f102` 僅 additive 擴充既有表：

- 保留 JSONB content、worker_actor_id、DRAFT default、created_at／updated_at 與舊欄位。
- 新增 nullable tenant_id／service_timezone／assignment_version／version，不 backfill。
  NULL version 舊紀錄不讀取、不升格；舊 SERVICE_NOTE 阻擋同派案新提交（409），不覆寫。
- v1 JSONB 為 `{ "note": "..." }`，API 明確輸出純文字 content，不透傳 JSONB。
- DB trigger 阻擋 v1 UPDATE／DELETE 與 legacy-to-v1 UPDATE；runtime 僅 SELECT／INSERT。
  存在 v1 資料時 downgrade 拒絕。表數不變：head 67 張。
- Supabase 唯讀 revision 是 d1f3a5c7e9b0；離線 upgrade SQL 已檢查。
  **未對 Supabase upgrade、重建或授權**。需先通過 disposable CI DB，再審閱部署與 grant。
  正式 retention／更正／刪除 fan-out 不在此切片自行定案。

## 驗證與未完成

- Core 全套 `1246 passed`；Core lint、靜態契約與 91-operation live verifier 通過。

- 新 unit 31 個：角色 HTTP 404、不查 DB、scope／時窗、等 claim 後撤權、版本／重複／
  timezone 衝突、server 日期、最小事件及 schema／grant 邊界。
- 新 DB identity 案例 3 個：legacy 隔離、提交／重送／回滾、different-key 並行；包含
  不可覆寫、失效／scope 撤銷、跨 worker／tenant。另新增 migration schema 案例 1 個。
  Identity＋migration 共 60 個案例 collect；沒有獨立 disposable TEST_DATABASE_URL，未執行 DB 測試。
- 靜態 contract、事件範例與 Core live verifier：91 operations、新 GET 無憑證拒絕。
  這不是帶授權 Browser→DB 或 migration 實際執行證據。
- 沒有前端變更，本次不重跑前端 build／Browser QA。原有 14 個 schema dirty files 保留。

下一步：先 CI／migration 驗證，再接紀錄 UI、完成派案整合，最後提供上次已完成派案摘要；
歷史查詢需另定同機構／當前服務授權，不以最近每日摘要猜測服務歸屬。

## PR #38：DB fixture lifecycle 修正

首輪 CI `34308417396` migration 成功，但 integration 為 `164 passed, 2 errors`：
legacy 紀錄測試最後 SELECT 留下交易；test body 的 function loop 與 committed_session
teardown 的 session loop 不同，close／rollback 失敗，未執行 truncate，下一個案例 seed 才主鍵重複。
這不是 migration 或 Supabase 連線故障，aggregate 是正常阻擋失敗 worker。

- committed_session 改成 function loop，專屬 NullPool engine 也在同 loop 建立／釋放。
  identity、care-action、voice、negative-authorization 四個 async seed fixtures 同步對齊。
- 清理順序為 rollback、close、必要時 invalidate，確認釋放後才清理測試表；錯誤不吞掉，
  無法釋放時不冒險執行 truncate；truncate 加 5 秒 lock timeout 防止無限等待。
- 新增 9 個 DB-free cases 與 3 個 PostgreSQL cases：開啟中的 SELECT 交易、固定主鍵隔離、
  body 失敗後清理、清理故障回報，以及相依 fixture loop 的結構回歸。
- 本機 Core 全套 `1255 passed`，Ruff lint／format 通過；全 integration 共 188 cases 已收集，
  實際 DB 驗證交由修正後 CI。
  不新增 retry／skip、不改 production API、migration 或業務授權，也不碰 Supabase 資料。

技術依據：[pytest-asyncio loop_scope](https://pytest-asyncio.readthedocs.io/en/v0.24.0/reference/decorators/)
可獨立於 fixture cache scope 設定；全域 fixture loop 預設不會改變 test body 的 loop。
