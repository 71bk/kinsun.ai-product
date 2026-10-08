# 文件歸納與 QA 清理（2026-10-08）

## 文件整理

- [文件總索引](../README.md)區分規格、ADR、交付、營運、設計、資料與 QA。
- [功能主題索引](README.md)歸納公開知識、RAG 演進、工作台、收案、報表、語音與跨角色驗收。
- Code review 與 CI review 歸入 `reviews/`；CI 根目錄保留短入口。
- [資料目錄說明](../../data/README.md)區分正式來源／版本與本機產物。
- v009 rollout 補上前端改由主工作樹啟動的日期更新，保留原始歷史。

## QA 清理範圍

依引用、Git 追蹤與 SHA-256 核對，清理 564 個檔案，共 54.40 MiB。
包含未被引用的可重建圖片／音訊／日誌／快取、13 份明列退役的工具／草稿／旗標，
及兩份與 `data/rag-rechunk/admission-fix/reports/v001/` 相同的 preflight／policy-replay 副本。

保留可重用腳本、報告引用附件、Git 追蹤驗收證據、失敗回歸、固定稽核 bytes、
private bootstrap、日常服務紀錄及最近日誌，與 `.qa/worktree-backups/20261008-102807/` 復原備份。
正式資料、評估、runtime、contracts、DB、provider 與啟用設定未變更。

逐檔清單與驗證結果保存於忽略的 `.qa/local/organization-20261008/`，
供本機追蹤，不複製憑證或原始內容進公開文件。後續產物放 `.qa/local/<topic>/`；
保留規則見 [QA 說明](../../.qa/README.md)。

## 驗證

175 個本機文件連結全部有效，所有本目錄交付文件均已納入主題索引。
2,925 個既有文件外檔案、885 個復原備份檔案及 18 個固定 QA 檔案均保留清理前內容。
Git diff --check、11 項離線工作台證據核對，以及 3000／8000／8001 健康檢查均通過。
健康檢查新增的 Core／Agent stdout 日誌不納入靜態指紋比對。
文件與產物清理未重跑完整建置或資料庫測試。


## Markdown 精簡續作

盤點 275 份工作文件（不含依賴、執行快取與復原備份），移除 16 份 Markdown：
11 份未被引用且已有正式交付報告的 PR 草稿，及 5 份已明確標示 LEGACY／SUPERSEDED 的 Kiro 舊文件。

| 類別 | 處理 |
| --- | --- |
| `.qa/companion-notices-pr.md` 與 `.qa/local/` 的 PR 草稿 | 刪除，功能與驗收留在原正式交付報告 |
| `.kiro/specs/elderly-care-ai-companion/` 的 requirements、design、tasks.legacy | 刪除，保留短退役入口及 canonical Gate 1 導引 |
| `.kiro/specs/role-based-login/` 的 requirements、design | 刪除，保留短 README 指向現行驗證 spec 與 ADR |
| 產品規格、ADR、核准的上次服務紀錄決策、分支退場及驗收報告 | 保留，仍有獨立決策／驗收用途 |
| 4 組重複內容中的稽核 README／REVIEW | 保留，屬固定稽核／版本證據，不能只依內容相同刪除 |
| 根目錄 CI 短入口 | 保留，CI impact rules 與舊連結仍辨識此路徑 |
| AGENTS、CLAUDE 與 Kiro steering | 保留，分別承載協作規則、工作方式與 Kiro 轉發入口 |

現行 Gate 1 文件已移除對工作樹舊任務檔的依賴，但保留禁止沿用歷史完成標記的規則。
刪除的 5 份版本化文件可從 Git commit `48a0ef54448888163fe923adf9a51fd251b7ba40` 取回。
本機逐檔清單與驗證留於 `.qa/local/md-cleanup-20261008/`；未刪除獨立評估協議、
RAG scope review、正式資料或復原備份。
