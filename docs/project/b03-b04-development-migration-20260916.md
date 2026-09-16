# B03／B04 開發資料庫升級 — 2026-09-16

## 結果

Owner 授權後，已將 Supabase development 從 `e3a5c7d9f102` 依序升級至
`f4b6d8e0a213`、`a5c7e9f1b324`。新版 Core 已從獨立 worktree 啟動，
`/ready` 回覆 200 且 `database=connected`。

程式基準為 main `eb8d4c4dbfc3650946a6e61779afb7fe2de5f7c4`。本次是開發 schema
升級與本機 runtime 驗證，不是 production 部署或 B03／B04 UI 驗收。

## Migration 審查與驗證

先以唯讀交易查詢 revision、欄位、約束及既有資料摘要，人工審查兩支 migration 與
`e3a5c7d9f102:a5c7e9f1b324` offline SQL，再以 Alembic upgrade 至固定 target。
已確認指定區間只有兩支 migration，graph 為單一 head。Connect timeout 15 秒、
lock timeout 5 秒、statement timeout 60 秒。

| 檢查 | 實際結果 |
| --- | --- |
| 升級前 | revision `e3a5c7d9f102`；新欄位與約束不存在 |
| 升級後 | revision `a5c7e9f1b324` |
| B03 review_decision | before／after_event_type：nullable VARCHAR(64)；before／after_event_time：nullable TIMESTAMPTZ |
| B03 約束 | `ck_review_event_metadata_pair` 定義符合 migration，convalidated=true |
| B04 care_event | source_type：nullable VARCHAR(32) |
| B04 約束 | `ck_care_event_source_type` 定義符合 migration，convalidated=true |
| 筆數 | care_event 10 筆、review_decision 1 筆，升級前後一致 |
| 內容 | 每筆排除新增欄位後計算並排序彙總指紋，兩表前後完全相同；不輸出原文或 row ID |
| 新欄位歷史值 | 兩表新增 metadata 非 NULL 筆數皆為 0，沒有 backfill |

未執行 downgrade、reset、fixture、業務資料寫入或角色／grant 調整。設定只在 process
內載入，沒有複製 `.env` 到獨立 worktree 或寫入版控。既有 `.env` 解析器回報第 3 行
無法解析；必要設定成功載入，Core Settings 與 DB readiness 通過，未修改設定檔。
所用 connection 對兩表具有 privileged access；本次不構成 runtime least-privilege 驗收。

## 新版 Core

- Worktree：`D:/Hackthon/kinsun-backend`；啟動前確認 8000 埠可用。
- 只啟動 Core，綁定 `127.0.0.1:8000`，FAKE_AUTH_ENABLED=false。
- `/health`：200，status=ok；`/ready`：200，status=ready、database=connected。
- OpenAPI：事件清單含 source_type 的 MANUAL／CONVERSATION_SESSION／UNKNOWN；
  ReviewCareEventRequest 含 corrected_event_type、corrected_event_time。
- 未帶憑證的事件清單 GET（附 MANUAL 篩選）：401。
- 啟動當下 PID 32452；logs 為 `.qa/b03-b04-core.stdout.log` 與
  `.qa/b03-b04-core.stderr.log`，不納入版控。PID 不保證後續仍相同。

## 後續與界線

另一個 frontend session 正在 `feat/b03-b04-event-frontend` 接 UI；本次未修改該
worktree 的檔案、分支或既有服務。共用資料庫的 schema 升級已生效，新欄位可空且未回填。

下一步為 UI 接線完成後，以真實登入驗證類型／時間修正、清除時間、版本衝突、來源篩選
與切換條件後分頁重置，再處理 B02 摘要來源回查／修正後重建驗收。
本次未執行登入後寫入、Browser E2E、全套 unit 或 DB integration。既有 CI 與功能細節見
[B03 交付紀錄](b03-event-metadata-correction-20260915.md)及
[B04 交付紀錄](b04-event-source-filter-20260915.md)。

本次文件驗證：diff whitespace 與四份文件的相對連結通過；CI rules 26 passed、
65 subtests passed。首次以 Core venv 收集 CI rules 因缺少 PyYAML 失敗，改用
`uv run --with pytest --with pyyaml python -m pytest scripts/ci -q` 後通過，未改動專案依賴。
