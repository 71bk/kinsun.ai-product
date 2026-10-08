# QA 腳本與歷史證據

此目錄隨 Git 同步可重用工具及已審查的合成 QA 證據。`docs/project/` 中的報告說明
各次驗證範圍；歷史 PASS 不代表目前環境或目前版本已重新通過。

## 新裝置準備

1. 取得包含這次整理的 commit，於 repository 根目錄執行 `npm ci`。
2. 在 `services/core-api` 執行 `uv sync --extra test --extra dev`；需要 Agent 時，
   在 `services/agent-runtime` 依該服務的依賴設定同步獨立環境。
3. 依根目錄 `.env.example` 與前端環境範例設定本機 `.env`、
   `packages/frontend/.env.local`。機密由原有安全管道取得，不放進 Git。
4. 啟動前先在根目錄執行 `npm run build --workspace @elderly-care/frontend`。
   需要 Chrome 的瀏覽器腳本使用本機安裝的 Chrome 與專案 Playwright 依賴。

以下 PowerShell 啟動器支援 Windows 任意 checkout 路徑。以 `$PSScriptRoot` 找專案，
使用 python-dotenv 展開 `.env`，只允許 development，檢查連接埠並回傳啟動的 PID。
它們不執行 migration、不建立或重設帳號。不同作業系統請沿用各服務的原生啟動命令。

| 工具 | 用途 |
| --- | --- |
| `start_workbench_real.ps1` | 工作台 Core 8000 + Frontend 3000 |
| `start_previous_record.ps1` | 上次服務紀錄 QA，同樣使用 8000 / 3000 |
| `start_law_repair_stack.ps1` | Core / Frontend + Agent 8001 |
| `start_wave2.ps1` | Wave2 Core / Frontend，預設先 build，已有 build 可用 `-SkipBuild` |
| `start_wave2_agent.ps1` | Wave2 Agent 8001 |
| `qa-environment.ps1` | 共用環境與連接埠檢查；單純 dot-source 不會啟動服務 |

從任意目前目錄呼叫啟動器即可；使用完依回傳 PID 停止自己啟動的服務。
不要同時啟動共用連接埠的多組 stack。

## 診斷與瀏覽器工具

從 repository 根目錄，以 `services/core-api/.venv/Scripts/python.exe .qa/<script>.py`
執行 Python 工具，以 `node .qa/<script>.cjs` 執行 Node 工具。

- `auth-rotation-impact.py`：唯讀 DB 統計與設定相等布林值；會更新同名 JSON。
  目前 JSON 是先前檢查的快照，不能據此判定新裝置設定。
- `service_record_schema_check.py`：唯讀 schema、版本、筆數與權限摘要。
- `wave2_preflight.py`、`wave2_chain_preflight.py`：唯讀既有合成 demo 資料。
- `workbench-diagnose.py`：唯讀工作台合成 fixture 的 API 診斷。
- `previous-auth-inspect.py`、`workbench-diagnose.cjs`：需要仍有效的合成 campaign；
  會登入並可能建立 session，不只是唯讀查詢。完成後依 fixture 流程退場。
- `check_previous_staged.py`：檢查暫存 diff 的已知設定值與本機 previous-record
  bootstrap 是否已退場。只輸出名稱與布林值；須有該裝置的私有 bootstrap，
  不是完整的通用機密掃描器。
- `wave2_recheck.py`：既有 Wave2 campaign 的 guarded fixture 包裝；預設 inspect，
  寫入仍須 `--allow-synthetic-write`，不覆寫或重設既有 demo 權限。
- `wave2_browser_login.cjs`、`wave2_chain_login.cjs`：使用既有合成 demo 帳號，
  從 process environment 讀取 `DEMO_ACCOUNT_PASSWORD`。PowerShell 可先 dot-source
  `qa-environment.ps1`，再執行 `Import-QaEnvironment -RepositoryRoot (Get-Location).Path`。
  腳本維持瀏覽器開啟供 QA，關閉瀏覽器後結束；不輸出密碼或 cookie。

