# 交接：core-domain-security 分支併入 main

- 日期：2026-07-31
- 狀態：**未完成**。應用層與契約已可運作並驗證過；整合測試尚未修完。
- 相關：[ADR 0003](../adr/0003-core-api-framework-and-schema-authority.md)、[contracts/DIVERGENCE.md](../../contracts/DIVERGENCE.md)

## 一、這次做了什麼

把 `origin/feature/core-domain-security` 的 `app/` 與 `tests/` 搬進 main，
並改接到 main 既有的 48 張表 `eldercare_ai` baseline。

**採檔案搬移，不是 `git merge`。** 因此分支歷史沒有進入 main——特別是分支
commit `d9e168d` 內含 2000 個 `.venv/` 檔案（含 Windows 平台二進位檔），
那些沒有被帶進來。分支本身仍在 remote，未動。

### 未併入的內容

- `services/core-api/.venv/`
- 分支的 `alembic/versions/001`–`003` 與其 `alembic/env.py`（9 張表、`public` schema）
- 分支的 `docker-compose.yml`（`version: "3.8"` 已廢棄、無 init script 掛載）
- `.kiro/`、`docs/reference/`、`docs/decisions/`、`docs/architecture/`

## 二、已完成且驗證過

| 項目 | 驗證方式 | 結果 |
| --- | --- | --- |
| 8 個 ORM model 改接 `eldercare_ai` | 對真實 DB 逐一 `SELECT` | 全過 |
| FastAPI app 可啟動 | in-process ASGI ＋ 真實 DB | `/health` 200、`/ready` 200 |
| 未設定認證時 fail closed | 實際請求受保護 endpoint | 401（修復前是 500） |
| `app/` ＋ `alembic/` lint | `ruff check` / `ruff format --check` | 全過 |
| Alembic 仍可運作 | `alembic current`、容器內執行 | `f393b4452ce8 (head)` |
| Docker migration job | `docker compose run --rm migrate` | 通過 |
| **單元測試** | `pytest tests/unit` | **301 passed** |
| API contract 自我驗證 | `scripts/validate_contracts.py` | 全過 |
| API contract 對執行中服務驗證 | `scripts/verify_contract_live.py` | 全過 |

## 三、尚未完成 — 整合測試

```
pytest tests/integration  →  41 passed, 35 failed, 30 errors
```

**30 個 error 全部集中在 `tests/integration/test_repositories.py`**，
看起來是同一個 fixture 問題連鎖造成，不是 30 個獨立缺陷。建議從那支的
fixture 開始查，修好可能一次解掉大部分。

負責這部分的 subagent 在工作中途被停止，所以這些檔案處於「改到一半」的狀態：
16 個測試檔已被修改，但沒有跑到全綠。

### 已知需要處理的方向

整合測試與單元測試不同，會真的寫入資料庫，因此受 baseline 的外鍵約束影響：

- `care_relationship`、`care_assignment`、`elder` 都有真實 FK，
  測試必須先建立 `tenant`、`actor`、`care_unit`、`elder` 這些被參照的列。
- `outbox_event` 的 `tenant_id`／`elder_id`／`actor_id` 也是真 FK
  （分支原本的 `outbox` 沒有）。塞隨機 UUID 會 FK violation，
  要嘛先建 tenant，要嘛設 `None`（該欄位可為 NULL）。
- `scope` / `service_scope` 的預設是 `'{}'`（空物件）而非 `'[]'`，
  預期放行的測試必須明確設定 scope。

### 不要這樣修

- 不要放寬或刪除 assertion 讓它變綠。這批測試裡的 cross-tenant 隔離、
  negative authorization、時間邊界是本專案最重要的安全證據。
- 不要改 `app/` 去遷就測試，除非確認是 `app/` 真的有錯。
- 不要改 schema。

## 四、順手修掉的既有缺陷

以下四項不是這次改接造成的，是分支原本就有的問題：

1. **整合測試根本跑不起來**（`tests/integration/conftest.py`）
   自訂 session-scoped `event_loop` fixture，pytest-asyncio 0.24 已棄用該寫法，
   導致 asyncpg 連線與測試處於不同 event loop。分支的
   `docs/runbooks/pending-environment-validation.md` 把這誤判為「缺少 Docker 環境」，
   實際上是設定缺陷。改用 `asyncio_default_fixture_loop_scope`。

