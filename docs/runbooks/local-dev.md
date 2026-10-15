# 本機開發與 QA 環境

整理日期：2026-10-15（自根目錄 AGENTS.md／CLAUDE.md 拆出）。啟動或停止本機服務、開 QA 埠號、清理 worktree、
檢查 `.env` 前先讀本檔。建置步驟見 [協作者指南](../project/COLLABORATOR_SETUP.md)。

## 資料庫與服務

- 開發與登入／註冊 E2E 預設由 repository 根目錄未版控 `.env` 的 `DATABASE_URL` 直接連 Supabase PostgreSQL；
  不啟動 Docker、`docker compose`、本機 PostgreSQL 或 Adminer，除非使用者明確要求隔離環境。
  `docker-compose.yml` 與 `docker/postgres/init/` 只是參考與明確要求時的工具，不是第二個 schema 來源。
- 日常服務埠：frontend 3000、Core 8000、Agent 8001、Speech 8002。隔離 QA 服務用其他埠，結束後停止。
- 獨立埠號的 frontend production QA server 必須為該程序設定相符的 `FRONTEND_ORIGIN`；沿用 3000 origin 啟動 3104
  會讓登入／寫入被 CSRF 拒絕。修 launcher，不放寬來源檢查，不必改既有 `.env.local`。
- 本機啟動器必須支援 dotenv 變數展開，不能逐行 split：`RAG_DATABASE_URL=${DATABASE_URL}` 原樣進入環境會導致
  `staging_rag_unavailable`。
- Demo launcher（如個人記憶 Demo 的 3110／8010）的 flags 不會套用到日常 3000／8000；排查未保存時先確認實際服務的
  `EVIDENCE_AWARE_MEMORY`／`PERSONAL_MEMORY_ENABLED` 與新同意 scope。不得代替真實使用者授予 Consent。
- 本機測試單工、BelowNormal 優先序；subagents 不同時跑測試；已有完整測試後只重跑實際變更涵蓋的定向檢查（使用者要求）。

## 安全地檢查設定

- 不得用只匹配 `NAME=` 前綴的 `rg --replace` 遮罩 `.env`：未匹配的 value 會原樣輸出。以 dotenv parser 在程序內讀取，
  只輸出 allowlist 的設定名稱、存在與否或相等布林值；不把原始行或 secret 送到 tool output。
- 不印 DSN；手動 DB 檢查方式見 [core-api AGENTS](../../services/core-api/AGENTS.md)。

## Windows 程序與 worktree

- Git ownership 問題用 scoped `git -c safe.directory=<repo> ...`，不改 repository owner 或全域安全設定。
- venv 的 `python.exe` 可能是啟動器，監聽埠由子 Python 擁有。停止 QA 時核對已記錄啟動器的命令／埠，再驗證 listener
  的同類 executable 與完整父子關係；只停止本輪程序，容許子程序結束後啟動器自行退出。
- 確認程序的實際工作目錄；只查 command line 會漏掉相對路徑啟動的日常前端。
- Worktree 副本的 `node_modules` 或 `.next/standalone/node_modules` 可能是指向主專案的 Junction。移除前以不跟隨連接的
  方式掃描整棵副本，先非遞迴解除連接本身，再 `git worktree remove`；不可對含連接的副本強制遞迴刪除。
- 清理前保存未提交／未追蹤／非快取忽略資料與 detached commits（主專案有未提交內容時保存檔案或 patch，不只存 status
  清單）；日常服務移回主專案後才清理副本。恢復後核對內容與 Git 狀態，並驗證型別、建置與服務健康。
