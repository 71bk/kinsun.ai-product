# RAG 簡化第 1 批：退役開發流程

2026-10-02 使用者授權取代舊有逐筆人工覆核、反覆 audit successor 與每改動封存要求。本批只處理開發流程；資料管線／准入 metadata 精簡、runtime／SQL 自然問句 Hybrid RAG 與實際問題評估分別留待第 2–4 批；import／環境切換另須後續授權，不宣稱已完成。

## 本批移除

- 停止 current byte audit successor 鏈，不建立 v021；程式及測試由 Git 管理，不因正常程式改動重建 manifest、snapshot 或封存包。
- 刪除 51 個獨立 audit CLI、模組與專用測試；早期 v3 candidate／policy v2 的 audit builder 亦退役。保留的歷史 snapshot validator 只檢查資料完整性，不要求目前程式碼等於當年版本。
- 退役 standalone `answer_evidence_review.py`、`review_app.py`、review assets 與專用測試；人工工作簿 prepare／validate、UI 與逐筆覆核不再是日常必經入口。
- 不要求使用者填 1,055 qrels，也不把未填完整視為開發流程阻塞。
- CI 不再因歷史 audit code hash inventory 把純 Markdown 或無關 Core 變更強制選取 RAG／Agent；依真正執行依賴及影響規則驗證。
- CI 保留 schema、契約與服務功能測試；Core 的 `knowledge_router.py`／`knowledge_intent.py` 因確有 RAG 評估依賴，仍精確觸發 RAG 檢查。

## 保留

- 真實來源、來源／資料版本、有效日期及 text／embedding_text 內容 hash；embedding 內容改變時仍須辨識重算需求。
- pending／needs_review 保持真實，AI 判定與 synthetic 結果不能冒充人工 verified；byte integrity 也不代表語意品質或 production approval。
- 身分、scope、Consent、secret、來源完整性、外部寫入及 production 授權邊界。
- v020 及以前 audit、歷史 acceptance／review／rechunk 文件與 pinned 資料 bytes。它們只描述當時版本，不代表當前程式；其中強制新增 successor、逐筆填表或每次變更封存的操作要求已被本次授權取代。無須刪除整份歷史文件或改寫其 hash。
- 舊 human_review_package／acceptance 與 owner acceptance validator 暫留相容工具，因 staging_embedding_authorization、v3_verified_candidate、source_family_policy_v2 仍相依；不是新批次必填作業，待第 2 批解除相依。

## 待第 2–4 批

第 2 批處理資料管線／准入 metadata 精簡、735 候選統整、內容 hash reuse 與自動來源／內容驗證。第 3 批一起調整 runtime／SQL gate，實作自然問句 Hybrid RAG，取消精確題目、人工 support sets、固定答覆與最低 3 筆要求。第 4 批以實際問題評估；之後有授權才 import、切換環境並準備 rollback。上述工作均待實作。本批未改 v004 release／policy、runtime flags 或現行 strict gate：V3 預設關閉，真實 needs_review 支持集合仍不能通過，V1／V2 引用數與既有 gate 尚未改。

第 2 批介面建議：以 source／data version、內容 hash、embedding profile 與來源定位統整 735 候選；相同 embedding 內容 hash／profile 重用既有向量，內容改變才重算。准入 metadata 保留必要的 `retrieval_eligible`、audience／purpose、current／stop 與 block reasons，以自動來源／內容驗證產出明確結果，review provenance 保持真實狀態。這是待實作的資料契約，不是本批已生效的新准入；第 3 批再同步調整 SQL projection／runtime 契約與自然回答，第 4 批用實際問題驗證資料不足、拒答與引用支持。

## 驗證

三個 GPT-6.1 Sol subagents 分別處理 audit 退役、CI、文件；主代理整合人工工作台退役、覆查相依、修正換行問題並審核結果。

以下為工作樹的回歸結果，包含先前尚未提交的 V3／重切資料工作。本次 commit 只提交第 1 批流程簡化；先前功能、候選資料與其 schema 留待後續提交。

- Agent Runtime 全套：684 passed（48.16 秒）。
- RAG ingestion 全套首輪：465 passed、2 failed（299.25 秒）。兩個失敗均為 `test_v2_artifacts.py` 建置測試，原因是既有 V3 request／response schema 使用 CRLF，違反專案現有 LF 規則。只正規化這兩份 schema 的換行後，兩個失敗案例重驗 2 passed（10.35 秒），沒有變更 schema 語意或歷史資料。
- v3 candidate／policy v2 最終定向測試：14 passed（20.66 秒），含全套首輪之後新增的兩個 snapshot 篡改負例。改過 inventory／candidate lock 並重算套件 checksum 仍會被拒絕；程式碼改動則不再要求歷史 current-byte gate。RAG 共 469 個不同案例已有通過結果，這是全套與定向重驗的合併覆蓋，非另一次完整 469-case 執行。
- CI 影響規則、workflow、telemetry：28 tests passed；真實 Core routing helper 相依有回歸覆蓋。
- 契約驗證：`python scripts/validate_contracts.py contracts` 通過。兩個保留的歷史候選／policy 驗證 CLI 實際執行通過。
- 最終 Ruff lint／format：通過，涵蓋 ingestion、CI 與本批修改的 CLI；89 files already formatted。`git diff --check` 通過。
- 已檢查活動中的 Python imports、CI commands 與文件入口，沒有指向退役工具的執行相依。舊報告中的路徑保留作為歷史紀錄。
- 未修改歷史 data／report packages、runtime 行為或設定；未執行外部 DB 寫入、provider 切換或 activation。本批沒有建立 audit v021。
