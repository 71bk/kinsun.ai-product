# B04 事件來源篩選 — 2026-09-15

## 交付範圍

來源篩選接入既有事件清單，不增加來源內容讀取權限。HTTP 範例：

```text
GET /api/v1/elders/{elder_id}/care-events?source_type=MANUAL&event_type=MEAL&date_from=2026-08-01&date_to=2026-08-01
```

| source_type | 判定 |
| --- | --- |
| 省略 | 所有來源，維持舊查詢行為 |
| MANUAL | care_event.source_type 明確保存 MANUAL |
| CONVERSATION_SESSION | source_session_id 非 NULL，包含既有歷史事件 |
| UNKNOWN | source_type 與 source_session_id 均 NULL；不猜測人工來源 |

只有以上三個大寫值可用，其他值回 422。來源、日期、類型與狀態在 SQL LIMIT 前套用；
排序／cursor 仍使用 created_at＋event_id，不改成事件發生時間。Client 更換任何條件時
應重新由第一頁查詢。預設只讀 VERIFIED／CORRECTED；待審等非正式狀態仍要求 review scope，
DELETED 不回傳，每頁都重新授權。查詢不 join 內容版本，不因多個版本而重複事件。

新事件透過既有 create command 的 source_type 保存來源；CORRECT 不改寫來源。
建立請求、回應與 outbox 形狀不变。此切片未增加 response 的 source_type 或原始 session 內容，
前端可沿用原 client；前端新增 filter/BFF 接線另行處理。

## Migration 與分支順序

- Worktree `D:/Hackthon/kinsun-backend`，分支 `feat/b04-event-source-filter`。
- 由最新 origin/main `b01c2a9` 建立分支後，以 fast-forward 納入已通過 CI 的 B03
  `d4102b7`，讓來源 migration 接續同一條 revision chain。
- CI 只接受以 main 為 base 的 PR，因此本次 draft PR 先以 main 為 base，明確標示依賴
  PR #48；[B04 專屬差異](https://github.com/71bk/kinsun.ai-product/compare/feat/wave2-backend...feat/b04-event-source-filter)
  以 B03 分支比較。先合併 B03 PR #48，再將 B04 整理至最新 main 並重驗單一 head／CI；
  不可跳過 dependency 直接套 source migration。
- Additive migration `a5c7e9f1b324`（down_revision `f4b6d8e0a213`）新增 nullable
  `care_event.source_type` 與來源一致性 check。未知只以 NULL 保存；MANUAL 不可有 session，
  CONVERSATION_SESSION 必須有 session，其他非 NULL 值拒絕。
- 不回填歷史資料。舊版 Core 在 migration 後仍可寫入 NULL；帶 session 者仍屬對話來源，
  舊版寫入且沒有 session 的事件為 UNKNOWN。新版本開始記錄的 MANUAL 才列入人工來源。
- **先 migration，再啟動新版 Core**；runtime 原有 care_event grant 可涵蓋新欄位。
  回退應用可保留新欄位；DB downgrade 會丟失明確來源，只在 disposable DB 驗證。
- 原前端 worktree、分支、服務與 Supabase 都未變動，未啟動本機 DB／Docker。

## 驗證紀錄

| 檢查 | 狀態 |
| --- | --- |
| 來源／既有事件 API targeted unit | 15 passed（新增 7） |
| 完整 Core unit | 1,437 passed |
| Core Ruff lint／format | 通過 |
| Static contracts／CI rules | 通過；CI rules 26 passed |
| PostgreSQL／migration lifecycle | 本機 collect-only，待 PR disposable PostgreSQL CI |

新增 17 個 DB cases：混合來源、日期／類型／status 交集、同 timestamp 的 UUID 分頁、
跨 elder／tenant／角色拒絕、review scope 失效、派案過期 cursor 拒絕、未知 filter 422、
create→CORRECT 後來源保留，以及每日摘要生成／重建兩次後 timeline identity 不變。
Migration regression 保存一筆舊 row，確認新增欄位仍 NULL、錯誤來源被 check 拒絕，
並執行 B03 head→B04 head→B03 head→head 的生命週期。

上述資料全部 synthetic；身分注入，交易／授權／SQL 為真實 PostgreSQL。這不是 Browser、
真實登入或部署驗收。B04 的前端操作、完整來源／摘要／修正歷史導覽與匯出仍待後續切片。