2. **`NoAuthenticatorConfiguredError` 回 500 而非 401**
   它繼承一般 `Exception` 而非 `DomainException`，掉進 catch-all handler。
   但 `app/middleware/auth.py` 的 docstring 明寫這種情況要
   「fail closed (HTTP 401 for all requests)」。正式環境若忘記設定 authenticator，
   回的會是「伺服器壞了」而非「請先認證」。已加專屬 handler。

3. **`get_active_membership()` 可能拋 `MultipleResultsFound`**
   membership 合併成單表後，同一 actor 在同一租戶可有多列（租戶層一列、
   每個照護單位各一列），`scalar_one_or_none()` 會炸。已加 `limit(1)`。

4. **`is_member()` 的 `tenant_id` 原為選填**，預設 `None` 會跳過跨租戶檢查。
   已改為必填。

## 五、關鍵設計決定（詳見 ADR 0003）

- **PK 命名**：baseline 每張表 PK 各自命名（`actor.actor_id`），分支程式碼假設統一 `id`。
  解法是每個 model 宣告 `__pk_name__`，`BaseModel` 用 `declared_attr` 把 Python 屬性
  `id` 映射過去。**應用層程式碼一行未改。** 新增 model 一定要設 `__pk_name__`。
- **membership 合併**：baseline 是單一 `actor_tenant_membership`，以 `care_unit_id`
  是否為 NULL 區分層級。兩個 repository class 保留，各自加述詞查同一個 model。
- **語彙以 baseline 為準**：`SCHEDULED`→`DRAFT`、移除 `BOTH`、
  `LEGAL_REPRESENTATIVE` 不再是 actor type。
- **`LEGAL_REPRESENTATIVE` 的連帶影響**：文件 06 §4.1 認為法定代理人是一種*關係*
  而非*身分*。若只是刪掉該 actor type，法代人會靜默失去所有權限，因為
  `FAMILY_MEMBER` 只會被比對 `FAMILY_SHARE`。因此 policy 一併調整為
  **`FAMILY_MEMBER` 同時比對兩種關係**，兩種都查完才拒絕。
- **兩個 driver 並存**：Alembic 用 psycopg（同步），應用層用 asyncpg（非同步）。
  `DATABASE_URL` 只維護一份，寫成 asyncpg 形式，`alembic/env.py` 自行轉換。

## 六、API Contract

`contracts/` 已建立，涵蓋 6 個已實作的 endpoint，兩支驗證腳本都通過。

**契約以目前實作為準，不是以文件 10 為準。** 兩者有實質差異，
全部列在 [`contracts/DIVERGENCE.md`](../../contracts/DIVERGENCE.md)，尚未決定收斂方向。

其中最值得優先處理的是**錯誤回應缺少 `reason_code` 與 `retryable`**：
`app/policies/elder_access.py` 其實已經算出 11 種 reason code
（`NO_VALID_RELATIONSHIP`、`SCOPE_INSUFFICIENT`、`OUTSIDE_TIME_WINDOW`…），
但在 HTTP 層被丟棄。前端只看得到 403／404，無法區分「同意未取得」與「關係已到期」。
補上去只是把已有資訊往上傳，不需要改授權邏輯，且屬非破壞性變更。

## 七、下一步建議順序

1. **修完整合測試**（見第三節）。這是唯一擋住「可宣稱完成」的項目。
2. 建立 CI quality gate：目前 lint 與測試指令都有了，但沒有接上。
3. 補 type check（mypy 或 pyright），`AGENTS.md` §10 列為未建立。
4. 依 `DIVERGENCE.md` §8 的順序處理契約差異，前兩項非破壞性。
5. 決定 `.kiro/steering/*` 與 `AGENTS.md` 是否整併——目前兩套 agent 規範並存。

## 八、環境備忘

```powershell
docker compose up -d postgres
docker compose run --rm migrate            # 套用 baseline

cd services/core-api
uv sync --extra test --extra dev
$env:DATABASE_URL = "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun"
$env:TEST_DATABASE_URL = "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test"
uv run pytest tests/unit          # 301 passed
uv run pytest tests/integration   # 尚未全綠
```

還原點：commit `e40a88b`（本次改接之前的狀態）。