`service-completion-browser-qa.js` 與 `service-completion-browser-states.js` 是
供 Playwright 執行的 `async (page, options) => ...` 函式片段，不是 Node CLI。
它們保存 2026-09-11 舊派案頁的合成 QA 流程；目前工作台改版的入口與覆蓋請看
`workbench-browser.js`、`workbench-states.js` 及工作台報告。
舊片段預設 `base=http://localhost:3107`、`folder=.qa/`（相對 Playwright 程序目錄）；
可傳入 `{ base, folder }`，`folder` 需存在且以 `/` 結尾。
原始報告見 [服務紀錄提交驗證](../docs/project/service-record-completion-20260911.md)。

Real-auth 的 `.env.previous-record-real-auth`、`.env.workbench-real-auth` 是
本機私有 bootstrap，不隨 Git 同步。已退場 campaign 不可恢復帳密或重複 prepare；
新驗證須依 `scripts/qa/` 的安全規則使用新 campaign，最後退場。Clone 不會搬移 DB、
session 或已刪除的 QA 截圖。

## 可離線核對的證據

```powershell
node .qa/workbench-verify-readback.cjs
```

此命令不連線、不需要 `.env`、不改寫報告；比對保存的 browser、退場前後 digest、
outbox、task 與正式 JSON 報告。要額外檢查本機 bootstrap 已清除帳密，可加
`--check-private`；未提供時不宣稱完成這項本機檢查。

- `previous-real-*-evidence.json`：
  [2026-09-14 真實登入 QA](../docs/project/previous-service-record-real-auth-20260914.md) 的合成證據。
- `workbench-before-retire.json`、`workbench-after-retire.json`、
  `workbench-real-flow-evidence.json`：
  [2026-09-15 工作台 QA](../docs/project/home-care-workbench-real-auth-20260915.md) 的合成證據。
  JSON 中的截圖名稱是歷史記錄；照片已按要求刪除，不能當作仍可開啟的附件。
- `law-regression-9p0n2nya/`、`law-regression-qnwozkow/`：保留失敗回歸的 JUnit 與
  input inventory，分別有 1 / 3 個 RAG 測試失敗；不能當作最終通過證據。
  這兩個封存目錄的 Git attributes 保留原始換行與 traceback 空白，不格式化歷史輸出。
- `law-sync-audit-v010-failed-lint-20260910/`：已撤回候選的不可變稽核封存，
  [治理同步報告](../docs/project/rag-law-governance-sync-plan-20260909.md) 記錄其背景。
  保留原始 bytes 與 `SHA256SUMS.txt`；內部 README 是當時候選內容，不表示已核准。

## 本機產物與清理規則

2026-10-08 已依使用者要求清理可重建、未被引用的產物，以及明列退役的一次性
source／contract 改寫工具、6 份過期 PR 草稿、2 份執行旗標；退役工具不可重跑。
清理數量與範圍見 [整理紀錄](../docs/project/project-organization-20261008.md)。

| 種類 | 處理方式 |
| --- | --- |
| 可重用 QA／環境／啟動工具 | 保留，遵守現行權限與 campaign 規則 |
| 報告引用附件、正式 JSON、失敗回歸 | 保留，不將歷史 PASS 當作目前驗收 |
| 未被引用的可重建圖片、音訊、舊日誌、快取 | 確認無程序使用後可刪除 |
| 與正式 data 副本 SHA-256 相同的無引用報告 | 刪除 QA 副本，保留正式來源 |
| worktree-backups/ | 保留復原檔案與提交紀錄，不納入一般清理 |
| dotenv、private bootstrap、credentials、匯入／退場證據 | 保留且不提交，不可整批刪除 |

新產物放 `local/<topic>/`，該目錄繼續由忽略規則排除。新增可重用腳本與已審查
JSON 預設仍出現在 Git status，提交前先審查；不要忽略整個 `.qa/`。
Windows 清理前檢查 ReparsePoint／Junction，不跟隨連接，並確認實際服務工作目錄。

`development-stack-pids.json` 是日常服務紀錄。3000 前端已於 2026-10-08 移回
`kinsun.ai/packages/frontend`；舊文件中的工作副本路徑屬歷史。
