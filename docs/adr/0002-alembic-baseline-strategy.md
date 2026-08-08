# ADR 0002：以凍結的 SQL 快照作為 Alembic baseline

- 狀態：Accepted
- 日期：2026-07-30
- 決策者：專案 Owner
- 相關文件：06｜Domain Model v0.1；13｜Database Migration、Release 與 Rollback v0.1
- 相關：[ADR 0001](0001-package-manager-uv.md)

## 背景

`docs/project/smart_eldercare_schema_v0_1.sql` 是手寫的完整 schema：48 張表、10 個 ENUM、
54 個 index、131 個 FK、46 個 trigger，以及每張表、每個欄位的中文 `COMMENT ON`。
該檔案自身第 4 行即建議「作為一次性初始化或 Alembic baseline」。

需要把它納入 Alembic 版本控制，並滿足文件 13 §六.6：CI 必須能在臨時 PostgreSQL 上
從零執行 migration。

注意：檔名是 `smart_eldercare_schema_v0_1`，但其建立的 **PostgreSQL schema 名稱是
`eldercare_ai`**。全專案以 `eldercare_ai` 為準。

## 候選方案

| 方案 | 優點 | 缺點 |
| --- | --- | --- |
| **凍結 SQL 快照** | 48 表／trigger／COMMENT 逐位元保留；`upgrade head` 可從空 DB 重建；工作量最小 | 無 SQLAlchemy models，`--autogenerate` 不可用 |
| 反推 SQLAlchemy models | 之後可用 `--autogenerate`；models 可供 ORM 直接使用 | 工作量大；trigger、function、COMMENT 是 autogenerate 抓不到的，容易在轉譯中遺失 |
| 手動建表後 `alembic stamp head` | 最快 | CI 無法從空 DB 驗證，違反文件 13 §六.6 |

## 決策

採用**凍結 SQL 快照**。

- 快照位置：`services/core-api/alembic/versions/sql/20260730_1502_baseline_eldercare_ai_schema_v0_1.sql`
- 內容與 `docs/project/smart_eldercare_schema_v0_1.sql` 逐位元相同
  （SHA-256 `2ed62d87…87def`）。
- migration `f393b4452ce8` 在執行前驗證該 SHA-256，不符即中止。
  已套用的 migration 必須不可變；schema 要改就新增 revision。

### 實作細節

三個不明顯但必要的處理：

1. **交易控制**：快照最外層的 `BEGIN;` / `COMMIT;` 會在執行前被移除，交易交給 Alembic 管。
   若保留 `COMMIT;`，Alembic 會在寫入 `alembic_version` 之前就把交易提交掉。
   移除只針對「整行且帶分號」的那兩行，`DO $$` 與 plpgsql 函式內的 15 個裸 `BEGIN` 不受影響。

2. **不能用 `op.execute()`**：它會帶一組空參數進 psycopg，psycopg 便將語句視為含
   placeholder 來解析，於是 plpgsql `RAISE EXCEPTION 'Table %.%'` 裡的 `%` 會被判為
   非法 placeholder。改用原生 psycopg cursor（`cursor.execute(sql)`，不帶 params），
   psycopg 原樣送出並使用 simple query protocol，一次多語句也可行。
   把 `%` 改寫成 `%%` 雖然也能過，但那會動到快照內容，與 SHA-256 驗證的用意相衝突。

3. **`alembic_version` 放在 `public`**：baseline 的 downgrade 是
   `DROP SCHEMA eldercare_ai CASCADE`，版本表若放在同一個 schema 會被一併刪除，
   Alembic 將無法得知自己的版本。

## 影響

- **`alembic revision --autogenerate` 目前不可用。** 後續 revision 需手寫
  `op.execute()` 或 `op.create_table()`。`env.py` 的 `target_metadata` 已預留，
  日後補上 models 即可啟用。
- 文件 8 §八要求 Database 變更採 Expand → Migrate → Contract，此原則對後續 revision 仍然適用。
- `docs/project/smart_eldercare_schema_v0_1.sql` 保留為設計產出物與 ER 圖匯入來源；
  **實際套用到資料庫的權威版本是 versions/sql/ 底下的快照**。
  兩者若要同步更新，必須連帶更新 migration 內的 `EXPECTED_SHA256`，
  且僅限於「這個 baseline 尚未被任何環境套用」的情況。

## 驗證紀錄（2026-07-30，本機 PostgreSQL 16.14）

- `alembic upgrade head` → 48 tables、10 enums、127 indexes、131 FK、46 triggers、48 table comments，中文 COMMENT 完整。
- `alembic downgrade base` → schema 與 `alembic_version` 皆清空。
- 於乾淨的 `kinsun_test` 從零 `upgrade head` → 48 tables（對應文件 13 §六.6 的 CI 情境）。
- 竄改快照後 `upgrade head` → 依 SHA-256 檢查中止。
- `docker compose run --rm migrate` → 於容器內套用成功。
