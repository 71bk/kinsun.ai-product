# ADR 0003：Core API 採 FastAPI，並以 eldercare_ai baseline 為 schema 權威

- 狀態：Accepted
- 日期：2026-07-31
- 決策者：專案 Owner
- 相關文件：06｜Domain Model v0.1；08｜AWS 系統架構 v0.1；13｜Database Migration v0.1
- 相關：[ADR 0001](0001-package-manager-uv.md)、[ADR 0002](0002-alembic-baseline-strategy.md)
- 取代：AGENTS.md §11 之「Python Backend Framework」待決事項
- 實作 commit：`0e21a75`（改接前的還原點為 `e40a88b`）

## 背景

`feature/core-domain-security` 分支獨立實作了一套 Core API 基礎：FastAPI + SQLAlchemy 2.0
async + asyncpg，含 Elder 授權 policy、tenant 隔離 repository 層、transactional outbox
與 294 個單元測試。

該分支同時自帶一套 9 張表的 schema（`public`、複數表名、Alembic revision 0001–0003），
與 main 上已建立的 48 張表 baseline（`eldercare_ai`、單數表名、revision `f393b4452ce8`）
互不相容。兩者的 `alembic_version` 也無法共存。

## 決策

### 1. Python Backend Framework 採 FastAPI

文件 13 §3.1 原本保留 FastAPI／SQLAlchemy 與 Django 兩條路線。分支已用 FastAPI 完成
可運作的實作與測試，且 ADR 0001 選定的 Alembic 本就屬 SQLAlchemy 路線。維持 FastAPI。

### 2. eldercare_ai baseline 是唯一 schema 權威

48 張表的 baseline 勝出，理由：

- 對應文件 06 的 Domain Model，分支那 9 張是子集。
- 具備完整 FK、CHECK、trigger 與逐欄中文 COMMENT。
- 分支的 001–003 migration 作廢，不併入 main。

分支的 `app/` 與 `tests/` 改接到 baseline，做法見下節。

### 3. 兩個 PostgreSQL driver 並存

- `psycopg`（同步）：Alembic migration。
- `asyncpg`（非同步）：FastAPI 應用層。

統一成 psycopg 可行（它也支援 async），但應用層與全部測試都以 asyncpg 寫成，
為了單一 driver 去改動已驗證的授權測試不划算。專案只維護一個 `DATABASE_URL`，
以 asyncpg 形式撰寫，`alembic/env.py` 自行換成 psycopg。

## 改接方式

### PK 欄位命名

baseline 每張表的 PK 各自命名（`actor.actor_id`、`elder.elder_id`），分支程式碼則假設
統一的 `id`。解法是讓 Python 屬性維持 `id`、對應到各表實際的 PK 欄位：每個 model 宣告
`__pk_name__`，`BaseModel` 以 `declared_attr` 把 `id` 映射過去。應用層程式碼一行未改。

### 表名對應

| 分支 | baseline |
| --- | --- |
| `actors` | `eldercare_ai.actor` |
| `tenants` | `eldercare_ai.tenant` |
| `elders` | `eldercare_ai.elder` |
| `care_units` | `eldercare_ai.care_unit` |
| `care_relationships` | `eldercare_ai.care_relationship` |
| `care_assignments` | `eldercare_ai.care_assignment` |
| `tenant_memberships` ＋ `care_unit_memberships` | `eldercare_ai.actor_tenant_membership` |
| `outbox` | `eldercare_ai.outbox_event` |

### Membership 合併

baseline 用單一 `actor_tenant_membership` 表，以 `care_unit_id` 是否為 NULL 區分
「租戶層成員」與「限縮到照護單位的成員」。分支拆成兩張表，兩個 ORM class 無法乾淨地
映射同一張表，因此合併為 `ActorTenantMembership`。
`TenantMembershipRepository` 與 `CareUnitMembershipRepository` 兩個類別保留，
各自加不同述詞查同一個 model，policy 層不受影響。

### 語彙對齊

分支的 enum 有三處與 baseline 不符，一律以 baseline 為準：

| 項目 | 分支 | baseline |
| --- | --- | --- |
| `AssignmentStatus` 初始狀態 | `SCHEDULED` | `DRAFT` |
| `PrimaryCareSetting` | 有 `BOTH` | `DAYCARE`／`COMMUNITY`／`HOME_CARE`／`INDEPENDENT` |
| `ActorType` | 有 `LEGAL_REPRESENTATIVE` | 無；另有 `CONTENT_MANAGER` |

第三項有實質後果。文件 06 §4.1 的 `actor_type` 不含法定代理人，§4.4 的
`relationship_type` 才有——「法定代理人」是一種關係，不是一種身分。分支的 policy 卻以
`actor_role` 分支去決定要找哪種關係，若直接刪掉該 actor type，法代人會靜默失去所有權限。

因此 policy 一併調整：`FAMILY_MEMBER` 現在同時比對 `FAMILY_SHARE` 與
`LEGAL_REPRESENTATIVE` 兩種關係，任一具備所需 action 即放行。兩種都查完才拒絕，
避免 scope 較窄的 `FAMILY_SHARE` 遮蔽了確實授權的 `LEGAL_REPRESENTATIVE`。

## 一併修掉的既有缺陷

- **整合測試無法執行**：`tests/integration/conftest.py` 自訂 session-scoped `event_loop`
  fixture，pytest-asyncio 0.24 已棄用該寫法，導致 asyncpg 連線與測試處於不同 event loop
  （`attached to a different loop`）。分支的 runbook 將此誤判為「缺少 Docker 環境」，
  實際上是設定缺陷。改用 `asyncio_default_fixture_loop_scope`。
- **`get_active_membership` 可能拋 MultipleResultsFound**：合併後同一 actor 在同一租戶
  可有多列（租戶層一列、每個照護單位各一列），`scalar_one_or_none()` 會炸。已加 `limit(1)`。
- **`is_member()` 的 `tenant_id` 原為選填**，預設 `None` 會跳過跨租戶檢查。改為必填。

## 未納入 main 的內容

分支的以下內容**沒有**併入：

- `services/core-api/.venv/`（2000 個檔案，含 Windows 平台二進位檔）。
- `alembic/versions/001`–`003` 與其 `alembic/env.py`。
- 分支的 `docker-compose.yml`（`version: "3.8"` 已廢棄、無 init script 掛載）。
- `.kiro/`、`docs/reference/`、`docs/decisions/`、`docs/architecture/` 等文件重組。

因為採檔案搬移而非 `git merge`，上述內容不會進入 main 的歷史。

## 待後續處理

- models 只涵蓋 48 張表中的 9 張，`alembic revision --autogenerate` 會把其餘 39 張誤判為
  應刪除。補齊 models 前，autogenerate 結果一律需人工檢查。
- 分支使用 `.kiro/steering/*` 作為 agent 規範，與本 repo 的 `AGENTS.md` 並存，尚未整併。
- 仍無 CI。lint、type check 與測試指令已具備，但未接上 quality gate。
