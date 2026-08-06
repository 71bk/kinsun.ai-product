# Kiro 開發與架構設計證據

本文件整理 kinsun.ai 使用 Kiro 進行規格設計、task 執行與開發規則管理的可稽核證據。
競賽資料將「使用 Kiro 進行開發或架構設計」列為 5% 加分項；本文件不擴張該規則，
只提供 repository 內可重現的事實。

## 已存在的真實執行證據

Core API Foundation 曾以 Kiro Requirements-First workflow 執行：

| Commit | 證據 |
| --- | --- |
| `65138c3` | 建立 `.kiro/specs/core-api-foundation/` 與五份 Steering |
| `7dd698c` | 執行第一批 Spec tasks，開始產生 `tasks.meta.json` |
| `d9e168d` | 完成歷史 task 清單，保存 execution history |
| `0e21a75` | 將 Core API 改接 main 的 `eldercare_ai` baseline 與 contracts |

目前主分支恢復並保存：

- `.kiro/specs/core-api-foundation/requirements.md`
- `.kiro/specs/core-api-foundation/design.md`
- `.kiro/specs/core-api-foundation/tasks.md`
- `.kiro/specs/core-api-foundation/tasks.meta.json`
- `.kiro/specs/core-api-foundation/implementation-status.md`

其中 metadata 有 120 筆 execution 與 120 筆 chat session 關聯紀錄。提交前已針對常見
API key、access key、Token、密碼、Authorization header 與私鑰模式掃描，未發現敏感值。

可用以下指令從 Git history 驗證原始 artifacts：

```powershell
git show 65138c3:.kiro/specs/core-api-foundation/requirements.md
git show 65138c3:.kiro/specs/core-api-foundation/design.md
git show d9e168d:.kiro/specs/core-api-foundation/tasks.md
git show d9e168d:.kiro/specs/core-api-foundation/tasks.meta.json
```

## 目前使用方式

`.kiro/steering/` 保存目前 main 適用的產品、技術、結構、安全與人工確認規則。
Steering 以根目錄 `AGENTS.md` 與 `docs/` 為權威來源，避免建立互相衝突的第二份完整規範。

`.kiro/hooks/` 使用 Kiro v1 JSON hooks，涵蓋：

- Spec 更新後的 Acceptance Criteria、task 與測試 traceability 檢查。
- Core API 與 Agent Runtime Python source 修改後的測試。
- Contract 變更後的 schema/example 驗證。
- Schema 變更後的 migration 與 baseline 安全檢查。
- Spec task 完成後的 README、架構與 contract 同步檢查。

在 Windows 開啟本 repository：

```powershell
kiro .
```

Kiro 應從 workspace root 載入 `AGENTS.md`、`.kiro/steering/`、`.kiro/specs/` 與
`.kiro/hooks/`。歷史 `core-api-foundation` tasks 已完成，不應重新執行；新功能應建立新 Spec。

## 下一個預定的真實 Spec

下一個候選是 `confirmed-memory-workflow`：

```text
Memory Candidate
→ Authorization/Consent Gate
→ 長者明確確認或拒絕
→ Core API 正式狀態轉換
→ ACTIVE Memory + Transactional Outbox
→ 後續對話只使用已確認記憶
```

此項目前只是預定工作，尚未建立、尚未實作，也不計入已完成證據。應由 Kiro 建立新的
requirements、design、tasks，並只在實際驗證後更新完成狀態。

## 證據邊界

- 不以空資料夾或事後全部勾選的 tasks 冒充 Kiro 執行。
- 不把歷史 Spec 的完成狀態當成目前 main 的測試結果。
- 不把 Bedrock、OpenSearch、Neptune、RAG、Memory Candidate 或其他目標功能描述成已實作。
- 不提交 Kiro 全域設定、登入資料、完整聊天匯出、真實長者資料或任何 Secret。
