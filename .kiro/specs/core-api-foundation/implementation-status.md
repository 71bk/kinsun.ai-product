# Core API Foundation：實作與證據狀態

本目錄保存的是實際透過 Kiro Requirements-First workflow 產生並執行的歷史 Spec。
`requirements.md`、`design.md`、`tasks.md` 與 `tasks.meta.json` 保留原始內容，作為開發過程證據；
它們不是目前 `main` 的最新規格來源。

## Provenance

| 階段 | Commit | 說明 |
| --- | --- | --- |
| 建立 Spec 與 Steering | `65138c3` | 建立 requirements、design、tasks 與專案 Steering |
| 開始執行 Kiro Task | `7dd698c` | 初始化 Core API，開始寫入 task execution metadata |
| 完成 Foundation | `d9e168d` | 完成歷史 task 清單並保留 execution history |
| 整合至 main | `0e21a75` | 將應用層、測試與 contract 改接 `eldercare_ai` baseline |

`tasks.meta.json` 目前保存 120 筆 execution 與 120 筆對應的 chat session 關聯紀錄。
它只保存識別碼、時間與測試結果 metadata，不保存 Secret、Token 或對話逐字內容。

## 與目前 main 的重要差異

- 目前套件與環境管理採 `uv`，`pyproject.toml` 使用受控版本範圍，不採歷史 Spec 的全部
  `==` 精確釘版要求。
- 目前 `services/core-api` 設定為 `package = false`，不以 `pip install -e .` 作為完成條件。
- 資料庫權威來源是 48 張表的 `eldercare_ai` Alembic baseline，不是歷史 Spec 原先設計的
  小型獨立 schema。
- 應用層使用 asyncpg；Alembic 刻意使用同步 psycopg。兩者共用一份 asyncpg 形式的
  `DATABASE_URL`，由 `alembic/env.py` 轉換 driver。
- ORM 的 Python 主鍵屬性統一為 `id`，實際資料庫欄位由各 model 的 `__pk_name__` 對應。
- 現階段不得直接使用 `alembic revision --autogenerate`；baseline 尚未被所有 ORM model
  完整覆蓋，產物可能誤刪未映射資料表。
- 歷史 `tasks.md` 的完成勾選只代表當時分支的 Kiro 執行狀態，不等於目前 main 的所有
  整合測試都已通過。

## 目前規格來源

後續工作應依 repository 根目錄的 `AGENTS.md`、`docs/`、`contracts/`、ADR 與目前程式碼為準。
若本歷史 Spec 與上述來源衝突，必須採用目前來源，並在新的 Kiro Spec 中記錄差異。

## 使用限制

- 不要重新執行本目錄已完成的歷史 tasks。
- 不要為了讓歷史 requirements 符合現況而改寫原始三份 Spec artifact。
- 新功能請建立新的 `.kiro/specs/<feature-name>/`，並只在實際完成驗證後勾選 task。
