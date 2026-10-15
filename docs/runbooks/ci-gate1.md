# CI Gate 1 規則

整理日期：2026-10-15（自根目錄 AGENTS.md／CLAUDE.md 拆出）。實作與量測背景見
[`ci-pipeline-optimization.md`](../project/ci-pipeline-optimization.md)。修改 `.github/workflows/gate1.yml`、
`scripts/ci/` 或新增跨服務依賴前先讀本檔。

## 範圍

- `.github/workflows/gate1.yml` 在對 `main` 的 pull request 與 push 觸發，`ubuntu-latest`＋pinned pgvector service。
- Jobs：永遠執行的 `changes`、八個 worker（`core-fast`、`core-db`、`agent-quality`、`speech-quality`、`rag-quality`、
  `contracts`、`cross-service`、`frontend-quality`）與 `always()` aggregate `synthetic-gate1`。
- 涵蓋：四個 Python 服務（＋notification-worker format）的 `ruff check`／`ruff format --check`／pytest、
  Core `tests/integration`（CI 自建 disposable `kinsun_test`，這是唯一實際跑 Core integration 的環境）、
  contract 靜態與兩支 live verifier、五輪 synthetic Core-to-Agent 證據（`scripts/verify_gate1_cross_service.py`，
  成功時上傳 artifact 30 天）、Frontend `npm ci`／typecheck／test／lint／production build。
- 不等於 branch protection、外部部署跨服務 E2E、browser E2E、Python type check 或 production IaC verification。

## 規則

- PR trigger 只接受 base=main。依賴未合併 PR 時，以 main 為 base 建 draft PR，標明依賴與增量比較連結，前案合併後
  再整理與重驗；不為單次任務硬編碼 feature branch trigger，不把 feature-base PR 說成已觸發 CI。
- PR 由 `changes`／`scripts/ci/impact.py` 選 workers，main push 全跑。`synthetic-gate1` 的 needs 含 changes 與八個
  worker；changes 與選定 worker 須 success 且有 metrics，只有有效、同 run／commit 的計畫明確排除者可 skipped。
  意外 skip／failure／cancelled／缺結果或計畫都不可放行。
- 未知路徑或無法取得完整 diff 時回退全跑；不得用 workflow-level paths filter 消除 aggregate。
- PR diff 用 merge-base→head、NUL 分隔、停用 rename detection（納入新舊路徑）；不能只比 HEAD~1 或用可能截斷的
  PR files API。純文件白名單也要過 CI 規則與 diff 檢查。
- 依實際執行依賴選 workers；不再以歷史 audit code hash 擴大 RAG 影響範圍。真正 retrieval／policy／ingestion／共用
  契約變更仍須對應驗證。新增檔案或跨服務依賴時同步影響規則與測試；開 PR 前跑 `scripts/ci/test_*.py`。
- 只有 `core-db` 啟動 PostgreSQL；Core live contract 的 `/ready` 依賴 DB，不可移到無 DB job。
- Core 與 Agent 的 httpx 依賴不同，維持各自 uv project environment；平行 uv cache 以 job suffix 隔離。
- Core migration lifecycle tests 先在獨立 pytest process 執行，再跑其餘 integration（見 core-api AGENTS）。

## 量測與報告

- `scripts/ci/telemetry.py` 收集命令耗時與 bounded 測試報告；輸出放 runner 暫存目錄，不污染 synthetic evidence 的
  working tree。Wrapper 保留原始 exit code；上傳報告成功不代表測試通過。
- Native job／step 與 command 耗時分開；不把平行 job 秒數相加當總等待時間。`run_report.py` 可唯讀取得實際耗時，
  未完成的 run 不得宣稱完整耗時或節省比例。
- Artifact 名稱含 run attempt；rerun failed jobs 可沿用同 run／commit 的先前成功 worker metrics。

## 已知地雷

- 新增 router／model 的 import 是 ASCII 排序（`assignments` < `assisted_*`、`asr_gate` < `assisted_*`），目測易錯，
  `ruff check` 的 `I001` 會直接擋 CI。新增 import 後先跑該服務 `ruff check` 與 `ruff format --check`。
- 已移除的 `.github/workflows-disabled/pr.yml` 不要重建或啟用。
