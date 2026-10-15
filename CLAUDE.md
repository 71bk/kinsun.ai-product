# CLAUDE.md

本檔定義 Claude 在本專案的工作流程與交付格式。架構、安全、Contract、資料庫與測試規則以根目錄 `AGENTS.md` 為準
（下方匯入）；進入特定模組時依 `AGENTS.md` §0 索引讀取該模組的 `AGENTS.md`。產品規格在 [`docs/spec/`](docs/spec/)，
不要把本檔當產品規格。整理日期：2026-10-15。

@AGENTS.md

## 每次工作固定流程

1. 確認工作區，不覆蓋使用者或其他工具未提交的變更：

   ```powershell
   # <repo> 換成這台機器上的實際 checkout 路徑；scoped safe.directory 不動全域 Git 設定
   git -c safe.directory=<repo> -C <repo> status --short
   git -c safe.directory=<repo> -C <repo> log -5 --oneline
   ```

2. 讀根目錄 `AGENTS.md`、目前模組的 `AGENTS.md`，再讀與需求直接相關的 spec、ADR、contract、migration、測試與實作。
   文件與程式衝突時，先以可執行 contract、migration、測試與 code path 建立證據，再修正文件。
3. 把需求拆成 Persona、User Story、Acceptance Criteria、Domain State、Security Gate、Test Gate；明確區分
   「目標架構」、「程式已實作」、「測試已通過」與「環境已部署」。
4. 追完整資料流：Browser／BFF → Core Command Gate → DB／Outbox → Agent、Speech、RAG 或通知邊界；寫入路徑一併檢查
   授權、Consent、狀態機、idempotency、audit 與 failure path。
5. 先做最小、可回復的變更，再跑受影響元件測試；跨 contract、migration 或共用套件時擴大驗證。
6. 交付前檢查 diff、更新必要文件，列出已驗證與因環境限制未驗證的項目。

```text
需求 → 實作證據 → Contract／State／Security 影響 → 最小修改 → 目標測試 → 跨層檢查 → 交付
```

只改文件時至少跑 `git diff --check` 並檢查連結與 diff。

## 交付前自我審查

- `git diff` 只包含本次需求；沒有重寫或刪除使用者既有變更。
- 實作、contract、migration、測試、文件與 feature flag 敘述一致。
- 每個 write path 都有 actor、scope、Consent、state、idempotency、audit 與失敗路徑。
- 沒有真實長者資料、逐字稿、音訊、token、secret、endpoint credential 或敏感 log。
- 沒有把 mock、adapter、disabled gate、合成或本機測試誤稱為已部署能力。
- 新增 API 有 schema 與 verifier；新增 state 有 migration 與 transition test；新增 UI 有雙語與 RWD。
- 必要測試已跑；未跑項目附具體原因與風險。
- 這次踩到文件沒記錄的坑：寫進對應模組的 `AGENTS.md` 或 `docs/runbooks/`，不要堆回根目錄或本檔。

## 常見誤判與禁止事項

- 不因 route 或 optional provider adapter 存在，就宣稱功能已啟用、已部署或 production-ready。
- 不把 Memory API 當成 Agent Context、不把 RAG retrieval 當成 projection、不把 notification CLI／README 當成 worker deployment。
- 不依賴舊 README 的 `allowed_tools` callback 敘述；以 proposal-only canonical path 為準。
- 不執行 `git reset --hard`、`git checkout --` 覆蓋變更，不直接 push `main`。
- Git commit 只寫本次變更的 subject／body；不得自行加入 `Co-Authored-By`、`Claude-Session`、`Generated-By` 或任何
  AI／工具協作者署名與追蹤連結，除非使用者明確要求。
- Supabase、網路、雲端或沙箱受限時記錄限制，不以關閉安全檢查繞過。

## 回報格式

完成工作時用精簡四段：

1. 結果：實際完成什麼。
2. 變更：關鍵檔案與行為。
3. 驗證：執行的命令與結果。
4. 未驗證／風險：只列真實存在的環境限制或待決事項。
